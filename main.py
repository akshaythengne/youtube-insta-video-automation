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

BATCH_FILE = os.path.join("prompt_images", "prompt_batch.json")
DID_API_KEY = os.environ["DID_API_KEY"]  # Format: username:password
username, password = DID_API_KEY.split(":")


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
    # Step 1: Convert image if needed
    avatar_path = prepare_image_for_did(avatar_path)

    # Step 2: Upload image to D-ID
    with open(avatar_path, "rb") as img:
        files = {"image": img}
        r = requests.post(
            "https://api.d-id.com/images",
            files=files,
            auth=HTTPBasicAuth(username, password)
        )

    print("D-ID Image Upload Response:", r.status_code, r.text)
    if r.status_code not in (200, 201):
        raise Exception(f"D-ID image upload failed: {r.text}")

    resp = r.json()
    image_url = resp.get("url")
    if not image_url:
        raise Exception(f"No image URL returned: {r.text}")

    # Convert s3:// to https:// for use in /talks
    if image_url.startswith("s3://d-id-images-prod/"):
        image_url = image_url.replace(
            "s3://d-id-images-prod/",
            "https://d-id-images-prod.s3.amazonaws.com/"
        ).replace("|", "%7C")

    # Step 3: Generate narration locally as MP3
    import asyncio
    audio_file = "story.mp3"
    asyncio.run(generate_tts_audio(story_text, audio_file))

    # Step 4: Upload audio to a public file hosting service
    # For simplicity, we upload directly to D-ID (they support multipart audio)
    with open(audio_file, "rb") as audio:
        files = {"audio": audio}
        r = requests.post(
            "https://api.d-id.com/audios",
            files=files,
            auth=HTTPBasicAuth(username, password)
        )

    print("D-ID Audio Upload Response:", r.status_code, r.text)
    if r.status_code not in (200, 201):
        raise Exception(f"D-ID audio upload failed: {r.text}")

    audio_url = r.json().get("url")
    if audio_url.startswith("s3://d-id-audios-prod/"):
        audio_url = audio_url.replace(
            "s3://d-id-audios-prod/",
            "https://d-id-audios-prod.s3.amazonaws.com/"
        ).replace("|", "%7C")

    # Step 5: Create talking video using audio
    payload = {
        "source_url": image_url,
        "script": {
            "type": "audio",
            "audio_url": audio_url
        }
    }

    r = requests.post(
        "https://api.d-id.com/talks",
        json=payload,
        auth=HTTPBasicAuth(username, password)
    )
    print("D-ID Video Creation Response:", r.status_code, r.text)
    if r.status_code != 200:
        raise Exception(f"D-ID video creation failed: {r.text}")

    talk_id = r.json().get("id")
    if not talk_id:
        raise Exception(f"No talk ID returned: {r.text}")

    # Step 6: Poll for video completion
    result_url = None
    for _ in range(25):
        time.sleep(12)
        check = requests.get(
            f"https://api.d-id.com/talks/{talk_id}",
            auth=HTTPBasicAuth(username, password)
        )
        result = check.json()
        if "result_url" in result:
            result_url = result["result_url"]
            break
        print("Waiting for video to be ready...")

    if not result_url:
        raise Exception("Video generation timed out.")

    # Step 7: Download the resulting video
    with requests.get(result_url, stream=True) as resp:
        with open('output.mp4', 'wb') as f:
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
