import os
import json
from datetime import datetime
from dotenv import load_dotenv
from google import genai

load_dotenv()
from flask import Flask, render_template, request, session, redirect, url_for, Response, send_from_directory

try:
    from weasyprint import HTML as WeasyprintHTML
    HAS_WEASYPRINT = True
except Exception:
    WeasyprintHTML = None
    HAS_WEASYPRINT = False

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "abf-secret-2024-unified")
app.config['UPLOAD_FOLDER'] = "/tmp/uploads" if os.environ.get("VERCEL") else os.path.join(os.path.dirname(__file__), 'uploads')
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

MONTHLY_LIMIT = 30
USAGE_FILE = "/tmp/usage.json" if os.environ.get("VERCEL") else os.path.join(os.path.dirname(__file__), "usage.json")

def _load_usage():
    if not os.path.exists(USAGE_FILE):
        return {"month": "", "count": 0}
    with open(USAGE_FILE) as f:
        return json.load(f)

def _save_usage(u):
    with open(USAGE_FILE, "w") as f:
        json.dump(u, f)

def usage_remaining():
    month = datetime.now().strftime("%Y-%m")
    u = _load_usage()
    if u.get("month") != month:
        return MONTHLY_LIMIT
    return max(0, MONTHLY_LIMIT - u["count"])

def increment_usage():
    month = datetime.now().strftime("%Y-%m")
    u = _load_usage()
    if u.get("month") != month:
        u = {"month": month, "count": 0}
    u["count"] += 1
    _save_usage(u)

PROMPT = """Analyze the following text and convert it into a professional, structured booklet JSON object with a CUSTOM DESIGN tailored to the topic.

1. Content Structuring:
- Choose the best matching section types: heading, paragraph, bullet_list, numbered_list, table, callout, quote, exercise (with options & answer).

2. Topic-Aware Custom Styling (custom_css):
Analyze the subject/field of the content and generate tailor-made CSS rules for:
- `.booklet-title`: background color/gradient, border-radius, color, padding.
- `.booklet-title h1`: font-weight, color.
- `.sec-heading`: heading color, border-right accent color.
- `.sec-exercise`: exercise card background, border color, border-radius.
- `.sec-exercise .ex-label`: badge background & text color.
- `.sec-bullets li::before`: bullet icon (e.g. "✦", "✔", "◆", "●") & color.
- `.sec-table th`: table header background color.
- `.sec-callout`: callout background & border color.

Design inspiration guidelines by topic:
- **Medicine / Biology / Environment**: Deep forest emerald `#064e3b` / teal `#0f766e`, fresh mint `#10b981` accents, light sage exercise cards `#f0fdf4`.
- **History / Literature / Religion / Philosophy**: Rich burgundy `#7f1d1d` or royal maroon `#581c87`, warm ivory `#fffbeb` exercise cards, antique gold accents `#b45309`.
- **Technology / Programming / Physics / Engineering**: Modern slate navy `#0f172a`, vibrant indigo `#4f46e5` or cyan `#06b6d4` highlights, crisp tech borders.
- **Business / Economics / Finance / Law**: Executive dark sapphire `#1e293b`, warm amber/gold `#d97706` badges and borders, structured cards.
- **Mathematics / Logic / Science**: Deep cobalt `#1e40af`, clean crisp cards `#f8fafc`.
- **Children / Fun / School**: Friendly warm indigo `#4338ca`, coral `#ea580c` badges, soft playful rounded borders.

Return ONLY a valid JSON object with this exact structure, no markdown fences, no explanation outside JSON:
{
  "title": "عنوان المذكرة المناسب والواضح",
  "sections": [
    { "type": "heading", "text": "..." },
    { "type": "paragraph", "text": "..." },
    { "type": "bullet_list", "items": ["...", "..."] },
    { "type": "numbered_list", "items": ["...", "..."] },
    { "type": "table", "headers": ["...", "..."], "rows": [["...", "..."]] },
    { "type": "callout", "title": "ملاحظة هامة", "text": "..." },
    { "type": "exercise", "question": "...", "options": ["...", "..."], "answer": "..." }
  ],
  "custom_css": "/* complete tailor-made CSS for this subject */"
}

Text:
"""

def parse_gemini_response(raw):
    raw = raw.strip()
    if "```json" in raw:
        raw = raw.split("```json")[1].split("```")[0]
    elif "```" in raw:
        raw = raw.split("```")[1].split("```")[0]
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1:
        raw = raw[start:end+1]
    return json.loads(raw.strip())

MODELS_FALLBACK = [
    "gemini-flash-latest",
    "gemini-3.5-flash",
    "gemini-3.1-flash-lite",
    "gemini-flash-lite-latest",
    "gemini-3.5-flash-lite",
]

def call_gemini(text):
    if usage_remaining() == 0:
        raise ValueError("الحد الشهري خلص (30 تحويل/شهر) — يرجى المحاولة الشهر القادم.")
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise ValueError("GEMINI_API_KEY غير موجود في متغيرات البيئة")
    client = genai.Client(api_key=api_key)
    last_error = None
    for model in MODELS_FALLBACK:
        try:
            resp = client.models.generate_content(model=model, contents=PROMPT + text)
            result = parse_gemini_response(resp.text)
            increment_usage()
            return result
        except Exception as e:
            last_error = e
            if any(x in str(e) for x in ("503", "UNAVAILABLE", "404", "NOT_FOUND", "429", "RESOURCE_EXHAUSTED", "Quota exceeded")):
                continue
            raise
    raise ValueError(f"كل الموديلات مشغولة حالياً، حاول بعد قليل. ({last_error})")

def validate_structure(data):
    if not isinstance(data, dict):
        raise ValueError("بيانات المذكرة ليست كائن JSON صالح")
    if "title" not in data or not str(data["title"]).strip():
        data["title"] = "مذكرة تعليمية"
    if "sections" not in data or not isinstance(data["sections"], list):
        data["sections"] = []
    
    # Normalize and validate all section types safely
    for s in data["sections"]:
        if not isinstance(s, dict):
            continue
        stype = s.get("type", "paragraph")
        if stype in ("bullet_list", "list", "numbered_list", "ordered_list"):
            if "items" not in s or not isinstance(s["items"], list):
                s["items"] = [s.get("text", "")] if s.get("text") else []
        elif stype == "table":
            if "headers" not in s or not isinstance(s["headers"], list):
                s["headers"] = []
            if "rows" not in s or not isinstance(s["rows"], list):
                s["rows"] = []
        elif stype in ("exercise", "quiz", "question"):
            if "question" not in s and "text" in s:
                s["question"] = s["text"]
        elif stype in ("callout", "note", "tip", "warning", "box"):
            if "text" not in s:
                s["text"] = s.get("content", "")
        elif stype in ("heading", "title", "subheading", "h1", "h2", "h3"):
            if "text" not in s and "title" in s:
                s["text"] = s["title"]
        else:
            # Any unknown type is gracefully handled as paragraph
            if "text" not in s:
                s["text"] = s.get("content", str(s))

def generate_pdf(data, override_css=""):
    html_str = render_template("booklet.html", data=data, override_css=override_css)
    if HAS_WEASYPRINT and WeasyprintHTML:
        try:
            return WeasyprintHTML(string=html_str, base_url=None).write_pdf()
        except Exception:
            pass
    return None

@app.route("/sw.js")
def service_worker():
    response = send_from_directory("static", "sw.js", mimetype="application/javascript")
    response.headers["Service-Worker-Allowed"] = "/"
    return response

@app.route("/manifest.json")
def manifest():
    return send_from_directory("static", "manifest.json", mimetype="application/manifest+json")

@app.route("/")
def index():
    has_booklet = bool(session.get("booklet"))
    history = session.get("style_history", [])
    return render_template("index.html",
                           remaining=usage_remaining(),
                           has_booklet=has_booklet,
                           history=history)

@app.route("/api/convert", methods=["POST"])
def api_convert():
    req_json = request.get_json(silent=True) or {}
    raw_text = req_json.get("raw_text") or request.form.get("raw_text", "")
    raw_text = raw_text.strip()
    if not raw_text:
        return {"success": False, "error": "الرجاء إدخال نص."}, 400
    try:
        data = call_gemini(raw_text)
        validate_structure(data)
        session["booklet"] = data
        if "custom_css" in data and isinstance(data["custom_css"], str) and data["custom_css"].strip():
            session["custom_css"] = data["custom_css"]
        else:
            session.pop("custom_css", None)
        session.pop("style_history", None)
        return {
            "success": True,
            "title": data.get("title", ""),
            "remaining": usage_remaining()
        }
    except ValueError as e:
        return {"success": False, "error": str(e)}, 400
    except Exception as e:
        return {"success": False, "error": f"خطأ في التحليل: {e}"}, 500

@app.route("/convert", methods=["POST"])
def convert():
    raw_text = request.form.get("raw_text", "").strip()
    if not raw_text:
        return render_template("index.html", error="الرجاء إدخال نص.", remaining=usage_remaining())
    try:
        data = call_gemini(raw_text)
        validate_structure(data)
    except ValueError as e:
        return render_template("index.html", error=str(e), raw_text=raw_text, remaining=usage_remaining())
    except Exception as e:
        return render_template("index.html", error=f"خطأ في تحليل النص: {e}", raw_text=raw_text, remaining=usage_remaining())
    session["booklet"] = data
    if "custom_css" in data and isinstance(data["custom_css"], str) and data["custom_css"].strip():
        session["custom_css"] = data["custom_css"]
    else:
        session.pop("custom_css", None)
    session.pop("style_history", None)
    return redirect(url_for("index"))

@app.route("/preview")
def preview():
    return redirect(url_for("index"))

@app.route("/pdf_inline")
@app.route("/pdf_live")
@app.route("/pdf_styled")
def pdf_styled():
    data = session.get("booklet")
    if not data:
        return redirect(url_for("index"))
    custom_css = session.get("custom_css", "")
    pdf = generate_pdf(data, custom_css)
    if pdf:
        return Response(pdf, mimetype="application/pdf",
                        headers={"Content-Disposition": "inline; filename=booklet.pdf"})
    return render_template("booklet.html", data=data, override_css=custom_css, is_html_preview=True)

@app.route("/download")
def download():
    data = session.get("booklet")
    if not data:
        return redirect(url_for("index"))
    custom_css = session.get("custom_css", "")
    pdf = generate_pdf(data, custom_css)
    if pdf:
        return Response(pdf, mimetype="application/pdf",
                        headers={"Content-Disposition": "attachment; filename=booklet.pdf"})
    return render_template("booklet.html", data=data, override_css=custom_css, auto_print=True)

AI_COPILOT_PROMPT = """You are an intelligent AI Booklet Assistant and Document Editor.
You have full capability to execute the user's instructions on this booklet, but you MUST follow strict precision and logic.

HTML Structure and CSS Selectors available in the PDF:
- `body`: Page font, main text color, font-size, line-height, direction.
- `@page`: Page size (A4), margins (e.g., `margin: 12mm 12mm;`).
- `.booklet-title`, `.booklet-title h1`: Title banner and text.
- `.sec-heading`: Section headings (color, border-right, background, padding, font-size).
- `.sec-paragraph`: Paragraph text.
- `.sec-bullets`, `.sec-bullets li`, `.sec-bullets li::before`: Bullet lists and bullet icons.
- `.sec-numbered-list`, `.sec-numbered-list li`: Numbered ordered lists.
- `.sec-table-wrap`, `.sec-table`, `.sec-table th`, `.sec-table td`: Comparison and data tables.
- `.sec-callout`, `.sec-callout .callout-title`, `.sec-callout p`: Highlighted tips and notes.
- `.sec-quote`, `.sec-quote p`, `.sec-quote footer`: Quotes and citations.
- `.sec-code`, `.sec-code code`: Monospaced code blocks.
- `.sec-exercise`, `.sec-exercise .ex-label`, `.sec-exercise .ex-question`, `.sec-exercise .ex-options`, `.sec-exercise .ex-answer`: Exercise boxes with questions, multiple-choice options, and answers.

Supported Section Types in `booklet.sections`:
1. `{"type": "heading", "text": "..."}`
2. `{"type": "paragraph", "text": "..."}`
3. `{"type": "bullet_list", "items": ["...", "..."]}`
4. `{"type": "numbered_list", "items": ["Step 1", "Step 2"]}`
5. `{"type": "table", "headers": ["Col 1", "Col 2"], "rows": [["A", "B"], ["C", "D"]]}`
6. `{"type": "callout", "title": "ملاحظة هامة", "text": "..."}`
7. `{"type": "quote", "text": "...", "author": "..."}`
8. `{"type": "code", "code": "...", "language": "python"}`
9. `{"type": "exercise", "question": "...", "options": ["A", "B"], "answer": "..."}`

Current Booklet Data (JSON):
{booklet_json}

Current Custom CSS:
{current_css}

User Request: {user_request}

Return ONLY a valid JSON object with this exact structure, no markdown fences, no text outside JSON:
{{
  "reply": "رسالة مباشرة وواضحة باللغة العربية تشرح بدقة ما قمت بتعديله رداً على طلب المستخدم فقط",
  "booklet": {{
    "title": "...",
    "sections": [
      {{ "type": "heading", "text": "..." }},
      {{ "type": "paragraph", "text": "..." }},
      {{ "type": "bullet_list", "items": ["...", "..."] }},
      {{ "type": "table", "headers": ["..."], "rows": [["..."]] }},
      {{ "type": "callout", "title": "...", "text": "..." }},
      {{ "type": "exercise", "question": "..." }}
    ]
  }},
  "custom_css": "/* complete, valid CSS for the booklet */"
}}

STRICT LOGIC & INTENT RULES:
1. **Scope Precision (الالتزام بنطاق الطلب فقط):**
   - **Spacing / Blank space / Page flow complaints (الفراغات، تداخل الصفحات، تقليل المسافات):**
     * ONLY adjust spacing, margins, padding, line-height, or `@page margin` in `custom_css`.
     * NEVER change the color palette, never apply a new theme, and never alter the text content when the user only complains about spacing or page breaks!
     * To fix unwanted blank gaps: reduce margins (e.g., `margin-bottom: 2mm`), reduce `@page { margin: 10mm; }`, set `.sec-exercise .ex-answer { min-height: 6mm; }`.
   - **Content-Only Requests (تعديل المحتوى فقط):**
     * If user asks to add exercises, rephrase, summarize, translate, or edit text: update the `booklet` JSON. Keep the existing `custom_css` unchanged.
   - **Theme / Color Requests (طلب تغيير الألوان أو الثيم صراحة):**
     * If the user explicitly asks to change colors or theme: update the colors, backgrounds, and styling in `custom_css` to match their requested aesthetic.
2. **Page Breaks (فواصل الصفحات):**
   - NEVER add forced page breaks (`page-break-before: always` or `page-break-after: always`) unless the user explicitly commands you to put specific items on new pages.
   - Content should flow naturally and smoothly from page to page.
3. **No Random Hallucinations:**
   - Always respond directly and sensibly to what the user said. Do not invent unrequested changes or assign unrequested theme names.
"""

def call_ai_editor(user_request, current_booklet, current_css=""):
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise ValueError("GEMINI_API_KEY غير موجود في متغيرات البيئة")
    client = genai.Client(api_key=api_key)
    prompt = (AI_COPILOT_PROMPT
              .replace("{{booklet_json}}", json.dumps(current_booklet, ensure_ascii=False))
              .replace("{booklet_json}", json.dumps(current_booklet, ensure_ascii=False))
              .replace("{{current_css}}", current_css or "")
              .replace("{current_css}", current_css or "")
              .replace("{{user_request}}", user_request)
              .replace("{user_request}", user_request))
    last_err = None
    for model in MODELS_FALLBACK:
        try:
            resp = client.models.generate_content(model=model, contents=prompt)
            data = parse_gemini_response(resp.text)
            if not isinstance(data, dict):
                raise ValueError("الرد ليس كائن JSON")
            if "booklet" in data and isinstance(data["booklet"], dict):
                validate_structure(data["booklet"])
            return data
        except Exception as e:
            last_err = e
            if any(x in str(e) for x in ("503", "UNAVAILABLE", "404", "NOT_FOUND", "429", "RESOURCE_EXHAUSTED", "Quota exceeded")):
                continue
            raise
    raise ValueError(f"الموديل غير متاح حالياً: {last_err}")

@app.route("/api/style-chat", methods=["POST"])
def api_style_chat():
    data = session.get("booklet")
    if not data:
        return {"success": False, "error": "لا توجد مذكرة حالياً."}, 400
    req_json = request.get_json(silent=True) or {}
    user_msg = req_json.get("user_msg") or request.form.get("user_msg", "")
    user_msg = user_msg.strip()
    if not user_msg:
        return {"success": False, "error": "الرجاء كتابة طلب التعديل."}, 400
    
    current_css = session.get("custom_css", "")
    history = session.get("style_history", [])
    try:
        result = call_ai_editor(user_msg, data, current_css)
        if "booklet" in result and isinstance(result["booklet"], dict):
            session["booklet"] = result["booklet"]
        if "custom_css" in result and isinstance(result["custom_css"], str):
            session["custom_css"] = result["custom_css"]
        
        reply = result.get("reply", "✅ تم تنفيذ التعديل بنجاح.")
        history.append({"role": "user", "text": user_msg})
        history.append({"role": "ai", "text": reply})
        session["style_history"] = history
        return {
            "success": True,
            "ai_reply": reply,
            "history": history
        }
    except ValueError as e:
        return {"success": False, "error": str(e)}, 400
    except Exception as e:
        return {"success": False, "error": f"حدث خطأ: {e}"}, 500

@app.route("/api/reset-style", methods=["POST", "GET"])
def api_reset_style():
    session.pop("custom_css", None)
    session.pop("style_history", None)
    return {"success": True}

@app.route("/api/clear-booklet", methods=["POST", "GET"])
def api_clear_booklet():
    session.pop("booklet", None)
    session.pop("custom_css", None)
    session.pop("style_history", None)
    return {"success": True, "remaining": usage_remaining()}

@app.route("/style-chat", methods=["GET", "POST"])
def style_chat():
    return redirect(url_for("index"))

@app.route("/reset-style")
def reset_style():
    session.pop("custom_css", None)
    session.pop("style_history", None)
    return redirect(url_for("index"))

if __name__ == "__main__":
    app.run(debug=True, port=5001)
