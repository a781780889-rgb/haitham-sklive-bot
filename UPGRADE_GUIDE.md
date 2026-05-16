# دليل الترقية الشامل — النظام الذكي للمدن والمستشفيات
## haitham-sklive-bot — Production-Level Upgrade

---

## 📦 الملفات الجديدة

| الملف | الوظيفة |
|-------|---------|
| `cities_hospitals_ui.py` | نظام InlineKeyboard للمدن/المستشفيات |
| `admin_cities_handler.py` | إدارة CRUD كاملة للمشرفين |
| `ai_data_processor.py` | محرك AI معزَّز لاستخراج البيانات |
| `bot_integration_patch.py` | خارطة طريق التكامل مع bot.py |

---

## 🏗️ Architecture Overview

```
bot.py
  ├── handle_message()
  │     ├── CitiesHospitalsFlow.handle_text_search()  ← جديد
  │     ├── AdminCitiesHospitalsRouter.handle_text()   ← جديد
  │     └── collecting_data → ai_data_processor.process_and_merge() ← جديد
  │
  ├── handle_inline_callback()  ← دالة جديدة كاملة
  │     ├── CitiesHospitalsFlow.handle_callback()
  │     └── AdminCitiesHospitalsRouter.handle_callback()
  │
  └── main()
        └── CallbackQueryHandler(handle_inline_callback) ← جديد

cities_hospitals_ui.py
  ├── build_cities_keyboard()     → InlineKeyboard مع صفحات + بحث
  ├── build_hospitals_keyboard()  → InlineKeyboard مع فلاتر + صفحات + بحث
  └── CitiesHospitalsFlow         → إدارة التدفق الكامل

admin_cities_handler.py
  ├── AdminAddHospitalFlow        → إضافة مستشفى (5 خطوات)
  ├── AdminDeleteHospitalFlow     → حذف مستشفى (3 خطوات)
  ├── AdminDeleteCityFlow         → حذف مدينة + cascade (2 خطوات)
  └── AdminCitiesHospitalsRouter  → router مركزي

ai_data_processor.py
  ├── SmartDataExtractor          → استخراج الحقول بـ 4 طرق
  ├── smart_merge()               → دمج البيانات بالأوزان
  ├── build_missing_prompt()      → رسائل ودودة للبيانات الناقصة
  └── build_smart_preview()       → معاينة جميلة للبيانات
```

---

## 🔄 تدفق اختيار المدينة والمستشفى (الجديد)

```
المستخدم → "📝 إرسال طلب جديد"
    │
    ▼
CitiesHospitalsFlow.start()
    │
    ▼ [InlineKeyboard]
صفحة المدن (15 مدينة/صفحة)
  🔍 ابحث عن مدينة...
  🏙 الرياض  🏙 جدة  🏙 مكة
  🏙 الدمام  🏙 الطائف  🏙 المدينة
  ◀️ السابق  📄 1/5  التالي ▶️
  ❌ إلغاء
    │
    ▼ [يضغط على مدينة]
صفحة المستشفيات
  🏛 حكومي  🏢 خاص  🏗 مجمعات  ← فلاتر النوع
  🔍 ابحث عن مستشفى...
  🏛 مستشفى الملك فهد  🏢 مستشفى الدكتور
  🏛 المستشفى العسكري   🏢 مركز الأطباء
  ◀️ السابق  📄 2/8  التالي ▶️
  🏙️ تغيير المدينة  ❌ إلغاء
    │
    ▼ [يضغط على مستشفى]
_on_hospital_selected() → choose_doctor → ...
```

---

## 🔍 نظام البحث الذكي

```
المستخدم → يضغط "🔍 ابحث عن مدينة..."
    │
    ▼
"اكتب اسم المدينة في الرسالة التالية 👇"
    │
    ▼ [يكتب: "جد"]
CitiesHospitalsFlow.handle_text_search()
    │
    ▼
build_cities_keyboard(search_query="جد")
  → فلترة: جدة (90%)
  → "🔍 نتائج البحث عن: جد — وُجد 1 مدينة"
```

---

## 🛡️ كشف التكرار الذكي

عند إضافة مستشفى جديد:

```
المشرف → "مستشفى الملك فهد"
    │
    ▼
DuplicateIndex.check("مستشفى الملك فهد")
  ↓ Levenshtein + Token + Translation
  ↓ يجد: "مستشفي الملك فهد" (96%)
    │
    ▼
⚠️ تحذير التكرار:
  🔴 مستشفي الملك فهد — شبه متطابق (96%)
  [✅ استخدم الموجود] [➕ أضف رغم ذلك] [✏️ غيّر الاسم]
```

---

## ⚡ نظام الكاش

| الكاش | المدة | الاستخدام |
|-------|-------|-----------|
| `ui:all_cities` | 15 دقيقة | قائمة المدن |
| `ui:hosp:{city}:{type}` | 10 دقائق | مستشفيات مدينة |
| `_hospitals_cache` | 10 دقائق | البيانات العامة |
| `_buttons_cache` | 30 دقيقة | أزرار التنقل |

**Invalidation تلقائي عند:**
- إضافة مستشفى → `invalidate_ui_cache(city)`
- حذف مستشفى → `invalidate_ui_cache(city)`
- حذف مدينة → `invalidate_ui_cache()` (كامل)

---

## 📝 خطوات التطبيق

### 1. نسخ الملفات الجديدة إلى مجلد المشروع
```bash
cp cities_hospitals_ui.py    /path/to/bot/
cp admin_cities_handler.py   /path/to/bot/
cp ai_data_processor.py      /path/to/bot/
```

### 2. تحديث bot.py

افتح `bot_integration_patch.py` واتبع الخطوات 1-7 المشروحة فيه.

### 3. التحقق من التوافق
```python
# اختبر الاستيراد:
from cities_hospitals_ui import CitiesHospitalsFlow
from admin_cities_handler import AdminCitiesHospitalsRouter
from ai_data_processor import ai_process, process_and_merge
```

### 4. تحديث requirements.txt (لا تغيير مطلوب)
جميع المكتبات المستخدمة موجودة مسبقاً.

---

## 🔧 ملاحظات مهمة

1. **Backward Compatibility**: الملفات القديمة (smart_parser.py, ai_nlp_engine.py, etc.) لا تُحذف، بل تظل كـ fallback.

2. **callback_data limit**: جميع الـ callbacks مقيّدة بـ 64 بايت (حد Telegram).

3. **الأمان**: لا يُمكن الإدخال اليدوي للمدن/المستشفيات — الأزرار فقط.

4. **الكاش**: `invalidate_ui_cache()` يُستدعى تلقائياً بعد كل تعديل.

5. **المدن الجديدة**: إضافة مدينة جديدة تتطلب إضافتها لـ `hospitals_data.py` أو قاعدة البيانات.

---

## 🌟 المميزات الجديدة مقارنة بالنسخة القديمة

| الميزة | قبل | بعد |
|--------|-----|-----|
| اختيار المدينة | ReplyKeyboard ثابتة (6 مدن) | InlineKeyboard ديناميكي (كل المدن) |
| البحث | غير متاح | 🔍 بحث فوري داخل الأزرار |
| الصفحات | غير متاح | Pagination تلقائي |
| فلاتر النوع | منفصلة | مدمجة في نفس الشاشة |
| كشف التكرار | نصي بسيط | Levenshtein + Translation |
| إضافة مستشفى | نموذج نصي | InlineKeyboard تدريجي |
| AI لاستخراج البيانات | Regex فقط | 4 طرق بالتوازي |
| رسائل الخطأ | تقنية | ودودة + أمثلة |
