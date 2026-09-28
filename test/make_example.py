#!/usr/bin/env python3
import argparse
import os
import sys
from pathlib import Path
from types import SimpleNamespace

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = Path(os.environ.get("BD_YT_REPO", SCRIPT_DIR.parent)).resolve()
sys.path.insert(0, str(REPO_ROOT))

import sync_videos as sv


def parse_args():
    parser = argparse.ArgumentParser(
        description="Render example captions locally (downloads and burns, never uploads)"
    )
    parser.add_argument("videos", nargs="+", help="YouTube video ids or urls")
    parser.add_argument("--out-dir", default=str(REPO_ROOT / "videos" / "example"))
    parser.add_argument("--models-dir", default=os.environ.get("MODELS_DIR", str(REPO_ROOT / "models")))
    parser.add_argument("--model", default=os.environ.get("WHISPER_MODEL", "distil-large-v3"))
    parser.add_argument("--device", default=os.environ.get("WHISPER_DEVICE", "cpu"))
    parser.add_argument("--compute-type", default=os.environ.get("WHISPER_COMPUTE_TYPE", "int8"))
    parser.add_argument("--language", default=os.environ.get("SUBTITLE_LANG", "en"))
    parser.add_argument("--glossary", default=str(REPO_ROOT / "glossary.json"))
    return parser.parse_args()


def as_video_id(value):
    value = value.strip()
    if "watch?v=" in value:
        return value.split("watch?v=")[1].split("&")[0]
    if "youtu.be/" in value:
        return value.split("youtu.be/")[1].split("?")[0]
    return value


def main():
    cli = parse_args()
    out_dir = Path(cli.out_dir)
    data_dir = out_dir / "data"
    captions_dir = data_dir / "captions"
    captions_dir.mkdir(parents=True, exist_ok=True)

    args = SimpleNamespace(
        video_dir=str(out_dir),
        data_dir=str(data_dir),
        whisper_model=cli.model,
        whisper_device=cli.device,
        whisper_compute_type=cli.compute_type,
        models_dir=cli.models_dir,
        language=cli.language,
        glossary=cli.glossary,
    )
    glossary = sv.subtitles.load_glossary(cli.glossary)

    for value in cli.videos:
        video_id = as_video_id(value)
        print("=" * 60)
        print(f"Video {video_id}")
        print("=" * 60)

        source = sv.download_source(video_id, out_dir)
        cues = sv.transcribe_video(source, args, glossary)
        if not cues:
            print("No speech detected, skipping")
            continue

        ass_path = out_dir / f"{video_id}.ass"
        sv.subtitles.write_ass(cues, ass_path, sv.OUTPUT_WIDTH, sv.OUTPUT_HEIGHT)
        sv.subtitles.write_srt(cues, captions_dir / f"{video_id}.srt")
        output = out_dir / f"{video_id}.mp4"
        sv.burn_subtitles(source, ass_path, output, out_dir)
        ass_path.rename(captions_dir / f"{video_id}.ass")
        source.unlink()

        print("\nTranscript:")
        for cue in cues:
            print(f"  [{cue['start']:6.1f}] {cue['text']}")
        print(f"\nRendered: {output}\n")


if __name__ == "__main__":
    main()
