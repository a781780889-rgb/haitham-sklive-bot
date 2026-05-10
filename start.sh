#!/bin/bash
echo "🚀 تشغيل النظام..."

# تفعيل venv إن وجد
if [ -d "venv" ]; then
    source venv/bin/activate
    echo "✅ البيئة الافتراضية مفعّلة"
fi

mkdir -p logs

# تشغيل الويب في الخلفية
echo "🌐 تشغيل موقع الاستعلام..."
python3 web.py > logs/web.log 2>&1 &
WEB_PID=$!
echo "✅ الويب يعمل (PID: $WEB_PID)"

# تشغيل البوت في المقدمة
echo "🤖 تشغيل البوت..."
python3 bot.py 2>&1 | tee logs/bot.log
