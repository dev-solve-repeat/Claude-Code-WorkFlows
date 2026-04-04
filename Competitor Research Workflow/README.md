# Competitor Analysis Workflow — Xpatz Global

An on-demand competitive intelligence pipeline that discovers competitors, scrapes their public websites, gathers review sentiment, analyzes everything with Claude AI, and produces a branded PDF report — automatically.

---

## What It Does

1. **Discovers** competitors via DuckDuckGo search + a pre-seeded list of known players
2. **Scrapes** each competitor's homepage and key subpages (services, pricing, visa, about)
3. **Gathers reviews** from Trustpilot and DuckDuckGo search snippets
4. **Analyzes** all data with Claude (`claude-sonnet-4-6`) to extract competitive insights
5. **Generates** a professionally branded PDF report with:
   - Executive Summary
   - Competitor Profiles (services, pricing, messaging, reviews)
   - Positioning Matrix (color-coded comparison table)
   - What Competitors Do Well
   - Gaps & Opportunities for Xpatz Global
   - Strategic Recommendations

---

## Project Structure

```
.
├── config/
│   └── business_profile.json     # Xpatz business info, known competitors, search config
├── assets/
│   └── xpatz_logo.png            # Company logo — used on every PDF page
├── tools/
│   ├── discover_competitors.py   # Step 1: Find competitors via DuckDuckGo
│   ├── scrape_competitor.py      # Step 2: Scrape each competitor website
│   ├── search_reviews.py         # Step 3: Gather review sentiment
│   ├── analyze_competitors.py    # Step 4: Claude AI analysis
│   └── generate_pdf.py           # Step 5: Generate branded PDF
├── workflows/
│   └── competitor_analysis.md    # Full SOP — read this before running
├── .tmp/                         # Intermediate files (auto-generated, safe to delete)
├── .env                          # API keys — never commit this
├── requirements.txt
└── README.md
```

---

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Add your Anthropic API key

Create or edit `.env`:

```
ANTHROPIC_API_KEY=sk-ant-api03-your-key-here
```

> Get your key at [console.anthropic.com](https://console.anthropic.com). The account must have credits loaded — go to **Plans & Billing** to add them.

### 3. Add the company logo

Save the Xpatz Global logo to:

```
assets/xpatz_logo.png
```

The PDF will generate without it if it's missing (a warning is logged), but it's recommended for branding.

---

## Running the Workflow

The full workflow takes **8–15 minutes** end-to-end. Run each step in order, or let Claude Code orchestrate it for you (see below).

### Step 1 — Discover Competitors

```bash
python tools/discover_competitors.py \
  --profile config/business_profile.json \
  --output .tmp/competitors.json
```

### Step 2 — Scrape Competitor Websites

Run once per competitor found in `.tmp/competitors.json`:

```bash
python tools/scrape_competitor.py \
  --id y-axis \
  --url https://www.y-axis.com \
  --output .tmp/scraped_y-axis.json
```

### Step 3 — Gather Reviews

Run once per competitor:

```bash
python tools/search_reviews.py \
  --id y-axis \
  --name "Y-Axis" \
  --domain y-axis.com \
  --output .tmp/reviews_y-axis.json
```

### Step 4 — Run AI Analysis

```bash
python tools/analyze_competitors.py \
  --competitors .tmp/competitors.json \
  --scraped-dir .tmp/ \
  --reviews-dir .tmp/ \
  --profile config/business_profile.json \
  --output .tmp/analysis.json
```

### Step 5 — Generate PDF Report

```bash
python tools/generate_pdf.py \
  --analysis .tmp/analysis.json \
  --profile config/business_profile.json \
  --logo assets/xpatz_logo.png
```

**Output:** `competitor_analysis_YYYY-MM-DD.pdf` in the project root.

---

## Re-running Individual Steps

All intermediate data is saved in `.tmp/`. If a step fails, re-run just that step:

```bash
# Re-run only the AI analysis (keeps all scraped data)
python tools/analyze_competitors.py

# Re-run only the PDF (keeps existing analysis)
python tools/generate_pdf.py

# Re-scrape a single competitor
python tools/scrape_competitor.py --id abhinav --url https://www.abhinav.com
```

---

## Running via Claude Code

Instead of running each step manually, you can instruct Claude Code to orchestrate the full workflow:

> "Run the competitor analysis workflow"

Claude will read `workflows/competitor_analysis.md`, execute each tool in sequence, handle errors, and report back when the PDF is ready.

---

## Known Competitors (Pre-seeded)

These are seeded directly in `config/business_profile.json` and will always be analyzed regardless of DuckDuckGo search results:

| Company | Website |
|---|---|
| Y-Axis | y-axis.com |
| Abhinav Immigration | abhinav.com |
| Visa Avenue | visasavenue.com |
| Xiphias Immigration | xiphias.in |
| Opulence Migration | opulencemigration.com |

To add more, edit the `known_competitors` array in `config/business_profile.json`.

---

## Common Issues

| Problem | Fix |
|---|---|
| `credit balance too low` | Add credits at console.anthropic.com → Plans & Billing |
| DDG returns unrelated results | Expected for niche queries — the known_competitors seed list is the primary source |
| Trustpilot not scraped | Normal — Trustpilot blocks bots. DDG snippets are used as fallback |
| Competitor site blocked (403) | Expected for some sites. Analyzer notes data gaps rather than fabricating |
| JS-heavy site returns sparse data | Status shows `partial_js_rendered` — analyzer handles this gracefully |

For full error handling guidance, see `workflows/competitor_analysis.md`.

---

## Architecture

This workflow follows the **WAT framework** (Workflows, Agents, Tools):

- **Workflows** (`workflows/`) — plain-language SOPs defining what to do, in what order, and how to handle edge cases
- **Agents** — Claude Code reads the workflow and orchestrates execution
- **Tools** (`tools/`) — deterministic Python scripts that do the actual work (search, scrape, analyze, generate)

This separation keeps AI reasoning focused on orchestration while leaving data processing to reliable, testable code.

---

## Output

The final PDF (`competitor_analysis_YYYY-MM-DD.pdf`) includes:

- **Cover page** — Xpatz logo, title, date
- **Executive Summary** — key stats and highlights
- **Competitor Profiles** — one section per competitor with services, pricing, messaging, and review sentiment
- **Positioning Matrix** — color-coded table comparing all competitors across key dimensions
- **What Competitors Do Well** — observations with implications for Xpatz
- **Gaps & Opportunities** — specific market gaps Xpatz can exploit
- **Strategic Recommendations** — prioritized action items (High / Medium / Low)
- **Appendix** — data sources, methodology, disclaimer
