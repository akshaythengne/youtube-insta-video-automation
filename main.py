import requests
import time
import os
from base64 import b64decode
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import pickle
import re
from diffusers import StableDiffusionPipeline
import torch
import json

# === CONFIGURATION ===
PERPLEXITY_API_KEY = os.environ['PERPLEXITY_API_KEY']
DID_API_KEY = os.environ['DID_API_KEY']

# === STEP 1: Generate story with Perplexity ===
def get_story():
    prompt = (
        "Write a 2-minute engaging story for a vertical video. "
        "Include narration, and in the end, provide a one-sentence vivid image prompt that evokes the main scene."
    )
    payload = {
        "model": "sonar-pro",  # Latest Perplexity model as of July 2025
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": "Give today's unique story."}
        ]
    }
    headers = {
        "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
        "Content-Type": "application/json"
    }
    response = requests.post(
        "https://api.perplexity.ai/chat/completions", json=payload, headers=headers
    )
    print("Perplexity API response:", response.text)  # Debug print
    resp_json = response.json()
    if "choices" not in resp_json:
        raise Exception(f"Perplexity API error: {resp_json}")
    content = resp_json["choices"][0]["message"]["content"]
    # Use regex to robustly extract the image prompt, including new variants and whitespace
    match = re.search(r"(.*?)(?:\*\*|\*)?\s*(?:One-sentence image prompt|Visual prompt|Vivid image prompt|Image prompt|Prompt to evoke the main scene|Prompt)\s*[:\-–]?\s*\**\s*\n*\s*(.+)$", content, re.IGNORECASE | re.DOTALL)
    if not match or len(match.groups()) < 2:
        raise Exception("No valid image prompt found in response: " + content)

    story = match.group(1)
    image_prompt = match.group(2)
    return story.strip(), image_prompt.strip()

# === STEP 2: Generate image with Perplexity ===
def generate_image(image_prompt):
    image_prompt = re.sub(r"[*_`#>\-]", "", image_prompt).strip()
    HUGGING_API_KEY = os.environ['HUGGING_API_KEY']
    pipe = StableDiffusionPipeline.from_pretrained(
        "stabilityai/stable-diffusion-2",
        use_auth_token=HUGGING_API_KEY
    )
    # Use GPU if available
    if torch.cuda.is_available():
        pipe = pipe.to("cuda")
    else:
        pipe = pipe.to("cpu")
    image = pipe(image_prompt).images[0]
    img_path = "avatar.png"
    image.save(img_path)
    print(f"Image saved to {img_path}")
    return img_path

# === STEP 3: Generate video with D-ID ===
def create_video(story_text, avatar_path):
    # Upload avatar image to D-ID
    with open(avatar_path, "rb") as img:
        files = {"image": img}
        headers = {"Authorization": f"Bearer {DID_API_KEY}"}
        r = requests.post("https://api.d-id.com/images", headers=headers, files=files)
        print(f"D-ID image upload response: {r.text}")
        resp_json = r.json()
        if "url" not in resp_json:
            raise Exception(f"D-ID image upload error: {r.text}")
        image_url = resp_json["url"]

    # Create talking video via D-ID
    payload = {
        "source_url": image_url,
        "script": {
            "type": "text",
            "input": story_text,
            "provider": {"type": "microsoft"},
            "voice": "en-US-JennyNeural"
        }
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {DID_API_KEY}"
    }
    r = requests.post("https://api.d-id.com/talks", headers=headers, json=payload)
    talk_id = r.json()["id"]

    # Poll for video completion
    for _ in range(25):
        time.sleep(12)
        get_headers = {"Authorization": f"Bearer {DID_API_KEY}"}
        check = requests.get(f"https://api.d-id.com/talks/{talk_id}", headers=get_headers)
        result = check.json()
        if "result_url" in result:
            result_url = result["result_url"]
            break
    else:
        raise Exception("Video generation timed out.")

    # Download the resulting video
    with requests.get(result_url, stream=True) as resp:
        with open('output.mp4', 'wb') as f:
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
    print("Video saved as output.mp4")

def upload_to_youtube(video_file, title, description):
    SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
    creds = None
    # Use token.pickle for storing user's access and refresh tokens
    if os.path.exists("token.pickle"):
        with open("token.pickle", "rb") as token:
            creds = pickle.load(token)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                "client_secret.json", SCOPES)
            creds = flow.run_local_server(port=0)
        with open("token.pickle", "wb") as token:
            pickle.dump(creds, token)
    youtube = build("youtube", "v3", credentials=creds)
    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": ["Shorts", "AI Story"],
            "categoryId": "22"  # People & Blogs
        },
        "status": {
            "privacyStatus": "public"
        }
    }
    media = MediaFileUpload(video_file, mimetype="video/mp4", resumable=True)
    request = youtube.videos().insert(
        part=",".join(body.keys()),
        body=body,
        media_body=media
    )
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"Uploading... {int(status.progress() * 100)}% done")
    print(f"Upload Complete! Video ID: {response['id']}")
    print(f"https://www.youtube.com/watch?v={response['id']}")

def batch_generate_prompts_and_images(batch_size=3):
    prompts = []
    for i in range(batch_size):
        story, image_prompt = get_story()
        img_path = f"avatar_{i+1}.png"
        # Generate and save image
        image = generate_image(image_prompt)
        os.rename("avatar.png", img_path)
        prompts.append({
            "story": story,
            "image_prompt": image_prompt,
            "image_path": img_path
        })
    # Save prompts to JSON
    with open("prompt_batch.json", "w", encoding="utf-8") as f:
        json.dump(prompts, f, ensure_ascii=False, indent=2)
    print(f"Batch of {batch_size} prompts and images generated.")

def use_next_prompt_and_image():
    # Load batch
    with open("prompt_batch.json", "r", encoding="utf-8") as f:
        prompts = json.load(f)
    if not prompts:
        raise Exception("No pre-generated prompts/images available.")
    # Use the first prompt/image
    item = prompts.pop(0)
    # Save the updated batch
    with open("prompt_batch.json", "w", encoding="utf-8") as f:
        json.dump(prompts, f, ensure_ascii=False, indent=2)
    print(f"Using prompt/image: {item['image_path']}")
    return item['story'], item['image_prompt'], item['image_path']

def main():
    # If batch file doesn't exist or is empty, generate a new batch
    if not os.path.exists("prompt_batch.json") or os.stat("prompt_batch.json").st_size == 0:
        batch_generate_prompts_and_images(batch_size=3)
    story, image_prompt, avatar_path = use_next_prompt_and_image()
    print("Story and image prompt loaded from batch.")
    create_video(story, avatar_path)
    print("Process completed.")
    # Upload to YouTube Shorts
    upload_to_youtube(
        video_file="output.mp4",
        title="AI Story Shorts | " + story[:40],
        description=story
    )

if __name__ == "__main__":
    main()
