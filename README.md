# Hiten Clip AI

A GitHub Pages frontend with a Python/FastAPI backend for speech transcription, highlight suggestions and captioned MP4 export.

## Features
- Upload video from your computer
- Whisper-powered speech-to-text (English, Hindi, Gujarati and auto-detect)
- Highlight suggestions ranked using transcript signals and speech density
- Export selected moments as MP4 with burned-in subtitles
- Vertical 9:16, square 1:1 and landscape output

## Deploy the frontend
1. Open **Settings → Pages** in this repository.
2. Select **Deploy from a branch**, branch `main`, folder `/(root)`, then Save.
3. Open the published Pages website.

## Deploy the AI backend
The AI backend is in `backend/` and requires Python, FFmpeg and a machine with enough RAM for Whisper. A small paid CPU instance is recommended; free-tier containers may run out of memory or sleep.

1. Create a new **Render Web Service** from this GitHub repository.
2. Set the Root Directory to `backend`.
3. Choose **Docker** runtime and deploy. The Dockerfile installs FFmpeg and Python dependencies.
4. Set environment variable `WHISPER_MODEL=tiny` for a lighter first deployment, or `small` for better accuracy if your instance has enough memory.
5. After deployment, copy the service URL (for example `https://your-service.onrender.com`).
6. Open the GitHub Pages frontend, paste that URL into **AI backend URL**, upload a video, and click **Find best moments with AI**.

## What the AI does
- Uses faster-whisper for actual speech recognition and timestamps.
- Suggests moments by ranking transcript content, speech density and expressive text signals. This is an assistive highlight ranker, not a guarantee of viral performance or a trained video-understanding model.
- Re-transcribes the chosen clip and burns timed subtitles into the exported MP4.

## Important
- Processing happens on the backend. Upload only videos you own or have permission to process.
- YouTube URL downloading is intentionally not included. Use a video file you are authorized to upload.
- Large videos take time and consume backend CPU/RAM. Do not expose the API publicly for high-volume use without authentication, upload limits and rate limiting.
- GitHub Pages hosts only the frontend; it cannot run the Python AI backend.
