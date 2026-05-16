#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
delete_system.py ─ نظام الحذف الاحترافي المتكامل
══════════════════════════════════════════════════════════════════════════
يغطي ثلاثة أنظمة:
  1. حذف المستشفيات   (+ شعاراتها + أطبائها الإضافيين)
  2. حذف شعارات المستشفيات فقط (بدون حذف المستشفى)
  3. حذف الأطباء      (+ دعم بحث بالاسم / المستشفى / التخصص)

كيفية التكامل مع bot.py:
─────────────────────────
1. في أعلى bot.py أضف:
       import delete_system

2. داخل handle_callback ─ قبل السطر الأخير return ─ أضف:
       if data.startswith("del_"):
           await delete_system.handle_delete_callback(query, uid, data, context)
           return

3. داخل handle_message، في الكتلة المخصصة للمشرفين أضف:
       if text == "🗑️ حذف مستشفى":
           await delete_system.start_delete_hospitals(update, context)
           return
       if text == "🗑️ حذف شعار":
           await delete_system.start_delete_logos(update, context)
           return
       if text == "🗑️ حذف طبيب":
           await delete_system.start_delete_doctors(update, context)
           return
       if state and state.startswith("del_search_"):
           await delete_system.handle_search_input(update, context, uid, text)
           return
══════════════════════════════════════════════════════════════════════════
"""

import logging
import os
from datetime import datetime
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from telegram.ext import ContextTypes
from telegram.error import BadRequest

import database as db

logger = logging.getLogger(__name__)

# ─── إعدادات الصفحات ────────────────────────────────────────────────────────
PAGE_SIZE   = 8   # عدد العناصر في كل صفحة
COLS        = 2   # عدد الأزرار في كل صف

# ─── أنواع العمليات لسجل الـ Log ─────────────────────────────────────────────
LOG_DELETE_HOSPITAL = "DELETE_HOSPITAL"
LOG_DELETE_LOGO     = "DELETE_LOGO"
LOG_DELETE_DOCTOR   = "DELETE_DOCTOR"


# ══════════════════════════════════════════════════════════════════════════════
#  مساعدات قاعدة البيانات (توافق مع database.py الأصلي + hospital_management.py)
# ══════════════════════════════════════════════════════════════════════════════

def _get_hospital_by_id(hospital_id: int) -> Optional[dict]:
    """يجلب بيانات المستشفى من DB بما يتوافق مع كلا الجدولين."""
    conn = db.get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM hospitals WHERE id=?", (hospital_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _count_doctors_for_hospital(hospital_id: int) -> int:
    conn = db.get_conn()
    try:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM doctors WHERE hospital_id=?",
            (hospital_id,)
        ).fetchone()
        return row["cnt"] if row else 0
    finally:
        conn.close()


def _hospital_has_logo(hospital: dict) -> bool:
    lp = hospital.get("logo_path") or ""
    return bool(lp.strip())


def _delete_hospital_logo_from_storage(hospital: dict) -> bool:
    """يحذف ملف الشعار من file_storage إذا وُجد."""
    try:
        from file_storage import delete_file, logo_key
        lp = hospital.get("logo_path") or ""
        if lp.startswith("db:"):
            fkey = lp[3:]
            delete_file(fkey)
            return True
        # أيضاً حاول عبر logo_key القياسي
        try:
            fkey = logo_key(hospital.get("name", ""))
            delete_file(fkey)
        except Exception:
            pass
        # حذف ملف على القرص إذا وُجد
        if lp and not lp.startswith("db:") and os.path.exists(lp):
            os.remove(lp)
        return True
    except Exception as e:
        logger.warning(f"⚠️ فشل حذف ملف الشعار: {e}")
        return False


def _full_delete_hospital(hospital_id: int) -> dict:
    """
    حذف شامل وآمن للمستشفى:
    - الشعار من file_storage
    - الأطباء المرتبطين
    - سجل المستشفى من DB
    يُعيد dict يحتوي على ملخص ما تم حذفه.
    """
    h = _get_hospital_by_id(hospital_id)
    if not h:
        return {"success": False, "reason": "المستشفى غير موجود"}

    h_name       = h.get("name", "غير معروف")
    h_city       = h.get("city", "—")
    doctors_count = _count_doctors_for_hospital(hospital_id)
    had_logo     = _hospital_has_logo(h)

    # 1. حذف الشعار
    if had_logo:
        _delete_hospital_logo_from_storage(h)

    conn = db.get_conn()
    try:
        # 2. حذف الأطباء المرتبطين
        conn.execute("DELETE FROM doctors WHERE hospital_id=?", (hospital_id,))
        # 3. حذف قوالب PDF المرتبطة
        try:
            conn.execute(
                "DELETE FROM pdf_templates WHERE hospital_id=?", (hospital_id,)
            )
        except Exception:
            pass
        # 4. حذف المستشفى نفسه
        conn.execute("DELETE FROM hospitals WHERE id=?", (hospital_id,))
        conn.commit()
    finally:
        conn.close()

    return {
        "success"       : True,
        "name"          : h_name,
        "city"          : h_city,
        "doctors_deleted": doctors_count,
        "logo_deleted"  : had_logo,
        "items_total"   : 1 + doctors_count + (1 if had_logo else 0),
    }


def _delete_logo_only(hospital_id: int) -> dict:
    """يحذف شعار المستشفى فقط دون المساس ببيانات المستشفى أو أطبائه."""
    h = _get_hospital_by_id(hospital_id)
    if not h:
        return {"success": False, "reason": "المستشفى غير موجود"}

    if not _hospital_has_logo(h):
        return {"success": False, "reason": "لا يوجد شعار مرتبط بهذا المستشفى"}

    _delete_hospital_logo_from_storage(h)

    # حذف المسار من عمود logo_path في جدولَي hospitals (db.py و hospital_management.py)
    conn = db.get_conn()
    try:
        conn.execute(
            "UPDATE hospitals SET logo_path=NULL WHERE id=?", (hospital_id,)
        )
        conn.commit()
    finally:
        conn.close()

    # حذف من جدول logos في hospital_management إذا وُجد
    try:
        from db_adapter import get_connection
        conn2 = get_connection()
        conn2.execute("DELETE FROM logos WHERE hospital_id=?", (hospital_id,))
        conn2.commit()
        conn2.close()
    except Exception:
        pass

    return {
        "success": True,
        "name"   : h.get("name", "غير معروف"),
        "city"   : h.get("city", "—"),
    }


def _full_delete_doctor(doctor_id: int) -> dict:
    """حذف شامل وآمن لطبيب."""
    conn = db.get_conn()
    try:
        row = conn.execute(
            """SELECT d.*, h.name as hospital_name
               FROM doctors d
               LEFT JOIN hospitals h ON d.hospital_id=h.id
               WHERE d.id=?""",
            (doctor_id,)
        ).fetchone()
        if not row:
            return {"success": False, "reason": "الطبيب غير موجود"}

        doc = dict(row)
        conn.execute("DELETE FROM doctors WHERE id=?", (doctor_id,))
        conn.commit()
    finally:
        conn.close()

    return {
        "success"   : True,
        "name"      : doc.get("name", "—"),
        "specialty" : doc.get("specialty", "—"),
        "hospital"  : doc.get("hospital_name", "—"),
    }


def _log_operation(admin_id: int, op_type: str, element_name: str, details: str = ""):
    """يسجّل عملية الحذف في جدول activity_log."""
    try:
        conn = db.get_conn()
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            """INSERT INTO activity_log (user_id, action, details, created_at)
               VALUES (?,?,?,?)""",
            (
                admin_id,
                f"{op_type}: {element_name}",
                details or ts,
                ts,
            )
        )
        conn.commit()
        conn.close()
        logger.info(f"[LOG] {op_type} | العنصر: {element_name} | المشرف: {admin_id}")
    except Exception as e:
        logger.warning(f"⚠️ فشل تسجيل العملية: {e}")


# ══════════════════════════════════════════════════════════════════════════════
#  دوال بناء لوحات المفاتيح Inline
# ══════════════════════════════════════════════════════════════════════════════

def _build_list_keyboard(
    items: list,
    page: int,
    prefix: str,
    id_key: str = "id",
    label_fn=None,
) -> InlineKeyboardMarkup:
    """
    يبني لوحة مفاتيح Inline مع Pagination.
    prefix:   بادئة callback_data  مثل "del_hosp_pick"
    id_key:   اسم حقل المعرف في كل عنصر
    label_fn: دالة تحوّل العنصر إلى نص الزر
    """
    total     = len(items)
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page      = max(0, min(page, total_pages - 1))
    start     = page * PAGE_SIZE
    page_items = items[start: start + PAGE_SIZE]

    # ─── صفوف الأزرار ─────────────────────────────────────────────────────
    rows = []
    row  = []
    for i, item in enumerate(page_items):
        label = label_fn(item) if label_fn else str(item.get("name", item.get(id_key)))
        btn   = InlineKeyboardButton(label, callback_data=f"{prefix}:{item[id_key]}")
        row.append(btn)
        if len(row) == COLS:
            rows.append(row)
            row = []
    if row:
        rows.append(row)

    # ─── شريط التنقل ──────────────────────────────────────────────────────
    nav = []
    list_prefix = prefix.rsplit("_pick", 1)[0].rsplit("_", 1)
    # استخراج الموضوع من البادئة: del_hosp / del_logo / del_doc
    topic = "_".join(prefix.split("_")[:2])   # del_hosp / del_logo / del_doc

    if page > 0:
        nav.append(InlineKeyboardButton("◀️ السابق", callback_data=f"{topic}_list:{page-1}"))
    nav.append(InlineKeyboardButton(f"📄 {page+1}/{total_pages}", callback_data="del_noop"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("التالي ▶️", callback_data=f"{topic}_list:{page+1}"))
    if nav:
        rows.append(nav)

    # ─── أزرار المساعدة ───────────────────────────────────────────────────
    rows.append([
        InlineKeyboardButton("🔍 بحث", callback_data=f"{topic}_search"),
        InlineKeyboardButton("🔄 تحديث", callback_data=f"{topic}_list:0"),
    ])
    rows.append([InlineKeyboardButton("❌ إلغاء", callback_data="del_cancel")])

    return InlineKeyboardMarkup(rows)


def _confirm_keyboard(confirm_cb: str, cancel_cb: str = "del_cancel") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ تأكيد الحذف", callback_data=confirm_cb),
            InlineKeyboardButton("❌ إلغاء",        callback_data=cancel_cb),
        ]
    ])


def _back_keyboard(back_cb: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ رجوع", callback_data=back_cb)]
    ])


# ══════════════════════════════════════════════════════════════════════════════
#  1. نظام حذف المستشفيات
# ══════════════════════════════════════════════════════════════════════════════

async def start_delete_hospitals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نقطة الدخول: يُظهر قائمة المستشفيات الأولى."""
    hospitals = db.get_all_hospitals()
    if not hospitals:
        await update.message.reply_text("❌ لا توجد مستشفيات مسجّلة في قاعدة البيانات.")
        return

    context.user_data["del_hospitals_cache"] = hospitals
    total = len(hospitals)

    keyboard = _build_list_keyboard(
        items    = hospitals,
        page     = 0,
        prefix   = "del_hosp_pick",
        label_fn = lambda h: f"🏥 {h['name']} — {h.get('city','')}"
    )

    await update.message.reply_text(
        f"🗑️ *حذف مستشفى*\n\n"
        f"📊 إجمالي المستشفيات: *{total}*\n"
        f"اختر المستشفى الذي تريد حذفه:",
        parse_mode="Markdown",
        reply_markup=keyboard
    )


async def _show_hospitals_page(query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE, page: int):
    hospitals = context.user_data.get("del_hospitals_cache") or db.get_all_hospitals()
    context.user_data["del_hospitals_cache"] = hospitals

    keyboard = _build_list_keyboard(
        items    = hospitals,
        page     = page,
        prefix   = "del_hosp_pick",
        label_fn = lambda h: f"🏥 {h['name']} — {h.get('city','')}"
    )

    try:
        await query.edit_message_text(
            f"🗑️ *حذف مستشفى*\n\n"
            f"📊 إجمالي المستشفيات: *{len(hospitals)}*\n"
            f"اختر المستشفى الذي تريد حذفه:",
            parse_mode="Markdown",
            reply_markup=keyboard
        )
    except BadRequest:
        pass


async def _hospital_confirm_page(query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE, hospital_id: int):
    h = _get_hospital_by_id(hospital_id)
    if not h:
        await query.edit_message_text("❌ لم يُعثر على المستشفى.")
        return

    doctors_count = _count_doctors_for_hospital(hospital_id)
    has_logo      = _hospital_has_logo(h)

    text = (
        f"⚠️ *تأكيد حذف المستشفى*\n\n"
        f"🏥 الاسم:    *{h['name']}*\n"
        f"🏙️ المدينة: *{h.get('city','—')}*\n"
        f"👨‍⚕️ الأطباء المرتبطون: *{doctors_count}*\n"
        f"🖼️ يوجد شعار: *{'نعم ─ سيُحذف' if has_logo else 'لا'}*\n\n"
        f"🚨 سيتم حذف المستشفى وجميع بياناته المرتبطة بشكل *نهائي* ولا يمكن التراجع!"
    )

    context.user_data["del_hosp_pending_id"] = hospital_id

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=_confirm_keyboard(
            confirm_cb=f"del_hosp_do:{hospital_id}",
            cancel_cb ="del_hosp_list:0"
        )
    )


async def _execute_delete_hospital(query: CallbackQuery, uid: int, hospital_id: int):
    result = _full_delete_hospital(hospital_id)

    if not result["success"]:
        await query.edit_message_text(f"❌ خطأ: {result.get('reason','فشل الحذف')}")
        return

    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _log_operation(
        admin_id     = uid,
        op_type      = LOG_DELETE_HOSPITAL,
        element_name = result["name"],
        details      = (
            f"المدينة: {result['city']} | "
            f"الأطباء المحذوفون: {result['doctors_deleted']} | "
            f"شعار محذوف: {result['logo_deleted']} | "
            f"الوقت: {ts}"
        )
    )

    await query.edit_message_text(
        f"✅ *تم الحذف بنجاح*\n\n"
        f"🏥 المستشفى: *{result['name']}*\n"
        f"🏙️ المدينة: *{result['city']}*\n"
        f"👨‍⚕️ الأطباء المحذوفون: *{result['doctors_deleted']}*\n"
        f"🖼️ الشعار: *{'تم حذفه' if result['logo_deleted'] else 'لم يكن موجوداً'}*\n"
        f"📦 إجمالي العناصر المحذوفة: *{result['items_total']}*\n"
        f"🕐 وقت الحذف: `{ts}`\n\n"
        f"_يمكنك الاستمرار بحذف مستشفيات أخرى من القائمة._",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🗑️ حذف مستشفى آخر", callback_data="del_hosp_list:0")],
            [InlineKeyboardButton("❌ إغلاق",           callback_data="del_cancel")],
        ])
    )


# ══════════════════════════════════════════════════════════════════════════════
#  2. نظام حذف الشعارات
# ══════════════════════════════════════════════════════════════════════════════

def _get_hospitals_with_logo() -> list:
    """يُعيد المستشفيات التي لديها شعار مرتبط فقط."""
    return [h for h in db.get_all_hospitals() if _hospital_has_logo(h)]


async def start_delete_logos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    hospitals = _get_hospitals_with_logo()
    if not hospitals:
        await update.message.reply_text("❌ لا توجد شعارات مرفوعة حالياً.")
        return

    context.user_data["del_logos_cache"] = hospitals

    keyboard = _build_list_keyboard(
        items    = hospitals,
        page     = 0,
        prefix   = "del_logo_pick",
        label_fn = lambda h: f"🖼️ {h['name']} ({h.get('city','—')})"
    )

    await update.message.reply_text(
        f"🗑️ *حذف شعار مستشفى*\n\n"
        f"📊 مستشفيات بشعار: *{len(hospitals)}*\n"
        f"اختر المستشفى الذي تريد حذف شعاره:",
        parse_mode="Markdown",
        reply_markup=keyboard
    )


async def _show_logos_page(query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE, page: int):
    hospitals = context.user_data.get("del_logos_cache") or _get_hospitals_with_logo()
    context.user_data["del_logos_cache"] = hospitals

    if not hospitals:
        try:
            await query.edit_message_text("❌ لا توجد شعارات مرفوعة حالياً.")
        except BadRequest:
            pass
        return

    keyboard = _build_list_keyboard(
        items    = hospitals,
        page     = page,
        prefix   = "del_logo_pick",
        label_fn = lambda h: f"🖼️ {h['name']} ({h.get('city','—')})"
    )

    try:
        await query.edit_message_text(
            f"🗑️ *حذف شعار مستشفى*\n\n"
            f"📊 مستشفيات بشعار: *{len(hospitals)}*\n"
            f"اختر المستشفى الذي تريد حذف شعاره:",
            parse_mode="Markdown",
            reply_markup=keyboard
        )
    except BadRequest:
        pass


async def _logo_confirm_page(query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE, hospital_id: int):
    h = _get_hospital_by_id(hospital_id)
    if not h:
        await query.edit_message_text("❌ لم يُعثر على المستشفى.")
        return

    if not _hospital_has_logo(h):
        await query.edit_message_text(
            "ℹ️ هذا المستشفى لا يمتلك شعاراً مرتبطاً.",
            reply_markup=_back_keyboard("del_logo_list:0")
        )
        return

    lp = h.get("logo_path", "")
    storage_type = "قاعدة البيانات" if lp.startswith("db:") else "القرص المحلي"

    context.user_data["del_logo_pending_id"] = hospital_id

    await query.edit_message_text(
        f"⚠️ *تأكيد حذف الشعار*\n\n"
        f"🏥 المستشفى: *{h['name']}*\n"
        f"🏙️ المدينة:  *{h.get('city','—')}*\n"
        f"💾 موقع التخزين: *{storage_type}*\n\n"
        f"سيتم حذف الشعار نهائياً من التخزين وتنظيف جميع الروابط المرتبطة.\n"
        f"سيُستخدم شعار افتراضي (أو لا يُعرض شعار) عند إنشاء ملفات PDF.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🗑️ حذف الشعار",      callback_data=f"del_logo_do:{hospital_id}"),
                InlineKeyboardButton("🔄 استبدال الشعار",   callback_data=f"del_logo_replace:{hospital_id}"),
            ],
            [
                InlineKeyboardButton("⬅️ رجوع", callback_data="del_logo_list:0"),
                InlineKeyboardButton("❌ إلغاء", callback_data="del_cancel"),
            ],
        ])
    )


async def _execute_delete_logo(query: CallbackQuery, uid: int, hospital_id: int):
    result = _delete_logo_only(hospital_id)

    if not result["success"]:
        await query.edit_message_text(
            f"❌ خطأ: {result.get('reason','فشل الحذف')}",
            reply_markup=_back_keyboard("del_logo_list:0")
        )
        return

    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _log_operation(
        admin_id     = uid,
        op_type      = LOG_DELETE_LOGO,
        element_name = result["name"],
        details      = f"المدينة: {result['city']} | الوقت: {ts}"
    )

    await query.edit_message_text(
        f"✅ *تم حذف الشعار بنجاح*\n\n"
        f"🏥 المستشفى: *{result['name']}*\n"
        f"🏙️ المدينة:  *{result['city']}*\n"
        f"🕐 وقت الحذف: `{ts}`\n\n"
        f"_ملاحظة: سيُستخدم تصميم بدون شعار عند إنشاء ملفات PDF لهذا المستشفى._",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🗑️ حذف شعار آخر", callback_data="del_logo_list:0")],
            [InlineKeyboardButton("❌ إغلاق",          callback_data="del_cancel")],
        ])
    )


# ══════════════════════════════════════════════════════════════════════════════
#  3. نظام حذف الأطباء
# ══════════════════════════════════════════════════════════════════════════════

def _get_all_doctors_with_hospital() -> list:
    return db.get_all_doctors()


def _search_doctors(query_text: str) -> list:
    """بحث في الأطباء بالاسم أو التخصص أو اسم المستشفى."""
    q = query_text.strip().lower()
    if not q:
        return _get_all_doctors_with_hospital()
    all_docs = _get_all_doctors_with_hospital()
    return [
        d for d in all_docs
        if q in (d.get("name") or "").lower()
        or q in (d.get("specialty") or "").lower()
        or q in (d.get("hospital_name") or "").lower()
    ]


def _doctor_label(d: dict) -> str:
    hosp = d.get("hospital_name") or "—"
    spec = d.get("specialty") or "—"
    return f"👨‍⚕️ {d['name']} | {spec} | {hosp}"


async def start_delete_doctors(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doctors = _get_all_doctors_with_hospital()
    if not doctors:
        await update.message.reply_text("❌ لا يوجد أطباء مسجّلون في قاعدة البيانات.")
        return

    context.user_data["del_docs_cache"] = doctors

    keyboard = _build_list_keyboard(
        items    = doctors,
        page     = 0,
        prefix   = "del_doc_pick",
        label_fn = _doctor_label
    )

    await update.message.reply_text(
        f"🗑️ *حذف طبيب*\n\n"
        f"📊 إجمالي الأطباء: *{len(doctors)}*\n"
        f"اختر الطبيب الذي تريد حذفه\nأو استخدم زر 🔍 للبحث:",
        parse_mode="Markdown",
        reply_markup=keyboard
    )


async def _show_doctors_page(
    query: CallbackQuery,
    context: ContextTypes.DEFAULT_TYPE,
    page: int,
    doctors: list = None
):
    if doctors is None:
        doctors = context.user_data.get("del_docs_cache") or _get_all_doctors_with_hospital()
        context.user_data["del_docs_cache"] = doctors

    keyboard = _build_list_keyboard(
        items    = doctors,
        page     = page,
        prefix   = "del_doc_pick",
        label_fn = _doctor_label
    )

    try:
        await query.edit_message_text(
            f"🗑️ *حذف طبيب*\n\n"
            f"📊 النتائج: *{len(doctors)}* طبيب\n"
            f"اختر الطبيب أو استخدم 🔍 للبحث:",
            parse_mode="Markdown",
            reply_markup=keyboard
        )
    except BadRequest:
        pass


async def _doctor_confirm_page(query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE, doctor_id: int):
    conn = db.get_conn()
    try:
        row = conn.execute(
            """SELECT d.*, h.name as hospital_name
               FROM doctors d
               LEFT JOIN hospitals h ON d.hospital_id=h.id
               WHERE d.id=?""",
            (doctor_id,)
        ).fetchone()
        doc = dict(row) if row else None
    finally:
        conn.close()

    if not doc:
        await query.edit_message_text("❌ لم يُعثر على الطبيب.")
        return

    added_at = doc.get("created_at") or "—"
    context.user_data["del_doc_pending_id"] = doctor_id

    await query.edit_message_text(
        f"⚠️ *تأكيد حذف الطبيب*\n\n"
        f"👨‍⚕️ الاسم:       *{doc['name']}*\n"
        f"🏥 المستشفى:   *{doc.get('hospital_name','—')}*\n"
        f"🩺 التخصص:     *{doc.get('specialty','—')}*\n"
        f"📅 تاريخ الإضافة: `{added_at}`\n\n"
        f"🚨 سيتم حذف بيانات الطبيب بشكل *نهائي* ولا يمكن التراجع!",
        parse_mode="Markdown",
        reply_markup=_confirm_keyboard(
            confirm_cb=f"del_doc_do:{doctor_id}",
            cancel_cb ="del_doc_list:0"
        )
    )


async def _execute_delete_doctor(query: CallbackQuery, uid: int, doctor_id: int):
    result = _full_delete_doctor(doctor_id)

    if not result["success"]:
        await query.edit_message_text(
            f"❌ خطأ: {result.get('reason','فشل الحذف')}",
            reply_markup=_back_keyboard("del_doc_list:0")
        )
        return

    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _log_operation(
        admin_id     = uid,
        op_type      = LOG_DELETE_DOCTOR,
        element_name = result["name"],
        details      = (
            f"التخصص: {result['specialty']} | "
            f"المستشفى: {result['hospital']} | "
            f"الوقت: {ts}"
        )
    )

    # تحديث الكاش
    context.user_data["del_docs_cache"] = _get_all_doctors_with_hospital()

    await query.edit_message_text(
        f"✅ *تم حذف الطبيب بنجاح*\n\n"
        f"👨‍⚕️ الاسم:     *{result['name']}*\n"
        f"🩺 التخصص:   *{result['specialty']}*\n"
        f"🏥 المستشفى: *{result['hospital']}*\n"
        f"🕐 وقت الحذف: `{ts}`",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🗑️ حذف طبيب آخر", callback_data="del_doc_list:0")],
            [InlineKeyboardButton("❌ إغلاق",          callback_data="del_cancel")],
        ])
    )


# ══════════════════════════════════════════════════════════════════════════════
#  4. معالج البحث (يُستدعى من handle_message في bot.py)
# ══════════════════════════════════════════════════════════════════════════════

async def handle_search_input(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    uid: int,
    text: str
):
    """يعالج نص البحث الذي يكتبه المشرف بعد ضغط زر البحث."""
    state = context.user_data.get("state", "")

    if state == "del_search_doctors":
        results = _search_doctors(text)
        if not results:
            await update.message.reply_text(
                f"🔍 لا توجد نتائج للبحث: *{text}*\n\nأعد المحاولة أو أرسل /cancel",
                parse_mode="Markdown"
            )
            return
        context.user_data["del_docs_cache"] = results
        context.user_data["state"] = ""

        keyboard = _build_list_keyboard(
            items    = results,
            page     = 0,
            prefix   = "del_doc_pick",
            label_fn = _doctor_label
        )
        await update.message.reply_text(
            f"🔍 نتائج البحث: *{len(results)} طبيب*",
            parse_mode="Markdown",
            reply_markup=keyboard
        )

    elif state == "del_search_hospitals":
        results = db.search_hospitals(text) if hasattr(db, "search_hospitals") else [
            h for h in db.get_all_hospitals()
            if text.lower() in (h.get("name") or "").lower()
            or text.lower() in (h.get("city") or "").lower()
        ]
        if not results:
            await update.message.reply_text(
                f"🔍 لا توجد نتائج للبحث: *{text}*",
                parse_mode="Markdown"
            )
            return
        context.user_data["del_hospitals_cache"] = results
        context.user_data["state"] = ""

        keyboard = _build_list_keyboard(
            items    = results,
            page     = 0,
            prefix   = "del_hosp_pick",
            label_fn = lambda h: f"🏥 {h['name']} — {h.get('city','')}"
        )
        await update.message.reply_text(
            f"🔍 نتائج البحث: *{len(results)} مستشفى*",
            parse_mode="Markdown",
            reply_markup=keyboard
        )

    elif state == "del_search_logos":
        results = [
            h for h in _get_hospitals_with_logo()
            if text.lower() in (h.get("name") or "").lower()
            or text.lower() in (h.get("city") or "").lower()
        ]
        if not results:
            await update.message.reply_text(
                f"🔍 لا توجد نتائج للبحث: *{text}*",
                parse_mode="Markdown"
            )
            return
        context.user_data["del_logos_cache"] = results
        context.user_data["state"] = ""

        keyboard = _build_list_keyboard(
            items    = results,
            page     = 0,
            prefix   = "del_logo_pick",
            label_fn = lambda h: f"🖼️ {h['name']} ({h.get('city','—')})"
        )
        await update.message.reply_text(
            f"🔍 نتائج البحث: *{len(results)} مستشفى*",
            parse_mode="Markdown",
            reply_markup=keyboard
        )


# ══════════════════════════════════════════════════════════════════════════════
#  5. المُوزّع الرئيسي للـ Callbacks ─ يُستدعى من handle_callback في bot.py
# ══════════════════════════════════════════════════════════════════════════════

async def handle_delete_callback(
    query: CallbackQuery,
    uid: int,
    data: str,
    context: ContextTypes.DEFAULT_TYPE
):
    """
    نقطة الدخول الوحيدة لجميع callbacks الخاصة بنظام الحذف.
    يُستدعى من bot.py هكذا:
        if data.startswith("del_"):
            await delete_system.handle_delete_callback(query, uid, data, context)
            return
    """
    try:
        await _dispatch(query, uid, data, context)
    except Exception as e:
        logger.error(f"❌ خطأ في delete_system: {e}", exc_info=True)
        try:
            await query.answer("⚠️ حدث خطأ، يرجى المحاولة مجدداً.", show_alert=True)
        except Exception:
            pass


async def _dispatch(query: CallbackQuery, uid: int, data: str, context: ContextTypes.DEFAULT_TYPE):
    """موزّع داخلي للـ callbacks."""

    # ─── إلغاء / لا إجراء ─────────────────────────────────────────────────
    if data == "del_cancel":
        try:
            await query.edit_message_text("✅ تم الإلغاء.")
        except BadRequest:
            pass
        return

    if data == "del_noop":
        await query.answer()
        return

    # ══════════════════════════════════════════════
    # المستشفيات
    # ══════════════════════════════════════════════
    if data.startswith("del_hosp_list:"):
        page = int(data.split(":")[1])
        # تحديث الكاش
        context.user_data["del_hospitals_cache"] = db.get_all_hospitals()
        await _show_hospitals_page(query, context, page)
        return

    if data.startswith("del_hosp_pick:"):
        hospital_id = int(data.split(":")[1])
        await _hospital_confirm_page(query, context, hospital_id)
        return

    if data.startswith("del_hosp_do:"):
        hospital_id = int(data.split(":")[1])
        await _execute_delete_hospital(query, uid, hospital_id)
        return

    if data == "del_hosp_search":
        context.user_data["state"] = "del_search_hospitals"
        await query.edit_message_text(
            "🔍 *بحث عن مستشفى*\n\nأرسل اسم المستشفى أو المدينة:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ إلغاء", callback_data="del_cancel")]
            ])
        )
        return

    # ══════════════════════════════════════════════
    # الشعارات
    # ══════════════════════════════════════════════
    if data.startswith("del_logo_list:"):
        page = int(data.split(":")[1])
        context.user_data["del_logos_cache"] = _get_hospitals_with_logo()
        await _show_logos_page(query, context, page)
        return

    if data.startswith("del_logo_pick:"):
        hospital_id = int(data.split(":")[1])
        await _logo_confirm_page(query, context, hospital_id)
        return

    if data.startswith("del_logo_do:"):
        hospital_id = int(data.split(":")[1])
        await _execute_delete_logo(query, uid, hospital_id)
        return

    if data.startswith("del_logo_replace:"):
        # تفويض عملية الاستبدال لنظام رفع الشعار الموجود
        hospital_id = int(data.split(":")[1])
        h = _get_hospital_by_id(hospital_id)
        name = h["name"] if h else "—"
        context.user_data["logo_replace_hospital_id"] = hospital_id
        context.user_data["logo_replace_hospital_name"] = name
        await query.edit_message_text(
            f"🔄 *استبدال شعار {name}*\n\n"
            f"أرسل الآن صورة الشعار الجديد مباشرةً في المحادثة.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ إلغاء", callback_data="del_cancel")]
            ])
        )
        return

    if data == "del_logo_search":
        context.user_data["state"] = "del_search_logos"
        await query.edit_message_text(
            "🔍 *بحث عن شعار*\n\nأرسل اسم المستشفى أو المدينة:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ إلغاء", callback_data="del_cancel")]
            ])
        )
        return

    # ══════════════════════════════════════════════
    # الأطباء
    # ══════════════════════════════════════════════
    if data.startswith("del_doc_list:"):
        page = int(data.split(":")[1])
        context.user_data["del_docs_cache"] = _get_all_doctors_with_hospital()
        await _show_doctors_page(query, context, page)
        return

    if data.startswith("del_doc_pick:"):
        doctor_id = int(data.split(":")[1])
        await _doctor_confirm_page(query, context, doctor_id)
        return

    if data.startswith("del_doc_do:"):
        doctor_id = int(data.split(":")[1])
        await _execute_delete_doctor(query, uid, doctor_id)
        return

    if data == "del_doc_search":
        context.user_data["state"] = "del_search_doctors"
        await query.edit_message_text(
            "🔍 *بحث عن طبيب*\n\nأرسل الاسم أو التخصص أو اسم المستشفى:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ إلغاء", callback_data="del_cancel")]
            ])
        )
        return

    # callback غير معروف
    await query.answer("⚠️ أمر غير معروف.", show_alert=True)
