import os
import re
import json
import uuid
import threading
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
_usage_lock = threading.Lock()

# ── Server-side booklet store (avoids 4KB cookie size limit) ──
BOOKLET_STORE_DIR = "/tmp/booklet_store" if os.environ.get("VERCEL") else os.path.join(os.path.dirname(__file__), "uploads", "booklet_store")
os.makedirs(BOOKLET_STORE_DIR, exist_ok=True)

def _store_path(bid):
    safe = re.sub(r'[^a-zA-Z0-9_-]', '', bid)
    return os.path.join(BOOKLET_STORE_DIR, f"{safe}.json")

def save_booklet_store(bid, booklet, custom_css, theme_family, classification, style_history):
    payload = {
        "booklet": booklet,
        "custom_css": custom_css,
        "theme_family": theme_family,
        "classification": classification,
        "style_history": style_history,
    }
    path = _store_path(bid)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    os.replace(tmp, path)

def load_booklet_store(bid):
    if not bid:
        return None
    path = _store_path(bid)
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def delete_booklet_store(bid):
    if not bid:
        return
    path = _store_path(bid)
    try:
        os.remove(path)
    except Exception:
        pass

def _load_usage():
    if not os.path.exists(USAGE_FILE):
        return {"month": "", "count": 0}
    try:
        with open(USAGE_FILE) as f:
            return json.load(f)
    except Exception:
        return {"month": "", "count": 0}

def _save_usage(u):
    tmp = USAGE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(u, f)
    os.replace(tmp, USAGE_FILE)

def usage_remaining():
    month = datetime.now().strftime("%Y-%m")
    with _usage_lock:
        u = _load_usage()
    if u.get("month") != month:
        return MONTHLY_LIMIT
    return max(0, MONTHLY_LIMIT - u["count"])

def increment_usage():
    month = datetime.now().strftime("%Y-%m")
    with _usage_lock:
        u = _load_usage()
        if u.get("month") != month:
            u = {"month": month, "count": 0}
        u["count"] += 1
        _save_usage(u)

THEME_FAMILIES = {
    "asalah": {
        "id": "asalah",
        "name": "عائلة «أصالة» (نحوي وأدبي رصين)",
        "font_family": '"Amiri", "Traditional Arabic", serif',
        "css": """:root {
  --font-main: "Amiri", "Traditional Arabic", serif !important;
}
.booklet-title {
  background: linear-gradient(135deg, #1e293b, #0f172a);
  color: #ffffff;
  border-radius: 4px;
}
.sec-heading {
  color: #1e293b;
  border-right: 4px solid #b45309;
}
.sec-paragraph {
  color: #334155;
  line-height: 1.7;
}
.sec-exercise {
  background: #fdfbf7;
  border: 1px solid #e2d9cc;
  border-radius: 4px;
}
.sec-exercise .ex-label {
  color: #881337;
  font-weight: 700;
}
.sec-exercise .ex-question {
  color: #1e293b;
}
.sec-callout {
  background: #fefce8;
  border-right: 4px solid #b45309;
  color: #713f12;
  border-radius: 4px;
}
.sec-table th {
  background: #1e293b;
  color: #ffffff;
}"""
    },
    "eshraq": {
        "id": "eshraq",
        "name": "عائلة «إشراق» (أطفال وتأسيس مرح)",
        "font_family": '"Amiri", "Traditional Arabic", serif',
        "css": """:root {
  --font-main: "Amiri", "Traditional Arabic", serif !important;
}
body {
  font-size: 11pt;
  line-height: 1.75;
}
.booklet-title {
  background: linear-gradient(135deg, #0284c7, #6366f1);
  color: #ffffff;
  border-radius: 12px;
}
.sec-heading {
  color: #0369a1;
  border-right: 5px solid #ea580c;
  font-size: 13pt;
}
.sec-paragraph {
  color: #0f172a;
}
.sec-exercise {
  background: #f0f9ff;
  border: 2px solid #7dd3fc;
  border-radius: 12px;
  padding: 4mm 5mm;
}
.sec-exercise .ex-label {
  display: inline-block;
  background: #0369a1;
  color: #ffffff;
  padding: 1mm 3.5mm;
  border-radius: 6px;
  font-size: 9pt;
  font-weight: 700;
}
.sec-exercise .ex-question {
  color: #0c4a6e;
  font-size: 11pt;
  font-weight: 600;
  margin-top: 2mm;
}
.sec-exercise .ex-answer {
  border-top: 2px dashed #94a3b8;
  min-height: 12mm;
  margin-top: 3mm;
}
.sec-callout {
  background: #fefce8;
  border: 2px solid #fde047;
  border-radius: 12px;
  color: #713f12;
}
.sec-table th {
  background: #0369a1;
  color: #ffffff;
}"""
    },
    "diqqah": {
        "id": "diqqah",
        "name": "عائلة «دقة» (علمي ورياضي محكم)",
        "font_family": '"Amiri", "Traditional Arabic", serif',
        "css": """:root {
  --font-main: "Amiri", "Traditional Arabic", serif !important;
}
.booklet-title {
  background: linear-gradient(135deg, #0f172a, #1e3a8a);
  color: #ffffff;
  border-radius: 6px;
}
.sec-heading {
  color: #0f172a;
  border-right: 4px solid #0284c7;
  font-weight: 700;
}
.sec-paragraph {
  color: #1e293b;
}
.sec-callout {
  background: #f1f5f9;
  border: 1px solid #cbd5e1;
  border-right: 4px solid #0284c7;
  border-radius: 6px;
  color: #0f172a;
}
.sec-callout .callout-title {
  color: #0369a1;
  font-weight: 700;
}
.sec-exercise {
  background: #f8fafc;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
}
.sec-exercise .ex-label {
  color: #1e3a8a;
  font-weight: 700;
}
.sec-exercise .ex-question {
  color: #0f172a;
}
.sec-table th {
  background: #0f172a;
  color: #38bdf8;
  border: 1px solid #334155;
}
code, .sec-code, .math-eq {
  font-family: Consolas, 'Courier New', monospace !important;
  direction: ltr !important;
  unicode-bidi: isolate !important;
  display: inline-block;
  background: #0f172a;
  color: #38bdf8;
  padding: 1px 5px;
  border-radius: 3px;
}"""
    },
    "manarah": {
        "id": "manarah",
        "name": "عائلة «منارة» (تاريخي وسردي وثائقي)",
        "font_family": '"Amiri", serif',
        "css": """:root {
  --font-main: "Amiri", serif !important;
}
.booklet-title {
  background: linear-gradient(135deg, #27170a, #78350f);
  color: #ffffff;
  border-radius: 4px;
}
.sec-heading {
  color: #27170a;
  border-right: 4px solid #d97706;
}
.sec-paragraph {
  color: #1f160e;
  line-height: 1.7;
}
.sec-quote {
  background: #faf8f5;
  border-right: 4px solid #b45309;
  color: #3d2314;
  border-radius: 4px;
}
.sec-exercise {
  background: #faf8f5;
  border: 1px solid #e7dfd5;
  border-radius: 4px;
}
.sec-exercise .ex-label {
  color: #78350f;
  font-weight: 700;
}
.sec-table th {
  background: #27170a;
  color: #fef3c7;
}"""
    }
}

CLASSIFIER_PROMPT = """أنت خبير تصنيف محتوى تعليمي لمذكرات PDF المدرسية والجامعية.
حلل النص التالي بدقة فائقة وصنفه وفق المعايير الثلاثة التالية:

1. نوع المادة ("subject_type"):
   - "linguistic": للغة العربية، النحو، الصرف، البلاغة، القراءة، القواعد.
   - "scientific": للفيزياء، الكيمياء، الرياضيات، الهندسة، الحاسب الآلي، العلوم الطبيعية.
   - "historical": للتاريخ، الجغرافيا، الحضارات، الدراسات الاجتماعية، الفلسفة.

2. الفئة العمرية ("target_audience"):
   - "kids": للأطفال، طلاب الابتدائي، دروس التأسيس والمبتدئين.
   - "academic": للإعدادي، الثانوي، الجامعي، والمحتوى المتقدم.

3. الطول والكثافة ("length_category"):
   - "short": ورقة عمل قصيرة (أقل من 400 حرف أو موضوع مباشر).
   - "long": مذكرة شاملة متعددة الأقسام.

4. العائلة التصميمية الموصى بها ("recommended_family"):
   - مواد اللغة العربية والنحو والصرف وقواعد الإعراب والأدب -> دائماً "asalah" بخط الأميري النسخي والتنسيق الهادئ.
   - مواد العلوم والفيزياء والكيمياء والرياضيات والحساب والمعادلات -> دائماً "diqqah" بالخط العصري الواضح وصناديق المعادلات والقوانين.
   - مواد التاريخ والحضارات والجغرافيا والدراسات الاجتماعية والسرد -> دائماً "manarah" بالطابع الوثائقي والتسلسل الزمني.
   - كتب ومذكرات الأطفال الصغار التفاعلية جداً (التأسيس، الحروف، تلوين، ابتدائي مبكر) -> "eshraq".

5. التفسير ("explanation"):
   اكتب رسالة موجزة ودقيقة للمستخدم تبدأ بصيغة:
   "صنّفت هذا الموضوع كـ: [نوع المادة] + [الفئة العمرية] + [الطول] → بناءً عليه، سأستخدم عائلة التصميم: [اسم العائلة] لأن [السبب]."

أرجع فقط كائن JSON صالح، بدون أي نصوص خارجه:
{
  "subject_type": "linguistic" | "scientific" | "historical",
  "target_audience": "kids" | "academic",
  "length_category": "short" | "long",
  "recommended_family": "asalah" | "eshraq" | "diqqah" | "manarah",
  "explanation": "..."
}

النص:
"""

def classify_document(raw_text):
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return {
            "subject_type": "linguistic",
            "target_audience": "academic",
            "length_category": "short" if len(raw_text) < 400 else "long",
            "recommended_family": "asalah",
            "explanation": "صنّفت هذا الموضوع كـ: محتوى عام → سأستخدم عائلة «أصالة» الافتراضية."
        }
    client = genai.Client(api_key=api_key)
    sample_text = raw_text[:1200]
    for model in MODELS_FALLBACK:
        try:
            resp = client.models.generate_content(model=model, contents=CLASSIFIER_PROMPT + sample_text)
            data = parse_gemini_response(resp.text)
            if isinstance(data, dict) and "recommended_family" in data:
                if data["recommended_family"] not in THEME_FAMILIES:
                    data["recommended_family"] = "asalah"
                return data
        except Exception:
            continue
    txt_lower = sample_text.lower()
    if any(w in txt_lower for w in ["نيوتن", "تسارع", "فيزياء", "كيمياء", "معادلة", "قوة", "كتلة", "رياضيات", "حساب"]):
        fam = "diqqah"
        desc = "صنّفت هذا الموضوع كـ: مادة علمية (فيزياء/رياضيات) + أكاديمي + متوسط الطول → بناءً عليه، سأستخدم عائلة التصميم: «دقة» لإبراز القوانين والمعادلات بوضوح."
    elif any(w in txt_lower for w in ["تاريخ", "حضارة", "عهد", "خليفة", "سنة", "معركة", "ثقافة"]):
        fam = "manarah"
        desc = "صنّفت هذا الموضوع كـ: مادة تاريخية/سردية + أكاديمي + متوسط الطول → بناءً عليه، سأستخدم عائلة التصميم: «منارة» ذات الطابع الوثائقي الرصين."
    elif any(w in txt_lower for w in ["أطفال", "تأسيس", "صف أول", "حروف", "تلوين"]):
        fam = "eshraq"
        desc = "صنّفت هذا الموضوع كـ: محتوى أطفال/مبتدئين + تعليم تفاعلي + قصير → بناءً عليه، سأستخدم عائلة التصميم: «إشراق» لتوفير خط واضح ومساحات حل واسعة."
    else:
        fam = "asalah"
        desc = "صنّفت هذا الموضوع كـ: مادة لغوية ونحوية + أكاديمي + متوسط الطول → بناءً عليه، سأستخدم عائلة التصميم: «أصالة» بخط النسخ الكلاسيكي والتنسيق الهادئ."
    return {
        "subject_type": "general",
        "target_audience": "academic",
        "length_category": "short" if len(raw_text) < 400 else "long",
        "recommended_family": fam,
        "explanation": desc
    }

PROMPT = """أنت محرر محتوى تعليمي محترف، حلل بنية النص الفعلية وحوله إلى كائن JSON منظم لمذكرة تعليمية احترافية.

قواعد تصنيف المحتوى:
1. مهم: أي أسئلة أو تدريبات أو واجبات دائمًا تكون type = exercise، حتى لو فيها ترقيم أو بنية شبيهة بالجدول. استخدم table فقط للبيانات المتوازية الحقيقية (مثل تصريف أفعال، مفردات ومعانيها، مقارنات بين حالات).
2. استخدم `note` فقط للتعريفات الصريحة أو التنبيهات المهمة في النص التي تستحق تمييزاً بصرياً خفيفاً.
3. استخدم `numbered_list` للخطوات المرتبة التي يجب حفظ ترتيبها.
4. استخدم `bullet_list` للقوائم النقطية غير المرتبة.
5. استخدم `exercise` للأسئلة أو التمارين الواردة في النص.
6. استنتج `subtitle` كملخص دقيق وموجز في سطر واحد من النص.
7. المعادلات والرموز العلمية اللاتينية: اكتبها كـ type = code أو بين علامات code (مثل: F = m × a) لضمان اتجاه LTR معزول.
8. لا تخترع أي محتوى غير موجود في النص الأصلي.

Return ONLY a valid JSON object with this exact structure, no markdown fences, no text outside JSON:
{
  "title": "عنوان المذكرة المناسب",
  "subtitle": "ملخص سطر واحد يستنتج من النص",
  "sections": [
    { "type": "heading", "text": "..." },
    { "type": "paragraph", "text": "..." },
    { "type": "bullet_list", "items": ["...", "..."] },
    { "type": "numbered_list", "items": ["...", "..."] },
    { "type": "table", "headers": ["الضمير", "الفعل"], "rows": [["أنا", "كتبتُ"], ["أنتَ", "كتبتَ"]] },
    { "type": "note", "text": "..." },
    { "type": "exercise", "question": "...", "options": ["...", "..."], "answer": "..." }
  ]
}

Text:
"""

def parse_gemini_response(raw):
    if not raw or not isinstance(raw, str):
        raise ValueError("رد الذكاء الاصطناعي فارغ أو غير صالح")
    raw = raw.strip()
    
    # محاولة التحليل المباشر أولاً
    try:
        return json.loads(raw)
    except Exception:
        pass
    
    # في حال الفشل: تنظيف الرد وإزالة علامات markdown وأي نصوص قبل { وبعد }
    cleaned = raw
    if "```json" in cleaned:
        cleaned = cleaned.split("```json", 1)[1].split("```", 1)[0]
    elif "```" in cleaned:
        cleaned = cleaned.split("```", 1)[1].split("```", 1)[0]
    
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1:
        cleaned = cleaned[start:end+1]
    
    try:
        return json.loads(cleaned.strip())
    except Exception as e:
        raise ValueError(f"فشل قراءة رد الذكاء الاصطناعي كـ JSON صالح: {e}")

MODELS_FALLBACK = [
    "gemini-flash-lite-latest",   # الأسرع والأرخص — الأول دائماً
    "gemini-3.1-flash-lite",      # بديل خفيف
    "gemini-3.5-flash-lite",      # بديل خفيف آخر
    "gemini-flash-latest",        # سريع ومتوازن
    "gemini-3.5-flash",           # قوي للنصوص الطويلة
    "gemini-3.1-flash-lite-preview", # preview كـ آخر ملاذ
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

KNOWN_INVERSIONS = {
    "ترصيف": "تصريف",
    "الضمري": "الضمير",
    "يتمزي": "يتميز",
    "تغري": "تغيّر",
    "يميش": "يمشي"
}

# Comprehensive Allowlist Regex:
# Allows:
# 1. Arabic Unicode blocks (Arabic, Supplement, Extended-A, Presentation Forms A & B)
# 2. Latin alphanumeric (for science/math formulas: F = m × a, E = mc², pH, etc.)
# 3. Standard punctuation, brackets, quotes, dashes, bullets
# 4. Mathematical operators, relations, and arrows (×, ÷, ±, ², ³, √, ≤, ≥, ≠, ≈, ∞, →, ←, etc.)
# Any rogue character outside this allowlist (Gurmukhi, Devanagari, Cyrillic, CJK, corrupted Latin) is cleanly stripped.
ALLOWLIST_REGEX = re.compile(
    r'[^\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF'
    r'a-zA-Z0-9'
    r'\s\.\,\:\;\!\?\-\_\+\=\*\/\(\)\[\]\{\}\«\»\•\◆\°\%\'\"\–\—\…\×\÷\±\²\³\√\\\|\`\#\@\$\^\&'
    r'\<\>\u2264\u2265\u2260\u2248\u221E\u2192\u2190]'
)

def _clean_arabic_str(val):
    if not isinstance(val, str):
        return val
    s = val
    for bad, good in KNOWN_INVERSIONS.items():
        if bad in s:
            s = s.replace(bad, good)
    s = ALLOWLIST_REGEX.sub('', s)
    return s

def audit_and_sanitize_arabic(data):
    if "title" in data:
        data["title"] = _clean_arabic_str(data["title"])
    if "subtitle" in data:
        data["subtitle"] = _clean_arabic_str(data["subtitle"])
    for s in data.get("sections", []):
        for k in ("text", "title", "question", "answer"):
            if k in s and isinstance(s[k], str):
                s[k] = _clean_arabic_str(s[k])
        if "items" in s and isinstance(s["items"], list):
            s["items"] = [_clean_arabic_str(x) for x in s["items"]]
        if "options" in s and isinstance(s["options"], list):
            s["options"] = [_clean_arabic_str(x) for x in s["options"]]
        if "headers" in s and isinstance(s["headers"], list):
            s["headers"] = [_clean_arabic_str(x) for x in s["headers"]]
        if "rows" in s and isinstance(s["rows"], list):
            s["rows"] = [[_clean_arabic_str(c) for c in r] for r in s["rows"]]

def validate_structure(data):
    if not isinstance(data, dict):
        raise ValueError("بيانات المذكرة ليست كائن JSON صالح")
    if "title" not in data or not str(data["title"]).strip():
        data["title"] = "مذكرة تعليمية"
    if "subtitle" not in data or not str(data["subtitle"]).strip():
        data["subtitle"] = ""
    if "sections" not in data or not isinstance(data["sections"], list):
        data["sections"] = []
    
    clean_sections = []
    for s in data["sections"]:
        if not isinstance(s, dict):
            continue
        stype = s.get("type", "paragraph")
        if stype == "cover":
            # عنصر الغلاف لا يُؤخذ من الـ AI
            if not data.get("title") and s.get("title"):
                data["title"] = s["title"]
            if not data.get("subtitle") and s.get("subtitle"):
                data["subtitle"] = s["subtitle"]
            continue
        elif stype in ("bullet_list", "list"):
            items = s.get("items", [])
            if not isinstance(items, list):
                items = [s.get("text", "")] if s.get("text") else []
            clean_sections.append({"type": "bullet_list", "items": items})
        elif stype in ("numbered_list", "ordered_list"):
            items = s.get("items", [])
            if not isinstance(items, list):
                items = [s.get("text", "")] if s.get("text") else []
            clean_sections.append({"type": "numbered_list", "items": items})
        elif stype == "table":
            headers = s.get("headers", [])
            if not isinstance(headers, list):
                headers = []
            rows = s.get("rows", [])
            if not isinstance(rows, list):
                rows = []
            clean_sections.append({"type": "table", "headers": headers, "rows": rows})
        elif stype in ("note", "callout", "tip", "warning", "box"):
            clean_sections.append({
                "type": "note",
                "title": s.get("title", ""),
                "text": s.get("text") or s.get("content", "")
            })
        elif stype in ("exercise", "quiz", "question"):
            clean_sections.append({
                "type": "exercise",
                "question": s.get("question") or s.get("text", ""),
                "options": s.get("options", []),
                "answer": s.get("answer", "")
            })
        elif stype in ("heading", "title", "subheading", "h1", "h2", "h3"):
            clean_sections.append({"type": "heading", "text": s.get("text") or s.get("title", "")})
        elif stype in ("quote", "blockquote"):
            clean_sections.append({"type": "quote", "text": s.get("text") or s.get("content", ""), "author": s.get("author", "")})
        elif stype in ("code", "code_block"):
            clean_sections.append({"type": "code", "code": s.get("code") or s.get("text", "")})
        else:
            txt = s.get("text") or s.get("content", "")
            if txt:
                clean_sections.append({"type": "paragraph", "text": str(txt)})
    
    # التحقق من عدم تكرار العنوان الرئيسي في أول قسم بعد الغلاف
    main_title_norm = "".join(str(data.get("title", "")).split()).strip().lower()
    while clean_sections:
        first_s = clean_sections[0]
        first_txt = first_s.get("text") or first_s.get("title", "")
        if first_s.get("type") in ("heading", "title", "paragraph") and "".join(str(first_txt).split()).strip().lower() == main_title_norm:
            clean_sections.pop(0)
        else:
            break

    # اتخاذ قرار ذكي بشأن الغلاف المستقل (Standalone Cover Page):
    # للمذكرات الطويلة والدروس المتعددة، يكون الغلاف صفحة مستقلة كاملة.
    # للمحتوى القصير (أقل من 3 أقسام)، يكون ترويسة أنيقة في أعلى نفس الصفحة تجنباً لإهدار الصفحات.
    total_text_len = sum(len(str(s.get("text", ""))) for s in clean_sections)
    is_standalone_cover = len(clean_sections) >= 3 or total_text_len > 400

    cover_item = {
        "type": "cover",
        "title": str(data["title"]).strip(),
        "subtitle": str(data.get("subtitle", "")).strip(),
        "standalone": is_standalone_cover
    }
    data["sections"] = [cover_item] + clean_sections
    
    # التدقيق والتحقق اللغوي الشامل
    audit_and_sanitize_arabic(data)

def generate_pdf(data, override_css=""):
    html_str = render_template("booklet.html", data=data, override_css=override_css, is_pdf_mode=True)
    if not HAS_WEASYPRINT or not WeasyprintHTML:
        raise RuntimeError("مكتبة WeasyPrint غير متاحة على هذا الخادم.")
    base_url = app.root_path
    return WeasyprintHTML(string=html_str, base_url=base_url).write_pdf()

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
    bid = session.get("booklet_id")
    store = load_booklet_store(bid) if bid else None
    has_booklet = bool(store)
    history = store["style_history"] if store else []
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
        classification = classify_document(raw_text)
        fam_key = classification.get("recommended_family", "asalah")
        theme = THEME_FAMILIES.get(fam_key, THEME_FAMILIES["asalah"])

        data = call_gemini(raw_text)
        validate_structure(data)

        explanation_msg = classification.get("explanation", f"تم تطبيق عائلة «{theme['name']}».")
        style_history = [{"role": "ai", "text": explanation_msg}]

        # Delete old store if exists
        old_bid = session.get("booklet_id")
        if old_bid:
            delete_booklet_store(old_bid)

        bid = str(uuid.uuid4())
        save_booklet_store(bid, data, theme["css"], fam_key, classification, style_history)
        session["booklet_id"] = bid

        return {
            "success": True,
            "title": data.get("title", ""),
            "remaining": usage_remaining(),
            "classification": classification
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
        classification = classify_document(raw_text)
        fam_key = classification.get("recommended_family", "asalah")
        theme = THEME_FAMILIES.get(fam_key, THEME_FAMILIES["asalah"])
        data = call_gemini(raw_text)
        validate_structure(data)
    except ValueError as e:
        return render_template("index.html", error=str(e), raw_text=raw_text, remaining=usage_remaining())
    except Exception as e:
        return render_template("index.html", error=f"خطأ في تحليل النص: {e}", raw_text=raw_text, remaining=usage_remaining())

    explanation_msg = classification.get("explanation", f"تم تطبيق عائلة «{theme['name']}».")
    style_history = [{"role": "ai", "text": explanation_msg}]
    old_bid = session.get("booklet_id")
    if old_bid:
        delete_booklet_store(old_bid)
    bid = str(uuid.uuid4())
    save_booklet_store(bid, data, theme["css"], fam_key, classification, style_history)
    session["booklet_id"] = bid
    return redirect(url_for("index"))

@app.route("/preview")
def preview():
    bid = session.get("booklet_id")
    store = load_booklet_store(bid)
    if not store:
        return redirect(url_for("index"))
    return render_template("preview.html", data=store["booklet"])

@app.route("/pdf_inline")
@app.route("/pdf_live")
@app.route("/pdf_styled")
def pdf_styled():
    bid = session.get("booklet_id")
    store = load_booklet_store(bid)
    if not store:
        return render_template("booklet.html", data={"title": "معاينة المذكرة", "sections": [{"type": "paragraph", "text": "لا توجد مذكرة حالياً، يرجى كتابة النص والضغط على زر إنشاء المذكرة."}]}, override_css="", is_html_preview=True)
    data = store["booklet"]
    custom_css = store["custom_css"]
    try:
        pdf = generate_pdf(data, custom_css)
        resp = Response(pdf, mimetype="application/pdf")
        resp.headers["Content-Disposition"] = "inline; filename=booklet.pdf"
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        resp.headers["Pragma"] = "no-cache"
        return resp
    except Exception:
        return render_template("booklet.html", data=data, override_css=custom_css, is_html_preview=True)

@app.route("/download")
def download():
    import urllib.parse
    bid = session.get("booklet_id")
    store = load_booklet_store(bid)
    if not store:
        return redirect(url_for("index"))
    data = store["booklet"]
    custom_css = store["custom_css"]
    try:
        pdf = generate_pdf(data, custom_css)
        raw_title = data.get("title", "booklet")
        clean_title = raw_title.replace("/", "_").replace("\\", "_").replace(":", "_").strip() or "booklet"
        encoded_title = urllib.parse.quote(f"{clean_title}.pdf")
        resp = Response(pdf, mimetype="application/pdf")
        resp.headers["Content-Disposition"] = f"attachment; filename=\"booklet.pdf\"; filename*=UTF-8''{encoded_title}"
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        resp.headers["Pragma"] = "no-cache"
        return resp
    except Exception:
        return render_template("booklet.html", data=data, override_css=custom_css, auto_print=True)

SAFE_FONTS = {
    "noto": ('"Noto Sans Arabic", Tahoma, Arial, sans-serif', "خط نوتو الحديث (Noto Sans Arabic)"),
    "amiri": ('"Amiri", "Traditional Arabic", serif', "خط الأميري النسخي الأصيل (Amiri)"),
    "tahoma": ('Tahoma, Arial, sans-serif', "خط تاهوما (Tahoma)"),
}

def apply_font_patch(current_css, user_msg):
    msg = user_msg.lower()
    chosen_key = None
    if any(k in msg for k in ["نوتو", "noto", "حديث", "عصري"]):
        chosen_key = "noto"
    elif any(k in msg for k in ["أميري", "اميري", "amiri", "نسخ", "كلاسيكي", "تقليدي"]):
        chosen_key = "amiri"
    elif any(k in msg for k in ["تاهوما", "tahoma"]):
        chosen_key = "tahoma"
    else:
        if "Noto Sans Arabic" in (current_css or ""):
            chosen_key = "amiri"
        else:
            chosen_key = "noto"
            
    font_family_str, font_name_ar = SAFE_FONTS[chosen_key]
    
    font_rule = f":root {{\n  --font-main: {font_family_str} !important;\n}}"
    pattern = r":root\s*\{[^}]*--font-main:[^}]+;?\s*\}"
    if current_css and re.search(pattern, current_css):
        new_css = re.sub(pattern, font_rule, current_css)
    else:
        new_css = (font_rule + "\n\n" + (current_css or "")).strip()
        
    reply = f"✅ تم تغيير خط المذكرة إلى **{font_name_ar}** بنجاح مع الحفاظ الكامل على التصميم والمحتوى."
    return new_css, reply

STYLE_PATCH_PROMPT = """أنت مصمم CSS محترف لمذكرات PDF تعليمية.
طلب المستخدم لتعديل التنسيق أو الألوان فقط:
"{user_request}"

كود الـ CSS المخصص الحالي للمذكرة:
{current_css}

المطلوب:
عدّل أو أضف فقط قواعد CSS المطلوبة بدقة لتنفيذ رغبة المستخدم، مع الحفاظ التام على باقي القواعد والألوان القائمة.
المحددات المتاحة:
- `.booklet-title`: عنوان الغلاف (background, color, border, padding).
- `.sec-heading`: العناوين الفرعية (color, border-right, padding, font-size).
- `.sec-paragraph`: الفقرات (color, line-height, margin).
- `.sec-bullets li`: القوائم النقطية.
- `.sec-numbered-list li`: القوائم الرقمية.
- `.sec-table`, `.sec-table th`, `.sec-table td`: الجداول ورؤوسها.
- `.sec-exercise`, `.sec-exercise .ex-label`, `.sec-exercise .ex-question`, `.sec-exercise .ex-answer`: بطاقات التمارين.
- `.sec-callout`: صندوق الملاحظات.
- `@page`: هوامش الصفحة (مثل margin: 15mm;).

تنبيهات هامة:
1. حافظ على قاعدة `:root` الخاصة بـ `--font-main` كما هي إن كانت موجودة.
2. لا تعدل أي محتوى ولا تولد أي نصوص تعليمية، فقط CSS.
3. أرجع كائن JSON فقط:
{
  "reply": "رسالة توضح ما تم تعديله في التنسيق فقط",
  "custom_css": "كود CSS المحدث كاملاً"
}
"""

def apply_style_patch(current_css, user_msg):
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise ValueError("GEMINI_API_KEY غير موجود في متغيرات البيئة")
    client = genai.Client(api_key=api_key)
    
    font_match = re.search(r":root\s*\{[^}]*--font-main:[^}]+;?\s*\}", current_css or "")
    existing_font_rule = font_match.group(0) if font_match else None
    
    prompt = STYLE_PATCH_PROMPT.replace("{user_request}", user_msg).replace("{current_css}", current_css or "/* no custom css */")
    last_err = None
    for model in MODELS_FALLBACK:
        try:
            resp = client.models.generate_content(model=model, contents=prompt)
            data = parse_gemini_response(resp.text)
            new_css = data.get("custom_css", current_css)
            if existing_font_rule and "--font-main" not in new_css:
                new_css = existing_font_rule + "\n\n" + new_css
            reply = data.get("reply", "✅ تم تحديث التنسيق بنجاح.")
            return new_css, reply
        except Exception as e:
            last_err = e
            if any(x in str(e) for x in ("503", "UNAVAILABLE", "404", "NOT_FOUND", "429", "RESOURCE_EXHAUSTED", "Quota exceeded")):
                continue
            raise
    raise ValueError(f"تعذر تحديث التنسيق حالياً: {last_err}")

CONTENT_PATCH_PROMPT = """أنت محرر محتوى تعليمي متخصص لمذكرات PDF المدرسية.
طلب المستخدم لتعديل المحتوى فقط:
"{user_request}"

محتوى المذكرة الحالي (JSON):
{booklet_json}

المطلوب:
نفّذ التعديل المطلوب على المحتوى بدقة (إضافة تمرين جديد، تعديل سؤال، تلخيص، إضافة قسم، حذف قسم).
قواعد صارمة:
1. حافظ على كافة الأقسام والعناوين الموجودة حالياً كما هي تماماً ولا تمسح أو تغير شيئاً لم يطلبه المستخدم.
2. أي أسئلة أو تدريبات أو واجبات تكون بنية type = exercise.
3. أرجع كائن JSON فقط:
{
  "reply": "رسالة توضح ما تم تعديله في المحتوى فقط",
  "booklet": {
    "title": "عنوان المذكرة",
    "subtitle": "الملخص",
    "sections": [ ...كافة الأقسام بعد التعديل... ]
  }
}
"""

def apply_content_patch(current_booklet, user_msg):
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise ValueError("GEMINI_API_KEY غير موجود في متغيرات البيئة")
    client = genai.Client(api_key=api_key)
    
    content_booklet = {
        "title": current_booklet.get("title", ""),
        "subtitle": current_booklet.get("subtitle", ""),
        "sections": [s for s in current_booklet.get("sections", []) if s.get("type") != "cover"]
    }
    
    prompt = CONTENT_PATCH_PROMPT.replace("{user_request}", user_msg).replace("{booklet_json}", json.dumps(content_booklet, ensure_ascii=False))
    last_err = None
    for model in MODELS_FALLBACK:
        try:
            resp = client.models.generate_content(model=model, contents=prompt)
            data = parse_gemini_response(resp.text)
            new_booklet = data.get("booklet", current_booklet)
            validate_structure(new_booklet)
            audit_and_sanitize_arabic(new_booklet)
            reply = data.get("reply", "✅ تم تحديث المحتوى بنجاح.")
            return new_booklet, reply
        except Exception as e:
            last_err = e
            if any(x in str(e) for x in ("503", "UNAVAILABLE", "404", "NOT_FOUND", "429", "RESOURCE_EXHAUSTED", "Quota exceeded")):
                continue
            raise
    raise ValueError(f"تعذر تحديث المحتوى حالياً: {last_err}")

COMBINED_PATCH_PROMPT = """أنت محرر ومصمم ذكي لمذكرات PDF تعليمية، تجمع بين تعديل المحتوى والتنسيق في خطوة واحدة.
طلب المستخدم:
"{user_request}"

كود CSS الحالي:
{current_css}

محتوى المذكرة الحالي (JSON):
{booklet_json}

نفّذ التعديلين معاً. أرجع JSON فقط:
{{
  "reply": "رسالة تلخص جميع ما تم تعديله",
  "custom_css": "كود CSS المحدث كاملاً",
  "booklet": {{ "جميع بيانات المذكرة بعد التعديل" }}
}}
"""

def apply_combined_patch(current_booklet, current_css, user_msg):
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise ValueError("مفتاح Gemini غير موجود")
    client = genai.Client(api_key=api_key)
    content_booklet = {
        "title": current_booklet.get("title", ""),
        "subtitle": current_booklet.get("subtitle", ""),
        "sections": [s for s in current_booklet.get("sections", []) if s.get("type") != "cover"]
    }
    font_match = re.search(r":root\s*\{[^}]*--font-main:[^}]+;?\s*\}", current_css or "")
    existing_font_rule = font_match.group(0) if font_match else None
    prompt = COMBINED_PATCH_PROMPT\
        .replace("{user_request}", user_msg)\
        .replace("{current_css}", current_css or "/* no custom css */")\
        .replace("{booklet_json}", json.dumps(content_booklet, ensure_ascii=False))
    last_err = None
    for model in MODELS_FALLBACK:
        try:
            resp = client.models.generate_content(model=model, contents=prompt)
            data = parse_gemini_response(resp.text)
            new_css = data.get("custom_css", current_css)
            if existing_font_rule and "--font-main" not in new_css:
                new_css = existing_font_rule + "\n\n" + new_css
            new_booklet = data.get("booklet", current_booklet)
            validate_structure(new_booklet)
            audit_and_sanitize_arabic(new_booklet)
            reply = data.get("reply", "✅ تم تحديث المذكرة بنجاح.")
            return new_booklet, new_css, reply
        except Exception as e:
            last_err = e
            if any(x in str(e) for x in ("503", "UNAVAILABLE", "404", "NOT_FOUND", "429", "RESOURCE_EXHAUSTED", "Quota exceeded")):
                continue
            raise
    raise ValueError(f"تعذّر تحديث المذكرة: {last_err}")

def classify_editor_intent(user_msg):
    msg_lower = user_msg.lower().strip()

    font_words = [
        "خط", "الخط", "font", "نوع الخط", "اميري", "أميري", "amiri",
        "نوتو", "noto", "تاهوما", "tahoma", "رقعة", "نسخ", "كوفي"
    ]
    style_words = [
        "لون", "الوان", "ألوان", "خلفية", "ثيم", "تصميم", "كحلي",
        "أزرق", "احمر", "أخضر", "رمادي", "ذهبي", "بوردير", "إطار",
        "هامش", "هوامش", "مسافة", "مسافات", "بادنج", "padding", "margin",
        "color", "background", "theme", "ستايل"
    ]
    content_words = [
        "تمرين", "تمارين", "سؤال", "اسئلة", "أسئلة", "اختبار", "واجب",
        "احذف", "امسح", "اضف", "أضف", "زيد", "لخص", "تلخيص", "ترجم", "ترجمة",
        "عدل نص", "صياغة", "فقرة", "شرح", "مثال", "امثلة", "أمثلة",
        "وضح", "بسّط", "اشرح", "عرّف", "صحّح", "حسّن", "طوّل", "اختصر",
        "اكتب", "أكتب", "نص", "معلومة", "معلومات", "قسم", "أقسام"
    ]

    has_font = any(k in msg_lower for k in font_words)
    has_style = any(k in msg_lower for k in style_words)
    has_content = any(k in msg_lower for k in content_words)

    if any(phrase in msg_lower for phrase in [
        "حجم الخط", "كبر الخط", "صغر الخط", "تكبير الخط", "تصغير الخط"
    ]):
        has_font = False
        has_style = True

    if has_font and not has_style and not has_content:
        return "font"
    if has_style and not has_content and not has_font:
        return "style"
    if has_content and not has_style and not has_font:
        return "content"
    if (has_style or has_font) and has_content:
        return "both"
    return "content"  # default to content edit (safer than style)

@app.route("/api/style-chat", methods=["POST"])
def api_style_chat():
    bid = session.get("booklet_id")
    store = load_booklet_store(bid)
    if not store:
        return {"success": False, "error": "لا توجد مذكرة حالياً."}, 400
    req_json = request.get_json(silent=True) or {}
    user_msg = req_json.get("user_msg") or request.form.get("user_msg", "")
    user_msg = user_msg.strip()
    if not user_msg:
        return {"success": False, "error": "الرجاء كتابة طلب التعديل."}, 400

    data = store["booklet"]
    current_css = store["custom_css"]
    history = store["style_history"]
    try:
        intent = classify_editor_intent(user_msg)

        if intent == "font":
            new_css, reply = apply_font_patch(current_css, user_msg)
            store["custom_css"] = new_css

        elif intent == "style":
            new_css, reply = apply_style_patch(current_css, user_msg)
            store["custom_css"] = new_css

        elif intent == "content":
            new_booklet, reply = apply_content_patch(data, user_msg)
            store["booklet"] = new_booklet

        else:  # "both" — single Gemini call
            new_booklet, new_css, reply = apply_combined_patch(data, current_css, user_msg)
            store["booklet"] = new_booklet
            store["custom_css"] = new_css

        history.append({"role": "user", "text": user_msg})
        history.append({"role": "ai", "text": reply})
        # Cap history at 20 messages to prevent session/store bloat
        store["style_history"] = history[-20:]

        save_booklet_store(
            bid,
            store["booklet"],
            store["custom_css"],
            store.get("theme_family", "asalah"),
            store.get("classification", {}),
            store["style_history"]
        )
        return {
            "success": True,
            "ai_reply": reply,
            "history": store["style_history"]
        }
    except ValueError as e:
        return {"success": False, "error": str(e)}, 400
    except Exception as e:
        return {"success": False, "error": f"حدث خطأ: {e}"}, 500

@app.route("/api/reset-style", methods=["POST", "GET"])
def api_reset_style():
    bid = session.get("booklet_id")
    store = load_booklet_store(bid)
    if store and bid:
        fam_key = store.get("theme_family", "asalah")
        theme = THEME_FAMILIES.get(fam_key, THEME_FAMILIES["asalah"])
        store["custom_css"] = theme["css"]
        store["style_history"] = store["style_history"][:1]  # keep only initial AI message
        save_booklet_store(
            bid,
            store["booklet"],
            store["custom_css"],
            fam_key,
            store.get("classification", {}),
            store["style_history"]
        )
    return {"success": True}

@app.route("/api/clear-booklet", methods=["POST", "GET"])
def api_clear_booklet():
    bid = session.get("booklet_id")
    if bid:
        delete_booklet_store(bid)
        session.pop("booklet_id", None)
    return {"success": True, "remaining": usage_remaining()}

@app.route("/style-chat", methods=["GET", "POST"])
def style_chat():
    return redirect(url_for("index"))

@app.route("/reset-style")
def reset_style():
    bid = session.get("booklet_id")
    store = load_booklet_store(bid)
    if store and bid:
        fam_key = store.get("theme_family", "asalah")
        theme = THEME_FAMILIES.get(fam_key, THEME_FAMILIES["asalah"])
        store["custom_css"] = theme["css"]
        store["style_history"] = store["style_history"][:1]
        save_booklet_store(
            bid,
            store["booklet"],
            store["custom_css"],
            fam_key,
            store.get("classification", {}),
            store["style_history"]
        )
    return redirect(url_for("index"))

@app.route("/api/export-json")
def api_export_json():
    bid = session.get("booklet_id")
    store = load_booklet_store(bid)
    if not store:
        return {"success": False, "error": "لا توجد مذكرة."}, 400
    data = store["booklet"]
    raw_title = data.get("title", "booklet")
    clean_title = raw_title.replace("/", "_").replace("\\", "_").replace(":", "_").strip() or "booklet"
    resp = Response(
        json.dumps(store, ensure_ascii=False, indent=2),
        mimetype="application/json"
    )
    resp.headers["Content-Disposition"] = f'attachment; filename="{clean_title}.json"'
    return resp

if __name__ == "__main__":
    app.run(debug=True, port=5001)
