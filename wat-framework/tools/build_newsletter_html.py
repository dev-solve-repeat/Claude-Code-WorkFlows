#!/usr/bin/env python3
"""
build_newsletter_html.py — WAT Tool: Render final newsletter HTML

Combines content JSON + charts data into a Jinja2 template, inlines all CSS
via premailer, checks file size, and opens the result in the browser.

Usage:
    python tools/build_newsletter_html.py \
        .tmp/newsletter_content_{slug}.json \
        [.tmp/charts_{slug}_full.json]

Output:
    .tmp/newsletter_{YYYY-MM-DD}.html  (opened in browser automatically)
"""

import argparse
import json
import os
import sys
import webbrowser
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Gmail clips HTML emails over 102KB — warn at 90KB
SIZE_WARN_BYTES = 90 * 1024  # 90 KB


def load_charts(charts_path):
    """Load charts full JSON. Returns empty dict if path not provided or missing."""
    if not charts_path:
        return {}
    try:
        with open(charts_path) as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"WARNING: Charts file not found: {charts_path} — building without charts",
              file=sys.stderr)
        return {}


def split_paragraphs(text):
    """Split body text into paragraphs on blank lines or double newlines."""
    import re
    parts = re.split(r'\n\s*\n|\n{2,}', text.strip())
    return [p.strip() for p in parts if p.strip()]


def build_sections(content_sections, charts):
    """Merge section content with chart data."""
    # Build lookup: section_index → chart
    chart_by_section = {v['section_index']: v for v in charts.values()}

    sections = []
    for i, sec in enumerate(content_sections):
        chart = chart_by_section.get(i)
        sections.append({
            'title': sec.get('title', ''),
            'body_paragraphs': split_paragraphs(sec.get('body', '')),
            'key_stat': sec.get('key_stat', ''),
            'chart': chart,  # None if no chart for this section
        })
    return sections


def render_html(content, charts):
    try:
        from jinja2 import Environment, FileSystemLoader, select_autoescape
    except ImportError:
        print("ERROR: jinja2 not installed. Run: pip install -r requirements.txt", file=sys.stderr)
        sys.exit(1)

    template_dir = Path(__file__).parent / 'templates'
    env = Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=select_autoescape(['html']),
    )
    template = env.get_template('newsletter.html')

    sections = build_sections(content.get('sections', []), charts)
    issue_date = date.today().strftime('%B %-d, %Y')

    # Read time comes from quality report if available, else estimate inline
    slug = content.get('slug', '')
    read_time = 5  # default
    quality_path = f".tmp/quality_report_{slug}.json"
    if os.path.exists(quality_path):
        with open(quality_path) as f:
            quality = json.load(f)
        read_time = quality.get('read_time_minutes', 5)

    rendered = template.render(
        headline=content.get('headline', ''),
        preview_text=content.get('preview_text', ''),
        introduction=content.get('introduction', ''),
        sections=sections,
        conclusion=content.get('conclusion', ''),
        cta=content.get('cta', {'text': 'Read More', 'description': ''}),
        hero_image=content.get('hero_image'),
        image_attribution_html=content.get('image_attribution_html', ''),
        issue_date=issue_date,
        read_time=read_time,
    )
    return rendered


def inline_css(html):
    try:
        from premailer import transform
    except ImportError:
        print("WARNING: premailer not installed — CSS will not be inlined (Gmail may strip styles)",
              file=sys.stderr)
        print("Run: pip install -r requirements.txt", file=sys.stderr)
        return html

    return transform(
        html,
        remove_classes=False,
        keep_style_tags=False,
        cssutils_logging_level=None,
    )


def check_size(html, output_path):
    size_bytes = len(html.encode('utf-8'))
    size_kb = size_bytes / 1024
    if size_bytes > SIZE_WARN_BYTES:
        print(f"\nWARNING: HTML is {size_kb:.1f}KB — exceeds 90KB threshold.")
        print("Gmail clips emails over 102KB. Consider reducing content or images.")
    else:
        print(f"File size: {size_kb:.1f}KB — OK (under 90KB Gmail threshold)")


def main():
    parser = argparse.ArgumentParser(description='Build newsletter HTML from content + charts')
    parser.add_argument('content_path', help='Path to newsletter content JSON')
    parser.add_argument('charts_path', nargs='?', default=None,
                        help='Path to charts full JSON (optional)')
    args = parser.parse_args()

    try:
        with open(args.content_path) as f:
            content = json.load(f)
    except FileNotFoundError:
        print(f"ERROR: Content file not found: {args.content_path}", file=sys.stderr)
        sys.exit(1)

    # Auto-detect charts path if not provided
    charts_path = args.charts_path
    if not charts_path:
        slug = content.get('slug', '')
        auto_charts = f".tmp/charts_{slug}_full.json"
        if os.path.exists(auto_charts):
            charts_path = auto_charts
            print(f"Auto-detected charts: {charts_path}")

    charts = load_charts(charts_path)
    print(f"Loaded {len(charts)} chart(s)")

    print("Rendering Jinja2 template...")
    raw_html = render_html(content, charts)

    print("Inlining CSS via premailer...")
    final_html = inline_css(raw_html)

    # Output path
    today = date.today().strftime('%Y-%m-%d')
    slug = content.get('slug', 'newsletter')
    output_path = f".tmp/newsletter_{today}_{slug}.html"
    os.makedirs('.tmp', exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(final_html)

    check_size(final_html, output_path)
    print(f"\nNewsletter saved: {output_path}")

    # Open in browser
    abs_path = os.path.abspath(output_path)
    print(f"Opening in browser...")
    webbrowser.open(f"file://{abs_path}")
    print("Done.")


if __name__ == '__main__':
    main()
