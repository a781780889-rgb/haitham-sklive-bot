#!/bin/bash
echo "⛔ إيقاف جميع الخدمات..."
pkill -f "python3 bot.py" && echo "✅ البوت أُوقف"
pkill -f "python3 web.py" && echo "✅ الويب أُوقف"
echo "🏁 تم الإيقاف"
