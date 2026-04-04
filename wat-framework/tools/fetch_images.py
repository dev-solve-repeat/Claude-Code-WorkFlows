#!/usr/bin/env python3
"""
fetch_images.py — WAT Tool: Fetch license-free images from Unsplash

Updates the newsletter content JSON in place with a hero image URL and
the required Unsplash attribution HTML string.

Usage:
    python tools/fetch_images.py .tmp/newsletter_content_{slug}.json

Output:
    Updates content JSON in place with:
      - hero_image: {url, alt, photographer, photographer_url, unsplash_url}
      - image_attribution_html: ready-to-embed attribution string (required by Unsplash ToS)
"""

import argparse
import json
import os
import sys

from dotenv import load_dotenv

load_dotenv()


def fetch_unsplash_image(query, access_key, orientation='landscape'):
    import requests
    url = "https://api.unsplash.com/photos/random"
    params = {
        'query': query,
        'orientation': orientation,
        'content_filter': 'high',
    }
    headers = {'Authorization': f'Client-ID {access_key}'}
    resp = requests.get(url, params=params, headers=headers, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    return {
        'url': data['urls']['regular'],
        'url_full': data['urls']['full'],
        'alt': data.get('alt_description') or query,
        'photographer': data['user']['name'],
        'photographer_url': data['user']['links']['html'],
        'unsplash_url': data['links']['html'],
    }


def main():
    parser = argparse.ArgumentParser(description='Fetch hero image from Unsplash')
    parser.add_argument('content_path', help='Path to newsletter content JSON')
    args = parser.parse_args()

    try:
        with open(args.content_path) as f:
            content = json.load(f)
    except FileNotFoundError:
        print(f"ERROR: Content file not found: {args.content_path}", file=sys.stderr)
        sys.exit(1)

    access_key = os.getenv('UNSPLASH_ACCESS_KEY')
    if not access_key:
        print("WARNING: UNSPLASH_ACCESS_KEY not set in .env — skipping image fetch", file=sys.stderr)
        content['hero_image'] = None
        content['image_attribution_html'] = ''
        with open(args.content_path, 'w') as f:
            json.dump(content, f, indent=2)
        print("Content JSON updated (no image).")
        return

    try:
        import requests  # noqa: F401
    except ImportError:
        print("ERROR: requests not installed. Run: pip install -r requirements.txt", file=sys.stderr)
        sys.exit(1)

    # Build search query from topic keywords
    keywords = content.get('keywords', [])
    topic = content.get('topic', '')
    query = ' '.join(keywords[:3]) if keywords else topic

    print(f"Fetching hero image for query: '{query}'")

    try:
        hero = fetch_unsplash_image(query, access_key, orientation='landscape')
        content['hero_image'] = hero

        # Required by Unsplash Terms of Service
        utm = '?utm_source=newsletter&utm_medium=referral'
        content['image_attribution_html'] = (
            f'Photo by <a href="{hero["photographer_url"]}{utm}">{hero["photographer"]}</a>'
            f' on <a href="{hero["unsplash_url"]}{utm}">Unsplash</a>'
        )

        print(f"Hero image: {hero['url']}")
        print(f"Photographer: {hero['photographer']} (attribution embedded in footer)")

    except Exception as e:
        print(f"WARNING: Could not fetch image: {e}", file=sys.stderr)
        content['hero_image'] = None
        content['image_attribution_html'] = ''

    with open(args.content_path, 'w') as f:
        json.dump(content, f, indent=2)

    print(f"Updated {args.content_path}")


if __name__ == '__main__':
    main()
