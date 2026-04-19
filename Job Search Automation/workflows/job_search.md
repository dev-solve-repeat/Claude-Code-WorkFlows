# Workflow: Job Search (Master SOP)

## Objective
Run the full job search pipeline: parse resume (once) → scrape new jobs → export to Excel.

## Inputs Required
- `input/resume.pdf` — Brijesh's resume PDF
- `.env` — GEMINI_API_KEY filled in (only needed for profile_builder.py — one-time)
- `data/scraped_jobs_registry.json` — auto-managed (created on first run)

## Steps

### Step 1 — Check for resume
Verify `input/resume.pdf` exists. If missing, stop and ask user to drop it in the `input/` folder.

### Step 2 — One-time resume analysis (Gemini)
Check if `skills/resume.md` exists.
- **Exists → SKIP entirely.** Zero API calls.
- **Missing → Run in order:**
  ```
  python tools/resume_parser.py
  python tools/profile_builder.py
  ```
  After running, ask Brijesh to review:
  - `skills/resume.md` — are the government roles translated correctly into corporate language?
  - `.tmp/search_roles.json` — are the job titles specific and accurate? Edit if needed.

### Step 3 — Scrape jobs
```
python tools/job_scraper.py
```

**Portals scraped (all free, no API key):**
| Portal              | Method       | Geography              |
|---------------------|--------------|------------------------|
| remoteok.com        | JSON API     | Global remote          |
| remotive.com        | JSON API     | Global remote          |
| weworkremotely.com  | RSS feeds    | Global remote          |
| dailyremote.com     | HTML/BS4     | Global remote          |
| naukri.com          | HTML/BS4     | India (remote + office)|

**Filter logic:**
- Only jobs posted in the **last 45 days**
- Only jobs matching keywords from `.tmp/search_roles.json` (your 7 target roles)
- Jobs already in `data/scraped_jobs_registry.json` are automatically skipped

**Optional flags:**
```
python tools/job_scraper.py --reset        # clear registry, re-fetch everything
python tools/job_scraper.py --days 60      # widen date window to 60 days
python tools/job_scraper.py --skip-india   # remote portals only
python tools/job_scraper.py --india-only   # only naukri (India jobs)
```

### Step 4 — Export to Excel
```
python tools/excel_exporter.py
```
- Reads all `.tmp/jobs_raw_*.json` files
- Output: `output/job_matches_YYYY-MM-DD.xlsx`
- Columns: Company, Job Role, Matched Roles, Yrs Exp, Description, Requirements, Skills, Location, Remote?, Portal, URL, Posted Date, Date Scraped
- Summary sheet: total jobs, breakdown by portal and by matched role

### Step 5 — Report to user
- How many new jobs found per portal
- How many skipped (already seen)
- Path to Excel file
- Note if naukri returned 0 results (common — JS-heavy site)

## Error Handling
- **resume.pdf not found**: Stop. Ask user to add file.
- **GEMINI_API_KEY missing**: Only needed for profile_builder.py. Scraping and exporting work without it.
- **HTTP 403/429**: Logged as a warning and skipped. Normal for some portals. Retry next run.
- **No new jobs found**: Suggest `--reset` to clear registry, or edit `.tmp/search_roles.json` to broaden keywords.
- **Naukri returns 0**: Expected if naukri is JS-rendering the page. Visit naukri.com directly and search manually.
- **profile_builder.py JSON parse error**: Raw output saved to `.tmp/search_roles.raw.txt` — ask user to fix and save as `.tmp/search_roles.json`.

## API Cost Reminder
- `profile_builder.py` (Gemini): runs ONCE only, never again unless `skills/resume.md` is deleted.
- `job_scraper.py`: ZERO API calls. All free web scraping.
- `excel_exporter.py`: ZERO API calls. Pure local processing.
