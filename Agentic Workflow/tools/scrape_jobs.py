"""
Tool: scrape_jobs.py
Purpose: Scrape remote job listings from dailyremote.com for a given search query.
         Deduplicates by job URL across pages.
Output: .tmp/jobs_{slug}.json

Usage:
    python tools/scrape_jobs.py --search "Inbound Sales" --experience "0-2" --pages 4
    python tools/scrape_jobs.py --search "Customer Success" --experience "2-5" --pages 3 --delay 2.0

Note: Company names are not publicly visible on dailyremote.com listing pages.
      Fields extracted: title, job_type, location, salary, experience, category,
      role, post_date, description_snippet, job_url
"""

import argparse
import json
import os
import re
import time
from datetime import datetime
from urllib.parse import urlencode, urljoin

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://dailyremote.com"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Referer": "https://dailyremote.com/",
}


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def build_url(page: int, search: str, experience: str) -> str:
    params = {"page": page, "experience": experience, "search": search}
    return f"{BASE_URL}/?{urlencode(params)}"


def fetch_page(url: str, session: requests.Session, timeout: int = 15) -> str | None:
    try:
        response = session.get(url, timeout=timeout, allow_redirects=True)
        if response.status_code in (403, 429):
            print(f"  [warn] HTTP {response.status_code} — blocked on {url}")
            return None
        response.raise_for_status()
        response.encoding = response.apparent_encoding
        return response.text
    except requests.exceptions.RequestException as e:
        print(f"  [warn] Network error fetching {url}: {e}")
        return None


def parse_job_card(card, base_url: str) -> dict:
    """
    Parse a div.profile-information card into a job dict.

    Actual HTML structure (as of 2026-04-05):
      <div class="profile-information">
        <div>
          <h2 class="job-position"><a href="/remote-job/...">Title</a></h2>
          <div class="company-name display-flex">
            <span>Full Time</span><span>·</span><span>Yesterday</span>
          </div>
        </div>
        <div class="job-meta ...">
          <span class="card-tag">🌎 <span>United States</span></span>
          <span><span class="card-tag">💵 $16.5 - $17 per hour</span></span>  (optional)
          <span><span class="card-tag">⭐ 0-2 yrs exp</span></span>
          <span class="job-category"><span class="category-tag ..."><a>💼 Sales</a></span></span>
          <a class="role-tag">Sales Representative</a>  (optional)
        </div>
        <div class="ai-responsibilities">Description text...</div>
      </div>
    """

    # Title and job URL
    title_el = card.find("h2", class_="job-position")
    title_link = title_el.find("a") if title_el else None
    title = title_link.get_text(strip=True) if title_link else ""
    job_url = urljoin(base_url, title_link["href"]) if title_link and title_link.get("href") else ""

    # Job type (Full Time / Part Time / Contract) and post date
    # Both live in div.company-name — first and last non-separator spans
    job_type = ""
    post_date = ""
    company_div = card.find("div", class_="company-name")
    if company_div:
        spans = [s.get_text(strip=True) for s in company_div.find_all("span") if s.get_text(strip=True) not in ("·", "")]
        if spans:
            job_type = spans[0]
        if len(spans) >= 2:
            post_date = spans[-1]

    # Location: span.card-tag that contains 🌎 (has a child <span> with the country)
    location = ""
    for tag in card.find_all("span", class_="card-tag"):
        text = tag.get_text(separator=" ", strip=True)
        if "🌎" in text:
            # Get the inner <span> text if available, otherwise strip emoji
            inner = tag.find("span")
            location = inner.get_text(strip=True) if inner else re.sub(r"[^\w\s,]", "", text).strip()
            break

    # Salary: span.card-tag whose text starts with 💵
    salary = ""
    for tag in card.find_all("span", class_="card-tag"):
        text = tag.get_text(separator=" ", strip=True)
        if "💵" in text:
            salary = re.sub(r"^💵\s*", "", text).strip()
            break

    # Experience: span.card-tag whose text starts with ⭐
    experience = ""
    for tag in card.find_all("span", class_="card-tag"):
        text = tag.get_text(separator=" ", strip=True)
        if "⭐" in text:
            experience = re.sub(r"^⭐\s*", "", text).strip()
            break

    # Category: inside span.job-category > span.category-tag > a, strip emoji
    category = ""
    cat_span = card.find("span", class_="job-category")
    if cat_span:
        cat_link = cat_span.find("a")
        if cat_link:
            category = re.sub(r"^[^\w]+", "", cat_link.get_text(strip=True)).strip()

    # Role sub-category: a.role-tag (optional, strips SVG icon text)
    role = ""
    role_tag = card.find("a", class_="role-tag")
    if role_tag:
        # Remove SVG content by getting only NavigableString children
        role_texts = [t for t in role_tag.strings if t.strip()]
        role = " ".join(role_texts).strip()

    # Description: div.ai-responsibilities
    description = ""
    desc_div = card.find("div", class_="ai-responsibilities")
    if desc_div:
        description = desc_div.get_text(strip=True)[:500]

    return {
        "title": title,
        "job_type": job_type,
        "location": location,
        "salary": salary,
        "experience": experience,
        "category": category,
        "role": role,
        "post_date": post_date,
        "description_snippet": description,
        "job_url": job_url,
    }


def parse_page(html: str) -> list:
    """Return a list of div.profile-information Tag objects from a page's HTML."""
    soup = BeautifulSoup(html, "lxml")
    return soup.find_all("div", class_="profile-information")


def scrape_all_pages(
    search: str, experience: str, pages: int, delay: float, session: requests.Session
) -> tuple[list, int]:
    """Scrape all pages, deduplicate by job_url, return (jobs_list, pages_failed_count)."""
    all_jobs = []
    seen_urls = set()
    pages_failed = 0

    for page_num in range(1, pages + 1):
        url = build_url(page_num, search, experience)
        print(f"[page {page_num}/{pages}] {url}")

        html = fetch_page(url, session)
        if html is None:
            print(f"  [warn] Page {page_num} failed — skipping")
            pages_failed += 1
            if page_num < pages:
                time.sleep(delay)
            continue

        cards = parse_page(html)
        print(f"  Found {len(cards)} cards", end="")

        new_count = 0
        for card in cards:
            job = parse_job_card(card, BASE_URL)
            if not job["job_url"] or job["job_url"] in seen_urls:
                continue
            seen_urls.add(job["job_url"])
            all_jobs.append(job)
            new_count += 1

        dupes = len(cards) - new_count
        if dupes > 0:
            print(f" ({dupes} duplicates skipped)")
        else:
            print()

        if len(cards) == 0:
            print(f"  [warn] 0 cards on page {page_num} — site structure may have changed")

        if page_num < pages:
            time.sleep(delay)

    return all_jobs, pages_failed


def main():
    parser = argparse.ArgumentParser(
        description="Scrape remote job listings from dailyremote.com"
    )
    parser.add_argument("--search", required=True, help='Search keyword, e.g. "Inbound Sales"')
    parser.add_argument("--experience", default="0-2", help="Experience range filter (default: 0-2)")
    parser.add_argument("--pages", type=int, default=4, help="Number of pages to scrape (default: 4)")
    parser.add_argument("--output", default=None, help="Override output JSON path")
    parser.add_argument(
        "--delay", type=float, default=1.5, help="Seconds between page requests (default: 1.5)"
    )
    args = parser.parse_args()

    slug = slugify(args.search)
    output_path = args.output or os.path.join(".tmp", f"jobs_{slug}.json")

    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".tmp", exist_ok=True)

    print(f"\nScraping dailyremote.com")
    print(f"  Search:     {args.search}")
    print(f"  Experience: {args.experience}")
    print(f"  Pages:      {args.pages}")
    print(f"  Delay:      {args.delay}s\n")

    with requests.Session() as session:
        session.headers.update(HEADERS)
        jobs, pages_failed = scrape_all_pages(
            args.search, args.experience, args.pages, args.delay, session
        )

    result = {
        "search": args.search,
        "experience": args.experience,
        "slug": slug,
        "timestamp": datetime.now().isoformat(),
        "pages_scraped": args.pages,
        "pages_failed": pages_failed,
        "total_found": len(jobs),
        "jobs": jobs,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"\n--- Summary ---")
    print(f"  Jobs collected: {len(jobs)}")
    print(f"  Pages failed:   {pages_failed}")
    print(f"  Output:         {output_path}")

    if pages_failed > 0:
        print(f"  [warn] {pages_failed} page(s) failed — results may be incomplete")


if __name__ == "__main__":
    main()
