# Workflow: Job Scraping Strategy

## How the Scraper Works
1. Loads job titles + keywords from `.tmp/search_roles.json`
2. For each role × portal combination, builds search queries
3. Sends queries to Firecrawl search API (handles JS-rendered pages)
4. Skips any job URL already in `data/scraped_jobs_registry.json`
5. Stops once the run cap (default 1,000) is reached
6. Saves raw job data to `.tmp/jobs_raw_{portal}.json`
7. Updates the persistent registry

## Per-Portal Notes

### LinkedIn
- **Best for**: Enterprise, mid-size SaaS, consulting roles
- **Search pattern**: `{role} remote site:linkedin.com "{location}"`
- **Rate limiting**: LinkedIn is aggressive. Firecrawl handles this but keep delays.
- **Login**: Set LINKEDIN_EMAIL + LINKEDIN_PASSWORD in .env (used for future browser-based scraping if needed)
- **Tip**: Best results for GTM Manager, RevOps, Sales Operations

### Wellfound (formerly AngelList)
- **Best for**: Startups, funded companies, remote-first culture
- **Search pattern**: `site:wellfound.com {role} remote`
- **No login required** for most public listings
- **Tip**: Very strong for GTM and early-stage RevOps roles

### Indeed
- **Best for**: Broadest coverage, all company sizes
- **Search pattern**: `{role} remote site:indeed.com "{country}"`
- **High volume**: Can generate many results quickly
- **Tip**: Good fallback if LinkedIn results are thin

### Glassdoor
- **Best for**: Mid-to-large companies with reviews
- **Search pattern**: `site:glassdoor.com {role} remote`
- **Note**: May require login for full JD access

### Naukri
- **Best for**: India-based roles
- **Search pattern**: `site:naukri.com {role}`
- **Use when**: Location filter includes India
- **Note**: Less useful for remote/US/Europe roles

### Remotify
- **Best for**: 100% remote jobs only
- **Search pattern**: `site:remotify.io {role}`
- **Tip**: Smaller portal but high signal for genuinely remote roles

## Adding a Custom Portal
When scraper prompts for portals and you choose [7] Custom URL:
- Enter any job board URL (e.g., `https://jobs.lever.co/company`)
- The scraper will use Firecrawl to scrape that URL directly
- Job fields will be extracted using the same text patterns

## Tips for Better Results

### First run strategy
- Start with **LinkedIn + Wellfound only**
- Use Remote + US/Canada/Europe location
- Experience: 0–3 years
- This gives the highest-quality 1,000 jobs

### Subsequent runs
- Add Indeed or Glassdoor for broader coverage
- Change location to include India if needed
- The registry ensures zero duplicate job URLs

### If results are too few
- Broaden experience range (e.g., 0–5 instead of 0–3)
- Add more locations
- Add more portals
- Review `search_roles.json` — add more job title variants

### If results are too irrelevant
- Tighten location filter
- Narrow experience range
- Edit `search_roles.json` — make role titles more specific
- Remove broad roles like "Business Operations Manager" from search_roles.json

## Rate Limits & Delays
- Firecrawl handles anti-bot measures for most portals
- Script adds 1.5 second delay between each search query
- If you hit Firecrawl rate limits (429 errors), wait 60 seconds and re-run
- FIRECRAWL_API_KEY must be set in .env

## Registry File
`data/scraped_jobs_registry.json` is the permanent deduplication record.
- Never delete this file — it's the memory of every job ever seen
- Backed up automatically on each run (future enhancement)
- To start completely fresh: delete the file (all jobs will be re-scraped)
