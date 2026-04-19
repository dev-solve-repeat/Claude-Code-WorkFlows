# Workflow: Resume Analysis (One-Time)

## Objective
Run Claude Sonnet once to analyze Brijesh's resume and generate long-lived skills files.
These files are used by the scraper on every future run — no AI call needed again.

## When to Run
- First time setting up (skills/*.md don't exist yet)
- When Brijesh uploads a significantly updated resume
- When the generated search roles look wrong and need a full rebuild

## When NOT to Run
- If `skills/resume.md` already exists — the guard will block the API call automatically
- For routine scraping runs — never needed

## Steps

### 1. Place resume
Copy the new resume to `input/resume.pdf`. Overwrite the old one.

### 2. Delete old skills files (only for rebuild)
```bash
rm skills/resume.md skills/skill.md skills/experience_library.md
```
Deleting `skills/resume.md` removes the guard — Sonnet will be called on next run.

### 3. Run parser
```bash
python tools/resume_parser.py
```
Check `.tmp/parsed_resume.json` — verify the text looks clean (no garbled characters).
If pages look wrong, the PDF may be image-based — try exporting from Word to PDF first.

### 4. Run profile builder
```bash
python tools/profile_builder.py
```
This calls Sonnet once. Expected time: 30–60 seconds.

### 5. Review outputs carefully
**skills/resume.md**
- Are government roles listed under "Government & Public Service"?
- Are they translated into corporate language? (e.g., "District Program Officer" → "Regional Operations Manager")
- Is the professional summary positioning for GTM/RevOps/Sales Ops?

**skills/skill.md**
- Are GTM, RevOps, Sales Operations listed under Core Domain Skills?
- Are government transferables (program mgmt, stakeholder mgmt, budget) listed separately?
- Remove any skills that are not real — don't let Sonnet hallucinate tools you haven't used

**.tmp/search_roles.json**
- Are the job titles specific? ("Revenue Operations Manager" not just "Operations Manager")
- Seniority should all be "mid" — if any say "senior", change them
- Aim for 5–8 roles. Remove any that feel off.

### 6. Proceed to scraping
Once satisfied with the skill files, run the scraper normally per `workflows/job_search.md`.

## Key Context for Sonnet
The `profile_builder.py` prompt explicitly tells Sonnet:
- 15 years total experience, large government portion
- Government experience = transferable (ops, budget, leadership) — NOT discarded
- Corporate experience ≈ 2 years in GTM/RevOps/Marketing/Sales
- Target seniority: mid-level (0–3 years corporate requirement)
- Target locations: Remote, US, Canada, Europe
