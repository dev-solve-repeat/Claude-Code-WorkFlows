"""
Analyze YouTube video data to extract trending AI topics, tools, and insights.

Pure Python — no API calls. Reads raw video JSON and produces a structured
trends report with topic breakdowns, top videos, and tools in spotlight.

Usage:
    python tools/analyze_trends.py
    python tools/analyze_trends.py .tmp/youtube_raw_2026-04-05.json
    python tools/analyze_trends.py .tmp/youtube_raw_2026-04-05.json --output .tmp/trends_2026-04-05.json
"""

import argparse
import json
import math
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from glob import glob

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ---------------------------------------------------------------------------
# Topic taxonomy — keywords searched in lowercase title + description
# ---------------------------------------------------------------------------
TOPIC_CATEGORIES = {
    "LLMs & Frontier Models": [
        "gpt-5", "gpt-4o", "gpt-4", "gpt", "claude 4", "claude 3", "claude",
        "gemini 2", "gemini", "llama 4", "llama 3", "llama", "grok",
        "deepseek", "phi-4", "phi-3", "phi", "mistral", "command r",
        "o1", "o3", "o4", "reasoning model", "foundation model",
        "frontier model", "large language model", "llm",
    ],
    "AI Agents": [
        "ai agent", "agentic", "autonomous agent", "multi-agent",
        "crewai", "crew ai", "langgraph", "langchain", "autogen",
        "computer use", "browser use", "operator agent",
        "manus", "devin", "openai operator", "agent framework",
    ],
    "Image & Video Generation": [
        "midjourney", "stable diffusion", "dall-e", "dall·e", "flux",
        "sora", "runway ml", "runway gen", "pika labs", "kling",
        "veo 2", "veo", "imagen", "firefly", "ideogram",
        "text-to-image", "text-to-video", "image generation", "video generation",
    ],
    "Voice & Audio AI": [
        "elevenlabs", "eleven labs", "whisper", "text-to-speech",
        "voice clone", "voice ai", "notebooklm", "audio overview",
        "hume ai", "speechify",
    ],
    "AI Coding Tools": [
        "cursor ai", "cursor", "github copilot", "copilot",
        "replit", "bolt.new", "bolt", "claude code", "windsurf",
        "codeium", "vibe coding", "vibecoding", "lovable",
        "code generation", "ai coding",
    ],
    "AI Products & Apps": [
        "chatgpt", "perplexity", "you.com", "claude.ai",
        "gemini app", "microsoft copilot", "meta ai",
        "ai app", "ai product", "ai feature", "ai tool",
    ],
    "Open Source AI": [
        "open source ai", "open-source", "hugging face",
        "ollama", "local llm", "self-hosted", "open weights",
        "llama", "mistral",
    ],
    "AI Infrastructure": [
        "openai api", "anthropic api", "google ai studio",
        "aws bedrock", "azure openai", "groq", "together ai",
        "inference", "gpu cluster", "tpu",
        "rag", "retrieval augmented", "vector database", "embedding",
        "fine-tuning", "lora", "quantization",
    ],
}

# Specific tool/product names to track individually
TOOL_NAMES = [
    "GPT-5", "GPT-4o", "GPT-4", "Claude 4", "Claude 3.5", "Claude",
    "Gemini 2.0", "Gemini", "LLaMA 4", "LLaMA 3", "Grok",
    "DeepSeek", "Mistral", "Phi-4",
    "Midjourney", "Stable Diffusion", "DALL-E", "FLUX", "Sora",
    "Runway", "Pika", "Kling", "Veo",
    "ElevenLabs", "Whisper", "NotebookLM",
    "Cursor", "GitHub Copilot", "Replit", "Bolt", "Claude Code", "Windsurf",
    "ChatGPT", "Perplexity", "Manus", "Devin",
    "CrewAI", "LangGraph", "LangChain", "AutoGen",
    "Ollama", "Hugging Face",
]


def engagement_score(video: dict) -> float:
    """Composite engagement score — logarithmic to prevent viral outliers dominating."""
    v = math.log(video.get("view_count", 0) + 1)
    l = math.log(video.get("like_count", 0) + 1)
    c = math.log(video.get("comment_count", 0) + 1)
    return round(v * 0.6 + l * 0.3 + c * 0.1, 4)


def extract_topics(text: str) -> list[str]:
    """Return list of matched topic category names from lowercase text."""
    lower = text.lower()
    matched = []
    for category, keywords in TOPIC_CATEGORIES.items():
        if any(kw in lower for kw in keywords):
            matched.append(category)
    return matched if matched else ["Other"]


def extract_tool_mentions(text: str) -> list[str]:
    """Return list of specific tool names mentioned (case-insensitive)."""
    lower = text.lower()
    return [tool for tool in TOOL_NAMES if tool.lower() in lower]


def find_latest_raw_file() -> str | None:
    """Find the most recent youtube_raw_*.json in .tmp/."""
    pattern = os.path.join(PROJECT_ROOT, ".tmp", "youtube_raw_*.json")
    files = sorted(glob(pattern), reverse=True)
    return files[0] if files else None


def analyze(raw_data: dict) -> dict:
    videos = raw_data.get("videos", [])
    date_range = raw_data.get("date_range", {})

    # Annotate each video with topics and tool mentions
    annotated = []
    for v in videos:
        search_text = f"{v['title']} {v['description']}"
        topics = extract_topics(search_text)
        tools = extract_tool_mentions(search_text)
        score = engagement_score(v)
        annotated.append({**v, "topics": topics, "tool_mentions": tools, "engagement_score": score})

    # --- Topic breakdown ---
    topic_stats = defaultdict(lambda: {"video_count": 0, "total_views": 0, "tool_counter": defaultdict(int)})
    for v in annotated:
        for topic in v["topics"]:
            topic_stats[topic]["video_count"] += 1
            topic_stats[topic]["total_views"] += v["view_count"]
            for tool in v["tool_mentions"]:
                topic_stats[topic]["tool_counter"][tool] += 1

    topic_breakdown = {}
    for topic, stats in sorted(topic_stats.items(), key=lambda x: -x[1]["video_count"]):
        top_tools = sorted(stats["tool_counter"].items(), key=lambda x: -x[1])[:3]
        avg_views = stats["total_views"] // stats["video_count"] if stats["video_count"] else 0
        topic_breakdown[topic] = {
            "video_count": stats["video_count"],
            "total_views": stats["total_views"],
            "avg_views": avg_views,
            "top_tools": [t[0] for t in top_tools],
        }

    # --- Top videos by engagement ---
    top_videos = sorted(annotated, key=lambda v: -v["engagement_score"])[:5]
    top_videos_clean = [
        {
            "title": v["title"],
            "channel_name": v["channel_name"],
            "view_count": v["view_count"],
            "like_count": v["like_count"],
            "url": v["url"],
            "topics": v["topics"],
            "engagement_score": v["engagement_score"],
        }
        for v in top_videos
    ]

    # --- Tools in spotlight (mentioned across ≥2 channels or ≥2 videos) ---
    tool_counter = defaultdict(lambda: {"mention_count": 0, "channels": set()})
    for v in annotated:
        for tool in v["tool_mentions"]:
            tool_counter[tool]["mention_count"] += 1
            tool_counter[tool]["channels"].add(v["channel_name"])

    tools_in_spotlight = [
        {
            "tool": tool,
            "mention_count": data["mention_count"],
            "channels_mentioning": len(data["channels"]),
        }
        for tool, data in sorted(tool_counter.items(), key=lambda x: -x[1]["mention_count"])
        if data["mention_count"] >= 2
    ]

    # --- Channel activity ---
    channel_stats = defaultdict(lambda: {"videos_posted": 0, "total_views": 0, "topic_counter": defaultdict(int)})
    for v in annotated:
        ch = v["channel_name"]
        channel_stats[ch]["videos_posted"] += 1
        channel_stats[ch]["total_views"] += v["view_count"]
        for topic in v["topics"]:
            channel_stats[ch]["topic_counter"][topic] += 1

    channel_activity = []
    for ch, stats in sorted(channel_stats.items(), key=lambda x: -x[1]["total_views"]):
        top_topic = max(stats["topic_counter"], key=stats["topic_counter"].get) if stats["topic_counter"] else "N/A"
        avg_views = stats["total_views"] // stats["videos_posted"] if stats["videos_posted"] else 0
        channel_activity.append({
            "channel_name": ch,
            "videos_posted": stats["videos_posted"],
            "avg_views": avg_views,
            "total_views": stats["total_views"],
            "top_topic": top_topic,
        })

    # Top 3 topics by video count for executive summary
    top_topics = [t for t in topic_breakdown if t != "Other"][:3]

    return {
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
        "date_range": date_range,
        "summary": {
            "total_videos": len(annotated),
            "channels_active": len(channel_activity),
            "top_topics": top_topics,
        },
        "topic_breakdown": topic_breakdown,
        "top_videos": top_videos_clean,
        "tools_in_spotlight": tools_in_spotlight[:10],
        "channel_activity": channel_activity,
    }


def main():
    parser = argparse.ArgumentParser(description="Analyze YouTube trend data")
    parser.add_argument(
        "input",
        nargs="?",
        default=None,
        help="Path to youtube_raw_*.json (default: latest in .tmp/)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output file path (default: .tmp/trends_YYYY-MM-DD.json)",
    )
    args = parser.parse_args()

    input_path = args.input
    if not input_path:
        input_path = find_latest_raw_file()
        if not input_path:
            print("ERROR: No youtube_raw_*.json found in .tmp/. Run fetch_youtube_data.py first.")
            sys.exit(1)
        print(f"Using latest raw file: {input_path}")

    with open(input_path) as f:
        raw_data = json.load(f)

    print(f"Analyzing {raw_data['total_videos']} videos from {raw_data['channels_fetched']} channels...")

    trends = analyze(raw_data)

    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    output_path = args.output or os.path.join(
        PROJECT_ROOT, ".tmp", f"trends_{date_str}.json"
    )
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, "w") as f:
        json.dump(trends, f, indent=2)

    print(f"\nTop topics: {', '.join(trends['summary']['top_topics'])}")
    print(f"Tools in spotlight: {', '.join(t['tool'] for t in trends['tools_in_spotlight'][:5])}")
    print(f"\nTrends saved to {output_path}")
    return output_path


if __name__ == "__main__":
    main()
