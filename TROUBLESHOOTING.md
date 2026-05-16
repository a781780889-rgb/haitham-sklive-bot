# 🔧 دليل حل المشاكل - Troubleshooting

## ⚠️ مشكلة: externally-managed-environment

### الأعراض:
```
error: externally-managed-environment
× This environment is externally managed
```

### السبب:
Ubuntu 22.04+ يمنع تثبيت حزم Python مباشرة في بيئة النظام للحماية.

### ✅ الحل:

استخدم السكريبت المحدّث `install_fixed.sh` بدلاً من `install.sh`:

```bash
# احذف المجلد القديم إن وجد
rm -rf venv

# شغل السكريبت المحدّث
chmod +x install_fixed.sh
./install_fixed.sh
```

هذا السكريبت سيقوم بـ:
1. إنشاء بيئة افتراضية (venv)
2. تثبيت جميع المتطلبات داخل البيئة
3. إنشاء سكريبت تشغيل جديد `start_venv.sh`

### التشغيل بعد الحل:
```bash
# استخدم السكريبت الجديد
./start_venv.sh
```

---

## ⚠️ مشكلة: Permission denied

### الأعراض:
```
bash: ./install.sh: Permission denied
```

### ✅ الحل:
```bash
chmod +x install_fixed.sh
chmod +x start_venv.sh
./install_fixed.sh
```

---

## ⚠️ مشكلة: البوت لا يستجيب

### التحقق:
```bash
# 1. تحقق من BOT_TOKEN
cat .env | grep BOT_TOKEN

# 2. تحقق من السجلات
tail -f logs/bot.log

# 3. تحقق من تشغيل البوت
ps aux | grep bot_enhanced
```

### ✅ الحل:
```bash
# تأكد من صحة TOKEN في .env
nano .env

# أعد تشغيل البوت
./start_venv.sh
```

---

## ⚠️ مشكلة: الموقع لا يفتح

### التحقق:
```bash
# تحقق من تشغيل الخادم
ps aux | grep web_enhanced

# تحقق من المنفذ
netstat -tuln | grep 5000

# تحقق من السجلات
tail -f logs/web_server.log
```

### ✅ الحل:
```bash
# تأكد من عدم استخدام المنفذ من برنامج آخر
sudo lsof -i :5000

# أعد التشغيل
./start_venv.sh
```

---

## ⚠️ مشكلة: ModuleNotFoundError

### الأعراض:
```
ModuleNotFoundError: No module named 'flask'
```

### ✅ الحل:
```bash
# تأكد من تفعيل البيئة الافتراضية
source venv/bin/activate

# أعد تثبيت المتطلبات
pip install -r requirements.txt

# شغل النظام
./start_venv.sh
```

---

## ⚠️ مشكلة: API Server لا يعمل

### التحقق:
```bash
# تحقق من تشغيل API
ps aux | grep api_server

# اختبر الاتصال
curl http://localhost:5001/api/health

# تحقق من السجلات
tail -f logs/api_server.log
```

### ✅ الحل:
```bash
# أعد التشغيل
./start_venv.sh
```

---

## ⚠️ مشكلة: لا يظهر PDF

### التحقق:
```bash
# تحقق من وجود ملفات PDF
ls -la uploads/pdfs/

# تحقق من صلاحيات الملفات
chmod -R 755 uploads/
```

### ✅ الحل:
```bash
# تأكد من وجود المجلدات
mkdir -p uploads/pdfs

# أعد إنشاء الإجازة من البوت
```

---

## ⚠️ مشكلة: قاعدة البيانات مقفلة

### الأعراض:
```
sqlite3.OperationalError: database is locked
```

### ✅ الحل:
```bash
# أوقف جميع الخدمات
pkill -f python3

# احذف ملف القفل إن وجد
rm -f bot_data.db-journal

# أعد التشغيل
./start_venv.sh
```

---

## 📋 أوامر مفيدة

### فحص حالة النظام:
```bash
# عرض جميع العمليات
ps aux | grep python3

# فحص المنافذ
netstat -tuln | grep -E "5000|5001"

# حجم قاعدة البيانات
ls -lh bot_data.db
```

### عرض السجلات:
```bash
# جميع السجلات دفعة واحدة
tail -f logs/*.log

# سجل محدد
tail -f logs/api_server.log
tail -f logs/web_server.log
tail -f logs/bot.log
tail -f logs/auto_cleanup.log
```

### إعادة التشغيل الكامل:
```bash
# إيقاف كل شيء
pkill -f python3

# مسح السجلات (اختياري)
rm -f logs/*.log

# إعادة التشغيل
./start_venv.sh
```

---

## 🔄 الترقية من النسخة القديمة

إذا كنت قد ثبتت النظام بدون بيئة افتراضية:

```bash
# 1. نسخ احتياطي لقاعدة البيانات
cp bot_data.db bot_data.db.backup

# 2. نسخ احتياطي للإعدادات
cp .env .env.backup

# 3. تشغيل التثبيت المحدث
./install_fixed.sh

# 4. استعادة الإعدادات
cp .env.backup .env

# 5. التشغيل
./start_venv.sh
```

---

## 🆘 الحصول على المساعدة

إذا استمرت المشكلة:

1. **تحقق من السجلات:**
   ```bash
   cat logs/api_server.log
   cat logs/web_server.log
   cat logs/bot.log
   ```

2. **تأكد من المتطلبات:**
   ```bash
   python3 --version  # يجب أن يكون 3.8+
   pip3 --version
   ```

3. **تحقق من الإعدادات:**
   ```bash
   cat .env
   ```

4. **راجع التوثيق:**
   - `README_ENHANCED.md` - للتفاصيل الكاملة
   - `QUICKSTART.md` - للبدء السريع

---

## ✅ قائمة التحقق السريع

- [ ] Python 3.8+ مثبت
- [ ] تم تشغيل `install_fixed.sh`
- [ ] البيئة الافتراضية موجودة (مجلد `venv/`)
- [ ] ملف `.env` محدّث بـ BOT_TOKEN
- [ ] المجلدات موجودة (`uploads/pdfs`, `logs`)
- [ ] تم تشغيل `start_venv.sh`
- [ ] جميع الخدمات تعمل (تحقق من `ps aux | grep python3`)

---

**💡 نصيحة:** احتفظ دائماً بنسخة احتياطية من `bot_data.db` و `.env` قبل أي تحديث!
