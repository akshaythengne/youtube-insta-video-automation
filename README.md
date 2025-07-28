# youtube-insta-video-automation
# Automated AI Story Video Generator (Serverless, Free)

This project generates a unique story and AI video daily, using Perplexity and D-ID APIs. It runs serverlessly via GitHub Actions (no infra costs).

## ⚙️ Setup

### 1. Get your API keys:
- Perplexity API: [perplexity.ai](https://www.perplexity.ai/pro)
- D-ID API: [d-id.com](https://studio.d-id.com/)

### 2. Add your keys:
Go to your repo → Settings → Secrets and variables → Actions → New repository secret  
Add:
- `PERPLEXITY_API_KEY`
- `DID_API_KEY`

### 3. Commit and push.
GitHub Actions will run the workflow (and you can trigger it manually in Actions tab).

### 4. Find results:
The script generates `output.mp4` on each workflow run (check the "Artifacts" of the workflow job—it can be downloaded from the run summary).

## ⭐ Extending this:

- Add code to auto-upload to YouTube Shorts/Instagram.
- Compose more sophisticated prompts/styles.
