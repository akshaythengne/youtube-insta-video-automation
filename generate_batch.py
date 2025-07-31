# generate_batch.py
import os
import json
import re
import torch
from diffusers import StableDiffusionPipeline
from PIL import Image

PERPLEXITY_API_KEY = os.environ['PERPLEXITY_API_KEY']

OUTPUT_DIR = "prompt_images"
os.makedirs(OUTPUT_DIR, exist_ok=True)
BATCH_FILE = os.path.join(OUTPUT_DIR, "prompt_batch.json")

def get_story():
    import requests
    prompt = (
        "Write a 2-minute engaging story for a vertical video. "
        "Include narration, and in the end, provide a one-sentence vivid image prompt that evokes the main scene."
    )
    payload = {
        "model": "sonar-pro",
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": "Give today's unique story."}
        ]
    }
    headers = {
        "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
        "Content-Type": "application/json"
    }
    response = requests.post("https://api.perplexity.ai/chat/completions", json=payload, headers=headers)
    content = response.json()["choices"][0]["message"]["content"]
    match = re.search(r"(.*?)(?:\*\*|\*)?\s*(?:Image prompt|Prompt)\s*[:\-–]?\s*\**\s*\n*\s*(.+)$", content, re.IGNORECASE | re.DOTALL)
    if not match or len(match.groups()) < 2:
        raise Exception("No valid image prompt found in response: " + content)
    return match.group(1).strip(), match.group(2).strip()

def load_pipeline():
    model_id = "stabilityai/stable-diffusion-2-1"
    pipe = StableDiffusionPipeline.from_pretrained(
        model_id,
        torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
    )
    if torch.cuda.is_available():
        pipe.to("cuda")
    else:
        pipe.to("cpu")
    return pipe

def generate_image(pipe, image_prompt, index):
    image_prompt_clean = re.sub(r"[*_`#>\-]", "", image_prompt).strip()
    image = pipe(image_prompt_clean).images[0]
    image_path = os.path.join(OUTPUT_DIR, f"image_{index}.png")
    image.save(image_path)
    return image_path

def main():
    batch = []
    pipe = load_pipeline()
    for i in range(7):  # Weekly batch
        print(f"Generating story and image {i + 1}/7")
        story, image_prompt = get_story()
        image_path = generate_image(pipe, image_prompt, i)
        batch.append({
            "story": story,
            "image_prompt": image_prompt,
            "image_path": image_path
        })

    with open(BATCH_FILE, "w", encoding="utf-8") as f:
        json.dump(batch, f, ensure_ascii=False, indent=2)
    print("Prompt and image batch saved.")

if __name__ == "__main__":
    main()
