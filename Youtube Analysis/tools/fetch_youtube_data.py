"""
Fetch recent videos from a curated list of YouTube channels using yt-dlp.
No YouTube API key required — yt-dlp scrapes directly from YouTube.

Usage:
    python tools/fetch_youtube_data.py
    python tools/fetch_youtube_data.py --config config/channels.json
    python tools/fetch_youtube_data.py --days 7
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import yt_dlp

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_channels_config(config_path: str) -> dict:
    with open(config_path) as f:
        return json.load(f)


def fetch_channel_videos(channel_id: str, channel_name: str,
                          max_videos: int, published_after: datetime) -> list[dict]:
    """
    Fetch recent videos from a YouTube channel using yt-dlp.
    Returns a list of video dicts with metadata.
    """
    date_str = published_after.strftime("%Y%m%d")
    channel_url = f"https://www.youtube.com/channel/{channel_id}/videos"

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,          # Fast initial pass — gets video IDs + basic info
        "playlistend": max_videos * 3, # Fetch more than needed to account for Shorts filtering
        "dateafter": date_str,
        "ignoreerrors": True,
    }

    video_ids = []
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(channel_url, download=False)
            if not info or "entries" not in info:
                return []
            for entry in info["entries"] or []:
                if entry and entry.get("id"):
                    video_ids.append(entry["id"])
                if len(video_ids) >= max_videos * 2:
                    break
    except Exception as e:
        print(f"  [{channel_name}] ERROR extracting playlist: {e}")
        return []

    if not video_ids:
        return []

    # Now fetch full metadata for each video (gets views, likes, duration)
    videos = []
    detail_opts = {
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
    }

    cutoff_str = published_after.strftime("%Y%m%d")

    try:
        with yt_dlp.YoutubeDL(detail_opts) as ydl:
            for vid_id in video_ids:
                if len(videos) >= max_videos:
                    break
                try:
                    url = f"https://www.youtube.com/watch?v={vid_id}"
                    v = ydl.extract_info(url, download=False)
                    if not v:
                        continue

                    # Date filter
                    upload_date = v.get("upload_date", "")
                    if upload_date and upload_date < cutoff_str:
                        continue

                    duration = v.get("duration") or 0
                    is_short = 0 < duration < 60

                    description = (v.get("description") or "")[:500]
                    published_at = ""
                    if upload_date and len(upload_date) == 8:
                        published_at = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:8]}T00:00:00Z"

                    videos.append({
                        "id": vid_id,
                        "title": v.get("title", ""),
                        "description": description,
                        "channel_name": channel_name,
                        "channel_id": channel_id,
                        "published_at": published_at,
                        "view_count": int(v.get("view_count") or 0),
                        "like_count": int(v.get("like_count") or 0),
                        "comment_count": int(v.get("comment_count") or 0),
                        "duration_secs": duration,
                        "is_short": is_short,
                        "url": f"https://www.youtube.com/watch?v={vid_id}",
                    })
                except Exception:
                    continue
    except Exception as e:
        print(f"  [{channel_name}] ERROR fetching video details: {e}")

    return videos


def main():
    parser = argparse.ArgumentParser(description="Fetch YouTube channel data (no API key)")
    parser.add_argument(
        "--config",
        default=os.path.join(PROJECT_ROOT, "config", "channels.json"),
    )
    parser.add_argument("--output", default=None)
    parser.add_argument("--days", type=int, default=None,
                        help="Override published_after_days from config")
    args = parser.parse_args()

    config = load_channels_config(args.config)
    fetch_cfg = config.get("fetch_config", {})
    videos_per_channel = fetch_cfg.get("videos_per_channel", 10)
    published_after_days = args.days or fetch_cfg.get("published_after_days", 14)

    now = datetime.now(timezone.utc)
    published_after = now - timedelta(days=published_after_days)

    date_str = now.strftime("%Y-%m-%d")
    output_path = args.output or os.path.join(
        PROJECT_ROOT, ".tmp", f"youtube_raw_{date_str}.json"
    )
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    channels = config["channels"]
    print(f"Fetching videos from {len(channels)} channels (last {published_after_days} days)...")
    print("Using yt-dlp — no API key required.\n")

    all_videos = []
    for channel in channels:
        name = channel["name"]
        channel_id = channel["channel_id"]
        print(f"  [{name}] fetching...", end="", flush=True)

        videos = fetch_channel_videos(channel_id, name, videos_per_channel, published_after)
        non_shorts = [v for v in videos if not v["is_short"]]
        shorts_count = len(videos) - len(non_shorts)

        if not non_shorts:
            print(" no videos found")
        else:
            suffix = f" ({shorts_count} Shorts filtered)" if shorts_count else ""
            print(f" {len(non_shorts)} videos{suffix}")

        all_videos.extend(non_shorts)

    output = {
        "fetched_at": now.isoformat(),
        "date_range": {
            "from": published_after.strftime("%Y-%m-%d"),
            "to": now.strftime("%Y-%m-%d"),
        },
        "channels_fetched": len(channels),
        "total_videos": len(all_videos),
        "videos": sorted(all_videos, key=lambda v: v["view_count"], reverse=True),
    }

    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nDone. {len(all_videos)} total videos → {output_path}")
    return output_path


if __name__ == "__main__":
    main()
