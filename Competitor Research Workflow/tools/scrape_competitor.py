"""
Tool: scrape_competitor.py
Purpose: Scrape a single competitor website for services, pricing, messaging, and content.
Output: .tmp/scraped_{id}.json
"""

import json
import os
import re
import time
import argparse
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

SUBPAGE_PATTERNS = [
    "/services", "/pricing", "/visa", "/work-permit", "/work-visa",
    "/about", "/about-us", "/europe", "/europe-visa", "/work-abroad",
    "/overseas", "/immigration", "/contact",
]

PRICING_KEYWORDS = re.compile(
    r"(₹|£|€|\$|AED|fee|fees|price|pricing|cost|costs|package|packages|"
    r"starting from|starting at|from only|per applicant|consultation charge)",
    re.IGNORECASE,
)

MAX_TEXT_CHARS = 15000


def fetch_page(url: str, timeout: int = 15) -> tuple[str | None, str]:
    """Returns (html_content, status) where status is 'success', 'blocked', or 'failed'."""
    for attempt, user_agent in enumerate([
        HEADERS["User-Agent"],
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/119.0",
    ]):
        try:
            headers = {**HEADERS, "User-Agent": user_agent}
            response = requests.get(
                url,
                headers=headers,
                timeout=timeout,
                allow_redirects=True,
            )
            response.encoding = response.apparent_encoding

            if response.status_code == 200:
                return response.text, "success"
            elif response.status_code in (403, 429) and attempt == 0:
                time.sleep(2)
                continue
            elif response.status_code in (403, 429):
                return response.text, "blocked"
            elif response.status_code == 404:
                return None, "not_found"
            else:
                return response.text, f"http_{response.status_code}"
        except requests.exceptions.Timeout:
            return None, "timeout"
        except requests.exceptions.ConnectionError:
            return None, "connection_error"
        except Exception as e:
            return None, f"error_{str(e)[:50]}"

    return None, "blocked"


def parse_page(html: str, base_url: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")

    # Remove noise elements
    for tag in soup(["script", "style", "footer", "noscript", "iframe", "svg"]):
        tag.decompose()

    title = soup.find("title")
    title_text = title.get_text(strip=True) if title else ""

    meta_desc = soup.find("meta", attrs={"name": "description"})
    meta_text = meta_desc.get("content", "").strip() if meta_desc else ""

    h1_tags = [h.get_text(strip=True) for h in soup.find_all("h1")][:5]
    h2_tags = [h.get_text(strip=True) for h in soup.find_all("h2")][:10]
    h3_tags = [h.get_text(strip=True) for h in soup.find_all("h3")][:10]

    # Nav links
    nav_links = []
    for nav in soup.find_all(["nav", "header"]):
        for a in nav.find_all("a"):
            text = a.get_text(strip=True)
            if text and len(text) < 50:
                nav_links.append(text)
    nav_links = list(dict.fromkeys(nav_links))[:20]  # deduplicate, cap at 20

    # CTA buttons
    cta_texts = []
    for el in soup.find_all(["button", "a"]):
        cls = " ".join(el.get("class", []))
        if re.search(r"cta|btn|button|apply|start|get|book|consult|enquir", cls, re.IGNORECASE):
            text = el.get_text(strip=True)
            if text and len(text) < 60:
                cta_texts.append(text)
    cta_texts = list(dict.fromkeys(cta_texts))[:10]

    # Pricing mentions
    pricing_mentions = []
    body = soup.find("main") or soup.find("body") or soup
    for p in body.find_all(["p", "li", "span", "div"]):
        text = p.get_text(strip=True)
        if PRICING_KEYWORDS.search(text) and len(text) < 300:
            pricing_mentions.append(text)
    pricing_mentions = list(dict.fromkeys(pricing_mentions))[:10]

    # Full text content
    raw_text = body.get_text(separator=" ", strip=True)
    raw_text = re.sub(r"\s+", " ", raw_text)

    # Detect JS-heavy pages (sparse content)
    status_hint = None
    if len(raw_text) < 500:
        status_hint = "partial_js_rendered"

    # Collect internal subpage links
    subpage_links = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith("#") or href.startswith("mailto:") or href.startswith("tel:"):
            continue
        full_url = urljoin(base_url, href)
        parsed = urlparse(full_url)
        base_parsed = urlparse(base_url)
        if parsed.netloc == base_parsed.netloc:
            path = parsed.path.rstrip("/")
            for pattern in SUBPAGE_PATTERNS:
                if path.endswith(pattern) or pattern in path:
                    subpage_links.append(full_url)
                    break
    subpage_links = list(dict.fromkeys(subpage_links))[:5]

    return {
        "title": title_text,
        "meta_description": meta_text,
        "h1_tags": h1_tags,
        "h2_tags": h2_tags,
        "h3_tags": h3_tags,
        "nav_links": nav_links,
        "cta_texts": cta_texts,
        "pricing_mentions": pricing_mentions,
        "raw_text": raw_text[:5000],  # Per-page cap
        "subpage_links": subpage_links,
        "status_hint": status_hint,
    }


def scrape_competitor(
    competitor_id: str,
    website_url: str,
    output_path: str = None,
) -> dict:
    if output_path is None:
        output_path = f".tmp/scraped_{competitor_id}.json"

    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)

    print(f"[scrape] {competitor_id} → {website_url}")
    html, status = fetch_page(website_url)

    if html is None:
        result = {
            "competitor_id": competitor_id,
            "website": website_url,
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "pages_scraped": [],
            "homepage": {},
            "subpages": [],
            "raw_text_combined": "",
            "error": status,
        }
        with open(output_path, "w") as f:
            json.dump(result, f, indent=2)
        return result

    homepage_data = parse_page(html, website_url)
    pages_scraped = [website_url]
    all_text = [homepage_data["raw_text"]]

    # Determine final status
    final_status = status
    if homepage_data.get("status_hint"):
        final_status = homepage_data["status_hint"]

    # Scrape subpages
    subpages = []
    for subpage_url in homepage_data.get("subpage_links", [])[:5]:
        print(f"  [subpage] {subpage_url}")
        time.sleep(1)
        sub_html, sub_status = fetch_page(subpage_url)
        if sub_html:
            sub_data = parse_page(sub_html, subpage_url)
            subpages.append({
                "url": subpage_url,
                "title": sub_data["title"],
                "headings": sub_data["h1_tags"] + sub_data["h2_tags"],
                "pricing_mentions": sub_data["pricing_mentions"],
                "content_excerpt": sub_data["raw_text"][:1000],
            })
            all_text.append(sub_data["raw_text"])
            pages_scraped.append(subpage_url)

    # Combine and cap total text
    raw_text_combined = " ".join(all_text)
    raw_text_combined = re.sub(r"\s+", " ", raw_text_combined)[:MAX_TEXT_CHARS]

    result = {
        "competitor_id": competitor_id,
        "website": website_url,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "status": final_status,
        "pages_scraped": pages_scraped,
        "homepage": {
            "title": homepage_data["title"],
            "meta_description": homepage_data["meta_description"],
            "h1_tags": homepage_data["h1_tags"],
            "h2_tags": homepage_data["h2_tags"],
            "h3_tags": homepage_data["h3_tags"],
            "nav_links": homepage_data["nav_links"],
            "cta_texts": homepage_data["cta_texts"],
            "pricing_mentions": homepage_data["pricing_mentions"],
        },
        "subpages": subpages,
        "raw_text_combined": raw_text_combined,
        "error": None if final_status in ("success", "partial_js_rendered") else final_status,
    }

    with open(output_path, "w") as f:
        json.dump(result, f, indent=2)

    print(f"  [done] {len(pages_scraped)} pages scraped, status={final_status} → {output_path}")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scrape a competitor website")
    parser.add_argument("--id", required=True, help="Competitor slug ID")
    parser.add_argument("--url", required=True, help="Competitor website URL")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    result = scrape_competitor(
        competitor_id=args.id,
        website_url=args.url,
        output_path=args.output,
    )
    print(f"\nStatus: {result['status']}")
    print(f"Pages scraped: {len(result['pages_scraped'])}")
