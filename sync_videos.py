#!/usr/bin/env python3
import json
import os
import subprocess
import sys
from pathlib import Path

import requests

CONFIG_FILE = "config.json"
TRACKING_FILE = "downloaded_videos.json"
ENV_FILE = ".env"

API_BASE = "https://info-beamer.com/api/v1"


def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            return json.load(f)
    return {}


def load_env():
    env = {}
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE) as f:
            for line in f:
                line = line.strip()
                if line and "=" in line:
                    key, value = line.split("=", 1)
                    env[key] = value
    return env


def get_config_from_env():
    config = {}
    
    config["youtube_channel"] = os.environ.get("YOUTUBE_CHANNEL", "")
    config["subtitle_lang"] = os.environ.get("SUBTITLE_LANG", "en")
    config["download_limit"] = int(os.environ.get("DOWNLOAD_LIMIT", "1"))
    
    playlist_names = os.environ.get("PLAYLIST_NAMES", "VideoPlaylist1,VideoPlaylist2")
    config["playlist_names"] = [name.strip() for name in playlist_names.split(",")]
    
    config["video_dir"] = os.environ.get("VIDEO_DIR", "/app/videos")
    config["data_dir"] = os.environ.get("DATA_DIR", "/app/data")
    
    return config


def get_api_key_from_env():
    return os.environ.get("INFOBEAMER_API_KEY", "")


def merge_config(file_config, env_config):
    merged = file_config.copy()
    for key, value in env_config.items():
        if value and value != "" and value != 0:
            merged[key] = value
    return merged


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


def get_api_key(file_env, env_config):
    api_key = os.environ.get("INFOBEAMER_API_KEY", "")
    if not api_key:
        api_key = file_env.get("INFOBEAMER_API_KEY", "")
    
    if not api_key:
        print("ERROR: INFOBEAMER_API_KEY not set (environment variable or .env file required)")
        sys.exit(1)
    return api_key


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


def download_video(video_id, config):
    video_dir = Path(config.get("video_dir", "/app/videos"))
    video_dir.mkdir(parents=True, exist_ok=True)
    
    sub_lang = config.get("subtitle_lang", "en")
    
    print(f"Downloading video {video_id}...")
    
    result = subprocess.run([
        "yt-dlp",
        "--write-subs",
        "--write-auto-subs",
        "--sub-lang", sub_lang,
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
    file_config = load_config()
    file_env = load_env()
    env_config = get_config_from_env()
    
    config = merge_config(file_config, env_config)
    
    if not config.get("youtube_channel"):
        print("ERROR: YOUTUBE_CHANNEL not set (environment variable or config.json required)")
        sys.exit(1)
    
    api_key = get_api_key(file_env, env_config)
    data_dir = config.get("data_dir", "/app/data")
    
    tracking = load_tracking(data_dir)
    downloaded_ids = set(tracking.get("downloaded", []))
    pending_ids = set(tracking.get("pending", []))
    
    video_ids = get_youtube_videos(config["youtube_channel"])
    
    all_known = downloaded_ids | pending_ids
    new_videos = [vid for vid in video_ids if vid not in all_known]
    
    limit = config.get("download_limit", 1)
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
    
    playlists = get_playlists(api_key)
    print(f"Found playlists: {list(playlists.keys())}")
    
    target_playlists = []
    for name in config.get("playlist_names", ["VideoPlaylist1", "VideoPlaylist2"]):
        if name in playlists:
            target_playlists.append((name, playlists[name]))
        else:
            print(f"WARNING: Playlist '{name}' not found")
    
    for video_id in videos_to_process:
        print(f"\n--- Processing {video_id} ---")
        
        video_file = download_video(video_id, config)
        if not video_file:
            continue
        
        asset_id = upload_to_infobeamer(video_file, api_key)
        if not asset_id:
            remaining = [v for v in videos_to_process if v != video_id]
            tracking["pending"] = list(set(pending_ids) | set(remaining))
            save_tracking(tracking, data_dir)
            print("Upload failed, will retry remaining on next run")
            return
        
        for playlist_name, playlist_id in target_playlists:
            if add_to_playlist(asset_id, playlist_id, api_key):
                print(f"Added to playlist '{playlist_name}'")
        
        downloaded_ids.add(video_id)
        tracking["downloaded"] = list(downloaded_ids)
        if video_id in pending_ids:
            pending_ids.remove(video_id)
            tracking["pending"] = list(pending_ids)
        save_tracking(tracking, data_dir)
    
    print("\nDone!")


if __name__ == "__main__":
    main()
