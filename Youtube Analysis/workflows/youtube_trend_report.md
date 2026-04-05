# YouTube AI Trend Report Workflow

## Objective
Fetch recent videos from the top 10 AI/automation YouTube channels, identify what's trending in the AI space (new tools, models, products, features), generate a professional PowerPoint slide deck, and deliver it via Gmail attachment.

## When to Run
On-demand. Run whenever you want a pulse on what's happening in AI — weekly is a good cadence.

---

## Prerequisites (One-Time Setup)

### 1. Generate a Gmail App Password
YouTube data requires no credentials — yt-dlp scrapes directly. Gmail just needs an App Password:

1. Go to **myaccount.google.com → Security**
2. Under "How you sign in" → enable **2-Step Verification** (if not already on)
3. Search for **App passwords** → create one, name it "YouTube Report"
4. Copy the 16-character password
5. Paste it into `.env` as `GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx`

That's it — no API keys, no OAuth, no credentials files.

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

---

## Running the Automation

### Full pipeline (recommended)
```bash
python tools/fetch_youtube_data.py && \
python tools/analyze_trends.py && \
python tools/create_report.py && \
python tools/send_email.py
```

### Step by step (for debugging)

**Step 1: Fetch YouTube data**
```bash
python tools/fetch_youtube_data.py
```
Output: `.tmp/youtube_raw_YYYY-MM-DD.json`
- Fetches last 14 days of videos from all 10 channels
- Filters out YouTube Shorts automatically
- Costs ~30 YouTube API quota units (10,000/day limit)

**Step 2: Analyze trends**
```bash
python tools/analyze_trends.py
```
Output: `.tmp/trends_YYYY-MM-DD.json`
- No API calls — pure keyword extraction
- Categorizes videos into 8 AI topic buckets
- Identifies specific tool/model mentions
- Scores videos by engagement

**Step 3: Generate slide deck**
```bash
python tools/create_report.py
```
Output: `.tmp/ai_trend_report_YYYY-MM-DD.pptx`
- 7 slides: Title, Executive Summary, Trending Topics, Top Videos, Tools in Spotlight, Channel Activity, Key Takeaways
- Dark theme with charts embedded as images
- Open in PowerPoint or Keynote to preview before sending

**Step 4: Send email**
```bash
python tools/send_email.py
```
- Sends HTML email with .pptx attached to REPORT_RECIPIENT
- Email body includes top topics and tools summary

---

## Output Artifacts

| File | Location | Description |
|------|----------|-------------|
| Raw video data | `.tmp/youtube_raw_YYYY-MM-DD.json` | All fetched videos with stats |
| Trend analysis | `.tmp/trends_YYYY-MM-DD.json` | Topic breakdowns, top videos, tools |
| Slide deck | `.tmp/ai_trend_report_YYYY-MM-DD.pptx` | Final deliverable |

All `.tmp/` files are disposable and regenerated each run.

---

## Customization

**Change date window:** Edit `published_after_days` in `config/channels.json` (default: 14)

**Add/remove channels:** Edit the `channels` array in `config/channels.json`

**Tune topic detection:** Edit `TOPIC_CATEGORIES` in `tools/analyze_trends.py` — add keywords for new tools/models as they emerge

**Adjust videos per channel:** Edit `videos_per_channel` in `config/channels.json` (default: 10)

---

## Known Constraints

- **No API key needed for YouTube:** yt-dlp scrapes YouTube directly. If YouTube changes its page structure, upgrade yt-dlp: `pip install -U yt-dlp`
- **Rate limiting:** Fetching full metadata per video takes ~1-2 seconds each. With 10 channels × 10 videos, expect ~2-3 minutes total. This is normal
- **Shorts filtering:** Videos under 60 seconds are excluded automatically via `duration < 60`
- **Topic taxonomy is keyword-based:** Titles + first 500 chars of description. Add new keywords to `TOPIC_CATEGORIES` in `analyze_trends.py` as new tools emerge
- **Gmail App Password:** If you change your Gmail password or revoke app passwords, regenerate one and update `.env`
- **Channel ID verification:** If a channel ID is wrong, yt-dlp will return no entries — update `config/channels.json`

---

## Learning Log

*Document discoveries, rate limit encounters, and improvements here as the system runs.*

- **2026-04-05:** Initial build. Channel IDs set from public sources — verify on first run.
- Note: Andrej Karpathy and Two Minute Papers share the same channel_id placeholder in initial config — must be corrected before first run.
