---
title: ViralClip Studio
emoji: 🎬
colorFrom: purple
colorTo: indigo
sdk: docker
app_port: 8000
---

# ViralClip Studio

No-login YouTube Viral Clips Generator (<60s clips, auto-subtitles, virality score /100, Title/Tags/Description, one-click MP4/SRT/ZIP download).

## Option A: Deploy on Hugging Face Spaces (Recommended Free 16GB RAM, No GitHub needed)

1. Go to https://huggingface.co/new-space
2. Choose **Space SDK: Docker** -> **Blank**, visibility **Public**, and create the Space.
3. Under **Files -> Add file -> Upload files**, upload all files from this folder (`Dockerfile`, `README.md`, `backend/`, `frontend/`, `render.yaml`, `.dockerignore`).
4. Wait ~3–5 minutes for the Docker build. Your live backend URL will be `https://<your-username>-<space-name>.hf.space`.

## Option B: Deploy on Render (Docker - Frontend + Backend together)

1. Push this folder to a GitHub repository.
2. Open https://dashboard.render.com -> **New +** -> **Web Service** (or **Blueprint** to auto-read `render.yaml`).
3. Connect your GitHub repository, choose **Docker**, Health Check Path `/api/health`, and click **Create Web Service**.
4. Once live, your backend URL will be `https://<service-name>.onrender.com`.
