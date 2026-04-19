"""
job_scraper.py — Free multi-portal job scraper using requests + BeautifulSoup + Playwright.

No paid API keys required. Portals:
  - remoteok.com       (free JSON API)   — global remote, US/Canada/Europe
  - remotive.com       (free JSON API)   — remote jobs by category
  - weworkremotely.com (RSS feeds)       — remote jobs by category
  - dailyremote.com    (HTML/BS4)        — remote jobs
  - indeed.com         (Playwright)      — US/Canada/India remote + office
  - wellfound.com      (Playwright)      — startup jobs, global remote
  - naukri.com         (HTML/BS4)        — India jobs (remote + office-based)

Playwright is required for Indeed and Wellfound (both are JS-heavy / block simple requests).
Install once: pip install playwright && playwright install chromium

Run:
  python tools/job_scraper.py                  # all portals (includes Indeed + Wellfound)
  python tools/job_scraper.py --reset          # clear registry, start fresh
  python tools/job_scraper.py --days 30        # override 45-day cutoff
  python tools/job_scraper.py --skip-india     # remote portals only (no naukri/indeed-india)
  python tools/job_scraper.py --india-only     # only naukri + indeed india
  python tools/job_scraper.py --no-playwright  # skip Indeed + Wellfound (fast BS4-only run)

Deduplication: checks data/scraped_jobs_registry.json — previously scraped job URLs
are never re-fetched. Run --reset only when you want a completely fresh dataset.

Output: .tmp/jobs_raw_{portal}.json per portal → run excel_exporter.py to export.
"""

import argparse
import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote_plus, urlencode, urljoin

try:
    import requests
    from bs4 import BeautifulSoup
    from dotenv import load_dotenv
except ImportError as e:
    print(f"ERROR: Missing dependency — {e}")
    print("Run: pip install requests beautifulsoup4 lxml python-dotenv")
    sys.exit(1)

ROOT = Path(__file__).parent.parent
SEARCH_ROLES_FILE = ROOT / ".tmp" / "search_roles.json"
REGISTRY_FILE = ROOT / "data" / "scraped_jobs_registry.json"
TMP_DIR = ROOT / ".tmp"

load_dotenv(ROOT / ".env")

DEFAULT_CUTOFF_DAYS = 45

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Referer": "https://google.com/",
}


# ── Date utilities ─────────────────────────────────────────────────────────────

def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def within_cutoff(dt: datetime, days: int) -> bool:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (now_utc() - dt).days <= days


def parse_relative_date(text: str) -> datetime | None:
    """Convert strings like '2 days ago', 'Yesterday', 'a week ago' to datetime."""
    text = text.lower().strip()
    now = now_utc()

    if text in ("today", "just now", "few hours ago", "an hour ago", "1 hour ago"):
        return now
    if text == "yesterday":
        return now - timedelta(days=1)

    m = re.search(r"(\d+)\s*day", text)
    if m:
        return now - timedelta(days=int(m.group(1)))

    if "a week" in text:
        return now - timedelta(weeks=1)
    m = re.search(r"(\d+)\s*week", text)
    if m:
        return now - timedelta(weeks=int(m.group(1)))

    if "a month" in text:
        return now - timedelta(days=30)
    m = re.search(r"(\d+)\s*month", text)
    if m:
        return now - timedelta(days=int(m.group(1)) * 30)

    return None  # unknown → include by default


# ── Text extraction helpers ────────────────────────────────────────────────────

def html_to_text(html: str) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    return soup.get_text(separator="\n", strip=True)


def extract_section(text: str, headings: list[str]) -> str:
    """Pull the first matching section under any of the given heading names."""
    for heading in headings:
        # Markdown-style headings (## Requirements)
        pattern = rf"(?i)#{1,3}\s*{re.escape(heading)}s?[^\n]*\n([\s\S]{{30,600}}?)(?=\n#|\Z)"
        m = re.search(pattern, text)
        if m:
            return m.group(1).strip()[:600]
        # Plain heading followed by colon or newline
        pattern = rf"(?i)\b{re.escape(heading)}s?[:\n]([\s\S]{{30,600}}?)(?=\n[A-Z\n]|\n#|\Z)"
        m = re.search(pattern, text)
        if m:
            return m.group(1).strip()[:600]
    return ""


def extract_requirements(text: str) -> str:
    return extract_section(text, [
        "requirement", "qualification", "what you need", "what we're looking for",
        "who you are", "minimum qualification", "required skill", "you have",
        "you bring", "must have", "about you",
    ])


def extract_skills(text: str) -> str:
    return extract_section(text, [
        "skill", "tech stack", "tool", "technolog", "technical skill",
        "nice to have", "preferred", "bonus point",
    ])


def extract_exp(text: str) -> str:
    patterns = [
        r"(\d+\+?\s*(?:–|-|to)\s*\d+)\s*years?\s*(?:of\s+)?experience",
        r"(\d+\+?)\s*\+?\s*years?\s*(?:of\s+)?experience",
        r"minimum\s+(\d+)\s*years?",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return m.group(1).strip() + " years"
    return ""


# ── Keyword / role matching ────────────────────────────────────────────────────

def build_keyword_index(roles: list[dict]) -> dict:
    """Returns {keyword_lower: [matched_role_name, ...]}."""
    index: dict[str, list[str]] = {}
    for role in roles:
        name = role["role"]
        for kw in [name] + role.get("keywords", []):
            kw_lower = kw.lower()
            index.setdefault(kw_lower, [])
            if name not in index[kw_lower]:
                index[kw_lower].append(name)
    return index


def match_roles(title: str, description: str, keyword_index: dict) -> list[str]:
    """Return sorted list of role names that match this job."""
    text = (title + " " + description[:2000]).lower()
    matched: set[str] = set()
    for kw, role_names in keyword_index.items():
        if re.search(rf"\b{re.escape(kw)}\b", text):
            matched.update(role_names)
    return sorted(matched)


# ── Registry (persistent deduplication) ───────────────────────────────────────

def load_registry() -> dict:
    REGISTRY_FILE.parent.mkdir(parents=True, exist_ok=True)
    if REGISTRY_FILE.exists():
        return json.loads(REGISTRY_FILE.read_text())
    return {"version": 1, "total_scraped": 0, "jobs": {}}


def save_registry(registry: dict):
    REGISTRY_FILE.write_text(json.dumps(registry, indent=2, ensure_ascii=False))


def reset_registry():
    REGISTRY_FILE.write_text(json.dumps({"version": 1, "total_scraped": 0, "jobs": {}}, indent=2))
    print("Registry cleared. Starting fresh.\n")


def is_seen(url: str, registry: dict) -> bool:
    return url in registry["jobs"]


def register_job(url: str, portal: str, title: str, run_id: str, registry: dict):
    if url not in registry["jobs"]:
        registry["jobs"][url] = {
            "scraped_at": datetime.now().isoformat(timespec="seconds"),
            "run_id": run_id,
            "portal": portal,
            "title": title,
        }
        registry["total_scraped"] += 1


# ── Job dict builder ───────────────────────────────────────────────────────────

def make_job(title, company, location, remote, description, url, portal, posted_at, matched_roles):
    if not isinstance(description, str):
        description = ""
    desc_clean = re.sub(r"\n{3,}", "\n\n", description).strip()
    return {
        "title": (title or "").strip(),
        "company": (company or "").strip(),
        "location": (location or "").strip(),
        "remote": bool(remote),
        "description": desc_clean[:2500],
        "requirements": extract_requirements(desc_clean),
        "skills": extract_skills(desc_clean),
        "exp_required": extract_exp(desc_clean),
        "url": (url or "").strip(),
        "portal": portal,
        "posted_at": posted_at or "",
        "scraped_at": datetime.now().isoformat(timespec="seconds"),
        "matched_roles": matched_roles,
    }


# ── HTTP fetch helper ──────────────────────────────────────────────────────────

def fetch(url: str, session: requests.Session, timeout: int = 20, as_json: bool = False):
    try:
        resp = session.get(url, timeout=timeout)
        if resp.status_code in (403, 429):
            print(f"  [warn] HTTP {resp.status_code} — {url[:70]}")
            return None
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding
        return resp.json() if as_json else resp.text
    except Exception as e:
        print(f"  [warn] Fetch failed {url[:65]}: {e}")
        return None


# ── Scraper: remoteok.com ──────────────────────────────────────────────────────

def scrape_remoteok(session, keyword_index, registry, run_id, cutoff_days) -> list[dict]:
    print("\n── remoteok.com (JSON API) ────────────────────────────────")

    data = fetch("https://remoteok.com/api", session, timeout=25, as_json=True)
    if not data:
        print("  [skip] Could not reach remoteok API")
        return []

    jobs, skipped_old, skipped_seen, skipped_nomatch = [], 0, 0, 0

    for item in data:
        if not isinstance(item, dict) or not item.get("position"):
            continue

        url = item.get("url") or f"https://remoteok.com/remote-jobs/{item.get('id', '')}"
        if is_seen(url, registry):
            skipped_seen += 1
            continue

        # Date filter
        epoch = item.get("epoch") or item.get("date")
        posted_at = ""
        if epoch:
            posted_dt = datetime.fromtimestamp(int(epoch), tz=timezone.utc)
            if not within_cutoff(posted_dt, cutoff_days):
                skipped_old += 1
                continue
            posted_at = posted_dt.isoformat()

        title = item.get("position", "")
        company = item.get("company", "")
        location = item.get("location") or "Worldwide"
        description = html_to_text(item.get("description", ""))
        tags_text = " ".join(item.get("tags", []))

        matched = match_roles(title, description + " " + tags_text, keyword_index)
        if not matched:
            skipped_nomatch += 1
            continue

        jobs.append(make_job(title, company, location, True, description, url, "remoteok", posted_at, matched))
        register_job(url, "remoteok", title, run_id, registry)

    print(f"  New: {len(jobs)} | Seen: {skipped_seen} | Old (>{cutoff_days}d): {skipped_old} | No match: {skipped_nomatch}")
    return jobs


# ── Scraper: remotive.com ──────────────────────────────────────────────────────

def scrape_remotive(session, keyword_index, registry, run_id, cutoff_days) -> list[dict]:
    print("\n── remotive.com (JSON API) ────────────────────────────────")

    categories = ["business", "sales", "marketing", "product", "management-finance"]
    all_items: list[dict] = []
    for cat in categories:
        url = f"https://remotive.com/api/remote-jobs?category={cat}&limit=100"
        data = fetch(url, session, as_json=True)
        if data and "jobs" in data:
            all_items.extend(data["jobs"])
        time.sleep(0.5)

    jobs, skipped_old, skipped_seen, skipped_nomatch = [], 0, 0, 0
    seen_ids: set[int] = set()

    for item in all_items:
        job_id = item.get("id")
        if job_id in seen_ids:
            continue
        seen_ids.add(job_id)

        url = item.get("url", "")
        if not url or is_seen(url, registry):
            skipped_seen += 1
            continue

        # Date filter
        pub_date = item.get("publication_date", "")
        posted_at = ""
        if pub_date:
            try:
                posted_dt = datetime.fromisoformat(pub_date.replace("Z", "+00:00"))
                if not within_cutoff(posted_dt, cutoff_days):
                    skipped_old += 1
                    continue
                posted_at = posted_dt.isoformat()
            except ValueError:
                posted_at = pub_date

        title = item.get("title", "")
        company = item.get("company_name", "")
        location = item.get("candidate_required_location") or "Worldwide"
        description = html_to_text(item.get("description", ""))

        matched = match_roles(title, description, keyword_index)
        if not matched:
            skipped_nomatch += 1
            continue

        jobs.append(make_job(title, company, location, True, description, url, "remotive", posted_at, matched))
        register_job(url, "remotive", title, run_id, registry)

    print(f"  New: {len(jobs)} | Seen: {skipped_seen} | Old (>{cutoff_days}d): {skipped_old} | No match: {skipped_nomatch}")
    return jobs


# ── Scraper: weworkremotely.com ────────────────────────────────────────────────

def scrape_weworkremotely(session, keyword_index, registry, run_id, cutoff_days) -> list[dict]:
    print("\n── weworkremotely.com (RSS) ───────────────────────────────")

    rss_feeds = [
        "https://weworkremotely.com/categories/remote-sales-and-marketing-jobs.rss",
        "https://weworkremotely.com/categories/remote-business-exec-management-jobs.rss",
        "https://weworkremotely.com/categories/remote-operations-jobs.rss",
        "https://weworkremotely.com/categories/remote-product-jobs.rss",
    ]

    jobs, skipped_old, skipped_seen, skipped_nomatch = [], 0, 0, 0

    for feed_url in rss_feeds:
        xml_text = fetch(feed_url, session)
        if not xml_text:
            continue

        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as e:
            print(f"  [warn] RSS parse error on {feed_url}: {e}")
            continue

        for item in root.findall(".//item"):
            title_el = item.find("title")
            link_el = item.find("link")
            desc_el = item.find("description")
            pubdate_el = item.find("pubDate")

            raw_title = title_el.text.strip() if title_el is not None and title_el.text else ""

            # WWR title format: "Company Name: Job Title at Location" or "FEATURED | Company: Title"
            raw_title = re.sub(r"^FEATURED\s*\|\s*", "", raw_title)
            company, title = "", raw_title
            if ":" in raw_title:
                parts = raw_title.split(":", 1)
                company = parts[0].strip()
                title = parts[1].split(" at ")[0].strip() if " at " in parts[1] else parts[1].strip()

            # Link element in RSS is often text after the closing tag; try sibling text
            url = ""
            if link_el is not None:
                url = (link_el.text or "").strip()
                if not url:
                    # Some parsers expose it differently
                    next_sib = link_el.tail
                    if next_sib:
                        url = next_sib.strip()

            if not url or is_seen(url, registry):
                skipped_seen += 1
                continue

            # Date filter
            posted_at = ""
            if pubdate_el is not None and pubdate_el.text:
                try:
                    posted_dt = parsedate_to_datetime(pubdate_el.text)
                    if not within_cutoff(posted_dt, cutoff_days):
                        skipped_old += 1
                        continue
                    posted_at = posted_dt.isoformat()
                except Exception:
                    posted_at = pubdate_el.text or ""

            description = html_to_text(desc_el.text if desc_el is not None and desc_el.text else "")

            matched = match_roles(title, description, keyword_index)
            if not matched:
                skipped_nomatch += 1
                continue

            jobs.append(make_job(title, company, "Remote", True, description, url, "weworkremotely", posted_at, matched))
            register_job(url, "weworkremotely", title, run_id, registry)

        time.sleep(0.5)

    print(f"  New: {len(jobs)} | Seen: {skipped_seen} | Old (>{cutoff_days}d): {skipped_old} | No match: {skipped_nomatch}")
    return jobs


# ── Scraper: dailyremote.com ───────────────────────────────────────────────────

def _build_dailyremote_search_terms(roles: list[dict]) -> list[str]:
    """Expand roles into broad search terms: role names + representative keywords."""
    terms: list[str] = []
    seen: set[str] = set()

    # Category-level broad terms always included
    broad = [
        "Revenue Operations", "Sales Operations", "Marketing Operations",
        "GTM Manager", "Business Operations", "Program Manager",
        "Operations Manager", "Sales Enablement", "Demand Generation",
        "Growth Manager", "Commercial Operations", "Strategy Manager",
        "AI Automation", "Workflow Automation",
    ]
    for t in broad:
        tl = t.lower()
        if tl not in seen:
            seen.add(tl)
            terms.append(t)

    for role in roles:
        for candidate in [role["role"]] + role.get("keywords", []):
            tl = candidate.lower()
            if tl not in seen and len(candidate) > 4:
                seen.add(tl)
                terms.append(candidate)

    return terms


def scrape_dailyremote(session, roles: list[dict], keyword_index, registry, run_id, cutoff_days) -> list[dict]:
    print("\n── dailyremote.com (HTML) ─────────────────────────────────")

    search_terms = _build_dailyremote_search_terms(roles)
    print(f"  Search terms : {len(search_terms)} (role names + keywords + broad categories)")

    jobs, skipped_old, skipped_seen, skipped_nomatch = [], 0, 0, 0

    for term in search_terms:
        for page in range(1, 4):  # 3 pages per search term
            params = {"search": term, "page": page, "experience": "0-3"}
            url = f"https://dailyremote.com/?{urlencode(params)}"

            html = fetch(url, session)
            if not html:
                break

            soup = BeautifulSoup(html, "lxml")
            cards = soup.find_all("div", class_="profile-information")
            if not cards:
                break

            for card in cards:
                title_el = card.find("h2", class_="job-position")
                title_link = title_el.find("a") if title_el else None
                if not title_link:
                    continue

                job_title = title_link.get_text(strip=True)
                job_url = urljoin("https://dailyremote.com", title_link.get("href", ""))
                if not job_url or is_seen(job_url, registry):
                    skipped_seen += 1
                    continue

                # Post date (relative string in last span of div.company-name)
                company_div = card.find("div", class_="company-name")
                post_date_str = ""
                if company_div:
                    spans = [s.get_text(strip=True) for s in company_div.find_all("span")
                             if s.get_text(strip=True) not in ("·", "")]
                    if len(spans) >= 2:
                        post_date_str = spans[-1]

                posted_dt = parse_relative_date(post_date_str)
                if posted_dt and not within_cutoff(posted_dt, cutoff_days):
                    skipped_old += 1
                    continue
                posted_at = posted_dt.isoformat() if posted_dt else ""

                # Location from card-tag with globe emoji
                location = ""
                for tag in card.find_all("span", class_="card-tag"):
                    tag_text = tag.get_text(separator=" ", strip=True)
                    if "🌎" in tag_text:
                        inner = tag.find("span")
                        location = inner.get_text(strip=True) if inner else re.sub(r"[^\w\s,]", "", tag_text).strip()
                        break

                desc_div = card.find("div", class_="ai-responsibilities")
                description = desc_div.get_text(strip=True) if desc_div else ""

                matched = match_roles(job_title, description, keyword_index)
                if not matched:
                    skipped_nomatch += 1
                    continue

                jobs.append(make_job(job_title, "", location, True, description, job_url, "dailyremote", posted_at, matched))
                register_job(job_url, "dailyremote", job_title, run_id, registry)

            time.sleep(1.5)

    print(f"  New: {len(jobs)} | Seen: {skipped_seen} | Old (>{cutoff_days}d): {skipped_old} | No match: {skipped_nomatch}")
    return jobs


# ── Scraper: naukri.com (India) ────────────────────────────────────────────────

def scrape_naukri(session, roles: list[dict], keyword_index, registry, run_id, cutoff_days) -> list[dict]:
    print("\n── naukri.com — India (HTML) ──────────────────────────────")

    jobs, skipped_seen, skipped_nomatch = [], 0, 0

    for role in roles[:5]:  # top 5 roles to stay polite
        role_slug = re.sub(r"[^a-z0-9]+", "-", role["role"].lower()).strip("-")
        url = f"https://www.naukri.com/{role_slug}-jobs-in-india?jobAge={cutoff_days}&experience=0"

        html = fetch(url, session, timeout=25)
        if not html:
            continue

        soup = BeautifulSoup(html, "lxml")

        # Naukri job cards — try multiple CSS patterns (SSR vs CSR varies by page)
        job_cards = (
            soup.find_all("article", class_=re.compile(r"jobTuple|job-tuple", re.I))
            or soup.find_all("div", class_=re.compile(r"jobTuple|srp-jobtuple", re.I))
            or soup.find_all(attrs={"data-job-id": True})
        )

        if not job_cards:
            print(f"  [warn] No cards for '{role['role']}' — naukri may be JS-rendered on this query")
            time.sleep(2)
            continue

        for card in job_cards:
            # Title + URL
            title_el = card.find(["a", "h2", "h3"], class_=re.compile(r"title|jobTitle|job-title", re.I))
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            job_url = title_el.get("href", "")
            if job_url and not job_url.startswith("http"):
                job_url = urljoin("https://www.naukri.com", job_url)
            if not job_url or is_seen(job_url, registry):
                skipped_seen += 1
                continue

            company_el = card.find(class_=re.compile(r"company|companyName", re.I))
            company = company_el.get_text(strip=True) if company_el else ""

            loc_el = card.find(class_=re.compile(r"location|loc-wrapper", re.I))
            location = loc_el.get_text(strip=True) if loc_el else "India"
            if not location:
                location = "India"

            exp_el = card.find(class_=re.compile(r"experience|exp-wrapper|expwdth", re.I))
            exp_text = exp_el.get_text(strip=True) if exp_el else ""

            desc_el = card.find(class_=re.compile(r"jobDescription|job-desc|job_desc", re.I))
            description = (desc_el.get_text(strip=True) if desc_el else "")
            if exp_text:
                description = exp_text + "\n" + description

            matched = match_roles(title, description, keyword_index)
            if not matched:
                skipped_nomatch += 1
                continue

            is_remote = "remote" in (location + " " + description).lower()
            jobs.append(make_job(title, company, location, is_remote, description, job_url, "naukri", "", matched))
            register_job(job_url, "naukri", title, run_id, registry)

        time.sleep(2.0)

    print(f"  New: {len(jobs)} | Seen: {skipped_seen} | No match: {skipped_nomatch}")
    if not jobs:
        print("  [note] Naukri is JS-heavy — 0 results is common. Visit naukri.com directly for India listings.")
    return jobs


# ── jobspy availability check ──────────────────────────────────────────────────

def _jobspy_available() -> bool:
    try:
        from jobspy import scrape_jobs  # noqa: F401
        return True
    except ImportError:
        return False


def _jobspy_df_to_jobs(df, portal: str, keyword_index: dict, registry: dict, run_id: str, cutoff_days: int) -> tuple[list[dict], int, int]:
    """Convert a jobspy DataFrame into our job dict format."""
    import pandas as pd
    jobs, skipped_seen, skipped_nomatch = [], 0, 0
    cutoff_dt = now_utc() - timedelta(days=cutoff_days)

    for _, row in df.iterrows():
        job_url = str(row.get("job_url") or "").strip()
        if not job_url or is_seen(job_url, registry):
            skipped_seen += 1
            continue

        # Date filter
        date_posted = row.get("date_posted")
        posted_at = ""
        if date_posted is not None and not (isinstance(date_posted, float) and pd.isna(date_posted)):
            try:
                if hasattr(date_posted, "isoformat"):
                    posted_dt = date_posted
                else:
                    from datetime import date as date_type
                    posted_dt = datetime.combine(date_posted, datetime.min.time()).replace(tzinfo=timezone.utc) if isinstance(date_posted, date_type) else datetime.fromisoformat(str(date_posted))
                if hasattr(posted_dt, "tzinfo") and posted_dt.tzinfo is None:
                    posted_dt = posted_dt.replace(tzinfo=timezone.utc)
                if posted_dt < cutoff_dt:
                    continue
                posted_at = posted_dt.isoformat()[:10]
            except Exception:
                posted_at = str(date_posted)

        title = str(row.get("title") or "").strip()
        if not title:
            continue
        company = str(row.get("company") or "").strip()
        location = str(row.get("location") or "").strip()
        description = html_to_text(str(row.get("description") or ""))
        is_remote_val = bool(row.get("is_remote")) or "remote" in location.lower()

        matched = match_roles(title, description, keyword_index)
        if not matched:
            skipped_nomatch += 1
            continue

        jobs.append(make_job(title, company, location, is_remote_val, description, job_url, portal, posted_at, matched))
        register_job(job_url, portal, title, run_id, registry)

    return jobs, skipped_seen, skipped_nomatch


# ── Scraper: indeed.com (jobspy) ──────────────────────────────────────────────

def scrape_indeed_jobspy(roles: list[dict], keyword_index, registry, run_id, cutoff_days, include_india: bool = True) -> list[dict]:
    """Scrape indeed.com via python-jobspy. Works around Indeed's bot detection."""
    from jobspy import scrape_jobs

    print("\n── indeed.com (jobspy) ────────────────────────────────────")

    all_jobs, total_seen, total_nomatch = [], 0, 0
    hours = cutoff_days * 24

    search_terms = [r["role"] for r in roles]

    configs = [
        ("USA", "indeed"),
        ("Canada", "indeed"),
    ]
    if include_india:
        configs.append(("India", "indeed_india"))

    for role_name in search_terms:
        for country, portal in configs:
            try:
                df = scrape_jobs(
                    site_name=["indeed"],
                    search_term=role_name,
                    location="remote" if country != "India" else "India",
                    results_wanted=30,
                    hours_old=hours,
                    country_indeed=country,
                    verbose=0,
                )
                jobs, seen, nomatch = _jobspy_df_to_jobs(df, portal, keyword_index, registry, run_id, cutoff_days)
                all_jobs.extend(jobs)
                total_seen += seen
                total_nomatch += nomatch
            except Exception as e:
                print(f"  [warn] Indeed jobspy failed for '{role_name}' ({country}): {e}")
            time.sleep(2.0)

    print(f"  New: {len(all_jobs)} | Seen: {total_seen} | No match: {total_nomatch}")
    return all_jobs


# ── Scraper: linkedin.com (jobspy) — replaces wellfound ───────────────────────

def scrape_linkedin_jobspy(roles: list[dict], keyword_index, registry, run_id, cutoff_days) -> list[dict]:
    """Scrape linkedin.com via python-jobspy for global remote jobs."""
    from jobspy import scrape_jobs

    print("\n── linkedin.com (jobspy) ──────────────────────────────────")

    all_jobs, total_seen, total_nomatch = [], 0, 0
    hours = cutoff_days * 24

    for role in roles:
        try:
            df = scrape_jobs(
                site_name=["linkedin"],
                search_term=role["role"],
                location="remote",
                results_wanted=30,
                hours_old=hours,
                verbose=0,
            )
            jobs, seen, nomatch = _jobspy_df_to_jobs(df, "linkedin", keyword_index, registry, run_id, cutoff_days)
            all_jobs.extend(jobs)
            total_seen += seen
            total_nomatch += nomatch
        except Exception as e:
            print(f"  [warn] LinkedIn jobspy failed for '{role['role']}': {e}")
        time.sleep(2.0)

    print(f"  New: {len(all_jobs)} | Seen: {total_seen} | No match: {total_nomatch}")
    return all_jobs


# ── Save per-portal output ─────────────────────────────────────────────────────

def save_portal_file(portal: str, jobs: list[dict]):
    out_path = TMP_DIR / f"jobs_raw_{portal}.json"
    out_path.write_text(json.dumps(jobs, indent=2, ensure_ascii=False))
    return out_path


# ── Main ───────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(
        description="Scrape jobs from free portals using requests + BeautifulSoup + Playwright"
    )
    p.add_argument("--reset", action="store_true", help="Clear the registry before running (fresh start)")
    p.add_argument("--days", type=int, default=DEFAULT_CUTOFF_DAYS, help=f"Only include jobs posted in last N days (default: {DEFAULT_CUTOFF_DAYS})")
    p.add_argument("--skip-india", action="store_true", help="Skip India portals (naukri + indeed-india)")
    p.add_argument("--india-only", action="store_true", help="Only scrape India portals (naukri + indeed-india)")
    p.add_argument("--no-playwright", action="store_true", help="Skip Indeed + Wellfound (fast BS4-only run, no browser needed)")
    return p.parse_args()


def main():
    args = parse_args()

    if not SEARCH_ROLES_FILE.exists():
        print("ERROR: .tmp/search_roles.json not found.")
        print("Run tools/profile_builder.py first to generate search roles from your resume.")
        sys.exit(1)

    roles = json.loads(SEARCH_ROLES_FILE.read_text())
    keyword_index = build_keyword_index(roles)

    use_jobspy = not args.no_playwright
    if use_jobspy and not _jobspy_available():
        print("  [note] python-jobspy not installed — skipping Indeed + LinkedIn.")
        print("         To enable: pip install python-jobspy\n")
        use_jobspy = False

    print("\n" + "=" * 58)
    print("  JOB SCRAPER — Free Edition (no API keys needed)")
    print("=" * 58)
    print(f"  Roles loaded : {len(roles)}")
    print(f"  Cutoff       : last {args.days} days")
    mode = "India only" if args.india_only else "Remote only" if args.skip_india else "All portals"
    print(f"  Mode         : {mode}")
    js_status = "enabled (Indeed + LinkedIn)" if use_jobspy else "disabled (--no-playwright or not installed)"
    print(f"  jobspy       : {js_status}")

    if args.reset:
        reset_registry()

    registry = load_registry()
    print(f"  Registry     : {registry['total_scraped']} jobs seen in previous runs (will be skipped)")
    print("=" * 58 + "\n")

    run_id = f"run_{datetime.now().strftime('%Y%m%d_%H%M')}"
    TMP_DIR.mkdir(parents=True, exist_ok=True)

    portal_results: dict[str, list[dict]] = {}

    with requests.Session() as session:
        session.headers.update(HEADERS)

        if not args.india_only:
            portal_results["remoteok"] = scrape_remoteok(session, keyword_index, registry, run_id, args.days)
            portal_results["remotive"] = scrape_remotive(session, keyword_index, registry, run_id, args.days)
            portal_results["weworkremotely"] = scrape_weworkremotely(session, keyword_index, registry, run_id, args.days)
            portal_results["dailyremote"] = scrape_dailyremote(session, roles, keyword_index, registry, run_id, args.days)

        if not args.skip_india:
            portal_results["naukri"] = scrape_naukri(session, roles, keyword_index, registry, run_id, args.days)

    # jobspy scrapers (Indeed + LinkedIn) — no browser needed, handles bot detection
    if use_jobspy:
        if not args.india_only:
            indeed_jobs = scrape_indeed_jobspy(roles, keyword_index, registry, run_id, args.days, include_india=not args.skip_india)
            portal_results["indeed"] = [j for j in indeed_jobs if j["portal"] == "indeed"]
            if not args.skip_india:
                portal_results["indeed_india"] = [j for j in indeed_jobs if j["portal"] == "indeed_india"]
            portal_results["linkedin"] = scrape_linkedin_jobspy(roles, keyword_index, registry, run_id, args.days)
        else:
            # India-only: scrape indeed india only
            indeed_jobs = scrape_indeed_jobspy(roles, keyword_index, registry, run_id, args.days, include_india=True)
            portal_results["indeed_india"] = [j for j in indeed_jobs if j["portal"] == "indeed_india"]

    # Save per-portal files and update registry
    save_registry(registry)

    total_new = 0
    for portal, jobs in portal_results.items():
        if jobs:
            out_path = save_portal_file(portal, jobs)
            total_new += len(jobs)
        else:
            # Write empty file so exporter doesn't error on missing portal
            save_portal_file(portal, [])

    print("\n" + "=" * 58)
    print("  Scraping complete")
    print(f"  New jobs collected : {total_new}")
    print(f"  Registry total     : {registry['total_scraped']}")
    print(f"  Run ID             : {run_id}")
    print("=" * 58)

    if total_new == 0:
        print("\nNo new jobs found. Tips:")
        print("  • Run with --reset to clear the registry and re-fetch everything")
        print("  • Edit .tmp/search_roles.json to broaden or change role keywords")
        print("  • Try --days 60 to widen the date window")

    # Per-portal summary
    print()
    for portal, jobs in portal_results.items():
        if jobs:
            print(f"  {portal:<18} {len(jobs):>4} new jobs")

    # Auto-run excel exporter
    if total_new > 0:
        print("\n" + "─" * 58)
        print("  Auto-running excel_exporter.py ...")
        print("─" * 58)
        exporter_path = Path(__file__).parent / "excel_exporter.py"
        import subprocess
        result = subprocess.run(
            [sys.executable, str(exporter_path)],
            cwd=str(ROOT),
        )
        if result.returncode != 0:
            print("\n[warn] Excel export failed — run manually: python tools/excel_exporter.py")


if __name__ == "__main__":
    main()
