import requests
import time
import os
from base64 import b64decode

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
        "model": "sonar-medium-online",
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
    content = response.json()["choices"][0]["message"]["content"]
    story, image_prompt = content.rsplit("Image prompt:", 1)
    return story.strip(), image_prompt.strip()

# === STEP 2: Generate image with Perplexity ===
def generate_image(image_prompt):
    payload = {
        "model": "gpt-image-1",
        "prompt": image_prompt
    }
    headers = {"Authorization": f"Bearer {PERPLEXITY_API_KEY}"}
    r = requests.post("https://api.perplexity.ai/images/generate", json=payload, headers=headers)
    image_url = r.json()["image_url"]
    # Download image locally (D-ID requires file)
    img_data = requests.get(image_url).content
    img_path = "avatar.png"
    with open(img_path, "wb") as f:
        f.write(img_data)
    return img_path

# === STEP 3: Generate video with D-ID ===
def create_video(story_text, avatar_path):
    # Upload avatar image to D-ID
    with open(avatar_path, "rb") as img:
        files = {"image": img}
        headers = {"Authorization": f"Bearer {DID_API_KEY}"}
        r = requests.post("https://api.d-id.com/images", headers=headers, files=files)
    image_url = r.json()["url"]

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

def main():
    story, image_prompt = get_story()
    print("Story and image prompt generated.")
    avatar_path = generate_image(image_prompt)
    print("Dynamic image generated.")
    create_video(story, avatar_path)
    print("Process completed.")

if __name__ == "__main__":
    main()
