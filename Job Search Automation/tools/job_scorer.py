"""
job_scorer.py — Score scraped jobs against resume profile using Gemini (free).

Batches 10 jobs per API call to stay well within free tier limits (1500 req/day).
Adds fit_score (0-100) and score_reasoning to each job.

Input:  .tmp/jobs_raw_*.json + skills/resume.md + skills/skill.md
Output: .tmp/jobs_scored.json (sorted by fit_score descending)
"""

import json
import os
import sys
import time
from pathlib import Path

try:
    from google import genai
    from google.genai import types as genai_types
except ImportError:
    print("ERROR: google-genai not installed. Run: pip install google-genai")
    sys.exit(1)

try:
    from dotenv import load_dotenv
except ImportError:
    print("ERROR: python-dotenv not installed. Run: pip install python-dotenv")
    sys.exit(1)

ROOT = Path(__file__).parent.parent
TMP_DIR = ROOT / ".tmp"
SKILLS_DIR = ROOT / "skills"
OUTPUT_FILE = TMP_DIR / "jobs_scored.json"

BATCH_SIZE = 10          # jobs per Gemini call
DELAY_BETWEEN_CALLS = 5  # seconds — keeps us under 15 RPM free limit

load_dotenv(ROOT / ".env")


def load_resume_context() -> str:
    resume_md = SKILLS_DIR / "resume.md"
    skill_md = SKILLS_DIR / "skill.md"

    parts = []
    if resume_md.exists():
        parts.append(f"=== RESUME ===\n{resume_md.read_text()}")
    if skill_md.exists():
        parts.append(f"=== SKILLS ===\n{skill_md.read_text()}")

    if not parts:
        print("ERROR: skills/resume.md not found. Run tools/profile_builder.py first.")
        sys.exit(1)

    return "\n\n".join(parts)


def load_all_jobs() -> list[dict]:
    raw_files = list(TMP_DIR.glob("jobs_raw_*.json"))
    if not raw_files:
        print("ERROR: No jobs_raw_*.json files found in .tmp/")
        print("Run tools/job_scraper.py first.")
        sys.exit(1)

    all_jobs = []
    for f in raw_files:
        try:
            jobs = json.loads(f.read_text())
            all_jobs.extend(jobs)
        except json.JSONDecodeError:
            print(f"  WARNING: Could not parse {f.name} — skipping")

    print(f"Loaded {len(all_jobs)} jobs to score")
    return all_jobs


SCORING_PROMPT = """You are a recruiter evaluating job fit for a candidate.

CANDIDATE PROFILE:
{resume_context}

---

Score each of the following jobs for this candidate on a scale of 0–100.

Scoring guide:
- 80–100: Excellent fit — skills and experience align well, strong chance of interview
- 60–79 : Good fit — mostly aligned, minor gaps
- 40–59 : Partial fit — some relevant skills but notable gaps
- 0–39  : Poor fit — significant mismatch in role, skills, or experience level

IMPORTANT: The candidate has ~2 years corporate experience (GTM/RevOps/Sales/Marketing).
Prefer roles asking for 0–3 years. Penalise roles requiring 5+ years corporate experience.
Reward roles that value government/public sector operational leadership as transferable.

Return ONLY a valid JSON array, one object per job, in this exact format:
[
  {{"job_index": 0, "fit_score": 85, "score_reasoning": "Strong RevOps match, remote US role, 2 years exp required"}},
  {{"job_index": 1, "fit_score": 42, "score_reasoning": "Requires 7 years SaaS experience, significant gap"}}
]

JOBS TO SCORE:
{jobs_block}"""


def format_jobs_block(batch: list[dict]) -> str:
    lines = []
    for i, job in enumerate(batch):
        lines.append(f"[{i}] Title: {job.get('title', 'N/A')}")
        lines.append(f"    Company: {job.get('company', 'N/A')}")
        lines.append(f"    Location: {job.get('location', 'N/A')} | Remote: {job.get('remote', False)}")
        lines.append(f"    Exp required: {job.get('exp_required', 'N/A')}")
        lines.append(f"    Skills: {job.get('skills', '')[:200]}")
        lines.append(f"    Description: {job.get('description', '')[:300]}")
        lines.append("")
    return "\n".join(lines)


def score_batch(client, batch: list[dict], resume_context: str) -> list[dict]:
    jobs_block = format_jobs_block(batch)
    prompt = SCORING_PROMPT.format(resume_context=resume_context, jobs_block=jobs_block)

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                system_instruction="You are a recruiter scoring job fit. Always return valid JSON only.",
                max_output_tokens=1000,
                temperature=0.1,
            ),
        )
        text = response.text.strip()

        # Strip markdown code fences if present
        if "```" in text:
            start = text.find("[")
            end = text.rfind("]") + 1
            text = text[start:end]

        scores = json.loads(text)
        return scores

    except (json.JSONDecodeError, Exception) as e:
        print(f"  WARNING: Scoring batch failed ({e}) — assigning default score 50")
        return [{"job_index": i, "fit_score": 50, "score_reasoning": "Could not score"} for i in range(len(batch))]


def main():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("ERROR: GEMINI_API_KEY not set in .env")
        print("Get a free key at: https://aistudio.google.com")
        sys.exit(1)

    client = genai.Client(api_key=api_key)

    resume_context = load_resume_context()
    jobs = load_all_jobs()

    total = len(jobs)
    batches = [jobs[i:i + BATCH_SIZE] for i in range(0, total, BATCH_SIZE)]
    total_batches = len(batches)

    print(f"Scoring {total} jobs in {total_batches} batches of {BATCH_SIZE}...")
    print(f"Estimated time: ~{total_batches * DELAY_BETWEEN_CALLS // 60 + 1} minutes\n")

    for batch_idx, batch in enumerate(batches):
        print(f"  Batch {batch_idx + 1}/{total_batches}...", end=" ", flush=True)
        scores = score_batch(client, batch, resume_context)

        for score_obj in scores:
            job_idx = score_obj.get("job_index", 0)
            if job_idx < len(batch):
                batch[job_idx]["fit_score"] = score_obj.get("fit_score", 50)
                batch[job_idx]["score_reasoning"] = score_obj.get("score_reasoning", "")

        scored_in_batch = sum(1 for s in scores if "fit_score" in s)
        print(f"{scored_in_batch} scored")

        if batch_idx < total_batches - 1:
            time.sleep(DELAY_BETWEEN_CALLS)

    # Sort by fit_score descending
    jobs.sort(key=lambda j: j.get("fit_score", 0), reverse=True)

    TMP_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(jobs, indent=2, ensure_ascii=False))

    # Summary
    high    = sum(1 for j in jobs if j.get("fit_score", 0) >= 80)
    good    = sum(1 for j in jobs if 60 <= j.get("fit_score", 0) < 80)
    partial = sum(1 for j in jobs if 40 <= j.get("fit_score", 0) < 60)
    low     = sum(1 for j in jobs if j.get("fit_score", 0) < 40)

    print(f"\nScoring complete:")
    print(f"  Excellent fit (80-100): {high} jobs")
    print(f"  Good fit     (60-79) : {good} jobs")
    print(f"  Partial fit  (40-59) : {partial} jobs")
    print(f"  Poor fit     (0-39)  : {low} jobs")
    print(f"\nOutput: {OUTPUT_FILE}")
    print("Next step: python3 tools/excel_exporter.py")


if __name__ == "__main__":
    main()
