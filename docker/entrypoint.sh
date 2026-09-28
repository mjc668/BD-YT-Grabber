#!/bin/bash
set -e

SCHEDULE="${SCHEDULE:-daily}"
SCHEDULE_TIME="${SCHEDULE_TIME:-02:00}"

INFOBEAMER_API_KEY="${INFOBEAMER_API_KEY:-}"
YOUTUBE_CHANNEL="${YOUTUBE_CHANNEL:-}"
PLAYLIST_NAMES="${PLAYLIST_NAMES:-VideoPlaylist1,VideoPlaylist2}"
SUBTITLE_LANG="${SUBTITLE_LANG:-en}"
DOWNLOAD_LIMIT="${DOWNLOAD_LIMIT:-1}"
REPROCESS_LIMIT="${REPROCESS_LIMIT:-1}"
WHISPER_MODEL="${WHISPER_MODEL:-distil-large-v3}"
WHISPER_DEVICE="${WHISPER_DEVICE:-cpu}"
WHISPER_COMPUTE_TYPE="${WHISPER_COMPUTE_TYPE:-int8}"
MODELS_DIR="${MODELS_DIR:-/app/models}"
GLOSSARY_PATH="${GLOSSARY_PATH:-/app/glossary.json}"
VIDEO_DIR="${VIDEO_DIR:-/app/videos}"
DATA_DIR="${DATA_DIR:-/app/data}"

convert_schedule_to_cron() {
    local schedule="$1"
    local time="$2"
    
    local hour=$(echo "$time" | cut -d: -f1)
    local minute=$(echo "$time" | cut -d: -f2)
    
    case "$schedule" in
        daily)
            echo "$minute $hour * * *"
            ;;
        weekly)
            echo "$minute $hour * * 0"
            ;;
        monthly)
            echo "$minute $hour 1 * *"
            ;;
        manual)
            echo ""
            ;;
        *)
            echo "$minute $hour * * *"
            ;;
    esac
}

PYTHON_ARGS=(
    --api-key "$INFOBEAMER_API_KEY"
    --channel "$YOUTUBE_CHANNEL"
    --playlists "$PLAYLIST_NAMES"
    --subtitle-lang "$SUBTITLE_LANG"
    --download-limit "$DOWNLOAD_LIMIT"
    --reprocess-limit "$REPROCESS_LIMIT"
    --whisper-model "$WHISPER_MODEL"
    --whisper-device "$WHISPER_DEVICE"
    --whisper-compute-type "$WHISPER_COMPUTE_TYPE"
    --models-dir "$MODELS_DIR"
    --glossary "$GLOSSARY_PATH"
    --video-dir "$VIDEO_DIR"
    --data-dir "$DATA_DIR"
)

echo "=========================================="
echo "BD-YT-Grabber"
echo "=========================================="
echo "Schedule: $SCHEDULE at $SCHEDULE_TIME"
echo "Whisper: $WHISPER_MODEL ($WHISPER_DEVICE/$WHISPER_COMPUTE_TYPE)"
echo "=========================================="
echo ""

if [ "$SCHEDULE" = "manual" ]; then
    echo "Running in manual mode..."
    /usr/local/bin/python3 -u /app/sync_videos.py "${PYTHON_ARGS[@]}"
else
    CRON_EXPRESSION=$(convert_schedule_to_cron "$SCHEDULE" "$SCHEDULE_TIME")
    CRON_ARGS=$(printf ' %q' "${PYTHON_ARGS[@]}")
    
    echo "Setting up cron: $CRON_EXPRESSION"
    
    cat > /etc/cron.d/bd-yt-grabber << CRONEOF
SHELL=/bin/bash
PATH=/usr/local/bin:/usr/bin:/bin
$CRON_EXPRESSION root /usr/local/bin/python3 -u /app/sync_videos.py$CRON_ARGS >> /proc/1/fd/1 2>&1
CRONEOF
    chmod 0644 /etc/cron.d/bd-yt-grabber
    
    echo "Starting cron daemon..."
    cron
    
    echo ""
    echo "Cron scheduled. Next run: $SCHEDULE at $SCHEDULE_TIME"
    echo ""
    echo "To view logs: docker logs bd-yt-grabber"
    echo "To run manually: docker exec bd-yt-grabber /usr/local/bin/python3 -u /app/sync_videos.py --api-key '$INFOBEAMER_API_KEY' --channel '$YOUTUBE_CHANNEL'"
    echo ""
    echo "Container is running. Press Ctrl+C to stop."
    
    sleep infinity
fi
