"""
profile_builder.py — Analyze resume with Google Gemini (FREE, ONE TIME ONLY).

GUARD: If skills/resume.md already exists, this script exits immediately
       with zero API calls. Delete skills/*.md to force a rebuild.

Outputs:
  skills/resume.md            — structured resume in corporate language
  skills/skill.md             — skills by category with proficiency
  skills/experience_library.md — achievement bullets per role
  .tmp/search_roles.json      — job titles + keywords for the scraper

Free API key: https://aistudio.google.com → Get API key (no credit card needed)
"""

import json
import os
import sys
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
PARSED_RESUME = ROOT / ".tmp" / "parsed_resume.json"
SKILLS_DIR = ROOT / "skills"
GUARD_FILE = SKILLS_DIR / "resume.md"
SEARCH_ROLES_FILE = ROOT / ".tmp" / "search_roles.json"

load_dotenv(ROOT / ".env")


SYSTEM_PROMPT = """You are an expert career coach and resume analyst specializing in helping professionals transition between sectors (government-to-corporate) and into GTM, RevOps, and Sales/Marketing Operations roles.

You will analyze a resume and produce four structured outputs. Be thorough, honest, and strategic."""


ANALYSIS_PROMPT = """Analyze this resume and produce four outputs. The person has the following background:

- 15 years of total experience, with a significant portion in Government/Public Service
- Government experience is NOT irrelevant — it demonstrates transferable skills: large-scale program management, multi-stakeholder coordination, budget ownership, policy design, and operational leadership at scale
- Recent corporate experience (~2 years) is in Marketing, Sales, GTM, and Revenue Operations
- Target: mid-level corporate roles (requiring 0–3 years experience) in GTM, RevOps, Sales Ops, Marketing Ops, and related fields
- Primary job search: Remote roles in US, Canada, Europe (India as fallback)

IMPORTANT RULES:
1. DO NOT discard government experience — translate it into corporate language
2. Set seniority to "mid" for all search roles (NOT senior/principal, as corporate experience is ~2 years)
3. Be specific with job titles — "Revenue Operations Manager" beats "Operations Manager"
4. Extract real achievements with metrics wherever visible in the resume

---

RESUME TEXT:
{resume_text}

---

Produce EXACTLY these four sections, each separated by ===SECTION===:

===SECTION===
FILENAME: resume.md
[Write a clean, structured version of the resume in corporate language. Format:]

# Professional Summary
[2-3 sentence summary positioning them for GTM/RevOps/corporate roles]

## Corporate Experience
[List each corporate role: Title | Company | Start–End | Brief scope 1-2 lines]

## Government & Public Service (Transferable Experience)
[List each government role with a corporate-equivalent title in brackets, e.g.:]
[Senior Field Operations Manager] — [Original Title] | [Dept/Org] | Years
- [Translate duties into corporate language: program management, stakeholder ops, budget, team leadership]

## Education & Certifications
[Degrees, certifications, relevant training]

===SECTION===
FILENAME: skill.md
[Write all skills organized by category with proficiency. Format:]

# Skills Profile

## Core Domain Skills
- [Skill] — [Beginner/Intermediate/Advanced] ([brief context])
[List GTM, RevOps, Sales Ops, Marketing Ops skills here]

## Transferable Leadership & Operations Skills
- [Skill] — [Level] ([brief context from government/corporate])
[Program management, stakeholder management, budget, team leadership, etc.]

## Technical Tools & Platforms
- [Tool/Platform] — [Level]
[CRM, analytics, marketing tools, etc. — only list what's visible in resume]

## Soft Skills & Competencies
- [Skill] — [brief evidence from resume]

===SECTION===
FILENAME: experience_library.md
[Achievement bullets per role, metrics-driven, formatted for reuse in cover letters and applications. Format:]

# Experience Library

## [Corporate Role Title] — [Company] ([YYYY]–[YYYY or Present])
- [Achievement with metric or outcome]
- [Achievement with metric or outcome]
[3–5 bullets per corporate role]

## Government Service — Transferable Highlights
(Framed in corporate language — safe to use in cover letters and applications)
- [Translated achievement with metric/scale, e.g. "Managed cross-departmental program serving 50,000+ beneficiaries with INR 12Cr annual budget"]
[5–8 bullets total from government experience, most impactful ones only]

===SECTION===
FILENAME: search_roles.json
[Output a valid JSON array of job search targets. Each object must have: role, keywords (array), seniority, notes]

Example format (replace with actual analysis):
[
  {{"role": "Revenue Operations Manager", "keywords": ["revops", "revenue operations", "CRM", "pipeline management", "sales ops"], "seniority": "mid", "notes": "Best match for current corporate experience"}},
  {{"role": "GTM Manager", "keywords": ["go-to-market", "GTM", "product launch", "sales enablement", "revenue growth"], "seniority": "mid", "notes": "Strong fit given marketing/sales background"}},
  {{"role": "Sales Operations Manager", "keywords": ["sales operations", "salesforce", "forecasting", "quota management", "sales analytics"], "seniority": "mid", "notes": ""}},
  {{"role": "Marketing Operations Manager", "keywords": ["marketing ops", "HubSpot", "marketing automation", "demand gen", "campaign ops"], "seniority": "mid", "notes": ""}},
  {{"role": "Business Operations Manager", "keywords": ["biz ops", "business operations", "strategy", "cross-functional", "process improvement"], "seniority": "mid", "notes": "Government ops background is differentiator"}}
]

Generate 5–8 roles based on the actual resume. Ensure all roles are realistic for someone with ~2 years corporate experience."""


def build_profile(resume_text: str) -> str:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("ERROR: GEMINI_API_KEY not set in .env")
        print("Get a free key at: https://aistudio.google.com → Get API key")
        sys.exit(1)

    client = genai.Client(api_key=api_key)

    print("Calling Gemini (free) for resume analysis — ONE-TIME call...")
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=ANALYSIS_PROMPT.format(resume_text=resume_text),
        config=genai_types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            max_output_tokens=8000,
            temperature=0.3,
        ),
    )

    return response.text


def parse_sections(response_text: str) -> dict:
    sections = {}
    parts = response_text.split("===SECTION===")

    for part in parts:
        part = part.strip()
        if not part:
            continue

        lines = part.split("\n")
        filename_line = next((l for l in lines if l.startswith("FILENAME:")), None)
        if not filename_line:
            continue

        filename = filename_line.replace("FILENAME:", "").strip()
        content_lines = [l for l in lines if not l.startswith("FILENAME:")]
        content = "\n".join(content_lines).strip()
        sections[filename] = content

    return sections


def main():
    # GUARD — never call Gemini if skills already exist
    if GUARD_FILE.exists():
        print("=" * 60)
        print("GUARD: skills/resume.md already exists.")
        print("Gemini will NOT be called — no API quota consumed.")
        print("To rebuild: delete skills/*.md then re-run this script.")
        print("=" * 60)
        sys.exit(0)

    if not PARSED_RESUME.exists():
        print("ERROR: .tmp/parsed_resume.json not found.")
        print("Run tools/resume_parser.py first.")
        sys.exit(1)

    resume_data = json.loads(PARSED_RESUME.read_text())
    resume_text = resume_data.get("full_text", "")

    if not resume_text.strip():
        print("ERROR: Resume text is empty. Check input/resume.pdf")
        sys.exit(1)

    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    SEARCH_ROLES_FILE.parent.mkdir(parents=True, exist_ok=True)

    response = build_profile(resume_text)
    sections = parse_sections(response)

    written = []
    for filename, content in sections.items():
        if filename == "search_roles.json":
            # Parse and validate JSON before saving
            try:
                # Extract JSON array from content (Claude may wrap it in ```json blocks)
                json_content = content
                if "```" in content:
                    start = content.find("[")
                    end = content.rfind("]") + 1
                    json_content = content[start:end]

                roles = json.loads(json_content)
                SEARCH_ROLES_FILE.write_text(json.dumps(roles, indent=2))
                written.append(str(SEARCH_ROLES_FILE))
                print(f"  Generated {len(roles)} search roles in search_roles.json")
            except json.JSONDecodeError as e:
                print(f"WARNING: Could not parse search_roles.json — {e}")
                # Save raw content so user can fix manually
                SEARCH_ROLES_FILE.with_suffix(".raw.txt").write_text(content)
                print(f"  Raw output saved to .tmp/search_roles.raw.txt — please fix manually")
        else:
            out_path = SKILLS_DIR / filename
            out_path.write_text(content)
            written.append(str(out_path))

    print("\nProfile build complete. Files written:")
    for f in written:
        print(f"  {f}")

    print("\nNEXT STEPS:")
    print("  1. Review skills/resume.md — check that government experience is translated correctly")
    print("  2. Review .tmp/search_roles.json — edit role titles/keywords if needed")
    print("  3. Run tools/job_scraper.py to start scraping")


if __name__ == "__main__":
    main()
