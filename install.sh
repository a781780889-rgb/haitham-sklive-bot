#!/bin/bash
echo "🤖 تثبيت بوت الأعذار الطبية v2.0..."

# إنشاء بيئة افتراضية
python3 -m venv venv
source venv/bin/activate

# تثبيت المتطلبات
pip install --upgrade pip
pip install -r requirements.txt

if [ ! -f .env ]; then
    cp .env.example .env
    echo "✅ تم إنشاء .env — يرجى تعديله بمعلوماتك"
fi

mkdir -p logos signatures templates uploads/pdfs logs

echo "✅ اكتمل التثبيت!"
echo ""
echo "الخطوات التالية:"
echo "1. عدّل ملف .env وأضف BOT_TOKEN"
echo "2. شغّل: ./start.sh"
