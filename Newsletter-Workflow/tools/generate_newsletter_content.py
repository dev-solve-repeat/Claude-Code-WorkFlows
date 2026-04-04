#!/usr/bin/env python3
"""
generate_newsletter_content.py — WAT Tool: Generate newsletter content from research

Usage:
    python tools/generate_newsletter_content.py .tmp/research_{slug}.json
        [--audience "tech professionals"]
        [--length standard]

Output:
    .tmp/newsletter_content_{slug}.json
    Schema: {headline, preview_text, introduction, sections, conclusion, cta, keywords, sources}
"""

import argparse
import json
import os
import sys
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

LENGTH_WORDS = {
    'short': 500,
    'standard': 800,
    'deep-dive': 1200,
}


def main():
    parser = argparse.ArgumentParser(description='Generate newsletter content from research')
    parser.add_argument('research_path', help='Path to research JSON file')
    parser.add_argument('--audience', default='general professionals',
                        help='Target audience description (default: "general professionals")')
    parser.add_argument('--length', choices=['short', 'standard', 'deep-dive'], default='standard',
                        help='Newsletter length (default: standard)')
    args = parser.parse_args()

    try:
        with open(args.research_path) as f:
            research = json.load(f)
    except FileNotFoundError:
        print(f"ERROR: Research file not found: {args.research_path}", file=sys.stderr)
        sys.exit(1)

    api_key = os.getenv('ANTHROPIC_API_KEY')
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not set in .env", file=sys.stderr)
        sys.exit(1)

    try:
        import anthropic
    except ImportError:
        print("ERROR: anthropic not installed. Run: pip install -r requirements.txt", file=sys.stderr)
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    # Build sources context (cap each source at 2,000 chars to stay within context limits)
    sources_text = "\n\n".join(
        f"SOURCE {i+1}: {s['title']}\nURL: {s['url']}\nDate: {s.get('date', 'unknown')}\n"
        f"Content:\n{s['content'][:2000]}"
        for i, s in enumerate(research['sources'])
    )

    target_words = LENGTH_WORDS[args.length]

    prompt = f"""You are a world-class newsletter writer. Based on the research below, write a structured newsletter about: {research['topic']}

Target audience: {args.audience}
Target body length: approximately {target_words} words

RESEARCH SOURCES:
{sources_text}

Return a JSON object with exactly this structure (no markdown, no code fences — raw JSON only):
{{
  "headline": "Compelling main headline (max 10 words)",
  "preview_text": "Email preview text — entices the open in 90 chars or less",
  "introduction": "2-3 sentence hook paragraph that draws the reader in",
  "sections": [
    {{
      "title": "Section heading (clear and scannable)",
      "body": "Section prose — 2 to 4 paragraphs, no jargon",
      "key_stat": "One striking statistic or quote from the sources, with attribution e.g. (Source: Title)",
      "chart_suggestion": {{
        "title": "Chart title",
        "type": "bar",
        "description": "What data this chart shows and why it matters",
        "sample_data": {{
          "labels": ["Label A", "Label B", "Label C"],
          "values": [42, 28, 30]
        }}
      }}
    }}
  ],
  "conclusion": "Closing paragraph with a clear takeaway or forward-looking thought",
  "cta": {{
    "text": "Button/link text for the call to action",
    "description": "One sentence explaining what the reader should do next"
  }},
  "keywords": ["keyword1", "keyword2", "keyword3", "keyword4", "keyword5"]
}}

Rules:
- Write exactly 3 to 4 sections
- Every key_stat must quote or paraphrase a specific source from the research (cite by title)
- For chart_suggestion: use type "none" and omit sample_data if no chart is appropriate for that section
- chart types available: bar, line, doughnut
- Choose bar for comparisons, line for trends over time, doughnut for proportions/percentages
- Write at grade 8-10 reading level: clear, direct, no unnecessary jargon
- Return ONLY valid JSON — no explanation, no markdown fences"""

    print(f"Generating newsletter content for: {research['topic']}")
    print(f"Audience: {args.audience} | Length: {args.length} (~{target_words} words)")

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}]
    )

    content_text = message.content[0].text.strip()

    # Strip markdown fences if the model added them despite instructions
    if content_text.startswith('```'):
        lines = content_text.split('\n')
        content_text = '\n'.join(lines[1:])  # drop first line (```json or ```)
        if content_text.endswith('```'):
            content_text = content_text[:-3]
        content_text = content_text.strip()

    try:
        content = json.loads(content_text)
    except json.JSONDecodeError as e:
        print(f"ERROR: Model returned invalid JSON: {e}", file=sys.stderr)
        print("Raw response saved to .tmp/debug_content_response.txt", file=sys.stderr)
        os.makedirs('.tmp', exist_ok=True)
        with open('.tmp/debug_content_response.txt', 'w') as f:
            f.write(content_text)
        sys.exit(1)

    # Attach metadata
    content['topic'] = research['topic']
    content['slug'] = research['slug']
    content['timestamp'] = datetime.utcnow().isoformat()
    content['audience'] = args.audience
    content['length'] = args.length
    content['sources'] = research['sources']

    output_path = f".tmp/newsletter_content_{research['slug']}.json"
    os.makedirs('.tmp', exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(content, f, indent=2)

    print(f"\nDone. Content saved to {output_path}")
    print(f"Headline: {content.get('headline', 'N/A')}")
    print(f"Sections: {len(content.get('sections', []))}")
    charts = sum(1 for s in content.get('sections', [])
                 if s.get('chart_suggestion', {}).get('type', 'none') != 'none')
    print(f"Charts suggested: {charts}")


if __name__ == '__main__':
    main()
