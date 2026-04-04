"""
Tool: search_reviews.py
Purpose: Find and extract review snippets for a competitor from Trustpilot and web search.
Output: .tmp/reviews_{id}.json
"""

import json
import os
import re
import time
import argparse
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS
from dotenv import load_dotenv

load_dotenv()

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

POSITIVE_KEYWORDS = re.compile(
    r"\b(great|excellent|recommend|recommended|helpful|professional|amazing|fantastic|"
    r"outstanding|superb|brilliant|wonderful|satisfied|happy|pleased|approved|success|"
    r"5 star|five star|best|top|reliable|trusted|honest)\b",
    re.IGNORECASE,
)

NEGATIVE_KEYWORDS = re.compile(
    r"\b(scam|fraud|fake|cheat|cheated|delay|delayed|slow|terrible|horrible|awful|"
    r"worst|never|waste|disappointed|unprofessional|mislead|misleading|complaint|"
    r"never replied|no response|pathetic|refund|lost money|beware|avoid|1 star|"
    r"one star|bad experience|don't use|do not use)\b",
    re.IGNORECASE,
)


def classify_sentiment(text: str) -> str:
    pos = len(POSITIVE_KEYWORDS.findall(text))
    neg = len(NEGATIVE_KEYWORDS.findall(text))
    if pos > neg:
        return "positive"
    elif neg > pos:
        return "negative"
    return "neutral"


def deduplicate_snippets(snippets: list[dict]) -> list[dict]:
    seen_words = []
    unique = []
    for s in snippets:
        words = set(s["text"].lower().split())
        if not seen_words:
            seen_words.append(words)
            unique.append(s)
            continue
        # Check for >70% word overlap with any existing snippet
        is_duplicate = any(
            len(words & existing) / max(len(words), 1) > 0.7
            for existing in seen_words
        )
        if not is_duplicate:
            seen_words.append(words)
            unique.append(s)
    return unique


def extract_trustpilot_rating(soup: BeautifulSoup) -> float | None:
    # Try to find overall rating
    for pattern in [
        {"data-rating-typography": True},
        {"class": re.compile(r"star-rating|rating-count|trustscore", re.IGNORECASE)},
    ]:
        el = soup.find(attrs=pattern)
        if el:
            text = el.get_text(strip=True)
            match = re.search(r"(\d+\.?\d*)", text)
            if match:
                score = float(match.group(1))
                if 1.0 <= score <= 5.0:
                    return score
    return None


def scrape_trustpilot(company_name: str, root_domain: str) -> dict:
    tp_url = f"https://www.trustpilot.com/review/{root_domain}"
    result = {
        "url": tp_url,
        "scraped": False,
        "average_rating": None,
        "review_count": None,
        "sample_reviews": [],
    }

    try:
        response = requests.get(tp_url, headers=HEADERS, timeout=15)
        if response.status_code != 200:
            return result

        soup = BeautifulSoup(response.text, "html.parser")
        result["scraped"] = True

        # Rating
        result["average_rating"] = extract_trustpilot_rating(soup)

        # Review count
        count_el = soup.find(string=re.compile(r"\d[\d,]+\s+reviews?", re.IGNORECASE))
        if count_el:
            result["review_count"] = count_el.strip()

        # Sample reviews — look for review article cards
        reviews = []
        for article in soup.find_all("article", limit=10):
            rating_el = article.find(attrs={"data-service-review-rating": True})
            rating = int(rating_el["data-service-review-rating"]) if rating_el else None

            body_el = article.find("p", attrs={"data-service-review-text-typography": True})
            if not body_el:
                body_el = article.find("p")
            text = body_el.get_text(strip=True) if body_el else ""

            date_el = article.find("time")
            date = date_el.get("datetime", "")[:10] if date_el else ""

            if text and len(text) > 20:
                reviews.append({
                    "rating": rating,
                    "text": text[:400],
                    "date": date,
                    "sentiment": classify_sentiment(text),
                })

        result["sample_reviews"] = reviews

    except Exception as e:
        print(f"  [trustpilot] Could not scrape {tp_url}: {e}")
        result["scraped"] = False

    return result


def search_reviews(
    competitor_id: str,
    competitor_name: str,
    root_domain: str = "",
    output_path: str = None,
) -> dict:
    if output_path is None:
        output_path = f".tmp/reviews_{competitor_id}.json"

    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)

    print(f"[reviews] Searching for: {competitor_name}")

    queries = [
        f'"{competitor_name}" site:trustpilot.com reviews',
        f'"{competitor_name}" reviews immigration visa India',
        f'"{competitor_name}" complaints OR "bad experience" visa',
        f'"{competitor_name}" "highly recommend" OR "excellent service" immigration',
    ]

    search_snippets = []
    for query in queries:
        print(f"  [ddg] {query}")
        results = []
        for attempt in range(2):
            try:
                with DDGS() as ddgs:
                    results = list(ddgs.text(query, max_results=5))
                break
            except Exception as e:
                if attempt == 0:
                    print(f"  [retry] {e} — sleeping 5s")
                    time.sleep(5)
                else:
                    print(f"  [fail] {e}")

        for r in results:
            text = r.get("body", "").strip()
            if text and len(text) > 30:
                search_snippets.append({
                    "source": "DuckDuckGo",
                    "query_used": query,
                    "text": text[:500],
                    "url": r.get("href", ""),
                    "sentiment": classify_sentiment(text),
                })

        time.sleep(2)

    search_snippets = deduplicate_snippets(search_snippets)

    # Trustpilot direct scrape
    tp_domain = root_domain or competitor_id.replace("-", "")
    trustpilot_data = scrape_trustpilot(competitor_name, tp_domain)

    # Build sentiment summary
    all_sentiments = [s["sentiment"] for s in search_snippets]
    all_sentiments += [r["sentiment"] for r in trustpilot_data.get("sample_reviews", [])]

    positive_count = all_sentiments.count("positive")
    negative_count = all_sentiments.count("negative")
    neutral_count = all_sentiments.count("neutral")
    total = len(all_sentiments)

    if total == 0:
        dominant = "unknown"
    elif positive_count > negative_count:
        dominant = "positive"
    elif negative_count > positive_count:
        dominant = "negative"
    else:
        dominant = "mixed"

    # Extract common complaint / praise themes from text
    complaint_patterns = re.compile(
        r"(slow|delay|expensive|no response|hidden fee|complicated|fraud|"
        r"pathetic|wasted|refund|unreliable)",
        re.IGNORECASE,
    )
    praise_patterns = re.compile(
        r"(quick|fast|approved|professional|helpful|transparent|easy|"
        r"recommend|knowledgeable|responsive|reliable)",
        re.IGNORECASE,
    )

    all_text = " ".join(s["text"] for s in search_snippets)
    all_text += " ".join(r["text"] for r in trustpilot_data.get("sample_reviews", []))

    common_complaints = list(dict.fromkeys(complaint_patterns.findall(all_text)))[:5]
    common_praises = list(dict.fromkeys(praise_patterns.findall(all_text)))[:5]

    result = {
        "competitor_id": competitor_id,
        "competitor_name": competitor_name,
        "searched_at": datetime.now(timezone.utc).isoformat(),
        "trustpilot": trustpilot_data,
        "search_snippets": search_snippets,
        "sentiment_summary": {
            "positive_count": positive_count,
            "negative_count": negative_count,
            "neutral_count": neutral_count,
            "dominant_sentiment": dominant,
            "common_complaints": [c.lower() for c in common_complaints],
            "common_praises": [p.lower() for p in common_praises],
        },
        "error": None,
    }

    with open(output_path, "w") as f:
        json.dump(result, f, indent=2)

    print(f"  [done] sentiment={dominant}, snippets={len(search_snippets)} → {output_path}")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Search for competitor reviews")
    parser.add_argument("--id", required=True, help="Competitor slug ID")
    parser.add_argument("--name", required=True, help="Competitor display name")
    parser.add_argument("--domain", default="", help="Root domain for Trustpilot lookup")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    result = search_reviews(
        competitor_id=args.id,
        competitor_name=args.name,
        root_domain=args.domain,
        output_path=args.output,
    )
    print(f"\nDominant sentiment: {result['sentiment_summary']['dominant_sentiment']}")
    print(f"Trustpilot scraped: {result['trustpilot']['scraped']}")
