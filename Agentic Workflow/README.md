# Agentic Workflow

A WAT (Workflows, Agents, Tools) framework project for automating research and data collection tasks. Deterministic Python scripts handle execution; Claude handles orchestration and decision-making.

## Structure

```
.
├── tools/                  # Python scripts for deterministic execution
├── workflows/              # Markdown SOPs defining objectives and steps
├── .tmp/                   # Intermediate files (gitignored, regenerated each run)
├── .env                    # API keys and credentials
└── requirements.txt        # Python dependencies
```

---

## Setup

```bash
pip3 install -r requirements.txt
```

---

## Workflows

### Job Scraping

Scrape remote job listings from [dailyremote.com](https://dailyremote.com) and export to Excel.

**Step 1 — Scrape:**
```bash
python3 tools/scrape_jobs.py \
  --search "Inbound Sales" \
  --experience "0-2" \
  --pages 4
```

| Flag | Default | Description |
|---|---|---|
| `--search` | required | Job search keyword |
| `--experience` | `0-2` | Experience filter (`0-2`, `2-5`, `5+`) |
| `--pages` | `4` | Number of pages (~30 listings/page) |
| `--delay` | `1.5` | Seconds between page requests |
| `--output` | `.tmp/jobs_{slug}.json` | Override output path |

Output: `.tmp/jobs_{slug}.json`

**Step 2 — Export to Excel:**
```bash
python3 tools/export_to_excel.py .tmp/jobs_inbound_sales.json
```

Output: `Job Listings - {search} ({date}).xlsx` in the project root.

**Excel columns:** Title · Job Type · Location · Salary · Experience · Category · Role · Post Date · Description · Job URL (clickable links, frozen header, auto-filter)

**Full SOP:** [workflows/job_scraping.md](workflows/job_scraping.md)

---

## Notes

- `FIRECRAWL_API_KEY` is configured in `.env` for JS-heavy sites — the job scraper does not use it (plain HTTP is sufficient for dailyremote.com)
- Company names are not publicly visible on dailyremote.com listing pages
- `.tmp/` files are disposable; re-run the scraper to refresh data
