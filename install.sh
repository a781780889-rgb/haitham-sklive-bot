#!/bin/bash
echo "🤖 تثبيت بوت الأعذار الطبية v2.0..."

cd "haitham sklive bot"
pip3 install -r requirements.txt

if [ ! -f .env ]; then
    cp .env.example .env
    echo "✅ تم إنشاء .env — يرجى تعديله بمعلوماتك"
fi

mkdir -p logos signatures templates
echo "✅ اكتمل التثبيت!"
echo ""
echo "الخطوات التالية:"
echo "1. عدّل ملف .env وأضف BOT_TOKEN و ADMIN_PASS"
echo "2. شغّل: python3 bot.py"
