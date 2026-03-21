import os
"""
AI Evaluator — Groq API
Handles typed, handwritten, and photo-based PDFs correctly.

KEY FIX: Photo-based PDFs (camera photos of paper) have images but NO text.
The fix is to ALWAYS try OCR first when text is short, regardless of stype.
"""
import json, os, re, base64, fitz
from groq import Groq

# ── PASTE YOUR KEY HERE ───────────────────────────────────────────────────────
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
# ─────────────────────────────────────────────────────────────────────────────

TEXT_MODEL   = "llama-3.3-70b-versatile"

# All known Groq vision model name variants — tried in order until one works
VISION_MODELS_TO_TRY = [
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "meta-llama/llama-4-maverick-17b-128e-instruct",
    "llama-4-scout-17b-16e-instruct",
    "llama-4-maverick-17b-128e-instruct",
    "llama-3.2-90b-vision-preview",
    "llama-3.2-11b-vision-preview",
]
VISION_MODEL = None  # Will be auto-detected on first use
_vision_model_cache = None


def evaluate_submission(extracted_text, rubric, max_marks, submission_type, file_path=None):
    """
    Main evaluation function.
    
    FLOW:
    1. If good text extracted (>80 chars) → evaluate text directly
    2. If little/no text BUT file_path given → run vision OCR on pages → evaluate
    3. If OCR also fails → flag for manual review
    
    This handles:
    - Typed PDFs (text extracted directly)
    - Scanned handwritten PDFs (rendered as images, OCR'd)
    - Photo PDFs (camera photos of paper — images detected but no text)
    """
    try:
        client = _get_client()
        text = (extracted_text or "").strip()

        print(f"[Evaluator] type={submission_type}, text_len={len(text)}, file={'yes' if file_path else 'no'}")

        # ── CASE 1: Good text extracted (typed PDF or PPT export) ───────────
        if submission_type == "typed" and len(text) > 80:
            print(f"[Evaluator] Typed/PPT PDF — {len(text)} chars. Evaluating directly.")
            return _evaluate_text(client, text, rubric, max_marks)

        # ── CASE 2: Handwritten / Mixed / Photo — use vision OCR ─────────────
        if file_path:
            print(f"[Evaluator] Running vision OCR on PDF pages...")
            ocr_text = _ocr_pages(client, file_path)
            print(f"[Evaluator] OCR result: {len(ocr_text)} chars")

            if len(ocr_text.strip()) > 80:
                print(f"[Evaluator] OCR succeeded. Evaluating transcribed text.")
                result = _evaluate_text(client, ocr_text, rubric, max_marks)
                result["needs_review"] = True
                result["feedback"] += (
                    "\n\n⚠ Teacher Note: This is a handwritten/scanned submission. "
                    "AI read the content from page images. Please verify marks are accurate."
                )
                return result
            else:
                print(f"[Evaluator] OCR got too little text ({len(ocr_text)} chars). Manual review needed.")
                return {
                    "marks": 0,
                    "feedback": (
                        "The handwritten content could not be read clearly from this submission. "
                        "This may be due to image quality or handwriting clarity. "
                        "Please evaluate this submission manually and update the marks."
                    ),
                    "breakdown": [],
                    "needs_review": True
                }

        # ── CASE 3: No file path, no text ─────────────────────────────────────
        return {
            "marks": 0,
            "feedback": "No content could be extracted. Please evaluate manually.",
            "breakdown": [],
            "needs_review": True
        }

    except Exception as e:
        print(f"[Evaluator] ERROR {type(e).__name__}: {e}")
        import traceback; traceback.print_exc()
        return {
            "marks": 0,
            "feedback": f"Evaluation error: {str(e)[:300]}. Please review manually.",
            "breakdown": [],
            "needs_review": True
        }


def _evaluate_text(client, text, rubric, max_marks):
    """Evaluate transcribed/extracted text against rubric with full breakdown."""

    prompt = f"""You are a senior university examiner. This evaluation directly affects the student's CGPA.
Be precise, fair, and thorough. Evaluate every question in the rubric.

RUBRIC / MARKING SCHEME:
{rubric}

TOTAL MAXIMUM MARKS: {max_marks}

STUDENT'S SUBMISSION (transcribed from handwritten paper):
{text[:7000]}

Instructions:
- Match each section of the student's answer to the corresponding rubric question
- Award marks based ONLY on what is actually written — not what you assume they meant
- If a question is partially answered, award partial marks proportionally
- Be specific in your feedback about WHAT was written correctly and WHAT was missing

Respond in JSON format only:
{{
  "total_marks": <integer 0 to {max_marks}>,
  "breakdown": [
    {{
      "question": "<exact question/section name from rubric>",
      "max_marks": <marks for this question as per rubric>,
      "awarded_marks": <marks awarded>,
      "what_was_correct": "<specific things the student wrote correctly>",
      "what_was_missing": "<specific things missing, wrong, or incomplete>",
      "reason": "<1-2 sentence justification>"
    }}
  ],
  "feedback": "<5-7 sentence detailed student feedback: overall summary, what was done well with specific references, what key concepts were missing or incorrect, how to improve>",
  "examiner_note": "<private note for teacher: concerns, unclear sections, verification needed>"
}}"""

    resp = client.chat.completions.create(
        model=TEXT_MODEL,
        temperature=0,
        max_tokens=2500,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a strict but fair university examiner. "
                    "Always respond in JSON format only. "
                    "Award marks precisely based on evidence in the student's answer."
                )
            },
            {"role": "user", "content": prompt}
        ]
    )

    raw = resp.choices[0].message.content
    print(f"[Evaluator] Raw response length: {len(raw)} chars")
    return _parse(raw, max_marks)


def _get_working_vision_model(client):
    """Auto-detect which vision model works on this Groq account."""
    global _vision_model_cache
    if _vision_model_cache:
        return _vision_model_cache

    # Get actual available models from API
    try:
        available = {m.id for m in client.models.list().data}
        print(f"[OCR] Available models: {sorted(available)}")
        for candidate in VISION_MODELS_TO_TRY:
            if candidate in available:
                print(f"[OCR] Using vision model: {candidate}")
                _vision_model_cache = candidate
                return candidate
        # If none matched by name, try each one live
        print("[OCR] No candidate matched available list — trying each live...")
    except Exception as e:
        print(f"[OCR] Could not list models: {e}")

    # Try each model with a tiny test
    import base64 as b64mod
    tiny = b64mod.b64encode(b"\xff\xd8\xff\xe0" + b"\x00"*100).decode()
    for candidate in VISION_MODELS_TO_TRY:
        try:
            client.chat.completions.create(
                model=candidate, max_tokens=5,
                messages=[{"role":"user","content":[
                    {"type":"image_url","image_url":{"url":f"data:image/jpeg;base64,{tiny}"}},
                    {"type":"text","text":"hi"}
                ]}]
            )
            print(f"[OCR] Working vision model found: {candidate}")
            _vision_model_cache = candidate
            return candidate
        except Exception as e:
            err = str(e).lower()
            # "invalid image" means model works but image was bad — that's fine
            if "image" in err or "decode" in err or "format" in err:
                print(f"[OCR] Model {candidate} exists (image error is OK)")
                _vision_model_cache = candidate
                return candidate
            print(f"[OCR] Model {candidate} failed: {str(e)[:80]}")

    print("[OCR] WARNING: No working vision model found!")
    return VISION_MODELS_TO_TRY[0]  # Last resort


def _ocr_pages(client, file_path):
    """
    Extract text from PDF pages or image files using Groq vision.
    Handles: PDF (multi-page), JPG, PNG, WEBP from mobile camera.
    Auto-detects the correct vision model name for this account.
    """
    pages = []
    vision_model = _get_working_vision_model(client)
    ext = os.path.splitext(file_path)[1].lower()

    # ── Direct image file (camera photo from mobile) ───────────────────────
    if ext in (".jpg", ".jpeg", ".png", ".webp"):
        try:
            with open(file_path, "rb") as img_f:
                b64 = base64.b64encode(img_f.read()).decode()
            print(f"[OCR] Direct image upload ({ext}), size: {len(b64)//1024}KB")
            page_text = _vision_ocr_page(client, b64, 1, vision_model)
            if page_text:
                pages.append(f"--- Page 1 ---\n{page_text}")
        except Exception as e:
            print(f"[OCR] Image OCR error: {e}")
        return "\n\n".join(pages)

    # ── PDF file ────────────────────────────────────────────────────────────
    try:
        doc = fitz.open(file_path)
        total_pages = len(doc)
        print(f"[OCR] PDF has {total_pages} pages, using model: {vision_model}")

        for i in range(min(total_pages, 8)):
            page = doc[i]
            mat = fitz.Matrix(150/72, 150/72)
            pix = page.get_pixmap(matrix=mat)
            b64 = base64.b64encode(pix.tobytes("jpeg")).decode()
            print(f"[OCR] Page {i+1}/{total_pages} ({len(b64)//1024}KB)...")

            page_text = _vision_ocr_page(client, b64, i+1, vision_model)
            if page_text:
                pages.append(f"--- Page {i+1} ---\n{page_text}")
                print(f"[OCR] Page {i+1}: {len(page_text)} chars")
            else:
                print(f"[OCR] Page {i+1}: empty")

        doc.close()

    except Exception as e:
        print(f"[OCR] Fatal: {type(e).__name__}: {e}")
        import traceback; traceback.print_exc()

    result = "\n\n".join(pages)
    print(f"[OCR] Done: {len(result)} chars from {len(pages)} pages")
    return result


def _vision_ocr_page(client, b64_image, page_num, model):
    """Send one page to Groq vision model for transcription."""
    try:
        resp = client.chat.completions.create(
            model=model,
            max_tokens=2000,
            messages=[{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_image}"}},
                {"type": "text", "text": (
                    "This is a page from a student university assignment. "
                    "Transcribe ALL text visible on this page. "
                    "Include question numbers, answers, code, tables, diagrams descriptions. "
                    "Preserve structure. Output ONLY the transcribed text, nothing else."
                )}
            ]}]
        )
        text = resp.choices[0].message.content.strip()
        if len(text) < 10:
            return ""
        # Remove unhelpful refusals
        for phrase in ["i cannot", "i'm unable", "i can't", "the image"]:
            if text.lower().startswith(phrase):
                return ""
        return text
    except Exception as e:
        print(f"[OCR] Page {page_num} model={model} error: {str(e)[:120]}")
        return ""


def _parse(text, max_marks):
    """Safely parse AI JSON response into marks + feedback + breakdown."""
    text = text.strip().replace("```json", "").replace("```", "").strip()

    for fn in [
        lambda t: json.loads(t),
        lambda t: json.loads(t[t.find("{"):t.rfind("}")+1])
    ]:
        try:
            o = fn(text)
            marks = max(0, min(int(float(str(o.get("total_marks", 0)))), max_marks))
            feedback = str(o.get("feedback", "Evaluation complete.")).strip()
            breakdown = o.get("breakdown", [])
            note = o.get("examiner_note", "")
            if note:
                feedback += f"\n\n[Teacher Note]: {note}"
            return {
                "marks": marks,
                "feedback": feedback,
                "breakdown": breakdown,
                "needs_review": False
            }
        except Exception:
            pass

    # Last resort regex
    m = re.search(r'"total_marks"\s*:\s*(\d+)', text)
    print(f"[Evaluator] JSON parse failed. Raw snippet: {text[:200]}")
    return {
        "marks": max(0, min(int(m.group(1)), max_marks)) if m else 0,
        "feedback": "AI responded but result could not be parsed. Please review manually.",
        "breakdown": [],
        "needs_review": True
    }


def _get_client():
    key = os.environ.get("GROQ_API_KEY") or GROQ_API_KEY
    if not key or key == "PASTE_YOUR_KEY_HERE":
        raise ValueError("Groq API key not set in evaluator.py")
    return Groq(api_key=key)
