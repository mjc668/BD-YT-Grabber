# BD-YT-Grabber - Docker Deployment for Unraid

Automated YouTube video downloader with hardcoded subtitles, uploading to info-beamer.

## Features

- Downloads videos from YouTube channel
- Generates/burns hardcoded English subtitles
- Uploads to info-beamer
- Adds to playlists automatically
- Configurable scheduling (daily/weekly/monthly/manual)

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `INFOBEAMER_API_KEY` | Yes | - | API key for info-beamer |
| `YOUTUBE_CHANNEL` | Yes | - | YouTube channel URL |
| `PLAYLIST_NAMES` | No | `VideoPlaylist1,VideoPlaylist2` | Comma-separated playlist names |
| `SUBTITLE_LANG` | No | `en` | Subtitle language |
| `DOWNLOAD_LIMIT` | No | `1` | Videos to download per run |
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
| `/app/videos` | `./videos` | Downloaded videos (persistent) |
| `/app/data` | `./data` | Tracking file (downloaded_videos.json) |

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
4. Copy `docker-compose.yml` to this directory
5. Run:
   ```bash
   docker compose up -d
   ```

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
  --restart unless-stopped \
  ghcr.io/yourusername/bd-yt-grabber:latest
```

## Building the Image

### Build locally on Unraid

```bash
cd /mnt/user/appdata/bd-yt-grabber
docker build -t bd-yt-grabber:latest -f docker/Dockerfile ..
```

### Build and push to GitHub Container Registry

```bash
# Login to ghcr.io
echo $GITHUB_TOKEN | docker login ghcr.io -u USERNAME --password-stdin

# Build and push
docker build -t ghcr.io/USERNAME/bd-yt-grabber:latest -f docker/Dockerfile ..
docker push ghcr.io/USERNAME/bd-yt-grabber:latest
```

## Usage

### View Logs (STDOUT)

All logs are sent to STDOUT, which means they appear automatically in:

**Unraid Docker UI:**
- Go to Docker → Container → **Log** tab

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
| Repository | `ghcr.io/yourusername/bd-yt-grabber:latest` (or local `bd-yt-grabber:latest`) |

### Environment Variables

| Variable | Value |
|----------|-------|
| `INFOBEAMER_API_KEY` | `your_api_key` |
| `YOUTUBE_CHANNEL` | `https://www.youtube.com/user/BerrimaDiesel` |
| `SCHEDULE` | `daily` |
| `SCHEDULE_TIME` | `02:00` |

### Port Mappings

None required.

### Volume Mappings

| Config Type | Container Path | Host Path |
|-------------|---------------|-----------|
| Path | `/app/videos` | `/mnt/user/appdata/bd-yt-grabber/videos` |
| Path | `/app/data` | `/mnt/user/appdata/bd-yt-grabber/data` |

## Troubleshooting

### Container not starting

Check logs:
```bash
docker logs bd-yt-grabber
```

### Videos not downloading

Ensure `INFOBEAMER_API_KEY` and `YOUTUBE_CHANNEL` are set correctly.

### Subtitles not appearing

Make sure `SUBTITLE_LANG` matches available subtitles on videos.

### Manual run works but scheduled doesn't

Check cron is running:
```bash
docker exec bd-yt-grabber crontab -l
```

## Local Testing (without Docker)

```bash
cd ..
nix-shell
python3 sync_videos.py
```

## License

MIT
