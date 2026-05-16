# 🚂 دليل النشر على Railway

دليل خطوة بخطوة لنشر البوت على [Railway](https://railway.app) باستخدام PostgreSQL بدل SQLite.

---

## ✅ ما تمّ إعداده مسبقاً

- 🔌 **`db_adapter.py`** — طبقة توافق تلقائية: تستخدم PostgreSQL إذا وُجد `DATABASE_URL`، وإلا SQLite محلياً.
- 📦 **`requirements.txt`** — تمّت إضافة `psycopg2-binary` و `flask-cors`.
- 🚀 **`Procfile`** — `worker: python bot.py` (بوت تيليغرام لا يفتح منفذ HTTP، لذا نستخدم `worker` وليس `web`).
- ⚙️ **`nixpacks.toml`** — حزم النظام اللازمة لـ Pillow/ReportLab (cairo, pango, fontconfig, ...).
- 📋 **`railway.json`** — إعدادات بناء ونشر Railway.

---

## 🧭 خطوات النشر

### 1) إنشاء حساب ومشروع Railway

1. توجّه إلى <https://railway.app> وسجّل الدخول بـ GitHub.
2. اضغط **New Project** → **Deploy from GitHub repo** (أو **Empty Project** ثم ارفع الكود يدوياً).

### 2) إضافة قاعدة بيانات PostgreSQL

1. داخل المشروع، اضغط **+ New** → **Database** → **Add PostgreSQL**.
2. انتظر حتى تُنشأ الخدمة (10–30 ثانية).
3. Railway يُعرّف تلقائياً متغيّر البيئة `DATABASE_URL` ويُشاركه بين الخدمات.

### 3) ربط خدمة البوت بـ `DATABASE_URL`

1. اذهب إلى خدمة البوت → **Variables**.
2. اضغط **+ New Variable** → **Add Reference** → اختر قاعدة PostgreSQL → اختر `DATABASE_URL`.
3. تأكّد من إضافة المتغيّرات التالية (قيمها من عندك):

| المتغيّر | الوصف | مثال |
|--------|------|------|
| `BOT_TOKEN` | توكن بوت تيليغرام | `1234567890:AA...` |
| `ADMIN_ID` | معرّف الأدمن | `123456789` |
| `IBAN` | رقم الآيبان للدفع | `SA12 1000 ...` |
| `PAYMENT_NAME` | اسم صاحب الحساب | `هيثم قائد` |
| `STC_NUMBER` | رقم STC Pay | `0555 555 555` |
| `API_SECRET_KEY` | مفتاح API (اختياري) | سلسلة عشوائية |

> 💡 `DATABASE_URL` يُضاف تلقائياً عند ربط خدمة PostgreSQL — لا تُعدّله يدوياً.

### 4) النشر

- إذا كنت من GitHub: عند كل push إلى الفرع الرئيسي يُعاد النشر تلقائياً.
- إذا كنت ترفع ZIP: ارفع المحتويات من خلال **Deploy** داخل الخدمة.

Railway سيكتشف `nixpacks.toml` و `requirements.txt` تلقائياً ويُشغّل `python bot.py`.

### 5) التحقق من السجلات

- اذهب إلى خدمة البوت → **Deployments** → **View Logs**.
- يجب أن ترى:
  ```
  🐘 db_adapter: تم تفعيل وضع PostgreSQL
  ```
- إذا رأيت `🗄️  db_adapter: تم تفعيل وضع SQLite` فهذا يعني أن `DATABASE_URL` غير مربوط. راجع الخطوة 3.

---

## 🧪 اختبار محلي قبل النشر

### تشغيل بـ SQLite (الوضع الافتراضي)

```bash
pip install -r requirements.txt
python bot.py
```

### تشغيل بـ PostgreSQL محلياً (محاكاة Railway)

```bash
# 1) شغّل PostgreSQL محلياً (Docker مثلاً)
docker run -d --name pg-local -e POSTGRES_PASSWORD=pass -p 5432:5432 postgres:16

# 2) عرّف DATABASE_URL
export DATABASE_URL="postgresql://postgres:pass@localhost:5432/postgres"

# 3) شغّل
pip install -r requirements.txt
python bot.py
```

أول تشغيل سيُنشئ كل الجداول تلقائياً (init_db داخل database.py).

---

## 🔄 ترحيل البيانات من SQLite إلى PostgreSQL

إذا كان لديك `bot_data.db` من بيئة سابقة، استخدم أحد الحلول:

### خيار أ — `pgloader` (الأسرع)
```bash
pgloader sqlite:///path/to/bot_data.db "$DATABASE_URL"
```

### خيار ب — تصدير/استيراد CSV يدوياً
1. من SQLite: `.headers on` + `.mode csv` + `.output users.csv` + `SELECT * FROM users;`
2. من PostgreSQL: `\copy users FROM 'users.csv' CSV HEADER`

---

## 🧰 استكشاف الأخطاء

| المشكلة | السبب المحتمل | الحل |
|--------|-------------|-----|
| `psycopg2 not installed` | requirements.txt لم يُثبَّت | أعد البناء |
| `relation "users" does not exist` | لم يُستدعَ `init_db()` | تأكّد أن `bot.py` يستدعيها عند البدء |
| `column ... already exists` | ALTER COLUMN في محاولة ثانية | لا مشكلة — SAVEPOINT يبتلع الخطأ بصمت |
| `datetime('now')` يظهر نصاً | المحوّل لا يُترجم SQL | تأكّد أن الاستعلام يمرّ عبر `conn.execute` من المحوّل |
| `cur.lastrowid` يُعيد `None` | جدول بدون عمود `id` | المحوّل يُعيد العمود الأول — تحقّق من بنية الجدول |

---

## 🧱 ملاحظات معماريّة

- المحوّل (`db_adapter.py`) يترجم تلقائياً:
  - `?` → `%s` (لصالح psycopg2)
  - `datetime('now')` → `to_char(CURRENT_TIMESTAMP, 'YYYY-MM-DD HH24:MI:SS')`
  - `DATE('now')` / `DATE(col)` → `CURRENT_DATE` / `(col::timestamp::date)`
  - `strftime('%Y-%m', col)` → `to_char(col::timestamp, 'YYYY-MM')`
  - `julianday(...)` → `EXTRACT(EPOCH FROM ...)`
  - `AUTOINCREMENT` → `SERIAL`
  - `INSERT OR IGNORE` → `INSERT ... ON CONFLICT DO NOTHING`
  - `PRAGMA ...` → يُتجاهل بصمت
- **SAVEPOINT**: يسمح بعمليات تفشل بأمان داخل معاملة PostgreSQL (PG يُبطل المعاملة كاملة عند أي خطأ، على عكس SQLite). استخدمناه حول كل `ALTER TABLE ADD COLUMN` و `CREATE INDEX` و `INSERT` اختياري.
- **lastrowid**: يتمّ تلقائياً عبر إضافة `RETURNING *` في نهاية كل `INSERT`.

---

## 📌 تشغيل الأوامر المساعدة

```bash
# تنظيف أسماء المستشفيات القصيرة
railway run python cleanup_hospitals.py

# إعادة تهيئة قاعدة البيانات
railway run python -c "from database import init_db; init_db()"

# فحص سريع للمحوّل
railway run python db_adapter.py
```

---

## 🎯 الأداء والحدود

- **الخطة المجانية على Railway**: تكفي لاختبار البوت. 5 دولار رصيد/شهر.
- **PostgreSQL**: ابدأ بـ 1 GB، ارفعها لاحقاً حسب الحاجة.
- **البوت**: لا يفتح منفذ — استهلاك ذاكرة منخفض (~150 MB).

في حال أردت تشغيل `api_server.py` كخدمة منفصلة، أضف خدمة ثانية في نفس المشروع مع نفس المستودع وعدّل `startCommand` إلى `python api_server.py` وعرّف `PORT` — Railway سيربطها تلقائياً.
