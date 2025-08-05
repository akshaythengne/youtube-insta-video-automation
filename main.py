import os
import json
import time
import requests
from requests.auth import HTTPBasicAuth
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import pickle
from PIL import Image
import edge_tts  # Microsoft local TTS
from urllib.parse import quote
import asyncio
import base64

BATCH_FILE = os.path.join("prompt_images", "prompt_batch.json")
DID_API_KEY = os.environ["DID_API_KEY"]  # Format: username:password
#username, password = DID_API_KEY.split(":")
BASIC_AUTH_HEADER = f"Basic {DID_API_KEY}"

def prepare_image_for_did(path):
    """Convert PNG to JPEG for D-ID uploads (if needed)."""
    if path.lower().endswith(".png"):
        img = Image.open(path).convert("RGB")
        jpeg_path = path.replace(".png", ".jpg")
        img.save(jpeg_path, "JPEG")
        return jpeg_path
    return path

def convert_did_url(s3_url: str, bucket_type: str):
    """Convert s3:// D-ID URLs to proper HTTPS with encoding."""
    if bucket_type == 'images':
        base = "https://d-id-images-prod.s3.amazonaws.com/"
        prefix = "s3://d-id-images-prod/"
    else:
        base = "https://d-id-audios-prod.s3.amazonaws.com/"
        prefix = "s3://d-id-audios-prod/"
    
    clean_path = s3_url.replace(prefix, "")
    return base + quote(clean_path, safe="/._-")

async def generate_tts_audio(text, output_file="story.mp3", voice="en-US-JennyNeural"):
    """Generate narration audio using Microsoft Edge TTS."""
    communicate = edge_tts.Communicate(text, voice=voice)
    await communicate.save(output_file)
    return output_file


def prepare_image_for_did(path):
    """Convert PNG to JPEG for D-ID uploads (if needed)."""
    if path.lower().endswith(".png"):
        img = Image.open(path).convert("RGB")
        jpeg_path = path.replace(".png", ".jpg")
        img.save(jpeg_path, "JPEG")
        return jpeg_path
    return path


async def generate_tts_audio(text, output_file="story.mp3", voice="en-US-JennyNeural"):
    """Generate narration audio using Microsoft Edge TTS."""
    communicate = edge_tts.Communicate(text, voice=voice)
    await communicate.save(output_file)
    return output_file


def create_video(story_text, avatar_path):
    """Create talking head video using D-ID with multipart upload (image + audio)."""
    #auth_string = f"{username}:{password}"
    #auth_encoded = base64.b64encode(auth_string.encode()).decode()
    # Step 1: Convert image if needed
    # avatar_path = prepare_image_for_did(avatar_path)

    # # Step 2: Generate local narration audio
    # audio_file = "story.mp3"
    # asyncio.run(generate_tts_audio(story_text, audio_file))

    # # Step 3: Call D-ID /talks endpoint with multipart files
    # files = {
    #     "image": open(avatar_path, "rb"),
    #     "audio": open(audio_file, "rb")
    # }

    # # Only specify minimal script info for audio input
    # data = {
    #     "script": json.dumps({
    #         "type": "audio"
    #     })
    # }

    # r = requests.post(
    #     "https://api.d-id.com/talks",
    #     files=files,
    #     data=data,
    #     auth=HTTPBasicAuth(username, password)
    # )

    url = "https://api.d-id.com/talks"

    payload = {
        "source_url": "https://d-id-public-bucket.s3.us-west-2.amazonaws.com/alice.jpg",
        "script": {
            "type": "text",
            "subtitles": "false",
            "provider": {
                "type": "microsoft",
                "voice_id": "en-US-JennyNeural"
            },
            "input": story_text,
            "ssml": "false"
        },
        "config": { "fluent": "false" }
    }
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "authorization": BASIC_AUTH_HEADER
    }

    r = requests.post(url, json=payload, headers=headers)


    print("D-ID Video Creation Response:", r.status_code, r.text)
    if r.status_code not in (200, 201):
        raise Exception(f"D-ID video creation failed: {r.text}")

    talk_id = r.json().get("id")
    if not talk_id:
        raise Exception(f"No talk ID returned: {r.text}")

    # Step 4: Poll for video completion
    result_url = None
    for attempt in range(30):  # up to ~6 minutes
        time.sleep(12)
        headers = {
            "Authorization": BASIC_AUTH_HEADER,
            "Content-Type": "application/json"
        }
        check = requests.get(
            f"https://api.d-id.com/talks/{talk_id}",
            headers=headers
        )
        result = check.json()
        if "result_url" in result:
            result_url = result["result_url"]
            break
        print(f"[Attempt {attempt+1}/30] Waiting for video to be ready...")

    if not result_url:
        raise Exception("Video generation timed out.")

    # Step 5: Download the resulting video
    with requests.get(result_url, stream=True) as resp:
        with open("output.mp4", "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

    print("Video saved as output.mp4")




def upload_to_youtube(video_file, title, description):
    SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
    creds = None
    if os.path.exists("token.pickle"):
        with open("token.pickle", "rb") as token:
            creds = pickle.load(token)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("client_secret.json", SCOPES)
            creds = flow.run_local_server(port=0)
        with open("token.pickle", "wb") as token:
            pickle.dump(creds, token)

    youtube = build("youtube", "v3", credentials=creds)
    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": ["Shorts", "AI Story"],
            "categoryId": "22"
        },
        "status": {"privacyStatus": "public"}
    }
    media = MediaFileUpload(video_file, mimetype="video/mp4", resumable=True)
    request = youtube.videos().insert(part=",".join(body.keys()), body=body, media_body=media)
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"Uploading... {int(status.progress() * 100)}% done")
    print(f"Upload Complete! Video ID: {response['id']}")
    print(f"https://www.youtube.com/watch?v={response['id']}")


def main():
    if not os.path.exists(BATCH_FILE):
        raise Exception("No prompt batch found. Please run generate_batch.py first.")

    with open(BATCH_FILE, "r", encoding="utf-8") as f:
        batch = json.load(f)

    if not batch:
        raise Exception("No prompts left in batch. Generate a new batch first.")

    story = batch.pop(0)

    # Update batch after consuming
    with open(BATCH_FILE, "w", encoding="utf-8") as f:
        json.dump(batch, f, ensure_ascii=False, indent=2)

    create_video(story["story"], story["image_path"])
    upload_to_youtube(
        video_file="output.mp4",
        title="AI Story Shorts | " + story["story"][:40],
        description=story["story"]
    )


if __name__ == "__main__":
    main()
