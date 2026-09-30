# BD-YT-Grabber - Docker Deployment for Unraid

Automated YouTube downloader that transcribes videos locally with Whisper, burns
styled subtitles, and uploads to info-beamer.

## Features

- Downloads new videos from a YouTube channel
- Transcribes audio locally with faster-whisper (no YouTube auto-captions)
- Corrects business terms via `glossary.json` (e.g. Berrima Diesel, berrimadiesel.com)
- Burns clean, styled subtitles (installed Roboto font, 1080p, max two lines)
- Uploads to info-beamer and adds to playlists automatically
- Gradually re-subtitles existing videos, replacing assets in place
- Configurable scheduling (daily/weekly/monthly/manual)

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `INFOBEAMER_API_KEY` | Yes | - | API key for info-beamer |
| `YOUTUBE_CHANNEL` | Yes | - | YouTube channel URL |
| `PLAYLIST_NAMES` | No | `VideoPlaylist1,VideoPlaylist2` | Comma-separated playlist names |
| `SUBTITLE_LANG` | No | `en` | Whisper language |
| `DOWNLOAD_LIMIT` | No | `1` | New videos to download per run (`0` disables) |
| `REPROCESS_LIMIT` | No | `1` | Existing videos to re-subtitle per run (`0` disables) |
| `WHISPER_MODEL` | No | `distil-large-v3` | faster-whisper model (`small.en` is much faster, less accurate) |
| `WHISPER_DEVICE` | No | `cpu` | `cpu` or `cuda` |
| `WHISPER_COMPUTE_TYPE` | No | `int8` | `int8` for CPU, `float16` for GPU |
| `MODELS_DIR` | No | `/app/models` | Whisper model cache (mount a volume) |
| `GLOSSARY_PATH` | No | `/app/glossary.json` | Business vocab + corrections |
| `SCHEDULE` | No | `daily` | `daily`, `weekly`, `monthly`, or `manual` |
| `SCHEDULE_TIME` | No | `02:00` | Time to run (HH:MM format) |
| `TZ` | No | `UTC` | Timezone |

### Schedule Examples

| SCHEDULE | SCHEDULE_TIME | Runs At |
|----------|---------------|---------|
| `daily` | `02:00` | Every day at 2:00 AM |
| `weekly` | `03:30` | Every Sunday at 3:30 AM |
| `monthly` | `01:00` | 1st of each month at 1:00 AM |
| `manual` | - | Run once and exit (no cron) |

## Volume Mounts

| Container Path | Host Path | Purpose |
|---------------|-----------|---------|
| `/app/videos` | `./videos` | Burned videos, `archive/` backups, `captions/` |
| `/app/data` | `./data` | `downloaded_videos.json` tracking, `captions/` |
| `/app/models` | `./models` | Whisper model cache (downloads on first run) |

## Subtitle Pipeline

1. `yt-dlp` downloads the source video (video only, no YouTube captions).
2. `faster-whisper` transcribes it locally with `vad_filter`, word timestamps
   and an `initial_prompt` built from `glossary.json`.
3. `glossary.json` `replacements` fix recurring mis-hearings
   (e.g. `bad diesel.com` -> `berrimadiesel.com`). Edit that file to add terms;
   the Docker image copies it at `/app/glossary.json`.
4. Captions are regrouped into sentence-sized cues, max two lines of 42
   characters, then rendered to ASS with a 1920x1080 style
   (Roboto, white with black outline, bottom margin).
5. `ffmpeg` burns the captions and encodes `libx264 -crf 18 -preset veryfast`
   with AAC audio and `+faststart`.

The first run downloads the Whisper model into `/app/models`. With
`distil-large-v3` that is ~1.5GB and CPU transcription is roughly real-time;
`small.en` is ~250MB and several times faster with slightly weaker punctuation.

## Reprocessing Existing Videos

info-beamer replaces an asset **in place** when a file with the same filename is
uploaded: the asset id is unchanged, playlists keep working, and devices pick up
the new version automatically. That makes gradual migration safe.

- Each run processes new videos first, then up to `REPROCESS_LIMIT` outdated
  videos (oldest first).
- Old burned files are archived under `videos/archive/<id>.p<version>.mp4`
  before being replaced, so you can roll back by re-uploading them.
- The tracking file stores a `pipeline` version and a `glossary` fingerprint per
  video. Editing `glossary.json` automatically re-queues videos transcribed with
  the old glossary; bump `SUBTITLE_PIPELINE_VERSION` for code/style changes.

Manual controls:

```bash
# Re-subtitle one video now
docker exec bd-yt-grabber /usr/local/bin/python3 -u /app/sync_videos.py \
  --api-key "$INFOBEAMER_API_KEY" --channel "$YOUTUBE_CHANNEL" \
  --reprocess-video pxmIlnhIsLI --download-limit 0

# Re-subtitle everything out of date (pipeline or glossary), no new downloads
docker exec bd-yt-grabber /usr/local/bin/python3 -u /app/sync_videos.py \
  --api-key "$INFOBEAMER_API_KEY" --channel "$YOUTUBE_CHANNEL" \
  --reprocess-all --download-limit 0
```

For fast glossary iteration, bind-mount your own file over `/app/glossary.json`
and edit it on the host; every run reads it fresh, so no image rebuild is needed:

```bash
-v /mnt/user/appdata/bd-yt-grabber/glossary.json:/app/glossary.json:ro
```

## Deployment on Unraid

### Option 1: Using Docker Compose (Recommended)

1. SSH into Unraid
2. Create directory:
   ```bash
   mkdir -p /mnt/user/appdata/bd-yt-grabber
   cd /mnt/user/appdata/bd-yt-grabber
   ```
3. Create `.env` file:
   ```bash
   INFOBEAMER_API_KEY=your_api_key_here
   YOUTUBE_CHANNEL=https://www.youtube.com/user/BerrimaDiesel
   SCHEDULE=daily
   SCHEDULE_TIME=02:00
   ```
4. Create a `models` directory and copy `docker-compose.yml`
5. Run:
   ```bash
   docker compose up -d
   ```

The compose file builds locally. To use the image published by GitHub Actions
instead, comment out `build:` and uncomment the `image:` line
(`ghcr.io/mjc668/bd-yt-grabber:latest`), then run `docker compose pull && docker compose up -d`.

### Option 2: Manual Docker Run

```bash
docker run -d \
  --name bd-yt-grabber \
  -e INFOBEAMER_API_KEY=your_api_key \
  -e YOUTUBE_CHANNEL=https://www.youtube.com/user/BerrimaDiesel \
  -e SCHEDULE=daily \
  -e SCHEDULE_TIME=02:00 \
  -v /mnt/user/appdata/bd-yt-grabber/videos:/app/videos \
  -v /mnt/user/appdata/bd-yt-grabber/data:/app/data \
  -v /mnt/user/appdata/bd-yt-grabber/models:/app/models \
  --restart unless-stopped \
  ghcr.io/mjc668/bd-yt-grabber:latest
```

## Building the Image

### Build locally on Unraid

```bash
cd /mnt/user/appdata/bd-yt-grabber
docker build -t bd-yt-grabber:latest -f docker/Dockerfile ..
```

### Build and push to GitHub Container Registry

Pushes to `main` build and push automatically via
`.github/workflows/docker.yml` (`ghcr.io/mjc668/bd-yt-grabber:latest`).
Manual build:

```bash
echo $GITHUB_TOKEN | docker login ghcr.io -u USERNAME --password-stdin

docker build -t ghcr.io/mjc668/bd-yt-grabber:latest -f docker/Dockerfile ..
docker push ghcr.io/mjc668/bd-yt-grabber:latest
```

## Usage

### View Logs (STDOUT)

All logs are sent to STDOUT, which means they appear automatically in:

**Unraid Docker UI:**
- Go to Docker -> Container -> **Log** tab

**Command line:**
```bash
docker logs -f bd-yt-grabber
```

### Run Manually

```bash
docker exec bd-yt-grabber python3 /app/sync_videos.py
```

### Restart Container

```bash
docker restart bd-yt-grabber
```

### Stop Container

```bash
docker stop bd-yt-grabber
```

## Unraid Docker Template

For Unraid's Docker GUI, use these settings:

### Container Settings

| Setting | Value |
|---------|-------|
| Name | `bd-yt-grabber` |
| Repository | `ghcr.io/mjc668/bd-yt-grabber:latest` (or local `bd-yt-grabber:latest`) |

### Environment Variables

| Variable | Value |
|----------|-------|
| `INFOBEAMER_API_KEY` | `your_api_key` |
| `YOUTUBE_CHANNEL` | `https://www.youtube.com/user/BerrimaDiesel` |
| `SCHEDULE` | `daily` |
| `SCHEDULE_TIME` | `02:00` |
| `REPROCESS_LIMIT` | `1` |
| `WHISPER_MODEL` | `distil-large-v3` (or `small.en` on weak CPUs) |

### Port Mappings

None required.

### Volume Mappings

| Config Type | Container Path | Host Path |
|-------------|---------------|-----------|
| Path | `/app/videos` | `/mnt/user/appdata/bd-yt-grabber/videos` |
| Path | `/app/data` | `/mnt/user/appdata/bd-yt-grabber/data` |
| Path | `/app/models` | `/mnt/user/appdata/bd-yt-grabber/models` |

## Troubleshooting

### Container not starting

Check logs:
```bash
docker logs bd-yt-grabber
```

### First run seems stuck at "Transcribing with Whisper"

The model is downloading into `/app/models` (~250MB for `small.en`, ~1.5GB for
`distil-large-v3`). Ensure the volume is mounted and the server can reach
Hugging Face. Subsequent runs use the cache.

### Transcription is too slow

Use a smaller model:
```bash
WHISPER_MODEL=small.en
```
Videos are processed one at a time overnight; one new video plus one reprocess
per night is usually enough even on modest CPUs.

### Videos not downloading

Ensure `INFOBEAMER_API_KEY` and `YOUTUBE_CHANNEL` are set correctly.

### Subtitles not appearing

Check the logs for `Generated N caption cues`. If the video has no speech
Whisper returns nothing and the run is skipped. Captions are kept in
`/app/data/captions/<id>.ass` and `.srt` for inspection.

### Manual run works but scheduled doesn't

Check cron is running:
```bash
docker exec bd-yt-grabber crontab -l
```

## Local Testing (without Docker)

```bash
cd ..
nix-shell
python3 sync_videos.py --video-dir videos --data-dir data
```

## License

MIT
