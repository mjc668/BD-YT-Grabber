#!/bin/bash
set -e

SCHEDULE="${SCHEDULE:-daily}"
SCHEDULE_TIME="${SCHEDULE_TIME:-02:00}"

parse_time() {
    local time="$1"
    local hour=$(echo "$time" | cut -d: -f1)
    local minute=$(echo "$time" | cut -d: -f2)
    printf "%02d %02d" "$hour" "$minute"
}

calculate_seconds_until_run() {
    local target_hour="$1"
    local target_minute="$2"
    
    local now=$(date +%s)
    local target=$(date -d "$(date +%Y-%m-%d) $target_hour:$target_minute:00" +%s 2>/dev/null || date -v+1d -f "%Y-%m-%d %H:%M:%S" "$(date +%Y-%m-%d) $target_hour:$target_minute:00" +%s)
    
    if [ "$target" -le "$now" ]; then
        target=$(date -v+1d -f "%Y-%m-%d %H:%M:%S" "$(date +%Y-%m-%d) $target_hour:$target_minute:00" +%s 2>/dev/null || \
                 date -d "$(date -v+1d +%Y-%m-%d) $target_hour:$target_minute:00" +%s)
    fi
    
    echo $((target - now))
}

run_sync() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] =========================================="
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting sync job..."
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] =========================================="
    
    python3 /app/sync_videos.py 2>&1 | while IFS= read -r line; do
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] $line"
    done
    
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Sync completed"
    echo ""
}

echo "=========================================="
echo "BD-YT-Grabber"
echo "=========================================="
echo "Schedule: $SCHEDULE at $SCHEDULE_TIME"
echo "=========================================="
echo ""

read -r target_hour target_minute <<< "$(parse_time "$SCHEDULE_TIME")"

if [ "$SCHEDULE" = "manual" ]; then
    echo "Running in manual mode..."
    run_sync
else
    echo "Running scheduled mode..."
    echo "Next run: $target_hour:$target_minute today"
    echo ""
    echo "To view logs: docker logs bd-yt-grabber"
    echo "To run manually: docker exec bd-yt-grabber python3 /app/sync_videos.py"
    echo ""
    
    while true; do
        seconds_until=$(calculate_seconds_until_run "$target_hour" "$target_minute")
        
        if [ "$seconds_until" -gt 0 ]; then
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] Next sync in ${seconds_until}s at ${target_hour}:${target_minute}"
            sleep "$seconds_until"
        fi
        
        run_sync
        
        sleep 60
        seconds_until=$(calculate_seconds_until_run "$target_hour" "$target_minute")
        
        while [ "$seconds_until" -gt 0 ]; do
            sleep 60
            seconds_until=$(calculate_seconds_until_run "$target_hour" "$target_minute")
        done
    done
fi
