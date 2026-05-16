# 📋 سجل التغييرات — النظام الذكي v3
## Production-Level Upgrade — Bot Enhancement

---

## 🆕 الملفات الجديدة

### `normalizer.py` — محرك التطبيع الشامل
- ✅ تطبيع الهمزات (أ / إ / آ / ٱ / ا → ا)
- ✅ توحيد التاء المربوطة (ة → ه)
- ✅ توحيد الياء والألف المقصورة (ى → ي)
- ✅ إزالة التشكيل والتطويل
- ✅ تحويل الأرقام العربية/الفارسية ↔ غربية
- ✅ معالجة Unicode (NFC + Zero-Width chars)
- ✅ توحيد المسافات المختلفة
- ✅ كشف لغة النص (عربي / إنجليزي / مختلط)
- ✅ تطبيع الجنسيات (40+ جنسية)
- ✅ تطبيع أرقام الهوية والجوال والتواريخ

### `date_intelligence.py` — محرك فهم التواريخ الذكي
يدعم الصيغ التالية:

| العربية | الإنجليزية |
|---------|------------|
| اليوم | today |
| بكره / غداً / الغد | tomorrow |
| أمس / البارحة | yesterday |
| بعد يومين | the day after tomorrow |
| بعد 3 أيام | in 3 days |
| الأسبوع الجاي | next week |
| الخميس القادم | next thursday |
| قبل يومين / منذ يومين | 2 days ago |

**صيغ التاريخ الرقمية:**
- `12/5` — اليوم/الشهر (يُكمل السنة تلقائياً)
- `12/5/2026` — اليوم/الشهر/السنة
- `2026-05-12` — ISO format
- `12 مايو 2026` — شهر ميلادي عربي
- `12 May 2026` — شهر ميلادي إنجليزي
- `10 رمضان 1447` — تاريخ هجري مع تحويل ميلادي
- جميع أيام الأسبوع بالعربي (الاثنين/الثلاثاء/...)

### `duplicate_detector.py` — كشف التكرار الذكي
- ✅ **Levenshtein Distance** — قياس المسافة التحريرية
- ✅ **Token Jaccard Similarity** — تشابه الكلمات
- ✅ **Prefix Matching** — التطابق من البداية
- ✅ **Cross-Language Translation** — مقارنة عربي-إنجليزي
- ✅ **Abbreviation Expansion** — توسيع الاختصارات
- ✅ **DuplicateIndex** — فهرس بحث سريع مع O(1) lookup
- ✅ رسائل تحذير ذكية مع نسب التشابه

**أمثلة يتم اكتشافها كمكررات:**
```
مستشفى الملك فهد       ← 🔴 شبه متطابق (95%)
مستشفي الملك فهد       ← 🔴 شبه متطابق (95%)
king fahad hospital     ← 🟠 متشابه جداً (88%)
King Fahad Hosp.        ← 🟠 متشابه جداً (85%)
king-fahad-hospital     ← 🟡 متشابه (80%)
```

### `smart_cache.py` — نظام الكاش عالي الأداء
- ✅ **TTL Cache** — انتهاء صلاحية تلقائي
- ✅ **LRU Eviction** — إزالة الأقل استخداماً
- ✅ **Thread-Safe** — آمن للاستخدام في Async
- ✅ **Cache Invalidation** — إبطال تلقائي عند التحديث
- ✅ **Prefix Invalidation** — إبطال مجموعات من المفاتيح
- ✅ **Cache Statistics** — إحصائيات الأداء
- ✅ **Periodic Cleanup** — تنظيف دوري للعناصر المنتهية
- ✅ **Decorator** — `@cached(...)` للدوال

| الكاش | TTL |
|-------|-----|
| المستشفيات | 10 دقائق |
| الأطباء | 5 دقائق |
| الأزرار | 30 دقيقة |
| الإعدادات | دقيقتان |
| المستخدمون | دقيقة واحدة |
| الشعارات | 15 دقيقة |

### `ai_nlp_engine.py` — محرك الذكاء الاصطناعي
- ✅ استخراج ذكي لجميع حقول الطلب
- ✅ دعم الإدخال المهيكل (label: value)
- ✅ دعم النص الحر (بدون فاصل)
- ✅ تعريف الاسم من سياق النص
- ✅ تعريف الجنسية تلقائياً
- ✅ Confidence Scoring لكل حقل
- ✅ Auto-completion للبيانات الناقصة
- ✅ رسائل طلب البيانات الناقصة الودودة

### `smart_validator.py` — محرك التحقق الذكي
- ✅ **مرن** — يقبل أغلب الصيغ المنطقية
- ✅ **ذكي** — رسائل خطأ واضحة وودودة
- ✅ **شامل** — يتحقق من كل الحقول
- ✅ قبول أرقام الهوية السعودية + الإقامة + الجوازات
- ✅ قبول الجوال بجميع الصيغ (05x / 9665x / +9665x)
- ✅ قبول الأسماء الثنائية مع تحذير
- ✅ قبول التواريخ الماضية/المستقبلية مع تنبيه

### `cities_hospitals_manager.py` — مدير المدن والمستشفيات
- ✅ جلب المدن من مصادر متعددة (ملف + DB) مع Cache
- ✅ بناء لوحات مفاتيح تفاعلية ديناميكية
- ✅ **Pagination** تلقائي (20 مستشفى/صفحة)
- ✅ **Search** داخل قوائم المستشفيات
- ✅ إضافة مع كشف التكرار الذكي
- ✅ حذف Cascade (أطباء + شعارات تلقائياً)
- ✅ تحديث مع فحص التكرار قبل الحفظ
- ✅ بناء لوحة تأكيد عند اكتشاف تشابه

---

## 🔄 الملفات المُحسّنة

### `smart_parser.py` (v3)
- ✅ يستخدم `ai_nlp_engine` الآن (بدلاً من regex فقط)
- ✅ دعم التواريخ النسبية الكاملة
- ✅ تحديث تلقائي للحقول (field update detection)
- ✅ دمج ذكي للبيانات (`merge_parsed_data`)
- ✅ Fallback كامل للخوارزمية الأصلية

### `hospital_management.py` (v3)
- ✅ `add_hospital_smart()` — إضافة مع كشف التكرار
- ✅ `delete_hospital_smart()` — حذف Cascade
- ✅ `update_hospital_smart()` — تحديث مع فحص التكرار
- ✅ `get_doctors_by_hospital_name()` — جلب بالاسم مع كاش
- ✅ `get_hospital_logo()` — شعار مع كاش
- ✅ `get_all_hospitals()` — مع كاش عالي الأداء

### `bot.py` (v3)
- ✅ `smart_parse_message()` — بديل محسّن لـ `parse_free_text_order`
- ✅ `smart_parse_date_v3()` — بديل محسّن لـ `normalize_date_input`
- ✅ `validate_hospital_add_smart()` — تحقق مع كشف التكرار
- ✅ `build_enhanced_hospitals_keyboard()` — مع Pagination
- ✅ `show_duplicate_warning()` — عرض تحذير التكرار
- ✅ `/search` command — بحث ذكي في المستشفيات
- ✅ `cmd_cache_stats()` — إحصائيات الكاش للمشرف

---

## 🏗 Architecture المُطوَّرة

```
bot_enhanced/
├── bot.py                     # البوت الرئيسي (محسّن)
├── smart_parser.py            # v3 — يدمج كل المحركات
├── ai_nlp_engine.py           # 🆕 محرك NLP الذكي
├── normalizer.py              # 🆕 التطبيع الشامل
├── date_intelligence.py       # 🆕 فهم التواريخ الذكي
├── duplicate_detector.py      # 🆕 كشف التكرار
├── smart_cache.py             # 🆕 الكاش عالي الأداء
├── smart_validator.py         # 🆕 التحقق المرن
├── cities_hospitals_manager.py# 🆕 مدير التفاعلي
├── hospital_management.py     # محسّن (v3 methods)
├── hospitals_data.py          # بيانات ثابتة (بدون تغيير)
├── database.py                # قاعدة البيانات (بدون تغيير)
├── db_adapter.py              # محول SQLite/PostgreSQL
├── pdf_gen.py                 # توليد PDF (بدون تغيير)
└── requirements_enhanced.txt  # 🆕 متطلبات محدّثة
```

---

## ⚙️ طريقة التشغيل

```bash
pip install -r requirements_enhanced.txt
python bot.py
```

---

## 🔒 Backward Compatibility

✅ جميع الدوال القديمة تعمل بدون تغيير  
✅ النظام الجديد يعمل كـ Enhancement فوق الأصلي  
✅ عند فشل أي محرك جديد → Fallback للأصلي تلقائياً  
✅ لا توجد وظيفة أصلية تم كسرها أو تعديلها بشكل مُخرِّب
