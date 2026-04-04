# Competitor Analysis Workflow

## Objective
Generate a branded PDF competitor intelligence report for Xpatz Global, covering pricing, services, marketing messaging, and customer sentiment for companies competing in the India-to-Europe immigration and work permit space.

## When to Run
On-demand — run whenever a fresh competitive snapshot is needed. All intermediate files in `.tmp/` are regenerated each run.

---

## Inputs Required

| Input | Path | Notes |
|---|---|---|
| Business profile | `config/business_profile.json` | Always present — do not delete |
| Anthropic API key | `.env` → `ANTHROPIC_API_KEY` | Required for Step 4 |
| Company logo | `assets/xpatz_logo.png` | Optional — PDF generates without it if missing |

---

## Pre-Run Checks

Before starting any tool, verify:

1. `config/business_profile.json` exists and is valid JSON
2. `.env` contains a non-empty `ANTHROPIC_API_KEY`
3. `.tmp/` directory exists (create with `mkdir -p .tmp` if not)
4. Python dependencies are installed: `pip install -r requirements.txt`

If `ANTHROPIC_API_KEY` is missing or empty, stop and ask the user to add it to `.env` before proceeding.

---

## Step 1: Discover Competitors

**Tool:** `tools/discover_competitors.py`

```bash
python tools/discover_competitors.py \
  --profile config/business_profile.json \
  --output .tmp/competitors.json
```

**What it does:** Searches DuckDuckGo using industry-specific queries and pre-seeds with Y-Axis (known competitor). Deduplicates results by domain, filters out job boards and news sites, caps at 8 total competitors.

**Expected output:** `.tmp/competitors.json` with 4–8 competitors including Y-Axis.

**Validation:**
- Check `.tmp/competitors.json` is valid JSON
- Check `competitors` array has at least 1 entry
- Y-Axis should always be present

**On failure:**
- If DuckDuckGo is rate-limited: the tool retries automatically (5s sleep). If it fails entirely, it falls back to `known_competitors` from the profile (Y-Axis only).
- If the output has 0 competitors: manually add entries to `.tmp/competitors.json` using known competitors and continue.

**Timing:** Approximately 30–60 seconds (sleeps 2s between queries).

---

## Step 2: Scrape Each Competitor Website

**Tool:** `tools/scrape_competitor.py`

Run once per competitor in `.tmp/competitors.json`:

```bash
python tools/scrape_competitor.py \
  --id {competitor.id} \
  --url {competitor.website} \
  --output .tmp/scraped_{competitor.id}.json
```

**What it does:** Fetches the homepage and up to 5 subpages (`/services`, `/pricing`, `/visa`, `/work-permit`, `/about`). Extracts headings, nav links, pricing mentions, CTA texts, and full-page text (capped at 15,000 chars).

**Expected output:** `.tmp/scraped_{id}.json` per competitor with `status: "success"` or `"partial_js_rendered"`.

**Validation after each scrape:**
- File exists in `.tmp/`
- Check `status` field — warn on `"blocked"` or `"failed"` but continue
- JS-heavy sites (SPAs) will return `"partial_js_rendered"` — this is expected and handled gracefully by the analyzer

**Timing:** Sleep 3 seconds between competitor scrapes to avoid IP-level rate limiting. Approximately 1–3 minutes total.

**On partial failure:** If more than 50% of competitors have status `"failed"`, warn the user. Proceeding is still worthwhile — the analyzer will note data gaps.

---

## Step 3: Gather Reviews for Each Competitor

**Tool:** `tools/search_reviews.py`

Run once per competitor:

```bash
python tools/search_reviews.py \
  --id {competitor.id} \
  --name "{competitor.name}" \
  --domain {competitor.root_domain} \
  --output .tmp/reviews_{competitor.id}.json
```

**What it does:** Runs 4 targeted DuckDuckGo queries to find review snippets and Trustpilot pages. Attempts a direct Trustpilot scrape for star ratings and sample reviews. Categorizes snippets as positive/negative.

**Expected output:** `.tmp/reviews_{id}.json` per competitor.

**Validation:** Check file exists. A file with `dominant_sentiment: "unknown"` is acceptable — not all competitors have review profiles.

**Timing:** Sleep 2 seconds between competitor runs. Approximately 2–4 minutes total.

**Common issue:** Trustpilot actively blocks scraping. The tool handles this gracefully and falls back to DDG search snippets. `trustpilot.scraped: false` is normal and expected for many competitors.

---

## Step 4: Run AI Analysis

**Tool:** `tools/analyze_competitors.py`

```bash
python tools/analyze_competitors.py \
  --competitors .tmp/competitors.json \
  --scraped-dir .tmp/ \
  --reviews-dir .tmp/ \
  --profile config/business_profile.json \
  --output .tmp/analysis.json
```

**What it does:** Consolidates all scraped data and sends it to Claude (claude-sonnet-4-6). Returns structured JSON covering competitor profiles, positioning matrix, what competitors do well, gaps/opportunities, and strategic recommendations. Processes in batches of 4 if there are many competitors.

**Expected output:** `.tmp/analysis.json` with all required sections populated.

**Validation:** Check that `competitor_profiles`, `positioning_matrix`, `gaps_and_opportunities`, and `recommendations` all exist and are non-empty arrays.

**On failure:**
- `ANTHROPIC_API_KEY` missing or invalid → the tool raises a clear error. Add the key to `.env` and re-run.
- Rate limit → tool uses exponential backoff (2s, 4s, 8s) and retries automatically.
- Malformed JSON from Claude → tool retries with a correction prompt (max 2 retries). If it fails, a raw response is saved to `.tmp/analysis_raw.txt` — report this as a bug.

**Timing:** 2–5 minutes depending on number of competitors and Claude response time.

---

## Step 5: Generate PDF Report

**Tool:** `tools/generate_pdf.py`

```bash
python tools/generate_pdf.py \
  --analysis .tmp/analysis.json \
  --profile config/business_profile.json \
  --logo assets/xpatz_logo.png
```

**What it does:** Generates a professionally formatted, branded PDF report with:
- Cover page (dark background, Xpatz logo, title, date)
- Executive Summary
- Competitor Profiles (one per competitor — services, pricing, messaging, reviews)
- Positioning Matrix (color-coded comparison table)
- What Competitors Do Well
- Gaps & Opportunities for Xpatz Global
- Strategic Recommendations
- Methodology & Disclaimer appendix

Page footer on all pages: Xpatz logo (left) | Page number (center) | Date (right).

**Expected output:** `competitor_analysis_YYYY-MM-DD.pdf` at the project root.

**Validation:** Check that the file exists and is at least 50KB. Open it and verify the cover page shows the logo and title correctly.

**On logo missing:** The tool logs a warning and continues. The PDF will be generated without the logo.

---

## Step 6: Confirm Completion

After the PDF is generated:

1. Report the full path to the user: `competitor_analysis_YYYY-MM-DD.pdf`
2. State how many competitors were analyzed
3. Note any warnings from earlier steps (e.g., blocked sites, Trustpilot unavailable)
4. Ask the user to open the PDF and provide feedback
5. Update this workflow with any new lessons learned (rate limits, unexpected behavior, better search queries, etc.)

---

## Error Handling Matrix

| Error | Step | Automatic Action | Manual Action if Needed |
|---|---|---|---|
| DDG rate limit | 1, 3 | Sleep 5s, retry once | Wait a few minutes and re-run |
| DDG total failure | 1 | Fall back to known_competitors | Manually edit `.tmp/competitors.json` |
| Competitor site blocked (403) | 2 | Try alternate User-Agent, mark `blocked` | Accept sparse data; continue |
| Competitor site JS-only | 2 | Mark `partial_js_rendered` | Accept; analyzer will note gap |
| Trustpilot blocks scraping | 3 | Fall back to DDG snippets | Normal behavior — no action needed |
| No reviews found | 3 | Mark `dominant_sentiment: unknown` | Continue; no action needed |
| `ANTHROPIC_API_KEY` missing | 4 | Raise clear error | Add key to `.env`, re-run Step 4 |
| Claude rate limit | 4 | Exponential backoff, retry 3x | If all fail, wait 60s and re-run |
| Claude malformed JSON | 4 | Retry with correction prompt 2x | Check `.tmp/analysis_raw.txt` |
| Logo file missing | 5 | Log warning, skip logo | Save logo to `assets/xpatz_logo.png` |
| PDF output dir missing | 5 | Create dir automatically | No action needed |

---

## Notes & Lessons Learned

- **DuckDuckGo rate limits:** `duckduckgo-search` requires sleeps between calls. The tools use 2s between DDG queries and 5s on retry. If you hit persistent blocks, wait 10 minutes before re-running.
- **DDG package rename:** `duckduckgo_search` has been renamed to `ddgs`. The warning is harmless — the old package still works — but migrate to `ddgs` when convenient.
- **DDG search returns off-topic results for niche queries:** When searching for "blue collar work permit" India/Europe, DDG matched unrelated sites (Chinese Q&A, Thai forums) due to the word "blue". Use generic immigration-focused queries without "blue collar". The `business_profile.json` `known_competitors` list is the primary source of competitors for this niche market — DDG search is supplementary only.
- **JS-heavy competitor sites:** Many modern immigration consultancy websites use React/Next.js. The scraper will return sparse data for these. The analyzer handles this gracefully by noting data gaps rather than fabricating information.
- **Trustpilot scraping:** Trustpilot actively blocks automated requests. Expect `trustpilot.scraped: false` for most competitors. DuckDuckGo snippets still provide useful sentiment signals.
- **Claude analysis quality:** The analyzer is instructed to flag data gaps rather than speculate. If a competitor's data was blocked or sparse, the report will say "Data not available" rather than hallucinating details.
- **Anthropic API credits:** The `ANTHROPIC_API_KEY` must have credits loaded. A 400 error with "credit balance too low" means the account needs topping up at console.anthropic.com → Plans & Billing. All scraped data is preserved in `.tmp/` so only Steps 4 and 5 need to be re-run after adding credits.
- **Inline analysis fallback (no API credits):** If the Anthropic API account has no credits, Claude Code can perform Step 4 inline — reading all `.tmp/scraped_*.json` and `.tmp/reviews_*.json` files directly in the session and writing `.tmp/analysis.json` manually. This uses the Claude Code subscription (no extra cost) instead of the API. Tell the agent "do the analysis yourself" and it will do this.
- **generate_pdf.py review_score bug:** The `build_positioning_matrix()` function assumed `review_score` was always a float. When the analysis JSON contains string values like `"N/A"` or `null`, it raises `ValueError: Unknown format code 'f' for object of type 'str'`. Fixed by wrapping in `try/except` with `float()` coercion. Already patched in the current codebase.
- **Total run time:** Approximately 8–15 minutes end-to-end depending on network speed and number of competitors.

---

## Re-running Individual Steps

Each tool writes to `.tmp/` and reads from there. If a step fails, you can re-run just that step without redoing earlier steps:

```bash
# Re-run just the analysis (keep existing scraped data)
python tools/analyze_competitors.py

# Re-run just the PDF (keep existing analysis)
python tools/generate_pdf.py

# Re-run scraping for one specific competitor
python tools/scrape_competitor.py --id abhinav --url https://www.abhinav.com
```

---

## Workflow Version History

| Version | Date | Notes |
|---|---|---|
| v1.0 | 2026-04-04 | Initial release |
| v1.1 | 2026-04-04 | Fixed review_score type bug in generate_pdf.py; added inline analysis fallback; expanded known_competitors to 5; fixed DDG search queries |
