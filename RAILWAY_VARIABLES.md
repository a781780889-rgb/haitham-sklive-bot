# 🚂 متغيرات Railway المطلوبة

## الخطوات:
1. Railway → مشروعك → Service → Variables
2. أضف المتغيرات التالية:

| المتغيّر | مطلوب | الوصف |
|---------|-------|-------|
| `BOT_TOKEN` | ✅ إجباري | توكن البوت من @BotFather |
| `ADMIN_IDS` | ✅ إجباري | معرّف الأدمن من @userinfobot |
| `ADMIN_PASS` | ✅ إجباري | كلمة سر لوحة التحكم |
| `IBAN` | ✅ إجباري | رقم الآيبان |
| `PAYMENT_NAME` | ✅ إجباري | اسم صاحب الحساب |
| `STC_NUMBER` | ✅ إجباري | رقم STC Pay |
| `DATABASE_URL` | 🔄 تلقائي | يُضاف تلقائياً عند ربط PostgreSQL |
| `PORT` | 🔄 تلقائي | Railway يضبطه تلقائياً |

## ربط PostgreSQL:
1. داخل المشروع → + New → Database → Add PostgreSQL
2. DATABASE_URL يُضاف تلقائياً ✅

## بعد الإعداد:
- ادفع الكود لـ GitHub → Railway يعيد النشر تلقائياً
- تحقق من Logs: يجب أن ترى `🐘 db_adapter: تم تفعيل وضع PostgreSQL`
