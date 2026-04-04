#!/usr/bin/env python3
"""
generate_charts.py — WAT Tool: Generate chart URLs/images for newsletter infographics

Primary: QuickChart.io (free, no key, email-safe <img> tags)
Fallback: Matplotlib → base64 PNG (when QuickChart URL exceeds ~2,000 chars)

Usage:
    python tools/generate_charts.py .tmp/newsletter_content_{slug}.json

Output:
    .tmp/charts_{slug}.json        — URL manifest (no base64, for logging/debugging)
    .tmp/charts_{slug}_full.json   — Full data including base64, used by build_newsletter_html.py
"""

import argparse
import base64
import io
import json
import os
import sys
import urllib.parse

from dotenv import load_dotenv

load_dotenv()

QUICKCHART_BASE = "https://quickchart.io/chart"
MAX_URL_LENGTH = 2000

# Default brand palette (neutral professional defaults)
COLORS = {
    'primary':   'rgba(37, 99, 235, 0.85)',   # blue-600
    'accent':    'rgba(239, 68, 68, 0.85)',   # red-500
    'green':     'rgba(16, 185, 129, 0.8)',   # emerald-500
    'amber':     'rgba(245, 158, 11, 0.8)',   # amber-500
    'slate':     'rgba(71, 85, 105, 0.7)',    # slate-600
    'grid':      'rgba(148, 163, 184, 0.2)',  # slate-300
    'bg':        'white',
}

PIE_COLORS = [
    COLORS['primary'], COLORS['accent'], COLORS['green'],
    COLORS['amber'], COLORS['slate'],
]


def build_chart_config(suggestion):
    chart_type = suggestion.get('type', 'bar')
    title = suggestion.get('title', '')
    data = suggestion.get('sample_data', {})
    labels = data.get('labels', [])
    values = data.get('values', [])

    base_font = {"family": "Arial, sans-serif"}
    title_plugin = {
        "display": True,
        "text": title,
        "font": {**base_font, "size": 15, "weight": "bold"},
        "padding": {"bottom": 12},
    }

    if chart_type == 'doughnut':
        bg_colors = PIE_COLORS[:len(values)]
        return {
            "type": "doughnut",
            "data": {
                "labels": labels,
                "datasets": [{"data": values, "backgroundColor": bg_colors, "borderWidth": 2}],
            },
            "options": {
                "plugins": {
                    "title": title_plugin,
                    "legend": {"position": "bottom", "labels": {"font": base_font}},
                },
            },
        }

    if chart_type == 'line':
        return {
            "type": "line",
            "data": {
                "labels": labels,
                "datasets": [{
                    "label": title,
                    "data": values,
                    "borderColor": COLORS['primary'],
                    "backgroundColor": "rgba(37, 99, 235, 0.1)",
                    "fill": True,
                    "tension": 0.4,
                    "pointRadius": 4,
                    "pointBackgroundColor": COLORS['primary'],
                }],
            },
            "options": {
                "plugins": {"title": title_plugin, "legend": {"display": False}},
                "scales": {
                    "y": {"beginAtZero": True, "grid": {"color": COLORS['grid']},
                          "ticks": {"font": base_font}},
                    "x": {"grid": {"display": False}, "ticks": {"font": base_font}},
                },
            },
        }

    # Default: bar
    return {
        "type": "bar",
        "data": {
            "labels": labels,
            "datasets": [{
                "label": title,
                "data": values,
                "backgroundColor": COLORS['primary'],
                "borderRadius": 5,
                "borderSkipped": False,
            }],
        },
        "options": {
            "plugins": {"title": title_plugin, "legend": {"display": False}},
            "scales": {
                "y": {"beginAtZero": True, "grid": {"color": COLORS['grid']},
                      "ticks": {"font": base_font}},
                "x": {"grid": {"display": False}, "ticks": {"font": base_font}},
            },
        },
    }


def make_quickchart_url(config, width=600, height=320):
    config_str = json.dumps(config, separators=(',', ':'))
    encoded = urllib.parse.quote(config_str)
    return f"{QUICKCHART_BASE}?c={encoded}&w={width}&h={height}&bkg=white&devicePixelRatio=2"


def make_matplotlib_base64(suggestion):
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except ImportError:
        return None

    data = suggestion.get('sample_data', {})
    labels = data.get('labels', [])
    values = data.get('values', [])
    title = suggestion.get('title', '')
    chart_type = suggestion.get('type', 'bar')

    primary_hex = '#2563EB'
    accent_hex = '#EF4444'
    pie_hexes = [primary_hex, accent_hex, '#10B981', '#F59E0B', '#475569']

    fig, ax = plt.subplots(figsize=(8, 4.2))
    fig.patch.set_facecolor('white')
    ax.set_facecolor('white')

    if chart_type == 'doughnut':
        colors = pie_hexes[:len(values)]
        wedges, texts, autotexts = ax.pie(
            values, labels=labels, colors=colors,
            autopct='%1.1f%%', startangle=90,
            wedgeprops={'linewidth': 1.5, 'edgecolor': 'white'},
        )
        for t in texts + autotexts:
            t.set_fontsize(9)
        ax.set_aspect('equal')
    elif chart_type == 'line':
        ax.plot(labels, values, color=primary_hex, linewidth=2.5,
                marker='o', markersize=5)
        ax.fill_between(range(len(labels)), values, alpha=0.1, color=primary_hex)
        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels, fontsize=9)
        ax.yaxis.grid(True, alpha=0.3)
        ax.set_axisbelow(True)
        ax.spines[['top', 'right']].set_visible(False)
    else:
        bars = ax.bar(labels, values, color=primary_hex,
                      edgecolor='white', linewidth=0.5)
        ax.yaxis.grid(True, alpha=0.3)
        ax.set_axisbelow(True)
        ax.spines[['top', 'right']].set_visible(False)
        ax.tick_params(axis='x', labelsize=9)

    ax.set_title(title, fontsize=13, fontweight='bold', pad=10,
                 fontfamily='DejaVu Sans')
    plt.tight_layout(pad=1.5)

    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=150, bbox_inches='tight',
                facecolor='white')
    plt.close()
    buf.seek(0)
    b64 = base64.b64encode(buf.read()).decode('utf-8')
    return f"data:image/png;base64,{b64}"


def main():
    parser = argparse.ArgumentParser(description='Generate chart images for newsletter')
    parser.add_argument('content_path', help='Path to newsletter content JSON')
    args = parser.parse_args()

    try:
        with open(args.content_path) as f:
            content = json.load(f)
    except FileNotFoundError:
        print(f"ERROR: Content file not found: {args.content_path}", file=sys.stderr)
        sys.exit(1)

    charts = {}

    for i, section in enumerate(content.get('sections', [])):
        suggestion = section.get('chart_suggestion', {})
        chart_type = suggestion.get('type', 'none')
        if chart_type == 'none' or not chart_type:
            continue

        chart_id = f"chart_{i}"
        print(f"Section {i+1}: generating {chart_type} chart — '{suggestion.get('title', '')}'")

        config = build_chart_config(suggestion)
        url = make_quickchart_url(config)

        if len(url) <= MAX_URL_LENGTH:
            charts[chart_id] = {
                'section_index': i,
                'type': chart_type,
                'title': suggestion.get('title', ''),
                'caption': suggestion.get('description', ''),
                'embed_type': 'url',
                'src': url,
            }
            print(f"  QuickChart URL ({len(url)} chars) — OK")
        else:
            print(f"  URL too long ({len(url)} chars) — falling back to matplotlib")
            b64 = make_matplotlib_base64(suggestion)
            if b64:
                charts[chart_id] = {
                    'section_index': i,
                    'type': chart_type,
                    'title': suggestion.get('title', ''),
                    'caption': suggestion.get('description', ''),
                    'embed_type': 'base64',
                    'src': b64,
                }
                print("  Matplotlib fallback — OK")
            else:
                print(f"  WARNING: Both methods failed — skipping chart for section {i+1}")

    slug = content['slug']
    os.makedirs('.tmp', exist_ok=True)

    # Manifest without base64 (readable)
    manifest = {k: {**v, 'src': v['src'] if v['embed_type'] == 'url' else '[base64 — see _full.json]'}
                for k, v in charts.items()}
    manifest_path = f".tmp/charts_{slug}.json"
    with open(manifest_path, 'w') as f:
        json.dump(manifest, f, indent=2)

    # Full data (used by HTML builder)
    full_path = f".tmp/charts_{slug}_full.json"
    with open(full_path, 'w') as f:
        json.dump(charts, f, indent=2)

    print(f"\nGenerated {len(charts)} chart(s)")
    print(f"Manifest:  {manifest_path}")
    print(f"Full data: {full_path}")

    if not charts:
        print("(No charts — all sections had type 'none')")


if __name__ == '__main__':
    main()
