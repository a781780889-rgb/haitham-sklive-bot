# 🤖 دليل الإعداد والتشغيل

هذا الدليل يشرح كيفية إعداد وتشغيل البوت.

---

## ⚙️ متطلبات التشغيل

- Python 3.11+
- قاعدة بيانات PostgreSQL أو SQLite
- مفاتيح Telegram Bot API

---

## 🗄️ متغيرات البيئة

| المتغير | الوصف |
|---------|-------|
| `BOT_TOKEN` | توكن البوت من @BotFather |
| `DATABASE_URL` | رابط قاعدة البيانات (PostgreSQL) |
| `ADMIN_IDS` | معرفات المشرفين مفصولة بفاصلة |

---

## 🚀 تشغيل البوت

```bash
# تثبيت المتطلبات
pip install -r requirements.txt

# تشغيل مباشر
python3 bot.py

# تشغيل بـ gunicorn (إنتاج)
gunicorn -w 2 -b 0.0.0.0:$PORT bot:app
```

---

## 📦 الملفات الأساسية

| الملف | الدور |
|-------|-------|
| `bot.py` | الملف الرئيسي للبوت |
| `database.py` | إدارة قاعدة البيانات المحلية |
| `external_api.py` | مزامنة بيانات الإجازات |
| `pdf_gen.py` | توليد ملفات PDF |
| `ai_nlp_engine.py` | محرك معالجة اللغة الطبيعية |
| `smart_data_engine.py` | محرك البيانات الذكي |

---

## 🚂 النشر على Railway

تأكد من وجود هذه المتغيرات في Railway:

```
BOT_TOKEN=...
DATABASE_URL=postgresql://...
```

أمر التشغيل في `nixpacks.toml` و `railway.json` مُعدّ مسبقاً على `python3 bot.py`.

---

## 📝 ملاحظات

- الـ `Procfile` الرئيسي يُشغّل `python3 bot.py` مباشرة.
- ملفات `web_*.py` المتخصصة تعمل بشكل مستقل إذا احتجت لنشر واجهة ويب منفصلة.
