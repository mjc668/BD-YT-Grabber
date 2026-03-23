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

if [ "$SCHEDULE" = "manual" ]; then
    echo "Running in manual mode (no scheduling)..."
    echo "Executing sync script..."
    python3 /app/sync_videos.py
else
    echo "Setting up cron: $CRON_EXPRESSION"
    echo "$CRON_EXPRESSION python3 /app/sync_videos.py >> /var/log/sync.log 2>&1" > /etc/cron.d/bd-yt-grabber
    chmod 0644 /etc/cron.d/bd-yt-grabber
    crontab /etc/cron.d/bd-yt-grabber
    
    touch /var/log/sync.log
    
    echo "Starting cron daemon..."
    cron
    
    echo "Cron scheduled. Next run: $SCHEDULE at $SCHEDULE_TIME"
    echo "Log file: /var/log/sync.log"
    echo ""
    echo "To view logs: docker exec <container> tail -f /var/log/sync.log"
    echo "To run manually: docker exec <container> python3 /app/sync_videos.py"
    echo ""
    echo "Container is running. Press Ctrl+C to stop."
    
    sleep infinity
fi
