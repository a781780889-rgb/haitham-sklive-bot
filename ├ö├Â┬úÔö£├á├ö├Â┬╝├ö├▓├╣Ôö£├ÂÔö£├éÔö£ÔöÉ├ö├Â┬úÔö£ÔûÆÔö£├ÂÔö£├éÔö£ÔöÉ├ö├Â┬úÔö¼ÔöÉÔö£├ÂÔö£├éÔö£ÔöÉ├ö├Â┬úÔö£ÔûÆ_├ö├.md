# 🚂 دليل ربط البوت بدومين sehasaa.com عبر Railway

دليل مختصر ومباشر بالعربي. اتّبع الخطوات بالترتيب.

---

## 📦 ما تم تجهيزه في الكود

✅ كل الروابط القديمة تم استبدالها بـ `https://www.sehasaa.com`
✅ البوت يستخدم متغيّر `PORT` تلقائياً على Railway
✅ ملف `Procfile` معدّل لـ `web:` ليعرض الموقع على الدومين
✅ `Dockerfile` و `requirements.txt` جاهزين

---

## 1️⃣ إنشاء حساب على Railway

1. روح [https://railway.com](https://railway.com)
2. اضغط **Login** وسجّل بحساب GitHub
3. تأكّد إن في رصيد مجاني (5$ شهرياً تكفي للبوت)

---

## 2️⃣ إنشاء المشروع ورفع الكود

### الطريقة الأسهل: عن طريق GitHub

1. فك ضغط ملف الـ ZIP
2. روح [https://github.com/new](https://github.com/new) وأنشئ Repository خاص (Private)
3. ارفع الملفات (Upload files)
4. في Railway: **New Project** → **Deploy from GitHub repo** → اختر الريبو

### أو رفع مباشر

1. ثبّت Railway CLI: `npm i -g @railway/cli`
2. `railway login`
3. من داخل مجلد المشروع: `railway init` ثم `railway up`

---

## 3️⃣ إضافة قاعدة بيانات PostgreSQL

1. داخل المشروع → اضغط **+ New** → **Database** → **Add PostgreSQL**
2. انتظر 30 ثانية حتى تجهز
3. Railway يضيف متغيّر `DATABASE_URL` تلقائياً

---

## 4️⃣ إضافة متغيّرات البيئة

اذهب إلى خدمة البوت → **Variables** → **+ New Variable** وأضف:

| المتغيّر | القيمة | إلزامي؟ |
|---------|--------|---------|
| `BOT_TOKEN` | توكن البوت من @BotFather | ✅ نعم |
| `ADMIN_IDS` | معرّفك في تيليغرام (من @userinfobot) | ✅ نعم |
| `ADMIN_PASS` | كلمة سر لوحة الأدمن | ✅ نعم |
| `IBAN` | رقم الآيبان للدفع | اختياري |
| `PAYMENT_NAME` | اسم صاحب الحساب | اختياري |
| `STC_NUMBER` | رقم STC Pay | اختياري |

> 💡 `DATABASE_URL` و `PORT` يُضافان تلقائياً — لا تلمسهم.

---

## 5️⃣ التحقق من تشغيل البوت

1. اذهب إلى الخدمة → **Deployments** → **View Logs**
2. لازم تشوف:
   ```
   🐘 db_adapter: تم تفعيل وضع PostgreSQL
   🌐 الموقع: https://www.sehasaa.com/#/inquiries/slenquiry
   🤖 البوت الشامل يعمل...
   ```
3. جرّب البوت في تيليغرام بأمر `/start`

---

## 6️⃣ ربط دومين sehasaa.com بالخدمة

### في Railway:

1. اذهب إلى الخدمة → **Settings** → **Networking** (أو **Domains**)
2. اضغط **+ Custom Domain**
3. اكتب: `www.sehasaa.com` واضغط **Add Domain**
4. Railway يعطيك قيمة CNAME شكلها:
   ```
   xxxxxxx.up.railway.app
   ```
   **انسخ هذي القيمة** — راح تستخدمها في Namecheap.

---

## 7️⃣ إعداد DNS في Namecheap (مهم — هذا اللي سألت عنه)

### 🔴 الوضع الحالي عندك (الصورتين):

```
❌ CNAME Record    | www | parkingpage.namecheap...   ← احذفه
❌ URL Redirect    | @   | http://www.sehasaa.co...   ← احذفه
```

كلاهما **عديم الفائدة**:
- الأول صفحة parking افتراضية من Namecheap
- الثاني redirect دائري (الدومين يحوّل لنفسه!)

### ✅ الخطوات:

1. روح [Namecheap](https://www.namecheap.com) → **Domain List** → جنب `sehasaa.com` اضغط **Manage**
2. روح تبويب **Advanced DNS**
3. **احذف** الإثنين بالنقر على أيقونة سلة المهملات 🗑️ بجانب كل سجل
4. اضغط **+ ADD NEW RECORD** وأضف الإثنين التاليين:

#### السجل الأول: CNAME للـ www

| Type | Host | Value | TTL |
|------|------|-------|-----|
| `CNAME Record` | `www` | `xxxxxxx.up.railway.app` *(القيمة من Railway في خطوة 6)* | `Automatic` |

#### السجل الثاني: تحويل الجذر (@) إلى www

| Type | Host | Value | TTL |
|------|------|-------|-----|
| `URL Redirect Record` | `@` | `https://www.sehasaa.com` | `Automatic` |
| | | اختار: **Permanent (301)** + **Unmasked** | |

5. اضغط على ✓ الخضراء لحفظ كل سجل.

### 🟢 الشكل النهائي عندك في Namecheap:

```
✅ CNAME Record         | www | xxxxxxx.up.railway.app    | 30 min
✅ URL Redirect Record  | @   | https://www.sehasaa.com   | 30 min (Permanent, Unmasked)
```

---

## 8️⃣ التحقق النهائي + شهادة SSL

1. **انتظر 5–30 دقيقة** حتى ينتشر الـ DNS عالميًا
2. ارجع إلى Railway → الخدمة → Settings → Networking
3. لازم تشوف بجانب الدومين علامة ✅ خضراء (يعني SSL تم تركيبه تلقائياً)
4. افتح المتصفح وجرّب: `https://www.sehasaa.com`
5. لازم تظهر صفحة التحقق من الإجازات

### اختبار سريع من الطرفية (اختياري):

```bash
curl "https://www.sehasaa.com/health"
```

لازم يرجع JSON فيه `"status": "ok"`.

---

## 🔧 حلّ المشاكل الشائعة

| المشكلة | الحل |
|---------|------|
| `BOT_TOKEN غير موجود` | أضف `BOT_TOKEN` في Variables |
| الموقع يطلع 502 | تأكّد إن `Procfile` فيه `web:` مو `worker:` |
| الدومين ما يفتح | انتظر 30 دقيقة، أو تحقق من DNS بـ [dnschecker.org](https://dnschecker.org) |
| `relation does not exist` | أعد deploy — قاعدة البيانات تُهيّأ تلقائياً |
| البوت ما يرد | تحقّق من اللوغ، تأكّد إن `BOT_TOKEN` صحيح |

---

## 📌 ملخّص نهائي

```
🌐 الموقع           : https://www.sehasaa.com
🤖 البوت            : على Railway (web service)
🗄️ القاعدة          : PostgreSQL على Railway
📋 DNS في Namecheap : CNAME (www→railway) + Redirect (@ → www)
```

كل التعديلات في الكود معمولة — فقط ارفع وانشر! 🚀
