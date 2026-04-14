"""
parse_resume.py
---------------
Extracts structured profile info from a resume PDF using:
  - doctr  → OCR (extracts raw text from PDF)
  - GPT-4o-mini → parses raw text into structured fields
Saves result to profile.json
"""

import json
import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

RESUME_PATH  = r"C:\Users\nikhi\OneDrive\Desktop\Nikhil CV.pdf"
OUTPUT_PATH  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "profile.json")
OPENAI_KEY   = os.getenv("OPENAI_API_KEY")


def extract_text_with_doctr(pdf_path: str) -> str:
    """Use doctr to OCR the PDF and return plain text."""
    print("Loading doctr model (first run downloads weights, may take a minute)...")
    from doctr.io import DocumentFile
    from doctr.models import ocr_predictor

    model = ocr_predictor(pretrained=True)
    doc   = DocumentFile.from_pdf(pdf_path)
    result = model(doc)

    lines = []
    for page in result.pages:
        for block in page.blocks:
            for line in block.lines:
                line_text = " ".join(word.value for word in line.words)
                lines.append(line_text)
    return "\n".join(lines)


def parse_with_gpt(raw_text: str) -> dict:
    """Send raw resume text to GPT-4o-mini and get back structured JSON."""
    client = OpenAI(api_key=OPENAI_KEY)

    prompt = f"""
You are a resume parser. Extract the following fields from the resume text below.
Return ONLY valid JSON with exactly these keys (use null if a field is not found):

{{
  "full_name": "...",
  "email": "...",
  "phone": "...",
  "current_city": "...",
  "years_of_experience": "...",
  "current_company": "...",
  "current_job_title": "...",
  "notice_period": "30 days",
  "expected_salary": null,
  "linkedin_url": "...",
  "resume_path": "{RESUME_PATH.replace(chr(92), '/')}"
}}

Rules:
- years_of_experience: a number like "2" or "3.5"
- notice_period is always "30 days" regardless of what the resume says
- expected_salary: leave as null (will be filled manually)
- phone: include country code if present
- If multiple cities found, pick the most recent/current one

Resume text:
---
{raw_text}
---
"""

    print("Sending to GPT-4o-mini for parsing...")
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )

    content = response.choices[0].message.content.strip()

    # Strip markdown code fences if present
    if content.startswith("```"):
        content = content.split("```")[1]
        if content.startswith("json"):
            content = content[4:]
    content = content.strip()

    return json.loads(content)


def main():
    if not OPENAI_KEY:
        raise ValueError("OPENAI_API_KEY not found in .env file")

    if not os.path.exists(RESUME_PATH):
        raise FileNotFoundError(f"Resume not found at: {RESUME_PATH}")

    print(f"Reading resume: {RESUME_PATH}")
    raw_text = extract_text_with_doctr(RESUME_PATH)

    print(f"Extracted {len(raw_text)} characters of text.")
    print("\n--- RAW TEXT PREVIEW (first 500 chars) ---")
    print(raw_text[:500])
    print("---\n")

    # Save raw resume text so linkedin_apply.py can use it for AI question answering
    text_path = os.path.join(os.path.dirname(OUTPUT_PATH), "resume_text.txt")
    with open(text_path, "w", encoding="utf-8") as f:
        f.write(raw_text)
    print(f"Resume text cached to: {text_path}")

    profile = parse_with_gpt(raw_text)

    # Always hardcode notice period
    profile["notice_period"] = "30 days"

    with open(OUTPUT_PATH, "w") as f:
        json.dump(profile, f, indent=2)

    print("Profile extracted successfully!\n")
    print(json.dumps(profile, indent=2))
    print(f"\nSaved to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
