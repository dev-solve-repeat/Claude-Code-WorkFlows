"""
Tool: discover_competitors.py
Purpose: Discover competitors for Xpatz Global using DuckDuckGo search.
Output: .tmp/competitors.json
"""

import json
import os
import re
import time
import argparse
from datetime import datetime, timezone
from urllib.parse import urlparse

from duckduckgo_search import DDGS
from dotenv import load_dotenv

load_dotenv()

BLOCKED_DOMAINS = {
    "linkedin.com", "indeed.com", "naukri.com", "glassdoor.com",
    "wikipedia.org", "youtube.com", "facebook.com", "twitter.com",
    "instagram.com", "reddit.com", "quora.com", "medium.com",
    "timesofindia.com", "indiatimes.com", "hindustantimes.com",
    "ndtv.com", "thehindu.com", "livemint.com", "economictimes.com",
    "moneycontrol.com", "business-standard.com", "gov.in", "gov.uk",
    "europa.eu", "ec.europa.eu", "uscis.gov", "ica.gov.sg",
    "justdial.com", "sulekha.com", "yellowpages.co.in",
    "ambitionbox.com", "shine.com", "monster.com", "foundit.in",
    # Content / forum / Q&A sites (not immigration companies)
    "zhihu.com", "pantip.com", "baidu.com", "weibo.com",
    "trustpilot.com", "sitejabber.com", "mouthshut.com",
    "immihelp.com", "trackitt.com", "murthy.com",
    "expatforum.com", "expat.com", "internations.org",
    "quora.com", "answers.com", "wikihow.com",
}


def extract_root_domain(url: str) -> str:
    try:
        parsed = urlparse(url)
        netloc = parsed.netloc.lower()
        # Strip www. prefix
        if netloc.startswith("www."):
            netloc = netloc[4:]
        return netloc
    except Exception:
        return ""


def is_blocked(domain: str) -> bool:
    if not domain:
        return True
    for blocked in BLOCKED_DOMAINS:
        if domain == blocked or domain.endswith("." + blocked):
            return True
    # Filter government and news TLDs
    if re.search(r"\.(gov|gov\.\w{2}|edu|mil)$", domain):
        return True
    return False


def slugify(name: str) -> str:
    slug = name.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug


def discover_competitors(
    business_profile_path: str = "config/business_profile.json",
    output_path: str = ".tmp/competitors.json",
    max_results: int = None,
) -> dict:
    # Load profile
    with open(business_profile_path, "r") as f:
        profile = json.load(f)

    config = profile["analysis_config"]
    search_queries = config["search_queries"]
    max_competitors = max_results or config.get("max_competitors", 8)
    client_domain = extract_root_domain(profile["company"].get("website", ""))

    # Pre-seed with known competitors
    seen_domains = set()
    competitors = []

    for kc in profile.get("known_competitors", []):
        domain = extract_root_domain(kc["website"])
        if domain and domain not in seen_domains:
            seen_domains.add(domain)
            competitors.append({
                "id": kc.get("id", slugify(kc["name"])),
                "name": kc["name"],
                "website": kc["website"],
                "root_domain": domain,
                "discovery_source": "known_competitor",
                "snippet": kc.get("notes", ""),
            })
            print(f"[seed] {kc['name']} ({domain})")

    # Add client domain to exclusion set
    if client_domain:
        seen_domains.add(client_domain)

    # DuckDuckGo search
    queries_used = []
    fallback_only = False

    for query in search_queries:
        if len(competitors) >= max_competitors:
            break

        print(f"[search] {query}")
        queries_used.append(query)

        results = []
        for attempt in range(2):
            try:
                with DDGS() as ddgs:
                    results = list(ddgs.text(query, max_results=10))
                break
            except Exception as e:
                if attempt == 0:
                    print(f"  [retry] DDG error: {e} — sleeping 5s")
                    time.sleep(5)
                else:
                    print(f"  [fail] DDG unavailable for query: {e}")
                    fallback_only = True

        for result in results:
            if len(competitors) >= max_competitors:
                break

            url = result.get("href", "")
            title = result.get("title", "").strip()
            snippet = result.get("body", "").strip()

            domain = extract_root_domain(url)
            if not domain:
                continue
            if domain in seen_domains:
                continue
            if is_blocked(domain):
                continue

            seen_domains.add(domain)
            comp_id = slugify(title or domain)
            competitors.append({
                "id": comp_id,
                "name": title,
                "website": url,
                "root_domain": domain,
                "discovery_source": query,
                "snippet": snippet[:300],
            })
            print(f"  [found] {title} ({domain})")

        # Rate-limit courtesy sleep between queries
        time.sleep(2)

    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)

    output = {
        "discovered_at": datetime.now(timezone.utc).isoformat(),
        "source_queries": queries_used,
        "fallback_only": fallback_only,
        "competitors": competitors,
        "total_found": len(competitors),
    }

    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\n[done] Found {len(competitors)} competitors → {output_path}")
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Discover competitors via DuckDuckGo")
    parser.add_argument("--profile", default="config/business_profile.json")
    parser.add_argument("--output", default=".tmp/competitors.json")
    parser.add_argument("--max", type=int, default=None)
    args = parser.parse_args()

    result = discover_competitors(
        business_profile_path=args.profile,
        output_path=args.output,
        max_results=args.max,
    )
    print(json.dumps(result, indent=2))
