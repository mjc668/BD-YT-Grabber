#!/bin/bash
set -e

SCHEDULE="${SCHEDULE:-daily}"
SCHEDULE_TIME="${SCHEDULE_TIME:-02:00}"

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

echo "=========================================="
echo "BD-YT-Grabber"
echo "=========================================="
echo "Schedule: $SCHEDULE at $SCHEDULE_TIME"
echo "=========================================="

CRON_EXPRESSION=$(convert_schedule_to_cron "$SCHEDULE" "$SCHEDULE_TIME")

run_sync_with_logging() {
    python3 /app/sync_videos.py 2>&1 | while IFS= read -r line; do
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] $line"
    done
}

if [ "$SCHEDULE" = "manual" ]; then
    echo "Running in manual mode (no scheduling)..."
    echo "Executing sync script..."
    run_sync_with_logging
else
    echo "Setting up cron: $CRON_EXPRESSION"
    
    cat > /usr/local/bin/run-sync.sh << 'WRAPPER_EOF'
#!/bin/bash
python3 /app/sync_videos.py 2>&1 | while IFS= read -r line; do
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $line"
done
WRAPPER_EOF
    chmod +x /usr/local/bin/run-sync.sh
    
    echo "$CRON_EXPRESSION /usr/local/bin/run-sync.sh" > /etc/cron.d/bd-yt-grabber
    chmod 0644 /etc/cron.d/bd-yt-grabber
    crontab /etc/cron.d/bd-yt-grabber
    
    echo "Starting cron daemon..."
    cron
    
    echo ""
    echo "Cron scheduled. Next run: $SCHEDULE at $SCHEDULE_TIME"
    echo ""
    echo "To view logs: docker logs bd-yt-grabber"
    echo "To run manually: docker exec bd-yt-grabber python3 /app/sync_videos.py"
    echo ""
    echo "Container is running. Press Ctrl+C to stop."
    
    sleep infinity
fi
