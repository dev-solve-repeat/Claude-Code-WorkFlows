# Newsletter Automation Workflow

## Objective
Produce a beautiful, research-backed, infographic-rich HTML newsletter from a topic prompt. The output is a browser-ready HTML file in `.tmp/` that can be reviewed, revised, and eventually sent.

---

## Required Inputs

| Input | Required | Default | Notes |
|---|---|---|---|
| `topic` | Yes | — | The newsletter subject (e.g., "The future of nuclear energy") |
| `audience` | No | "general professionals" | Shapes tone and vocabulary level |
| `length` | No | `standard` | `short` (~500w), `standard` (~800w), `deep-dive` (~1200w) |

---

## Step-by-Step Execution

### Step 1: Topic Brief (No API Cost)
Before running any tools, generate a one-paragraph interpretation of the topic:
- What angle you plan to cover
- What audience you assume
- What 3-4 sub-questions you will research
- What chart types you anticipate

**Present this to the user for confirmation before proceeding.** This prevents spending Tavily credits on the wrong interpretation.

---

### Step 2: Research
```bash
python tools/research_topic.py "<topic>" [--max-results 8]
```
- Output: `.tmp/research_{slug}.json`
- Schema: `{topic, slug, timestamp, sources: [{title, url, content, date, relevance_score}]}`
- Tavily fetches full page content; sources are ranked by relevance

**Edge cases:**
- Paywalled sources return partial content (first few paragraphs). This is expected — use what is available and note the limitation in the newsletter.
- Free tier limit: 1,000 searches/month. Each run uses 1 search credit. Check usage at app.tavily.com.
- If `TAVILY_API_KEY` is missing, the script exits with a clear error.

---

### Step 3: Generate Newsletter Content
```bash
python tools/generate_newsletter_content.py .tmp/research_{slug}.json [--audience "..."] [--length standard]
```
- Output: `.tmp/newsletter_content_{slug}.json`
- Schema: `{headline, preview_text, introduction, sections: [{title, body, key_stat, chart_suggestion}], conclusion, cta, keywords, sources}`
- 3-4 sections, each with an optional chart suggestion
- Every `key_stat` cites a specific source

**If content quality is poor:** Re-run with a more specific `--audience` flag or adjust the topic phrasing. The research step does not need to be re-run.

---

### Step 4: Fetch Hero Image
```bash
python tools/fetch_images.py .tmp/newsletter_content_{slug}.json
```
- Queries Unsplash using the newsletter's keyword tags
- Updates the content JSON in place with `hero_image` and `image_attribution_html`
- **Attribution is required by Unsplash terms** — it is embedded automatically in the newsletter footer

**Edge cases:**
- If `UNSPLASH_ACCESS_KEY` is missing, the script warns and skips (newsletter renders without hero image)
- Unsplash free tier: 50 requests/hour

---

### Step 5: Generate Charts
```bash
python tools/generate_charts.py .tmp/newsletter_content_{slug}.json
```
- Output: `.tmp/charts_{slug}.json` (URL manifest) + `.tmp/charts_{slug}_full.json` (includes base64 data)
- Primary: QuickChart.io URLs (free, no key, email-safe `<img>` tags)
- Fallback: Matplotlib → base64 PNG if QuickChart URL exceeds 2,000 characters

**How QuickChart works:** Chart config is JSON-encoded into a URL. The QuickChart server renders it as a PNG at request time. No API key needed. The `<img src="https://quickchart.io/chart?c=...">` tag works in all email clients.

**Verify charts:** Paste any QuickChart URL into a browser to confirm rendering before building HTML.

---

### Step 6: Quality Gate
```bash
python tools/score_newsletter.py .tmp/newsletter_content_{slug}.json
```
- Output: `.tmp/quality_report_{slug}.json`
- Checks: Flesch-Kincaid grade level (target: 8-10), estimated read time, word count

**If grade is too high (>10):** Return to Step 3 and re-generate with a note to simplify. The research JSON can be reused — no Tavily credit spent.

**If grade is too low (<8):** Consider adding more depth or technical context. Usually fine for shorter newsletters.

---

### Step 7: Build HTML
```bash
python tools/build_newsletter_html.py .tmp/newsletter_content_{slug}.json .tmp/charts_{slug}_full.json
```
- Output: `.tmp/newsletter_{YYYY-MM-DD}.html`
- Auto-opens in default browser
- Warns if HTML file size exceeds 90KB (Gmail clips at 102KB)
- All CSS is inlined via `premailer` — safe for email clients

---

### Step 8: Manual Review
Inspect the browser preview. To revise:

| Change needed | Action |
|---|---|
| Layout/design only | Re-run Step 7 only |
| Content tweaks (wording, sections) | Edit `.tmp/newsletter_content_{slug}.json` manually, then re-run Step 7 |
| Different content angle | Re-run Step 3 (reuses research), then Steps 5-7 |
| More/different research | Re-run Step 2 onward (costs 1 Tavily credit) |

---

## Output Artifacts

| File | Location | Lifespan |
|---|---|---|
| Research data | `.tmp/research_{slug}.json` | Disposable — regenerate as needed |
| Newsletter content | `.tmp/newsletter_content_{slug}.json` | Disposable |
| Charts manifest | `.tmp/charts_{slug}.json` | Disposable |
| Charts full data | `.tmp/charts_{slug}_full.json` | Disposable |
| Quality report | `.tmp/quality_report_{slug}.json` | Disposable |
| **Final HTML** | `.tmp/newsletter_{date}.html` | **Keep until sent/archived** |

All `.tmp/` files are gitignored and safe to delete.

---

## Known Constraints

- **Gmail size limit:** Emails over 102KB are clipped. The HTML builder warns at 90KB. If clipped, reduce image usage or shorten content.
- **QuickChart URL limit:** ~2,000 chars practical limit. The tool falls back to matplotlib automatically.
- **Email client JS:** Email clients strip all JavaScript. Never add `<script>` tags to the template.
- **Unsplash attribution:** Required by Terms of Service. Always present in the footer — do not remove.
- **Tavily free tier:** 1,000 searches/month. Monitor usage at app.tavily.com.

---

## Deferred Features (Designed to Add Later)

These are not currently implemented but the system is designed to accommodate them:

- `tools/send_newsletter.py` — Send via Resend API, log to Google Sheets
- `tools/generate_social_posts.py` — LinkedIn, X/Twitter, Instagram derivatives
- Subject line A/B variant generation (add to `generate_newsletter_content.py` prompt)
- Google Sheets send log (add to `send_newsletter.py`)

---

## Learning Log

*Document discoveries, quirks, and improvements here as the system evolves.*

- **2026-04-03:** Workflow initialized. QuickChart.io chosen over inline Chart.js due to email client JavaScript stripping. premailer chosen for CSS inlining due to Gmail `<head>` style stripping.
