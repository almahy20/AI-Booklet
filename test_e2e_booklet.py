import os
from app import app, generate_pdf, validate_structure

data = {
    "title": "الفعل المضارع وتصريفه",
    "subtitle": "دليل تعليمي شامل لقواعد وتصريف الفعل المضارع",
    "sections": [
        {
            "type": "heading",
            "text": "مقدمة عن الفعل المضارع"
        },
        {
            "type": "paragraph",
            "text": "الفعل المضارع هو الفعل الذي يدل على حدث يقع في الزمن الحاضر أو المستقبل ويبدأ بأحد أحرف المضارعة."
        },
        {
            "type": "bullet_list",
            "items": [
                "أحرف المضارعة مجموعة في كلمة نأتي",
                "يقبل دخول السين وسوف",
                "يكون معرباً في أغلب أحواله"
            ]
        },
        {
            "type": "numbered_list",
            "items": [
                "الخطوة الأولى: تحديد جذر الفعل",
                "الخطوة الثانية: إضافة حرف المضارعة",
                "الخطوة الثالثة: ضبط حركة الحرف الأخير"
            ]
        },
        {
            "type": "table",
            "headers": ["الضمير", "الفعل المضارع", "الحالة الإعرابية"],
            "rows": [
                ["هو", "يكتبُ", "مرفوع بالضمة"],
                ["هما", "يكتبانِ", "مرفوع بثبوت النون"],
                ["هم", "يكتبونَ", "مرفوع بثبوت النون"]
            ]
        },
        {
            "type": "note",
            "title": "قاعدة هامة",
            "text": "ملاحظة: يبنى الفعل المضارع على السكون إذا اتصلت به نون النسوة، وعلى الفتح إذا اتصلت به نون التوكيد المباشرة."
        },
        {
            "type": "exercise",
            "question": "أعرب الفعل في الجملة الآتية: الطلاب يكتبون الدرس.",
            "options": [
                "فعل مضارع مرفوع بالضمة",
                "فعل مضارع مرفوع بثبوت النون",
                "فعل مضارع مبني على السكون"
            ],
            "answer": "فعل مضارع مرفوع وعلامة رفعه ثبوت النون لأنه من الأفعال الخمسة."
        }
    ]
}

with app.app_context():
    validate_structure(data)
    print("Cleaned sections types:", [s["type"] for s in data["sections"]])
    pdf = generate_pdf(data)
    if pdf:
        out_file = os.path.join(os.path.dirname(__file__), "test_booklet_result.pdf")
        with open(out_file, "wb") as f:
            f.write(pdf)
        print(f"SUCCESS: Generated PDF at {out_file}, size: {len(pdf)} bytes")
    else:
        print("FAILED to generate PDF")
