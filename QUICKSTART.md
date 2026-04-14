# 🚀 دليل البدء السريع - نظام الأعذار الطبية

## ⚡ التثبيت والتشغيل في 5 دقائق

### 1️⃣ التثبيت (مرة واحدة)

```bash
# فك ضغط الملف
unzip enhanced_bot.zip
cd enhanced_bot

# تشغيل سكريبت التثبيت
chmod +x install.sh
./install.sh
```

### 2️⃣ التكوين

```bash
# تحرير ملف الإعدادات
nano .env

# قم بتحديث هذه القيم:
BOT_TOKEN=your_telegram_bot_token_here  # 👈 مهم!
```

### 3️⃣ التشغيل

```bash
# تشغيل جميع الخدمات
./start_all.sh
```

**✅ تم! النظام يعمل الآن**

---

## 🌐 الوصول للخدمات

| الخدمة | الرابط | الوصف |
|--------|--------|-------|
| 🌐 موقع الاستعلام | http://localhost:5000 | للمستخدمين |
| 📡 API Server | http://localhost:5001 | داخلي فقط |
| 🤖 Telegram Bot | @YourBotName | على تيليجرام |

---

## 📱 استخدام البوت

### إنشاء إجازة مرضية:

1. ابدأ محادثة مع البوت: `/start`
2. اختر "إنشاء إجازة"
3. املأ البيانات المطلوبة
4. احصل على:
   - ملف PDF
   - رمز الإجازة (GSL######)
   - رابط الاستعلام

### الاستعلام عن إجازة:

1. افتح الموقع: http://localhost:5000
2. أدخل:
   - رمز الإجازة
   - رقم الهوية
3. شاهد:
   - تفاصيل الإجازة
   - معاينة PDF

---

## 🛠️ أوامر مفيدة

```bash
# فحص حالة الخدمات
ps aux | grep python3

# عرض السجلات
tail -f logs/api_server.log
tail -f logs/web_server.log
tail -f logs/bot.log

# إيقاف الخدمات
# اضغط Ctrl+C في نافذة start_all.sh

# إعادة التشغيل
./start_all.sh
```

---

## 🔧 استكشاف الأخطاء

### ❌ البوت لا يعمل

```bash
# تحقق من BOT_TOKEN
cat .env | grep BOT_TOKEN

# تحقق من السجلات
tail -f logs/bot.log
```

### ❌ الموقع لا يفتح

```bash
# تحقق من المنفذ
netstat -tuln | grep 5000

# أعد تشغيل Web Server
python3 web_enhanced.py
```

### ❌ لا يظهر PDF

```bash
# تحقق من ملفات PDF
ls -la uploads/pdfs/

# تحقق من API
curl http://localhost:5001/api/health
```

---

## 📊 أوامر المشرف في البوت

```
/api_stats  - إحصائيات النظام
/cleanup    - تنظيف السجلات القديمة
/check_api  - فحص API Server
/website    - رابط الموقع
```

---

## 🔒 الأمان والخصوصية

✅ **حذف تلقائي:** البيانات تُحذف بعد 90 يوماً
✅ **تشفير:** جميع الاتصالات محمية
✅ **مفاتيح API:** تأمين الوصول لـ API
✅ **سجلات الوصول:** تتبع جميع الاستعلامات

---

## 📁 بنية الملفات

```
enhanced_bot/
├── api_server.py           # خادم API
├── web_enhanced.py         # موقع الويب
├── bot_enhanced.py         # بوت تيليجرام
├── bot_api_integration.py  # طبقة التكامل
├── auto_cleanup.py         # التنظيف التلقائي
├── database.py             # قاعدة البيانات
├── pdf_gen.py              # توليد PDF
├── start_all.sh            # تشغيل شامل
├── install.sh              # التثبيت
├── .env                    # الإعدادات
├── requirements.txt        # المتطلبات
├── logs/                   # السجلات
├── uploads/pdfs/           # ملفات PDF
└── README_ENHANCED.md      # الدليل الشامل
```

---

## 🚀 للإنتاج (Production)

### استخدام Nginx + SSL:

```bash
# 1. تثبيت Nginx
sudo apt install nginx

# 2. نسخ التكوين
sudo cp nginx_config.conf /etc/nginx/sites-available/seha
sudo ln -s /etc/nginx/sites-available/seha /etc/nginx/sites-enabled/

# 3. تثبيت SSL (Let's Encrypt)
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com

# 4. إعادة تشغيل Nginx
sudo systemctl restart nginx
```

### استخدام Systemd:

```bash
# راجع ملف systemd_services.txt للتفاصيل
sudo systemctl enable seha-api
sudo systemctl enable seha-web
sudo systemctl enable seha-bot
sudo systemctl start seha-api seha-web seha-bot
```

---

## 📞 المساعدة

📚 **الدليل الشامل:** README_ENHANCED.md
📝 **السجلات:** logs/
🐛 **الأخطاء:** تحقق من السجلات أولاً

---

## ✨ الميزات الرئيسية

✅ ربط البوت بالموقع عبر API آمن
✅ واجهة استعلام احترافية
✅ عرض PDF مباشر في الموقع
✅ حذف تلقائي بعد 90 يوم
✅ تشفير وحماية شاملة
✅ سجلات مفصلة
✅ سهولة في الصيانة
✅ جاهز للإنتاج

---

**🎉 استمتع باستخدام النظام!**
