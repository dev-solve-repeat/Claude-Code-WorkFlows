#!/usr/bin/env python3
"""
score_newsletter.py — WAT Tool: Score newsletter readability and estimate read time

Uses Flesch-Kincaid grade level analysis. Target range for newsletters: grade 8-10.

Usage:
    python tools/score_newsletter.py .tmp/newsletter_content_{slug}.json

Output:
    .tmp/quality_report_{slug}.json
    Prints a quality summary to stdout
"""

import argparse
import json
import os
import re
import sys

from dotenv import load_dotenv

load_dotenv()

# Average adult reading speed (words per minute)
READING_SPEED_WPM = 238


def _count_syllables(word):
    """Simple syllable estimator — no NLTK/cmudict required."""
    word = word.lower().strip(".,!?;:'\"()")
    if not word:
        return 0
    if len(word) <= 3:
        return 1
    word = re.sub(r'(?<=[^aeiou])es$', '', word)
    word = re.sub(r'(?<=[^aeiou])ed$', '', word)
    word = re.sub(r'e$', '', word)
    return max(1, len(re.findall(r'[aeiouy]+', word)))


def _compute_readability(text):
    """Return (fk_grade, flesch_ease) using the standard formula."""
    words = text.split()
    word_count = max(1, len(words))
    sentences = max(1, len(re.findall(r'[.!?]+', text)))
    syllables = sum(_count_syllables(w) for w in words)

    avg_words = word_count / sentences
    avg_syllables = syllables / word_count

    fk_grade = 0.39 * avg_words + 11.8 * avg_syllables - 15.59
    ease = 206.835 - 1.015 * avg_words - 84.6 * avg_syllables
    return round(fk_grade, 1), round(ease, 1)


def extract_body_text(content):
    """Concatenate all prose sections for scoring."""
    parts = [
        content.get('introduction', ''),
        content.get('conclusion', ''),
    ]
    for section in content.get('sections', []):
        parts.append(section.get('body', ''))
        # Include key stats in word count but not readability (they're often quoted)
    return ' '.join(p for p in parts if p)


def grade_to_label(grade):
    if grade < 6:
        return ('too_simple', 'Too simple — consider adding more depth')
    if grade <= 10:
        return ('good', 'Excellent — hits the newsletter sweet spot (grade 8-10)')
    if grade <= 14:
        return ('slightly_dense', 'Slightly dense — consider simplifying some sentences')
    return ('too_complex', 'Too complex — readers will disengage. Simplify.')


def main():
    parser = argparse.ArgumentParser(description='Score newsletter readability')
    parser.add_argument('content_path', help='Path to newsletter content JSON')
    args = parser.parse_args()

    try:
        with open(args.content_path) as f:
            content = json.load(f)
    except FileNotFoundError:
        print(f"ERROR: Content file not found: {args.content_path}", file=sys.stderr)
        sys.exit(1)

    text = extract_body_text(content)
    word_count = len(text.split())
    read_time = max(1, round(word_count / READING_SPEED_WPM))

    fk_grade, ease = _compute_readability(text)
    grade_key, grade_note = grade_to_label(fk_grade)
    grade_ok = grade_key in ('good', 'slightly_dense')

    # Count sections and charts
    sections = content.get('sections', [])
    chart_count = sum(
        1 for s in sections
        if s.get('chart_suggestion', {}).get('type', 'none') != 'none'
    )

    report = {
        'slug': content.get('slug'),
        'topic': content.get('topic'),
        'word_count': word_count,
        'read_time_minutes': read_time,
        'flesch_kincaid_grade': round(fk_grade, 1),
        'flesch_reading_ease': round(ease, 1),
        'grade_status': grade_key,
        'grade_note': grade_note,
        'grade_ok': grade_ok,
        'section_count': len(sections),
        'chart_count': chart_count,
    }

    slug = content.get('slug', 'unknown')
    output_path = f".tmp/quality_report_{slug}.json"
    os.makedirs('.tmp', exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(report, f, indent=2)

    # Pretty print to terminal
    width = 44
    print(f"\n{'─' * width}")
    print(f"  Quality Report: {content.get('topic', 'N/A')}")
    print(f"{'─' * width}")
    print(f"  Word count:       {word_count:,}")
    print(f"  Est. read time:   {read_time} min")
    print(f"  FK grade level:   {fk_grade:.1f}  (target: 8-10)")
    print(f"  Reading ease:     {ease:.1f} / 100")
    print(f"  Sections:         {len(sections)}")
    print(f"  Charts planned:   {chart_count}")
    print(f"{'─' * width}")
    print(f"  {grade_note}")
    print(f"{'─' * width}\n")

    if not grade_ok:
        print("ACTION REQUIRED: Readability outside target range.")
        print("Re-run generate_newsletter_content.py to revise, then re-score.")
        print("(Research JSON can be reused — no Tavily credits needed.)\n")
    else:
        print("OK: Ready to build HTML.\n")

    print(f"Full report: {output_path}")


if __name__ == '__main__':
    main()
