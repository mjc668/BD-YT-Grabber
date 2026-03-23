#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import requests

API_BASE = "https://info-beamer.com/api/v1"


def parse_args():
    parser = argparse.ArgumentParser(description="BD-YT-Grabber - YouTube to info-beamer sync")
    
    parser.add_argument("--api-key", dest="api_key", 
                        help="info-beamer API key (or set INFOBEAMER_API_KEY env var)")
    parser.add_argument("--channel", dest="channel", 
                        help="YouTube channel URL (or set YOUTUBE_CHANNEL env var)")
    parser.add_argument("--playlists", dest="playlists", 
                        default="VideoPlaylist1,VideoPlaylist2",
                        help="Comma-separated playlist names (default: VideoPlaylist1,VideoPlaylist2)")
    parser.add_argument("--subtitle-lang", dest="subtitle_lang", default="en",
                        help="Subtitle language (default: en)")
    parser.add_argument("--download-limit", dest="download_limit", type=int, default=1,
                        help="Number of videos to download per run (default: 1)")
    parser.add_argument("--video-dir", dest="video_dir", default="/app/videos",
                        help="Directory for downloaded videos (default: /app/videos)")
    parser.add_argument("--data-dir", dest="data_dir", default="/app/data",
                        help="Directory for tracking data (default: /app/data)")
    
    args = parser.parse_args()
    
    args.api_key = args.api_key or os.environ.get("INFOBEAMER_API_KEY", "")
    args.channel = args.channel or os.environ.get("YOUTUBE_CHANNEL", "")
    args.playlists = args.playlists or os.environ.get("PLAYLIST_NAMES", "VideoPlaylist1,VideoPlaylist2")
    args.subtitle_lang = args.subtitle_lang or os.environ.get("SUBTITLE_LANG", "en")
    args.download_limit = args.download_limit or int(os.environ.get("DOWNLOAD_LIMIT", "1") or "1")
    args.video_dir = args.video_dir or os.environ.get("VIDEO_DIR", "/app/videos")
    args.data_dir = args.data_dir or os.environ.get("DATA_DIR", "/app/data")
    
    return args


def load_tracking(data_dir):
    tracking_path = Path(data_dir) / "downloaded_videos.json"
    if tracking_path.exists():
        with open(tracking_path) as f:
            return json.load(f)
    return {"downloaded": [], "pending": []}


def save_tracking(data, data_dir):
    tracking_path = Path(data_dir) / "downloaded_videos.json"
    tracking_path.parent.mkdir(parents=True, exist_ok=True)
    with open(tracking_path, "w") as f:
        json.dump(data, f, indent=2)


def get_youtube_videos(channel_url):
    print(f"Fetching video list from {channel_url}...")
    
    result = subprocess.run(
        ["yt-dlp", "--flat-playlist", "--print", "%(id)s", channel_url],
        capture_output=True,
        text=True
    )
    
    if result.returncode != 0:
        print(f"ERROR: Failed to get video list: {result.stderr}")
        sys.exit(1)
    
    video_ids = [vid.strip() for vid in result.stdout.strip().split("\n") if vid.strip()]
    print(f"Found {len(video_ids)} videos on channel")
    return video_ids


def download_video(video_id, video_dir, subtitle_lang):
    video_dir = Path(video_dir)
    video_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"Downloading video {video_id}...")
    
    result = subprocess.run([
        "yt-dlp",
        "--write-subs",
        "--write-auto-subs",
        "--sub-lang", subtitle_lang,
        "--convert-subs", "srt",
        "-o", str(video_dir / "%(id)s.%(ext)s"),
        f"https://youtube.com/watch?v={video_id}"
    ], capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"WARNING: Failed to download subs for {video_id}: {result.stderr}")
    
    result = subprocess.run([
        "yt-dlp",
        "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "-o", str(video_dir / "%(id)s.%(ext)s"),
        f"https://youtube.com/watch?v={video_id}"
    ], capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"ERROR: Failed to download video {video_id}: {result.stderr}")
        return None
    
    video_file = None
    for ext in ["mp4", "mkv", "webm"]:
        potential = video_dir / f"{video_id}.{ext}"
        if potential.exists():
            video_file = potential
            break
    
    if not video_file:
        print(f"ERROR: Could not find downloaded file for {video_id}")
        return None
    
    sub_file = video_dir / f"{video_id}.en.srt"
    if sub_file.exists():
        print(f"Burning hardcoded subtitles into video...")
        output_file = video_dir / f"{video_id}_burned.mp4"
        
        subprocess.run([
            "ffmpeg", "-y",
            "-i", str(video_file),
            "-vf", f"subtitles='{sub_file}':force_style='FontName=Arial,FontSize=24,PrimaryColour=&HFFFFFF,Outline=1,Shadow=1'",
            "-c:a", "copy",
            str(output_file)
        ], capture_output=True)
        
        if output_file.exists():
            output_file.rename(video_file)
            sub_file.unlink()
            print(f"Hardcoded subtitles burned successfully")
    
    return video_file


def upload_to_infobeamer(video_file, api_key):
    print(f"Uploading {video_file.name} to info-beamer...")
    
    url = f"{API_BASE}/asset/upload"
    
    with open(video_file, "rb") as f:
        files = {"file": (video_file.name, f, "video/mp4")}
        response = requests.post(
            url,
            files=files,
            auth=("", api_key)
        )
    
    if response.status_code != 200:
        print(f"ERROR: Upload failed: {response.status_code} - {response.text}")
        return None
    
    data = response.json()
    asset_id = data.get("asset_id")
    print(f"Uploaded successfully, asset_id: {asset_id}")
    return asset_id


def get_playlists(api_key):
    url = f"{API_BASE}/playlist/list"
    response = requests.get(url, auth=("", api_key))
    
    if response.status_code != 200:
        print(f"ERROR: Failed to get playlists: {response.status_code}")
        return {}
    
    playlists = response.json().get("playlists", {})
    return {p["name"]: p["id"] for p in playlists}


def add_to_playlist(asset_id, playlist_id, api_key):
    url = f"{API_BASE}/playlist/{playlist_id}"
    
    response = requests.get(url, auth=("", api_key))
    if response.status_code != 200:
        print(f"WARNING: Failed to get playlist: {response.status_code}")
        return False
    
    playlist = response.json()
    slots = playlist.get("slots", [])
    filters = playlist.get("filters", [])
    default_duration = playlist.get("default_duration", 10.0)
    
    new_slot = ["asset", {"asset_id": asset_id, "duration": None, "schedule": "always"}]
    slots.append(new_slot)
    
    response = requests.post(
        url,
        data={
            "slots": json.dumps(slots),
            "filters": json.dumps(filters),
            "default_duration": str(default_duration)
        },
        auth=("", api_key)
    )
    
    if response.status_code not in (200, 201):
        print(f"WARNING: Failed to add to playlist: {response.status_code} - {response.text}")
        return False
    
    return True


def main():
    args = parse_args()
    
    if not args.api_key:
        print("ERROR: API key not set (use --api-key or set INFOBEAMER_API_KEY env var)")
        sys.exit(1)
    
    if not args.channel:
        print("ERROR: YouTube channel not set (use --channel or set YOUTUBE_CHANNEL env var)")
        sys.exit(1)
    
    playlist_names = [name.strip() for name in args.playlists.split(",")]
    
    print("=" * 50)
    print("BD-YT-Grabber")
    print("=" * 50)
    print(f"Channel: {args.channel}")
    print(f"Playlists: {playlist_names}")
    print(f"Download limit: {args.download_limit}")
    print(f"Video dir: {args.video_dir}")
    print(f"Data dir: {args.data_dir}")
    print("=" * 50)
    
    tracking = load_tracking(args.data_dir)
    downloaded_ids = set(tracking.get("downloaded", []))
    pending_ids = set(tracking.get("pending", []))
    
    video_ids = get_youtube_videos(args.channel)
    
    all_known = downloaded_ids | pending_ids
    new_videos = [vid for vid in video_ids if vid not in all_known]
    
    limit = args.download_limit
    videos_to_process = list(pending_ids)[:limit]
    
    if len(videos_to_process) < limit:
        videos_to_process += new_videos[:limit - len(videos_to_process)]
    
    videos_to_process = videos_to_process[:limit]
    
    print(f"New videos on channel: {len(new_videos)}")
    print(f"Already downloaded: {len(downloaded_ids)}")
    print(f"Pending from last run: {len(pending_ids)}")
    print(f"Will process this run: {len(videos_to_process)}")
    
    if not videos_to_process:
        print("No new videos to download")
        return
    
    playlists = get_playlists(args.api_key)
    print(f"Found playlists: {list(playlists.keys())}")
    
    target_playlists = []
    for name in playlist_names:
        if name in playlists:
            target_playlists.append((name, playlists[name]))
        else:
            print(f"WARNING: Playlist '{name}' not found")
    
    for video_id in videos_to_process:
        print(f"\n--- Processing {video_id} ---")
        
        video_file = download_video(video_id, args.video_dir, args.subtitle_lang)
        if not video_file:
            continue
        
        asset_id = upload_to_infobeamer(video_file, args.api_key)
        if not asset_id:
            remaining = [v for v in videos_to_process if v != video_id]
            tracking["pending"] = list(set(pending_ids) | set(remaining))
            save_tracking(tracking, args.data_dir)
            print("Upload failed, will retry remaining on next run")
            return
        
        for playlist_name, playlist_id in target_playlists:
            if add_to_playlist(asset_id, playlist_id, args.api_key):
                print(f"Added to playlist '{playlist_name}'")
        
        downloaded_ids.add(video_id)
        tracking["downloaded"] = list(downloaded_ids)
        if video_id in pending_ids:
            pending_ids.remove(video_id)
            tracking["pending"] = list(pending_ids)
        save_tracking(tracking, args.data_dir)
    
    print("\nDone!")


if __name__ == "__main__":
    main()
