# YouTube AI Trend Report

Automated weekly intelligence on what's happening in AI — scraped from 10 top YouTube channels, analyzed for trends, rendered as a dark editorial PDF, and delivered to your inbox.

## What it does

1. **Fetches** the last 14 days of videos from 10 AI/tech channels using `yt-dlp` (no API key needed)
2. **Analyzes** titles and descriptions for topic categories, tool mentions, and engagement scores
3. **Renders** a Signal Noir–styled PDF report with arc visualizations, channel activity bars, and top video callouts
4. **Emails** the PDF to a recipient via Gmail SMTP

## Channels tracked

Matt Wolfe · Andrej Karpathy · Two Minute Papers · Fireship · AI Explained · The AI Advantage · Wes Roth · AI Jason · David Shapiro · Lex Fridman

## Setup

**1. Install dependencies**
```bash
pip install -r requirements.txt
pip install reportlab pillow  # for PDF rendering
```

**2. Create a `.env` file**
```env
GMAIL_SENDER=you@gmail.com
GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
REPORT_RECIPIENT=recipient@example.com
```

To get a Gmail App Password: Google Account → Security → 2-Step Verification → App passwords → create one named "YouTube Report".

**3. Run the full pipeline**
```bash
python3 tools/fetch_youtube_data.py && \
python3 tools/analyze_trends.py && \
python3 tools/send_email.py
```

## Tools

| Script | Input | Output |
|--------|-------|--------|
| `tools/fetch_youtube_data.py` | `config/channels.json` | `.tmp/youtube_raw_YYYY-MM-DD.json` |
| `tools/analyze_trends.py` | raw JSON | `.tmp/trends_YYYY-MM-DD.json` |
| `tools/create_report.py` | trends JSON | `.tmp/ai_trend_report_YYYY-MM-DD.pptx` |
| `.tmp/render_pdf.py` | trends JSON | `.tmp/ai_trend_report_YYYY-MM-DD.pdf` |
| `tools/send_email.py` | PDF (or pptx) | email sent |

`send_email.py` auto-detects the latest report (PDF preferred over pptx).

## Customization

- **Date window** — edit `published_after_days` in `config/channels.json` (default: 14)
- **Channels** — add/remove entries in the `channels` array in `config/channels.json`
- **Topic detection** — edit `TOPIC_CATEGORIES` in `tools/analyze_trends.py`
- **Videos per channel** — edit `videos_per_channel` in `config/channels.json` (default: 10)

## File structure

```
tools/                  Python scripts for each pipeline step
workflows/              Markdown SOPs describing how to run and extend the system
config/channels.json    Channel list and fetch settings
.tmp/                   Generated outputs (disposable, regenerated each run)
.env                    Credentials (never committed)
```

## Design

Reports use the **Signal Noir** aesthetic — dark obsidian background, electric indigo and cold cyan accents, arc-based topic visualizations, and sparse clinical typography. The design is built with `matplotlib` using system fonts (Baskerville, Futura, Avenir Next, Menlo).
