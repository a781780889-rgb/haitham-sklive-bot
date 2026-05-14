# دليل تكامل نظام معالجة البيانات الذكي v4.0
# INTEGRATION_SMART_ENGINE.md
# ══════════════════════════════════════════════

## الملفات المُضافة

| الملف | الوصف |
|---|---|
| `smart_data_engine.py` | المحرك الرئيسي الجديد (13 قسم متكامل) |
| `bot_smart_patch.py` | طبقة التكامل مع bot.py (backward compatible) |

---

## خطوات التكامل في bot.py (3 خطوات فقط)

### الخطوة 1: إضافة الاستيراد في بداية bot.py

```python
# في بداية bot.py، بعد الـ imports الحالية، أضف:
try:
    from bot_smart_patch import (
        sde_parse,
        sde_missing,
        sde_missing_prompt,
        sde_preview,
        sde_date,
        sde_validate,
        sde_merge,
        process_patient_message,
        sde_engine_status,
    )
    _SMART_ENGINE = True
    logger.info("✅ Smart Data Engine v4.0 محمّل")
except ImportError as e:
    _SMART_ENGINE = False
    logger.warning(f"⚠️ Smart Engine غير متوفر: {e}")
```

---

### الخطوة 2: تحديث دالة handle_message في collecting_data state

**الكود الحالي (في bot.py حول السطر 1480):**
```python
if state == "collecting_data":
    parsed = smart_parse_full(text)
    if not parsed:
        parsed = parse_free_text_order(text)
    if not parsed:
        await update.message.reply_text("🤖 لم أتمكن من التعرف...")
        return
    od = context.user_data.get("order_data", {})
    # ... باقي الكود
```

**استبدله بـ:**
```python
if state == "collecting_data":
    # ── المحرك الذكي الجديد ──
    if _SMART_ENGINE:
        proc = process_patient_message(text, context.user_data.get("order_data", {}))
        parsed = proc["parsed"]
        od     = proc["merged"]
    else:
        parsed = smart_parse_full(text) or parse_free_text_order(text)
        od = context.user_data.get("order_data", {})

    if not parsed:
        await update.message.reply_text(
            "🤖 *لم أتمكن من التعرف على البيانات.*\n\n"
            "💡 يمكنك الإرسال بأي صيغة، مثلاً:\n"
            "`الاسم: محمد علي`\n"
            "`رقم الهوية: 1234567890`\n"
            "`جهة العمل: وزارة الصحة`\n\n"
            "أو أرسل البيانات كلها دفعة واحدة.",
            parse_mode="Markdown", reply_markup=back_keyboard()
        )
        return

    # ── تحقق من الأخطاء الحرجة ──
    if _SMART_ENGINE and proc.get("errors"):
        for err_msg in proc["errors"]:
            await update.message.reply_text(
                err_msg,
                parse_mode="Markdown", reply_markup=back_keyboard()
            )
        return

    # ── دمج البيانات ──
    if "excuse_date" in parsed:
        od["excuse_date"] = parsed.pop("excuse_date")
    if "exit_date" in parsed:
        od["exit_date"] = parsed.pop("exit_date")
    if "days_count" in parsed:
        od["days_count"] = parsed.pop("days_count")
    od.update(parsed)
    context.user_data["order_data"] = od

    # ── التحقق من الحقول الناقصة ──
    missing = get_missing(od)  # يعمل مع القديم والجديد

    if missing:
        received_lines = []
        labels_map = {
            'full_name': 'الاسم', 'id_number': 'رقم الهوية',
            'workplace': 'جهة العمل', 'nationality': 'الجنسية',
            'excuse_date': 'تاريخ الإجازة',
        }
        for key, label in labels_map.items():
            if od.get(key):
                received_lines.append(f"  ✅ {label}: *{od[key]}*")

        received_block = "\n".join(received_lines)
        missing_prompt = build_missing_prompt(od)

        # إضافة تحذيرات (إن وجدت)
        warn_text = ""
        if _SMART_ENGINE and proc.get("warnings"):
            warn_text = "\n".join(proc["warnings"]) + "\n\n"

        reply = ""
        if received_block:
            reply = f"📥 *تم استيعاب:*\n{received_block}\n\n"
        reply += warn_text + missing_prompt

        await update.message.reply_text(
            reply,
            parse_mode="Markdown", reply_markup=back_keyboard()
        )
    else:
        context.user_data["state"]      = "confirm_order"
        context.user_data["prev_state"] = "collecting_data"
        context.user_data.setdefault("license_enabled", False)

        preview = build_smart_preview(od, context.user_data)

        await update.message.reply_text(
            "✅ *تم استلام جميع البيانات بنجاح!*\n\n" + preview,
            parse_mode="Markdown",
            reply_markup=confirm_keyboard()
        )
        await update.message.reply_text(
            "👆 *راجع البيانات ثم اضغط تأكيد:*",
            parse_mode="Markdown",
            reply_markup=confirm_inline_keyboard(context.user_data.get("license_enabled", False))
        )
    return
```

---

### الخطوة 3: استبدال دوال البناء والمعاينة (اختياري للتحسين)

في أي مكان في bot.py يستخدم:
- `smart_parse_full(text)` → استبدل بـ `sde_parse(text)`
- `get_missing(od)` → يبقى كما هو (متوافق)
- `build_missing_prompt(od)` → يبقى كما هو (متوافق)
- `build_smart_preview(od, ctx)` → يبقى كما هو (متوافق)
- `parse_any_date(raw)` → استبدل بـ `sde_date(raw)`

---

## مميزات النظام الجديد

### 1. فهم ذكي للبيانات
```
الإدخال: "اسمي خالد وشغلي في أرامكو وهويتي 1234567890 والاجازة بكره"
النتيجة: {full_name: "خالد", workplace: "أرامكو", id_number: "1234567890", excuse_date: "15/05/2026"}
```

### 2. معالجة التواريخ الذكية
```
"اليوم"           → 14/05/2026
"بكره"            → 15/05/2026
"بعد 3 أيام"      → 17/05/2026
"الأسبوع القادم"  → 18/05/2026
"الخميس"          → 15/05/2026 (الخميس القادم)
"15/5"            → 15/05/2026
"15 مايو"         → 15/05/2026
"١٥/٥/١٤٤٧"      → يُحوّل من هجري لميلادي
```

### 3. تطبيع الجنسيات
```
"سعوديه" / "saudi" / "KSA"  → "سعودي"
"مصرى" / "egyptian"         → "مصري"
"يمنيه" / "yemeni"          → "يمني"
```

### 4. تطبيع المدن
```
"جده" / "jeddah" / "جدا"   → "جدة"
"مكه" / "mecca"             → "مكة المكرمة"
"رياض" / "riyadh"           → "الرياض"
```

### 5. ترجمة الأسماء (بشرية وليست حرفية)
```
"حكيم"    → "Hakim"   (وليس SAGE)
"اليمن"   → "Yemen"   (وليس "the Yemen")
"خالد"    → "Khalid"
"فاطمة"   → "Fatimah"
```

### 6. التحقق الشامل
```
رقم هوية خاطئ        → رسالة واضحة
تاريخ إجازة قديم      → تحذير
اسم ناقص (كلمة واحدة) → طلب التكملة
مدينة = دولة أجنبية   → تحذير بالتصحيح
```

### 7. الحماية من الانهيار
- جميع الدوال محاطة بـ try/catch
- Fallback تلقائي للمحرك القديم عند الفشل
- تسجيل احترافي لكل الأخطاء
- LocalCache لتحسين الأداء

---

## الأسئلة الشائعة

**Q: هل سيتأثر البوت الحالي؟**
A: لا. النظام الجديد يعمل كطبقة إضافية فوق الكود القديم. عند فشله يعود للمحرك القديم تلقائياً.

**Q: هل يحتاج مكتبات إضافية؟**
A: لا. كل شيء مبني بـ Python القياسي فقط (re, datetime, logging, unicodedata).

**Q: هل يدعم التقويم الهجري؟**
A: نعم، يدعم تحويل التواريخ الهجرية تقريبياً للميلادية.

**Q: كيف أتحقق أن المحرك يعمل؟**
A: أضف في بداية البوت:
```python
from bot_smart_patch import sde_engine_status
print(sde_engine_status())
# {'engine_loaded': True, 'fallback_loaded': True, 'version': '4.0'}
```
