# AI Shorts Generator

This project generates short AI-powered stories and converts them into narrated videos using Hugging Face, Perplexity, D-ID, and YouTube API.

## Structure

- `generate_batch.py` — Generates a batch of 7 stories and images for the week.
- `main.py` — Converts one story/image pair into a narrated video and uploads to YouTube.
- `.github/workflows/schedule.yml` — GitHub Actions for automation.

## GitHub Actions Setup

- Store the following secrets in your GitHub repository:
  - `PERPLEXITY_API_KEY`
  - `HUGGING_API_KEY`
  - `DID_API_KEY`

## Cron Schedules

- Weekly batch generation: **Sunday 00:00 UTC**
- Daily video generation: **Every day 09:00 UTC**

## Local Setup

```bash
pip install -r requirements.txt
python generate_batch.py  # Run weekly
python main.py            # Run daily
