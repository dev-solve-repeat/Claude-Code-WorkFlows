# Job Scraping Workflow

## Objective
Scrape remote job listings from dailyremote.com for a given search keyword and experience filter, then export them to a formatted Excel file for manual review and outreach.

---

## When to Run
On-demand. Run whenever a fresh snapshot of job listings is needed for a specific search term. All intermediate files in `.tmp/` are regenerated each run.

---

## Inputs Required

| Input | Flag | Required | Default | Example |
|---|---|---|---|---|
| Search keyword | `--search` | Yes | — | `"Inbound Sales"` |
| Experience filter | `--experience` | No | `0-2` | `"2-5"`, `"5+"` |
| Number of pages | `--pages` | No | `4` | `2` (for quick sample) |
| Delay between pages | `--delay` | No | `1.5` | `2.0` (if getting blocked) |
| Output JSON path | `--output` | No | `.tmp/jobs_{slug}.json` | — |

---

## Pre-Run Checks
1. Dependencies installed: `pip3 install -r requirements.txt`
2. No API key required — scraper uses plain HTTP requests, no FireCrawl credits consumed

---

## Step 1: Scrape Job Listings

```bash
cd "/Users/brijeshbabu/Claude Code WorkFlows/Agentic Workflow"

python3 tools/scrape_jobs.py \
  --search "Inbound Sales" \
  --experience "0-2" \
  --pages 4 \
  --delay 1.5
```

**Expected output:** `.tmp/jobs_inbound_sales.json`

**Validate:**
- `total_found` is greater than 0
- `pages_failed` is 0 (if non-zero, some pages were blocked — results are partial)
- No entry in `jobs[]` has a paywalled company name (paywalled listings are skipped automatically)
- All `job_url` values start with `https://dailyremote.com/remote-job/`

**Edge cases:**
- **HTTP 403 on a page**: The scraper logs it and moves on. Increase `--delay` to 2.0–3.0 and retry.
- **0 cards on a page despite 200 status**: The site HTML structure may have changed. Inspect the page manually and update the selector in `parse_page()` in `tools/scrape_jobs.py`.
- **All companies paywalled for a specific listing**: The listing is skipped. This is expected behavior per the workflow design.

---

## Step 2: Export to Excel

```bash
python3 tools/export_to_excel.py .tmp/jobs_inbound_sales.json
```

**Expected output:** `Job Listings - Inbound Sales (YYYY-MM-DD).xlsx` in the project root

**Validate:**
- Row count in Excel matches `total_found` from Step 1's JSON
- Column I (Job URL) links are clickable and open the correct job pages
- Header row is dark blue with white text
- Row 1 remains visible when scrolling (freeze pane)
- Filter dropdowns are present on all column headers

---

## Output Artifacts

| File | Location | Lifespan |
|---|---|---|
| Scraped listings (JSON) | `.tmp/jobs_{slug}.json` | Disposable — regenerated each run |
| **Excel export** | `Job Listings - {search} ({date}).xlsx` (project root) | Keep until reviewed |

---

## Error Handling Matrix

| Situation | Behavior |
|---|---|
| HTTP 403 / 429 on a page | Log warning, skip page, increment `pages_failed` |
| Network timeout | Log warning, skip page |
| 0 cards on a 200-status page | Print structural warning; check if site HTML changed |
| Paywalled company listing | Skip silently with one-line log |
| `openpyxl` not installed | `export_to_excel.py` exits with install instructions |
| Input JSON not found | `export_to_excel.py` exits with clear error message |
| Empty jobs array | Excel created with header row only; warning printed |

---

## Reusing for Other Searches

```bash
# Different search term
python3 tools/scrape_jobs.py --search "Customer Success" --experience "0-2" --pages 3
python3 tools/export_to_excel.py .tmp/jobs_customer_success.json

# Quick 1-page sample to test a new query before scraping all pages
python3 tools/scrape_jobs.py --search "Account Executive" --experience "0-2" --pages 1

# More experienced candidates
python3 tools/scrape_jobs.py --search "Sales Manager" --experience "5+" --pages 2
```

Each run produces an independent JSON and Excel file. Old files are not overwritten unless the search term and date happen to match exactly.

---

## Known Constraints & Lessons Learned

- **Site structure (as of 2026-04-05):** Job cards are `<a href="/remote-job/...">` elements. Fields are extracted from emoji-prefixed text lines: `💵` salary, `⭐` experience, `💼` category, `🌎` location.
- **Paywall detection strings:** `"unlock"`, `"premium"`, `"hidden"`, `"confidential"` (case-insensitive substring match on the company field).
- **Parser:** Uses `lxml` (faster than `html.parser`, better malformed HTML tolerance).
- **Session:** `requests.Session` reuses TCP connections across page fetches and carries cookies automatically for pagination.
- **No FireCrawl:** Plain HTTP scraping is sufficient; FireCrawl API credits are preserved for JS-heavy sites.
- **Rate limiting:** Default 1.5s delay between pages is sufficient. If pages start returning 403, increase to 2.5–3.0s.
