# WAT Framework

**Workflows · Agents · Tools** — a personal automation framework where AI handles reasoning and Python handles execution.

## How It Works

```
workflows/   →   Agent (Claude)   →   tools/
(Instructions)   (Orchestration)   (Execution)
```

- **Workflows** are Markdown SOPs. They define the objective, inputs, tool sequence, edge cases, and expected outputs.
- **The Agent** (Claude) reads the relevant workflow, makes decisions, calls tools in order, and recovers from errors.
- **Tools** are deterministic Python scripts. They handle API calls, data transforms, and file I/O — no guesswork.

This separation keeps AI where it excels (reasoning, synthesis, judgment) and keeps execution reliable (deterministic scripts, testable, consistent).

---

## Workflows

| Workflow | Description |
|---|---|
| [Newsletter Automation](workflows/newsletter_automation.md) | Research a topic → generate content → fetch images → build infographic-rich HTML newsletter |

---

## Tools

| Tool | Purpose |
|---|---|
| `tools/research_topic.py` | Search a topic via Tavily API, extract top sources into structured JSON |
| `tools/generate_newsletter_content.py` | Generate structured newsletter prose via Claude (Anthropic API) |
| `tools/fetch_images.py` | Fetch a license-free hero image from Unsplash with auto-attribution |
| `tools/generate_charts.py` | Build email-safe infographics via QuickChart.io (matplotlib fallback) |
| `tools/score_newsletter.py` | Flesch-Kincaid readability gate + estimated read time |
| `tools/build_newsletter_html.py` | Render Jinja2 template, inline CSS via premailer, open in browser |

---

## Quick Start

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure API keys
Copy `.env` and fill in your keys:
```
TAVILY_API_KEY=        # app.tavily.com — free tier (1,000 searches/month)
ANTHROPIC_API_KEY=     # console.anthropic.com
UNSPLASH_ACCESS_KEY=   # unsplash.com/developers — free, attribution required
```

### 3. Run the newsletter pipeline
```bash
# Step 1 — Research
python tools/research_topic.py "your topic here"

# Step 2 — Generate content
python tools/generate_newsletter_content.py .tmp/research_{slug}.json

# Step 3 — Hero image
python tools/fetch_images.py .tmp/newsletter_content_{slug}.json

# Step 4 — Charts
python tools/generate_charts.py .tmp/newsletter_content_{slug}.json

# Step 5 — Readability check
python tools/score_newsletter.py .tmp/newsletter_content_{slug}.json

# Step 6 — Build & preview
python tools/build_newsletter_html.py .tmp/newsletter_content_{slug}.json
```

The final HTML opens in your browser automatically.

---

## Project Structure

```
.
├── workflows/                  # Markdown SOPs — what to do and how
│   └── newsletter_automation.md
├── tools/                      # Python scripts — deterministic execution
│   ├── research_topic.py
│   ├── generate_newsletter_content.py
│   ├── fetch_images.py
│   ├── generate_charts.py
│   ├── score_newsletter.py
│   ├── build_newsletter_html.py
│   └── templates/
│       └── newsletter.html     # Jinja2 email template
├── .tmp/                       # Intermediate files (gitignored, disposable)
├── requirements.txt
├── .env                        # API keys (gitignored — never commit)
└── CLAUDE.md                   # Agent operating instructions
```

---

## Design Principles

- **Outputs live in the cloud.** Final deliverables go where you can access them (browser, email, Google Sheets). `.tmp/` is disposable.
- **Each tool is a single responsibility.** One input, one output, one job. Easy to test, easy to debug.
- **Workflows evolve.** When you discover a rate limit, a better API, or a smarter sequence — update the workflow. That's how the system gets better over time.
- **AI reasons, code executes.** Never put probabilistic generation inside a deterministic script. Never make Claude do what a 10-line Python function can do reliably.
