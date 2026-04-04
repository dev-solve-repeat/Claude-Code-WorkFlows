"""
Tool: analyze_competitors.py
Purpose: Use Claude API to generate structured competitive analysis from all scraped data.
Output: .tmp/analysis.json
"""

import json
import os
import re
import time
import argparse
import glob
from datetime import datetime, timezone
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv()

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 8000
CHARS_PER_COMPETITOR = 8000


def load_json(path: str) -> dict | None:
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return None


def build_competitor_payload(competitor: dict, scraped: dict | None, reviews: dict | None) -> str:
    """Build a text payload for one competitor, capped at CHARS_PER_COMPETITOR chars."""
    lines = []
    lines.append(f"## Competitor: {competitor['name']}")
    lines.append(f"Website: {competitor['website']}")
    lines.append(f"Discovery: {competitor.get('snippet', '')[:200]}")
    lines.append("")

    if scraped and scraped.get("status") not in ("failed", "timeout", "connection_error"):
        hp = scraped.get("homepage", {})
        lines.append(f"Page Title: {hp.get('title', 'N/A')}")
        lines.append(f"Meta Description: {hp.get('meta_description', 'N/A')}")

        h1 = hp.get("h1_tags", [])
        if h1:
            lines.append(f"H1: {' | '.join(h1[:3])}")

        h2 = hp.get("h2_tags", [])
        if h2:
            lines.append(f"H2 headings: {' | '.join(h2[:6])}")

        nav = hp.get("nav_links", [])
        if nav:
            lines.append(f"Navigation: {', '.join(nav[:10])}")

        pricing = hp.get("pricing_mentions", [])
        if pricing:
            lines.append(f"Pricing mentions: {' | '.join(pricing[:5])}")

        cta = hp.get("cta_texts", [])
        if cta:
            lines.append(f"CTAs: {', '.join(cta[:5])}")

        # Subpages
        for sub in scraped.get("subpages", [])[:3]:
            lines.append(f"\n[Subpage: {sub.get('url', '')}]")
            headings = sub.get("headings", [])
            if headings:
                lines.append(f"  Headings: {' | '.join(headings[:4])}")
            pricing_sub = sub.get("pricing_mentions", [])
            if pricing_sub:
                lines.append(f"  Pricing: {' | '.join(pricing_sub[:3])}")

        # Raw text excerpt
        raw = scraped.get("raw_text_combined", "")
        if raw:
            lines.append(f"\nContent excerpt:\n{raw[:2000]}")
    else:
        lines.append("Website data: Could not be scraped (blocked or unavailable)")

    lines.append("")

    # Reviews
    if reviews:
        tp = reviews.get("trustpilot", {})
        if tp.get("average_rating"):
            lines.append(f"Trustpilot rating: {tp['average_rating']}/5 ({tp.get('review_count', 'unknown')} reviews)")
        sentiment = reviews.get("sentiment_summary", {})
        if sentiment:
            lines.append(f"Overall sentiment: {sentiment.get('dominant_sentiment', 'unknown')}")
            lines.append(f"Positive signals: {', '.join(sentiment.get('common_praises', []))}")
            lines.append(f"Negative signals: {', '.join(sentiment.get('common_complaints', []))}")

        for r in tp.get("sample_reviews", [])[:3]:
            lines.append(f"Review ({r.get('rating', '?')}/5): \"{r.get('text', '')[:200]}\"")

        for s in reviews.get("search_snippets", [])[:4]:
            lines.append(f"[{s.get('sentiment', 'neutral')}] {s.get('text', '')[:200]}")
    else:
        lines.append("Reviews: No review data available")

    payload = "\n".join(lines)
    return payload[:CHARS_PER_COMPETITOR]


ANALYSIS_SCHEMA = """{
  "analyzed_at": "ISO timestamp",
  "client": "Xpatz Global",
  "competitors_analyzed": 0,
  "competitor_profiles": [
    {
      "id": "slug",
      "name": "Company Name",
      "website": "URL",
      "services": ["service1", "service2"],
      "pricing_tier": "budget|mid-range|premium|unknown",
      "pricing_detail": "Any specific pricing info found",
      "key_messaging": "Their main value proposition or tagline",
      "target_audience": "Who they target",
      "digital_presence": "weak|moderate|strong",
      "europe_specialization": "low|moderate|high",
      "blue_collar_focus": "low|moderate|high",
      "strengths": ["strength1", "strength2"],
      "weaknesses": ["weakness1", "weakness2"],
      "review_sentiment": "positive|negative|mixed|unknown",
      "review_score": 0.0,
      "notable_review_themes": ["theme1", "theme2"]
    }
  ],
  "positioning_matrix": [
    {
      "competitor": "Name",
      "service_breadth": "low|moderate|high",
      "pricing": "budget|mid-range|premium|unknown",
      "digital_presence": "weak|moderate|strong",
      "review_score": 0.0,
      "europe_specialization": "low|moderate|high",
      "blue_collar_focus": "low|moderate|high",
      "india_market_presence": "low|moderate|high|very high"
    }
  ],
  "what_competitors_do_well": [
    {
      "observation": "What they do well",
      "competitors": ["Competitor A"],
      "implication_for_xpatz": "What Xpatz can learn or counter"
    }
  ],
  "gaps_and_opportunities": [
    {
      "gap": "What is missing in the market",
      "evidence": "Specific evidence from the data",
      "opportunity": "How Xpatz can exploit this"
    }
  ],
  "recommendations": [
    {
      "priority": "high|medium|low",
      "recommendation": "Specific action",
      "rationale": "Why this matters",
      "effort": "low|medium|high"
    }
  ]
}"""

SYSTEM_PROMPT = """You are a competitive intelligence analyst specializing in the immigration and visa consultancy industry.
Your client is Xpatz Global — a UK-registered company that helps blue-collar workers in India obtain European work permits.
Services: work permit documentation, talent screening, Schengen visit visas, business visas.
Differentiators: UK registered, offices in Dubai and India, fully digital.

Analyze the provided competitor data objectively and return actionable insights.
Be specific — cite evidence from the data rather than making generic statements.
When data is sparse or unavailable, say so explicitly rather than speculating.
Focus on: Pricing & Offers, Product/Services, Marketing & Messaging, Reviews & Sentiment."""


def extract_json_from_response(text: str) -> dict | None:
    # Try tagged extraction first
    match = re.search(r"<analysis>(.*?)</analysis>", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Try to find JSON block
    json_match = re.search(r"\{[\s\S]*\}", text)
    if json_match:
        try:
            return json.loads(json_match.group(0))
        except json.JSONDecodeError:
            pass

    return None


def analyze_batch(client: anthropic.Anthropic, batch_payload: str, profile: dict) -> dict | None:
    company = profile["company"]
    user_prompt = f"""CLIENT PROFILE:
Company: {company['name']}
Description: {company['description']}
Services: {', '.join(profile.get('services', []))}
Target Market: {profile['target_market']['segment']} in {profile['target_market']['geography']} → {profile['target_market']['destination']}
Differentiators: {', '.join(profile.get('differentiators', []))}

COMPETITOR DATA:
{batch_payload}

Analyze each competitor across: Pricing & Offers, Product/Services, Marketing & Messaging, Reviews & Sentiment.
Return your complete analysis as valid JSON between <analysis> and </analysis> tags.
Use exactly this JSON schema:
{ANALYSIS_SCHEMA}

Important:
- Fill all fields. Use "unknown" or empty arrays if data is missing.
- Do not add markdown formatting inside the JSON.
- competitors_analyzed should equal the number of competitor_profiles entries.
"""

    for attempt in range(3):
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
            )
            text = response.content[0].text
            result = extract_json_from_response(text)

            if result:
                return result

            # Retry with correction prompt
            if attempt < 2:
                print(f"  [retry] JSON extraction failed, sending correction prompt (attempt {attempt + 1})")
                correction = client.messages.create(
                    model=MODEL,
                    max_tokens=MAX_TOKENS,
                    system=SYSTEM_PROMPT,
                    messages=[
                        {"role": "user", "content": user_prompt},
                        {"role": "assistant", "content": text},
                        {"role": "user", "content": "Your response did not contain valid JSON between <analysis> and </analysis> tags. Please return ONLY the JSON object wrapped in <analysis>...</analysis> tags, with no other text."},
                    ],
                )
                result = extract_json_from_response(correction.content[0].text)
                if result:
                    return result

        except anthropic.RateLimitError:
            wait = 2 ** (attempt + 1)
            print(f"  [rate limit] Waiting {wait}s...")
            time.sleep(wait)
        except anthropic.APIError as e:
            print(f"  [api error] {e}")
            if attempt < 2:
                time.sleep(4)

    return None


def analyze_competitors(
    competitors_path: str = ".tmp/competitors.json",
    scraped_dir: str = ".tmp/",
    reviews_dir: str = ".tmp/",
    business_profile_path: str = "config/business_profile.json",
    output_path: str = ".tmp/analysis.json",
) -> dict:
    # Check API key
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise EnvironmentError(
            "ANTHROPIC_API_KEY is not set. Add it to your .env file and try again."
        )

    client = anthropic.Anthropic(api_key=api_key)

    # Load inputs
    profile = load_json(business_profile_path)
    if not profile:
        raise FileNotFoundError(f"Business profile not found: {business_profile_path}")

    competitors_data = load_json(competitors_path)
    if not competitors_data:
        raise FileNotFoundError(f"Competitors file not found: {competitors_path}")

    competitors = competitors_data.get("competitors", [])
    print(f"[analyze] Processing {len(competitors)} competitors with Claude {MODEL}")

    # Build payload per competitor
    payloads = []
    for comp in competitors:
        comp_id = comp["id"]
        scraped = load_json(os.path.join(scraped_dir, f"scraped_{comp_id}.json"))
        reviews = load_json(os.path.join(reviews_dir, f"reviews_{comp_id}.json"))
        payload = build_competitor_payload(comp, scraped, reviews)
        payloads.append((comp, payload))

    # Batch if needed (groups of 4 to stay within context)
    BATCH_SIZE = 4
    all_profiles = []
    all_matrix = []
    all_doing_well = []
    all_gaps = []
    all_recommendations = []

    batches = [payloads[i:i + BATCH_SIZE] for i in range(0, len(payloads), BATCH_SIZE)]

    for batch_num, batch in enumerate(batches):
        print(f"  [batch {batch_num + 1}/{len(batches)}] Analyzing {len(batch)} competitors...")
        combined_payload = "\n\n---\n\n".join(p for _, p in batch)

        result = analyze_batch(client, combined_payload, profile)

        if result is None:
            print(f"  [warn] Batch {batch_num + 1} failed — saving raw response for debugging")
            continue

        all_profiles.extend(result.get("competitor_profiles", []))
        all_matrix.extend(result.get("positioning_matrix", []))
        all_doing_well.extend(result.get("what_competitors_do_well", []))
        all_gaps.extend(result.get("gaps_and_opportunities", []))
        all_recommendations.extend(result.get("recommendations", []))

    # If multiple batches, run a synthesis pass
    if len(batches) > 1 and all_gaps:
        print("  [synthesize] Running synthesis pass across all batches...")
        synthesis_prompt = f"""You analyzed {len(competitors)} immigration/visa competitors for Xpatz Global in multiple batches.
Now synthesize the key cross-cutting insights.

Previously identified gaps: {json.dumps(all_gaps[:5])}
Previously identified observations: {json.dumps(all_doing_well[:5])}
Previously identified recommendations: {json.dumps(all_recommendations[:5])}

Return a consolidated JSON between <analysis> and </analysis> with:
- "what_competitors_do_well": top 5 observations (deduplicated, most impactful)
- "gaps_and_opportunities": top 5 gaps (deduplicated, most actionable)
- "recommendations": top 5 recommendations ordered by priority
"""
        try:
            synth_response = client.messages.create(
                model=MODEL,
                max_tokens=4000,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": synthesis_prompt}],
            )
            synth_result = extract_json_from_response(synth_response.content[0].text)
            if synth_result:
                all_doing_well = synth_result.get("what_competitors_do_well", all_doing_well)
                all_gaps = synth_result.get("gaps_and_opportunities", all_gaps)
                all_recommendations = synth_result.get("recommendations", all_recommendations)
        except Exception as e:
            print(f"  [warn] Synthesis pass failed: {e}")

    # Assemble final output
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)

    final_output = {
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
        "client": "Xpatz Global",
        "competitors_analyzed": len(all_profiles),
        "competitor_profiles": all_profiles,
        "positioning_matrix": all_matrix,
        "what_competitors_do_well": all_doing_well[:6],
        "gaps_and_opportunities": all_gaps[:6],
        "recommendations": all_recommendations[:6],
    }

    with open(output_path, "w") as f:
        json.dump(final_output, f, indent=2)

    print(f"\n[done] Analyzed {len(all_profiles)} competitors → {output_path}")
    return final_output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analyze competitors with Claude AI")
    parser.add_argument("--competitors", default=".tmp/competitors.json")
    parser.add_argument("--scraped-dir", default=".tmp/")
    parser.add_argument("--reviews-dir", default=".tmp/")
    parser.add_argument("--profile", default="config/business_profile.json")
    parser.add_argument("--output", default=".tmp/analysis.json")
    args = parser.parse_args()

    result = analyze_competitors(
        competitors_path=args.competitors,
        scraped_dir=args.scraped_dir,
        reviews_dir=args.reviews_dir,
        business_profile_path=args.profile,
        output_path=args.output,
    )
    print(f"Competitors analyzed: {result['competitors_analyzed']}")
