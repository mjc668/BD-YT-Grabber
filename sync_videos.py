#!/usr/bin/env python3
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import requests

import subtitles

API_BASE = "https://info-beamer.com/api/v1"
SUBTITLE_PIPELINE_VERSION = 2
OUTPUT_WIDTH = 1920
OUTPUT_HEIGHT = 1080
DEFAULT_GLOSSARY = Path(__file__).resolve().parent / "glossary.json"


class PipelineError(Exception):
    pass


def parse_args():
    parser = argparse.ArgumentParser(description="BD-YT-Grabber - YouTube to info-beamer sync")

    parser.add_argument("--api-key", dest="api_key",
                        help="info-beamer API key (or set INFOBEAMER_API_KEY env var)")
    parser.add_argument("--channel", dest="channel",
                        help="YouTube channel URL (or set YOUTUBE_CHANNEL env var)")
    parser.add_argument("--playlists", dest="playlists",
                        help="Comma-separated playlist names (default: VideoPlaylist1,VideoPlaylist2)")
    parser.add_argument("--subtitle-lang", "--language", dest="language",
                        help="Subtitle language (default: en)")
    parser.add_argument("--download-limit", dest="download_limit", type=int,
                        help="Number of new videos to download per run (default: 1)")
    parser.add_argument("--reprocess-limit", dest="reprocess_limit", type=int,
                        help="Number of existing videos to re-subtitle per run (default: 1)")
    parser.add_argument("--reprocess-video", dest="reprocess_video",
                        help="Re-subtitle a single video id this run")
    parser.add_argument("--reprocess-all", dest="reprocess_all", action="store_true",
                        help="Re-subtitle every outdated video this run")
    parser.add_argument("--whisper-model", dest="whisper_model",
                        help="faster-whisper model (default: distil-large-v3)")
    parser.add_argument("--whisper-device", dest="whisper_device",
                        help="Whisper device, e.g. cpu (default: cpu)")
    parser.add_argument("--whisper-compute-type", dest="whisper_compute_type",
                        help="Whisper compute type, e.g. int8 (default: int8)")
    parser.add_argument("--models-dir", dest="models_dir",
                        help="Directory for Whisper models (default: /app/models)")
    parser.add_argument("--glossary", dest="glossary",
                        help="Path to glossary.json with business vocabulary")
    parser.add_argument("--video-dir", dest="video_dir",
                        help="Directory for downloaded videos (default: /app/videos)")
    parser.add_argument("--data-dir", dest="data_dir",
                        help="Directory for tracking data (default: /app/data)")

    args = parser.parse_args()

    args.api_key = args.api_key or os.environ.get("INFOBEAMER_API_KEY", "")
    args.channel = args.channel or os.environ.get("YOUTUBE_CHANNEL", "")
    args.playlists = args.playlists or os.environ.get("PLAYLIST_NAMES", "VideoPlaylist1,VideoPlaylist2")
    args.language = args.language or os.environ.get("SUBTITLE_LANG", "en")
    args.whisper_model = args.whisper_model or os.environ.get("WHISPER_MODEL", "distil-large-v3")
    args.whisper_device = args.whisper_device or os.environ.get("WHISPER_DEVICE", "cpu")
    args.whisper_compute_type = args.whisper_compute_type or os.environ.get("WHISPER_COMPUTE_TYPE", "int8")
    args.video_dir = args.video_dir or os.environ.get("VIDEO_DIR", "/app/videos")
    args.data_dir = args.data_dir or os.environ.get("DATA_DIR", "/app/data")
    args.models_dir = args.models_dir or os.environ.get("MODELS_DIR", "/app/models")
    args.glossary = args.glossary or os.environ.get("GLOSSARY_PATH", str(DEFAULT_GLOSSARY))

    if args.download_limit is None:
        args.download_limit = int(os.environ.get("DOWNLOAD_LIMIT", "1") or "1")
    if args.reprocess_limit is None:
        args.reprocess_limit = int(os.environ.get("REPROCESS_LIMIT", "1") or "1")

    return args


def load_tracking(data_dir):
    tracking_path = Path(data_dir) / "downloaded_videos.json"
    if tracking_path.exists():
        with open(tracking_path) as f:
            return migrate_tracking(json.load(f))
    return {"version": 2, "videos": {}, "pending": []}


def migrate_tracking(data):
    if "videos" in data:
        data.setdefault("pending", [])
        data["version"] = 2
        return data

    videos = {}
    for video_id in data.get("downloaded", []):
        videos[video_id] = {
            "status": "uploaded",
            "filename": f"{video_id}.mp4",
            "asset_id": None,
            "pipeline": 1,
            "in_playlists": True,
            "updated": None,
        }
    return {"version": 2, "videos": videos, "pending": list(data.get("pending", []))}


def save_tracking(tracking, data_dir):
    tracking_path = Path(data_dir) / "downloaded_videos.json"
    tracking_path.parent.mkdir(parents=True, exist_ok=True)
    with open(tracking_path, "w") as f:
        json.dump(tracking, f, indent=2)


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


def download_source(video_id, video_dir):
    video_dir = Path(video_dir)
    video_dir.mkdir(parents=True, exist_ok=True)
    source_path = video_dir / f"{video_id}.source.mp4"
    if source_path.exists():
        source_path.unlink()

    print(f"Downloading source video {video_id}...")

    result = subprocess.run([
        "yt-dlp",
        "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "--merge-output-format", "mp4",
        "-o", str(source_path),
        f"https://youtube.com/watch?v={video_id}"
    ], capture_output=True, text=True)

    if result.returncode != 0 or not source_path.exists():
        raise PipelineError(f"failed to download source video: {result.stderr.strip()[-500:]}")

    return source_path


def transcribe_video(source_path, args, glossary):
    print(f"Transcribing with Whisper ({args.whisper_model}, {args.whisper_device})...")

    if "distil" in args.whisper_model and args.language != "en":
        print(f"WARNING: {args.whisper_model} is English-only, ignoring language '{args.language}'")

    progress = {"reported": 0.0}

    def on_progress(seconds):
        if seconds - progress["reported"] >= 15:
            progress["reported"] = seconds
            print(f"  ... transcribed {seconds:.0f}s of audio")

    segments = subtitles.transcribe(
        source_path,
        model_name=args.whisper_model,
        device=args.whisper_device,
        compute_type=args.whisper_compute_type,
        model_dir=args.models_dir,
        language=args.language,
        initial_prompt=glossary.prompt,
        on_progress=on_progress,
    )
    cues = subtitles.build_cues(segments, glossary)
    print(f"Generated {len(cues)} caption cues")
    return cues


def burn_subtitles(source_path, ass_path, output_path, video_dir):
    print("Burning styled subtitles...")

    filters = (
        f"scale={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:force_original_aspect_ratio=decrease,"
        f"pad={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:(ow-iw)/2:(oh-ih)/2,"
        f"ass={ass_path.name}"
    )

    result = subprocess.run([
        "ffmpeg", "-y",
        "-i", str(source_path),
        "-vf", filters,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "160k",
        "-movflags", "+faststart",
        str(output_path)
    ], capture_output=True, text=True, cwd=str(video_dir))

    if result.returncode != 0 or not output_path.exists():
        raise PipelineError(f"ffmpeg failed: {result.stderr.strip()[-500:]}")

    return output_path


def upload_to_infobeamer(video_file, api_key):
    print(f"Uploading {video_file.name} to info-beamer...")

    url = f"{API_BASE}/asset/upload"
    last_error = None

    for attempt in range(1, 4):
        with open(video_file, "rb") as f:
            files = {"file": (video_file.name, f, "video/mp4")}
            response = requests.post(url, files=files, auth=("", api_key), timeout=600)

        if response.status_code == 200:
            data = response.json()
            asset_id = data.get("asset_id")
            print(f"Uploaded successfully, asset_id: {asset_id}")
            return asset_id

        last_error = f"{response.status_code} - {response.text[:300]}"
        print(f"WARNING: Upload attempt {attempt} failed: {last_error}")
        if response.status_code == 429:
            time.sleep(int(response.headers.get("Retry-After", "10")))
        else:
            time.sleep(5)

    print(f"ERROR: Upload failed: {last_error}")
    return None


def get_playlists(api_key):
    url = f"{API_BASE}/playlist/list"
    response = requests.get(url, auth=("", api_key), timeout=60)

    if response.status_code != 200:
        print(f"ERROR: Failed to get playlists: {response.status_code}")
        return {}

    playlists = response.json().get("playlists", {})
    return {p["name"]: p["id"] for p in playlists}


def get_target_playlists(playlist_names, api_key):
    playlists = get_playlists(api_key)
    print(f"Found playlists: {list(playlists.keys())}")

    targets = []
    for name in playlist_names:
        if name in playlists:
            targets.append((name, playlists[name]))
        else:
            print(f"WARNING: Playlist '{name}' not found")
    return targets


def add_to_playlist(asset_id, playlist_id, api_key):
    url = f"{API_BASE}/playlist/{playlist_id}"

    response = requests.get(url, auth=("", api_key), timeout=60)
    if response.status_code != 200:
        print(f"WARNING: Failed to get playlist: {response.status_code}")
        return False

    playlist = response.json()
    slots = playlist.get("slots", [])
    filters = playlist.get("filters", [])
    default_duration = playlist.get("default_duration", 10.0)

    for slot in slots:
        if (isinstance(slot, list) and len(slot) == 2 and slot[0] == "asset"
                and str(slot[1].get("asset_id")) == str(asset_id)):
            return True

    slots.append(["asset", {"asset_id": asset_id, "duration": None, "schedule": "always"}])

    response = requests.post(
        url,
        data={
            "slots": json.dumps(slots),
            "filters": json.dumps(filters),
            "default_duration": str(default_duration)
        },
        auth=("", api_key),
        timeout=60
    )

    if response.status_code not in (200, 201):
        print(f"WARNING: Failed to add to playlist: {response.status_code} - {response.text[:300]}")
        return False

    return True


def process_video(video_id, args, glossary, target_playlists, old_pipeline=None):
    video_dir = Path(args.video_dir)
    captions_dir = Path(args.data_dir) / "captions"
    video_dir.mkdir(parents=True, exist_ok=True)
    captions_dir.mkdir(parents=True, exist_ok=True)

    final_path = video_dir / f"{video_id}.mp4"
    archive_path = None
    if old_pipeline is not None and final_path.exists():
        archive_dir = video_dir / "archive"
        archive_dir.mkdir(parents=True, exist_ok=True)
        candidate = archive_dir / f"{video_id}.p{old_pipeline}.mp4"
        if not candidate.exists():
            shutil.move(str(final_path), str(candidate))
            archive_path = candidate
        else:
            final_path.unlink()

    source_path = None
    ass_path = None
    try:
        source_path = download_source(video_id, video_dir)
        cues = transcribe_video(source_path, args, glossary)
        if not cues:
            raise PipelineError("no speech detected")

        ass_path = video_dir / f"{video_id}.ass"
        subtitles.write_ass(cues, ass_path, OUTPUT_WIDTH, OUTPUT_HEIGHT)
        subtitles.write_srt(cues, captions_dir / f"{video_id}.srt")
        burn_subtitles(source_path, ass_path, final_path, video_dir)

        shutil.move(str(ass_path), str(captions_dir / f"{video_id}.ass"))
        ass_path = None
        source_path.unlink()
        source_path = None

        asset_id = upload_to_infobeamer(final_path, args.api_key)
        if not asset_id:
            raise PipelineError("upload failed")

        in_playlists = True
        if target_playlists is not None:
            in_playlists = bool(target_playlists)
            for name, playlist_id in target_playlists:
                if add_to_playlist(asset_id, playlist_id, args.api_key):
                    print(f"Added to playlist '{name}'")
                else:
                    in_playlists = False

        return asset_id, in_playlists
    except Exception:
        if archive_path and archive_path.exists():
            if final_path.exists():
                final_path.unlink()
            shutil.move(str(archive_path), str(final_path))
        raise
    finally:
        if source_path and source_path.exists():
            source_path.unlink()
        if ass_path and ass_path.exists():
            ass_path.unlink()


def select_reprocess_candidates(videos, args):
    if args.reprocess_video:
        if args.reprocess_video not in videos:
            print(f"WARNING: {args.reprocess_video} is not tracked, cannot reprocess")
            return []
        return [args.reprocess_video]

    outdated = [
        video_id for video_id, record in videos.items()
        if record.get("pipeline", 1) < SUBTITLE_PIPELINE_VERSION
    ]
    outdated.sort(key=lambda video_id: videos[video_id].get("updated") or 0)

    if args.reprocess_all:
        return outdated
    return outdated[: max(0, args.reprocess_limit)]


def main():
    args = parse_args()

    if not args.api_key:
        print("ERROR: API key not set (use --api-key or set INFOBEAMER_API_KEY env var)")
        sys.exit(1)

    if not args.channel:
        print("ERROR: YouTube channel not set (use --channel or set YOUTUBE_CHANNEL env var)")
        sys.exit(1)

    playlist_names = [name.strip() for name in args.playlists.split(",") if name.strip()]

    print("=" * 50)
    print("BD-YT-Grabber")
    print("=" * 50)
    print(f"Channel: {args.channel}")
    print(f"Playlists: {playlist_names}")
    print(f"New video limit: {args.download_limit}")
    print(f"Reprocess limit: {args.reprocess_limit}")
    print(f"Whisper model: {args.whisper_model}")
    print(f"Video dir: {args.video_dir}")
    print(f"Data dir: {args.data_dir}")
    print("=" * 50)

    tracking = load_tracking(args.data_dir)
    videos = tracking["videos"]
    pending = list(tracking.get("pending", []))
    glossary = subtitles.load_glossary(args.glossary)

    to_process = pending[: max(0, args.download_limit)]
    if len(to_process) < args.download_limit:
        video_ids = get_youtube_videos(args.channel)
        new_videos = [
            video_id for video_id in video_ids
            if video_id not in videos and video_id not in pending and video_id not in to_process
        ]
        print(f"New videos on channel: {len(new_videos)}")
        to_process.extend(new_videos[: args.download_limit - len(to_process)])

    reprocess = select_reprocess_candidates(videos, args)

    print(f"Already downloaded: {len(videos)}")
    print(f"Pending from last run: {len(pending)}")
    print(f"Will process this run: {len(to_process)} new, {len(reprocess)} reprocessed")

    if not to_process and not reprocess:
        print("Nothing to do")
        return

    target_playlists = []
    if to_process:
        target_playlists = get_target_playlists(playlist_names, args.api_key)

    for video_id in to_process:
        print(f"\n--- Processing new video {video_id} ---")

        try:
            asset_id, in_playlists = process_video(video_id, args, glossary, target_playlists)
        except PipelineError as error:
            print(f"ERROR: {error}")
            if video_id not in pending:
                pending.append(video_id)
                tracking["pending"] = pending
                save_tracking(tracking, args.data_dir)
            continue

        videos[video_id] = {
            "status": "uploaded",
            "filename": f"{video_id}.mp4",
            "asset_id": asset_id,
            "pipeline": SUBTITLE_PIPELINE_VERSION,
            "in_playlists": in_playlists,
            "updated": int(time.time()),
        }
        if video_id in pending:
            pending.remove(video_id)
            tracking["pending"] = pending
        save_tracking(tracking, args.data_dir)
        print(f"Finished {video_id}")

    for video_id in reprocess:
        record = videos[video_id]
        old_pipeline = record.get("pipeline", 1)
        print(f"\n--- Reprocessing {video_id} (pipeline {old_pipeline} -> {SUBTITLE_PIPELINE_VERSION}) ---")

        targets = None
        if not record.get("in_playlists"):
            targets = get_target_playlists(playlist_names, args.api_key)

        try:
            asset_id, in_playlists = process_video(
                video_id, args, glossary, targets, old_pipeline=old_pipeline
            )
        except PipelineError as error:
            print(f"ERROR: {error} (will retry on next run)")
            continue

        record.update({
            "status": "uploaded",
            "filename": f"{video_id}.mp4",
            "asset_id": asset_id,
            "pipeline": SUBTITLE_PIPELINE_VERSION,
            "in_playlists": record.get("in_playlists", True) and in_playlists,
            "updated": int(time.time()),
        })
        save_tracking(tracking, args.data_dir)
        print(f"Finished {video_id}")

    print("\nDone!")


if __name__ == "__main__":
    main()
