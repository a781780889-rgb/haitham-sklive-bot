# 🌐 دليل ربط البوتين بموقع التحقق الموحّد www.seha-s.com

هذا الدليل يشرح بشكل كامل كيفية ربط البوتين معاً بموقع تحقق
واحد عبر **قاعدة بيانات PostgreSQL مشتركة**.

---

## 📋 ملخص المعمارية

```
┌────────────────────┐              ┌────────────────────┐
│  بوت 1             │              │  بوت 2             │
│ (haitham-sklive)   │              │ (jdjdn)            │
│                    │              │                    │
│ قاعدته الخاصة      │              │ قاعدته الخاصة     │
│ (SQLite/Postgres)  │              │ (SQLite)           │
└─────────┬──────────┘              └──────────┬─────────┘
          │                                    │
          │   ✅ مزامنة فورية لكل تقرير جديد   │
          │                                    │
          ↓                                    ↓
     ┌───────────────────────────────────────────┐
     │  قاعدة بيانات مشتركة (PostgreSQL)         │
     │  جدول واحد: reports                       │
     │  متغير البيئة: SHARED_DATABASE_URL        │
     └───────────────────┬───────────────────────┘
                         │
                         ↓
              ┌─────────────────────┐
              │  www.seha-s.com     │
              │  (web_seha_s.py)    │
              │  يقرأ فقط           │
              └─────────────────────┘
```

**المبدأ:**
- كل بوت يحتفظ بقاعدته الخاصة (لا تغيير على آلية عمله الداخلية).
- عند إصدار أي تقرير جديد، البوت يُرسل نسخة من البيانات الأساسية إلى
  القاعدة المشتركة في **خلفية** (لا يُبطئ البوت).
- الموقع `www.seha-s.com` يقرأ فقط من القاعدة المشتركة، لذا
  يجد كل التقارير من البوتين معاً بدون أي تكامل بينهما.

---

## 🗄️ الجدول المشترك

اسم الجدول: **`reports`** — يُنشأ تلقائياً عند أول تشغيل.

```sql
CREATE TABLE IF NOT EXISTS reports (
    id              SERIAL PRIMARY KEY,
    report_number   TEXT UNIQUE NOT NULL,    -- رمز GSL/PSL
    source_bot      TEXT DEFAULT '',          -- bot1 أو bot2
    report_type     TEXT DEFAULT 'sick_leave',
    patient_name    TEXT DEFAULT '',
    patient_id      TEXT DEFAULT '',          -- رقم الهوية (واضح، غير مشفّر)
    nationality     TEXT DEFAULT '',
    employer        TEXT DEFAULT '',
    leave_date      TEXT DEFAULT '',
    end_date        TEXT DEFAULT '',
    days            INTEGER DEFAULT 0,
    admission_date  TEXT DEFAULT '',
    discharge_date  TEXT DEFAULT '',
    issue_date      TEXT DEFAULT '',
    doctor_name     TEXT DEFAULT '',
    doctor_specialty TEXT DEFAULT '',
    hospital_name   TEXT DEFAULT '',
    report_data     TEXT DEFAULT '',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## ⚙️ خطوات الإعداد

### 1) جهّز قاعدة بيانات PostgreSQL مشتركة

أي من هذه الخيارات يعمل:
- **Supabase** (مجاني): أنشئ مشروع وانسخ Connection String من
  Settings → Database → URI.
- **Railway PostgreSQL**: أنشئ خدمة PostgreSQL واحصل على
  `DATABASE_URL`.
- **Neon / Aiven / Render Postgres**: أي مزود PostgreSQL.

ستحصل على رابط بهذه الصيغة:
```
postgresql://USER:PASSWORD@HOST:PORT/DBNAME
```

> ✅ لا داعي لإنشاء الجدول يدوياً — الكود يُنشئه تلقائياً.

### 2) أضف متغير البيئة في كلا البوتين والموقع

في **كلا البوتين** والموقع، أضف هذا المتغير:

| المتغير | القيمة |
|---------|--------|
| `SHARED_DATABASE_URL` | `postgresql://USER:PASSWORD@HOST:PORT/DBNAME` |

اختياري:
| المتغير | القيمة الافتراضية | الوصف |
|---------|------------------|--------|
| `BOT_SOURCE_NAME` | `bot1` أو `bot2` | اسم البوت في القاعدة المشتركة |

### 3) شغّل البوتين

كل بوت يعمل كالمعتاد:
```bash
# بوت 1
cd bot1 && python3 bot.py

# بوت 2
cd bot2 && python3 bot.py
```

عند إصدار أي تقرير جديد، البوت سيُرسل نسخة منه إلى القاعدة المشتركة
تلقائياً (في الخلفية، بدون تأخير).

### 4) شغّل الموقع www.seha-s.com

```bash
# تثبيت
pip install flask psycopg2-binary gunicorn

# تشغيل (تطوير)
SHARED_DATABASE_URL="postgresql://..." python3 web_seha_s.py

# تشغيل (إنتاج)
SHARED_DATABASE_URL="postgresql://..." gunicorn -w 2 -b 0.0.0.0:5000 web_seha_s:app
```

---

## 🔍 طرق الوصول للموقع

| المسار | الوصف |
|--------|--------|
| `GET /` | الصفحة الرئيسية (نموذج التحقق) |
| `GET /verify?gsl=GSL123` | تعبئة رمز الخدمة تلقائياً من URL |
| `GET /api/verify?gsl=...&id=...` | API JSON للتحقق |
| `GET /api/stats` | إحصائيات (إجمالي/اليوم/توزيع المصادر) |
| `GET /health` | فحص صحة الخدمة |

### مثال على رد JSON من `/api/verify`:

```json
{
  "success": true,
  "data": {
    "report_number": "GSL56098894651",
    "full_name":     "هيثم قائد",
    "id_number":     "1234567890",
    "leave_date":    "2026-04-25",
    "end_date":      "2026-04-27",
    "days_count":    3,
    "doctor":        "د. أحمد",
    "specialty":     "طبيب عام",
    "hospital":      "مستشفى الملك فهد",
    "nationality":   "سعودي",
    "employer":      "شركة تجريبية",
    "issued_at":     "2026-04-27 05:31:35",
    "source":        "bot1"
  }
}
```

---

## 📦 الملفات الجديدة في كل بوت

| الملف | الدور |
|-------|------|
| `shared_db.py` | وحدة قاعدة البيانات المشتركة (نفس النسخة في البوتين والموقع) |
| `web_seha_s.py` | كود موقع التحقق (يمكن نشره من أي بوت أو منفصلاً) |

### بوت 1 (haitham-sklive):
- ✅ تم استبدال `external_api.py` بنسخة تستخدم `shared_db.py`
  مع الحفاظ على نفس واجهة `send_leave_to_external_api()`.
- ✅ لا تغيير على `bot.py` — يستمر بنفس استدعاءاته.

### بوت 2 (jdjdn):
- ✅ تم استبدال دالة `_sync_report_to_pg` داخل `bot.py` بنسخة
  تستخدم `shared_db.py`.
- ✅ نفس واجهة الاستدعاء، لا تغيير على باقي الكود.
- ✅ يفك تشفير `patient_id` تلقائياً قبل الحفظ ليطابقه الموقع.

---

## 🚀 نشر الموقع على www.seha-s.com

### خيار 1: نشر مستقل (موصى به)

أنشئ خدمة جديدة على Railway/Heroku/Render تحتوي فقط على:
```
shared_db.py
web_seha_s.py
requirements_web.txt   (انظر أدناه)
Procfile               (انظر أدناه)
```

**`requirements_web.txt`:**
```
flask>=3.0
psycopg2-binary>=2.9.9
gunicorn>=21.0
```

**`Procfile`:**
```
web: gunicorn -w 2 -b 0.0.0.0:$PORT web_seha_s:app
```

ثم اربط الدومين `www.seha-s.com` بهذه الخدمة.

### خيار 2: تشغيل الموقع داخل أحد البوتين

ضع هذا في Procfile البوت:
```
worker: python3 bot.py
web:    gunicorn -w 2 -b 0.0.0.0:$PORT web_seha_s:app
```

---

## 🛡️ ملاحظات أمنية

- ✅ كل بوت يحفظ نسخة من البيانات في القاعدة المشتركة
  بحيث `patient_id` يكون **واضحاً** (غير مشفّر) لأن الموقع يحتاجه
  للمطابقة. هذا التصرف هو نفسه السلوك القديم في `external_api.py`.
- ✅ بيانات `report_data` تبقى **مشفّرة** كما في الأصل (في بوت 2).
- ✅ المزامنة في **thread منفصل** — لا تُبطئ البوت.
- ✅ إذا فشلت المزامنة (مثلاً قاعدة المعطيات غير متاحة) لن يتأثر البوت.
- ✅ القفل `ON CONFLICT (report_number) DO UPDATE` يضمن عدم تكرار التقارير.

---

## 🧪 اختبار سريع

بعد النشر، يمكنك اختبار الربط:

```bash
# 1) أرسل تقريراً تجريبياً من بوت 1 (مثلاً GSL123…)
# 2) أرسل تقريراً تجريبياً من بوت 2 (مثلاً PSL456…)
# 3) افتح الموقع وأدخل أحدهما
# 4) لازم يظهر النتيجة الصحيحة من الجدول المشترك
```

أو من سطر الأوامر:
```bash
curl "https://www.seha-s.com/api/verify?gsl=GSL56098894651&id=1234567890"
```

---

## 📝 استكشاف الأخطاء

| المشكلة | السبب المحتمل | الحل |
|--------|--------------|------|
| الموقع يقول "قاعدة البيانات غير مُهيّأة" | `SHARED_DATABASE_URL` غير مُعدّ | أضِف المتغير وأعد التشغيل |
| التقرير لا يظهر في الموقع | البوت لم ينجح في المزامنة | تحقق من logs البوت — ابحث عن `📤 تم إرسال التقرير` |
| رد "لم يُعثر على نتيجة" مع وجود التقرير | رقم الهوية لا يطابق | تأكد أن `patient_id` يُحفَظ بدون تشفير في القاعدة المشتركة |
| خطأ اتصال SSL | بعض المزودين يحتاجون `?sslmode=require` | أضِفها لنهاية الـ URL |
| الجدول لا يُنشأ | المستخدم ليس له صلاحية CREATE | امنحه صلاحية أو أنشئ الجدول يدوياً |

---

## ✅ المختصر

- **بوت 1**: يعمل كالمعتاد، يُزامن كل تقرير جديد.
- **بوت 2**: يعمل كالمعتاد، يُزامن كل تقرير جديد.
- **الموقع**: يقرأ من القاعدة المشتركة، يجد كل التقارير من البوتين.
- **القاعدة**: مشتركة واحدة، تُنشأ تلقائياً.

نقطة الإعداد الوحيدة: **متغير `SHARED_DATABASE_URL` في الأمكنة الثلاثة.**
