# نتائج فحص مسار الاستعلام الخارجي

بتاريخ 2026-08-18 تم فحص الرابط العام: https://sehasa.online/#/inquiries/slenquiry

الصفحة تعرض حقلي `service_code` و`national_id` وتنفذ طلبًا إلى:

`/api/verify?gsl=${encodeURIComponent(gsl)}&id=${encodeURIComponent(id)}`

عند اختبار:

- رمز الخدمة: `VCC26092162302`
- رقم الهوية: `1074820224`

أعاد الموقع HTTP 404 والرسالة: `لم يُعثر على العذر الطبي` قبل إضافة مسار شهادات التطعيم.

الاستنتاج: الموقع يستخدم `web.py` كواجهة Flask وفق `Procfile.web`، ومسار `/api/verify` كان يبحث في جدول `orders` الخاص بالإجازات الطبية فقط. تم بدء إضافة فرع `VCC` ليبحث في جدول `vaccine_records` ويطابق رقم الهوية داخل `data_json`.
