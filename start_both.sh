#!/bin/bash
# ════════════════════════════════════════════
# تشغيل البوتين معاً على نفس السيرفر
# ════════════════════════════════════════════

if [ -d "venv" ]; then
    source venv/bin/activate
fi

mkdir -p logs

# ── تشغيل الموقع ──
echo "🌐 تشغيل الموقع..."
python3 web.py > logs/web.log 2>&1 &
echo "✅ الموقع يعمل (PID: $!)"

sleep 2

# ── تشغيل البوت الأساسي (5 ريال) ──
echo "🤖 تشغيل البوت الأساسي..."
env $(cat .env.basic | grep -v '^#' | xargs) python3 bot.py > logs/bot_basic.log 2>&1 &
echo "✅ البوت الأساسي يعمل (PID: $!)"

sleep 2

# ── تشغيل بوت VIP (30 ريال) ──
echo "💎 تشغيل بوت VIP..."
env $(cat .env.vip | grep -v '^#' | xargs) python3 bot.py > logs/bot_vip.log 2>&1 &
echo "✅ بوت VIP يعمل (PID: $!)"

echo ""
echo "═══════════════════════════"
echo "✅ جميع الخدمات تعمل"
echo "📄 السجلات في مجلد logs/"
echo "═══════════════════════════"
wait
