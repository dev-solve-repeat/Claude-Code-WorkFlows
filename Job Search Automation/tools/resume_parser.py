"""
resume_parser.py — Extract structured text from input/resume.pdf
Output: .tmp/parsed_resume.json
No API calls — pure deterministic extraction.
"""

import json
import sys
from pathlib import Path

try:
    import pdfplumber
except ImportError:
    print("ERROR: pdfplumber not installed. Run: pip install pdfplumber")
    sys.exit(1)

ROOT = Path(__file__).parent.parent
OUTPUT_JSON = ROOT / ".tmp" / "parsed_resume.json"


def find_resume() -> Path:
    input_dir = ROOT / "input"
    pdfs = sorted(input_dir.glob("*.pdf"))
    if not pdfs:
        return None
    return pdfs[0]


def extract_resume(pdf_path: Path) -> dict:
    pages = []
    full_text_parts = []

    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            pages.append({"page": i + 1, "text": text})
            full_text_parts.append(text)

    full_text = "\n\n".join(full_text_parts).strip()

    return {
        "source": str(pdf_path),
        "total_pages": len(pages),
        "full_text": full_text,
        "pages": pages,
    }


def main():
    pdf_path = find_resume()
    if not pdf_path:
        print("ERROR: No PDF found in input/ folder.")
        print("Please drop your resume PDF into the input/ folder.")
        sys.exit(1)

    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)

    print(f"Parsing: {pdf_path.name}")
    data = extract_resume(pdf_path)
    OUTPUT_JSON.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    word_count = len(data["full_text"].split())
    print(f"Done. {data['total_pages']} pages, ~{word_count} words extracted.")
    print(f"Output: {OUTPUT_JSON}")


if __name__ == "__main__":
    main()
