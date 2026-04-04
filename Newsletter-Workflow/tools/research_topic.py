#!/usr/bin/env python3
"""
research_topic.py — WAT Tool: Research a newsletter topic using Tavily API

Usage:
    python tools/research_topic.py "your topic here" [--max-results 8]

Output:
    .tmp/research_{slug}.json
    Schema: {topic, slug, timestamp, sources: [{title, url, content, date, relevance_score}]}
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()


def slugify(text):
    return re.sub(r'[^a-z0-9]+', '_', text.lower()).strip('_')


def main():
    parser = argparse.ArgumentParser(description='Research a newsletter topic using Tavily')
    parser.add_argument('topic', help='The newsletter topic to research')
    parser.add_argument('--max-results', type=int, default=8,
                        help='Number of sources to fetch (default: 8)')
    args = parser.parse_args()

    api_key = os.getenv('TAVILY_API_KEY')
    if not api_key:
        print("ERROR: TAVILY_API_KEY not set in .env", file=sys.stderr)
        sys.exit(1)

    try:
        from tavily import TavilyClient
    except ImportError:
        print("ERROR: tavily-python not installed. Run: pip install -r requirements.txt", file=sys.stderr)
        sys.exit(1)

    client = TavilyClient(api_key=api_key)

    print(f"Researching: {args.topic}")
    print(f"Fetching up to {args.max_results} sources...")

    response = client.search(
        query=args.topic,
        search_depth="advanced",
        include_raw_content=True,
        max_results=args.max_results,
    )

    sources = []
    for result in response.get('results', []):
        sources.append({
            'title': result.get('title', ''),
            'url': result.get('url', ''),
            'content': result.get('raw_content') or result.get('content', ''),
            'date': result.get('published_date', ''),
            'relevance_score': result.get('score', 0),
        })

    slug = slugify(args.topic)
    output = {
        'topic': args.topic,
        'slug': slug,
        'timestamp': datetime.utcnow().isoformat(),
        'sources': sources,
    }

    os.makedirs('.tmp', exist_ok=True)
    output_path = f'.tmp/research_{slug}.json'
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2)

    print(f"\nDone. {len(sources)} sources saved to {output_path}")
    for i, s in enumerate(sources):
        print(f"  [{i+1}] {s['title']} ({s['url'][:60]}...)" if len(s['url']) > 60 else f"  [{i+1}] {s['title']} ({s['url']})")


if __name__ == '__main__':
    main()
