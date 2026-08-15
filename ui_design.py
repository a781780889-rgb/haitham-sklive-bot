#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ui_design.py — وحدة الواجهة الفاخرة (Premium UI Module)
═══════════════════════════════════════════════════════════════════
إعادة تصميم كاملة لواجهة بوت "صَحَّة" بأسلوب Modern Medical UI
ضمن إمكانيات تيليجرام — مع أقصى درجة فخامة بصرية.

كيفية الاستخدام:
    from ui_design import (
        build_main_menu_text, main_menu_keyboard,
        build_order_preview, back_keyboard, ...
    )
    
    parse_mode = "HTML"   # ← مهم: كل النصوص بصيغة HTML
"""

from telegram import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from html import escape as h


# ═══════════════════════════════════════════════════════════════════
# 🎨 نظام التصميم البصري (Design Tokens)
# ═══════════════════════════════════════════════════════════════════

# فواصل بصرية فاخرة
DIVIDER_THICK   = "▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰"
DIVIDER_THIN    = "─────────────────────"
DIVIDER_DOTTED  = "┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄"
DIVIDER_DOUBLE  = "═════════════════════"

# مؤشر زخرفي
ACCENT      = "✦"
BULLET      = "◆"
BULLET_SOFT = "◇"
ARROW       = "▸"
ARROW_DBL   = "»"
DIAMOND     = "❖"

# نظام الأيقونات (موحّد عبر البوت بالكامل)
ICON = {
    # عام
    "logo":         "🩺",
    "premium":      "💎",
    "shield":       "🛡️",
    "spark":        "✨",
    "clock":        "⏱",
    "check":        "✓",
    "cross":        "✕",
    # المستخدم
    "user":         "👤",
    "id":           "🆔",
    "wallet":       "💳",
    "tag":          "🏷",
    "bolt":         "⚡",
    "package":      "📦",
    # المنشآت
    "hospital":     "🏥",
    "doctor":       "👨‍⚕️",
    "city":         "🏙",
    "map":          "🗺",
    "logo_img":     "🖼",
    # الإجراءات
    "new":          "📝",
    "list":         "📋",
    "search":       "🔍",
    "add":          "➕",
    "edit":         "✏️",
    "send":         "📤",
    "calendar":     "📅",
    "time":         "🕒",
    "exit":         "🚪",
    # المالية
    "money":        "💰",
    "voucher":      "🎫",
    "gift":         "🎁",
    "history":      "📜",
    # النظام
    "globe":        "🌐",
    "settings":     "⚙️",
    "stats":        "📊",
    "trend":        "📈",
    "broadcast":    "📢",
    "bell":         "🔔",
    "panel":        "🎛",
    # حالات
    "success":      "✅",
    "warning":      "⚠️",
    "error":        "⛔",
    "info":         "ℹ️",
    "pending":      "⏳",
    "lock":         "🔒",
    # تنقّل
    "home":         "🏠",
    "back":         "‹",
    "next":         "›",
    "up":           "⬆",
    "down":         "⬇",
}


# ═══════════════════════════════════════════════════════════════════
# 🧱 بنّاءات بصرية (Visual Builders)
# ═══════════════════════════════════════════════════════════════════

def header(title: str, subtitle: str = "") -> str:
    """عنوان رئيسي فاخر بإطار علوي وسفلي."""
    out = f"<b>{ICON['logo']}  {h(title)}</b>"
    if subtitle:
        out += f"\n<i>{h(subtitle)}</i>"
    out += f"\n{DIVIDER_THICK}"
    return out


def section(label: str) -> str:
    """فاصل قسم داخلي — يفصل بين مجموعات المعلومات."""
    return f"\n<b>{ACCENT} {h(label)}</b>\n{DIVIDER_DOTTED}"


def kv(icon_key: str, label: str, value: str, bold_value: bool = True) -> str:
    """سطر بيانات منسّق: أيقونة • تسمية • قيمة."""
    icon = ICON.get(icon_key, BULLET)
    val = f"<b>{h(str(value))}</b>" if bold_value else h(str(value))
    return f"{icon}  {h(label):<14} {val}"


def progress_bar(filled: int, total: int = 5, color: str = "🟦") -> str:
    """شريط تقدّم بصري بأزرق طبي بدلاً من الأخضر التقليدي."""
    filled_n = max(0, min(filled, total))
    return color * filled_n + "⬜" * (total - filled_n)


def badge(text: str, kind: str = "info") -> str:
    """شارة صغيرة (Pill) بصيغة نصية."""
    icons = {"success": "✓", "warn": "⚠", "info": "ℹ", "premium": "✦"}
    icon = icons.get(kind, "•")
    return f"⟦ {icon} {h(text)} ⟧"


def quote_box(text: str) -> str:
    """صندوق اقتباس — لإبراز معلومة أو ملاحظة."""
    lines = text.split("\n")
    out = ["<blockquote>"]
    out.extend(lines)
    out.append("</blockquote>")
    return "\n".join(out)


# ═══════════════════════════════════════════════════════════════════
# 🏠 الشاشة الرئيسية (Premium Dashboard)
# ═══════════════════════════════════════════════════════════════════

def build_main_menu_text(name: str, user_id: int, balance: float,
                         price: float, total_orders: int) -> str:
    """
    لوحة التحكم الشخصية — تصميم فاخر بأسلوب Premium SaaS.
    يستخدم HTML parse mode.
    """
    can_order = int(balance / price) if price > 0 else 0
    bar = progress_bar(min(can_order, 5))
    
    # تحديد حالة الرصيد
    if can_order >= 5:
        status = badge("رصيد ممتاز", "premium")
    elif can_order >= 2:
        status = badge("رصيد جيد", "success")
    elif can_order >= 1:
        status = badge("رصيد منخفض", "warn")
    else:
        status = badge("نفد الرصيد", "warn")
    
    return (
        f"<b>{ICON['logo']}  صَحَّة</b>  <i>· منصّة الإجازات الطبية</i>\n"
        f"{DIVIDER_THICK}\n"
        f"\n"
        f"<b>{ACCENT}  أهلاً، {h(name)}</b>\n"
        f"<code>ID: {user_id}</code>   {status}\n"
        f"\n"
        f"<b>{DIAMOND} المحفظة</b>\n"
        f"{DIVIDER_DOTTED}\n"
        f"{ICON['premium']}  الرصيد المتاح   <b>{balance:,.2f}</b> ر.س\n"
        f"{ICON['tag']}  سعر الطلب الواحد <b>{price:,.0f}</b> ر.س\n"
        f"{ICON['bolt']}  طلبات يمكن إصدارها  <b>{can_order}</b>\n"
        f"     {bar}\n"
        f"{ICON['package']}  إجمالي طلباتك    <b>{total_orders}</b>\n"
        f"\n"
        f"{DIVIDER_THIN}\n"
        f"<i>اختر من القائمة بالأسفل {ARROW_DBL}</i>\n"
        f"\n"
        f"<b>{ICON['shield']} الدعم الفني</b>\n"
        f"<code>781780889</code>"
    )


# ═══════════════════════════════════════════════════════════════════
# ⌨️  لوحات المفاتيح (Modern Keyboard Layouts)
# ═══════════════════════════════════════════════════════════════════
#
# مبادئ التصميم:
#   • صف واحد للإجراء الأساسي (Primary CTA)
#   • صفّان (2 أزرار) للإجراءات الثانوية — أسهل للقراءة على الجوال
#   • أيقونة قبل كل زر — تتعرّف العين على الزر بنظرة
#   • التنقّل دائماً في الأسفل (Home + Back)
#   • فصل بصري بين الإجراءات والتنقّل
# ───────────────────────────────────────────────────────────────────

def main_menu_keyboard(is_admin: bool = False) -> ReplyKeyboardMarkup:
    """قائمة رئيسية معاد تصميمها — منظّمة بهرم بصري واضح."""
    keyboard = [
        # ─ الإجراء الرئيسي (Primary CTA) ─
        [KeyboardButton(f"{ICON['new']} إصدار إجازة جديدة")],
        [KeyboardButton("💉 إصدار شهادة التطعيم")],
        # ─ الحساب والمالية ─
        [
            KeyboardButton(f"{ICON['list']} طلباتي"),
            KeyboardButton(f"{ICON['premium']} شحن الرصيد"),
        ],
        # ─ المنشآت والأطباء ─
        [
            KeyboardButton(f"{ICON['hospital']} المستشفيات"),
            KeyboardButton(f"{ICON['globe']} منصّة التحقق"),
        ],
        # ─ المساهمات (Contributions) ─
        [
            KeyboardButton(f"{ICON['add']} إضافة مستشفى"),
            KeyboardButton(f"{ICON['add']} إضافة طبيب"),
        ],
        [KeyboardButton(f"{ICON['logo_img']} إضافة شعار")],
    ]
    
    # ─ قسم الإدارة (للمشرفين فقط) ─
    if is_admin:
        keyboard.append([
            KeyboardButton(f"{ICON['panel']} لوحة الإدارة"),
            KeyboardButton(f"{ICON['settings']} نظام البوت"),
        ])
    
    # ─ التنقّل (دائماً في الأسفل) ─
    keyboard.append([KeyboardButton(f"{ICON['home']} الرئيسية")])
    
    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        input_field_placeholder="اضغط على أي خيار من القائمة…"
    )


def back_keyboard(with_home: bool = True) -> ReplyKeyboardMarkup:
    """شريط تنقّل سفلي بسيط ومتسق."""
    if with_home:
        rows = [[
            KeyboardButton(f"{ICON['back']}  رجوع"),
            KeyboardButton(f"{ICON['home']} الرئيسية"),
        ]]
    else:
        rows = [[KeyboardButton(f"{ICON['back']}  رجوع")]]
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def dashboard_keyboard() -> ReplyKeyboardMarkup:
    """لوحة الإدارة — مرتبة في أربع مجموعات منطقية."""
    return ReplyKeyboardMarkup([
        # المستخدمون والإحصائيات
        [
            KeyboardButton(f"{ICON['user']} إدارة المستخدمين"),
            KeyboardButton(f"{ICON['stats']} الإحصائيات"),
        ],
        # المنشآت
        [
            KeyboardButton(f"{ICON['hospital']} إدارة المستشفيات"),
            KeyboardButton(f"{ICON['doctor']} إدارة الأطباء"),
        ],
        # الموارد المالية
        [
            KeyboardButton(f"{ICON['logo_img']} إدارة الشعارات"),
            KeyboardButton(f"{ICON['money']} إدارة الأسعار"),
        ],
        # العمليات
        [
            KeyboardButton(f"{ICON['broadcast']} رسالة جماعية"),
            KeyboardButton(f"{ICON['settings']} إعدادات النظام"),
        ],
        # تنقّل
        [KeyboardButton(f"{ICON['back']}  رجوع")],
    ], resize_keyboard=True)


def admin_panel_keyboard(badge_count: int = 0) -> ReplyKeyboardMarkup:
    """لوحة المراجعة الإدارية الموسّعة."""
    review_label = f"{ICON['search']} لوحة المراجعة"
    if badge_count > 0:
        review_label += f" ({badge_count})"
    
    return ReplyKeyboardMarkup([
        [
            KeyboardButton(f"📄 قوالب PDF"),
            KeyboardButton(f"{ICON['logo_img']} الشعارات"),
        ],
        [
            KeyboardButton(f"{ICON['hospital']} المستشفيات"),
            KeyboardButton(f"{ICON['doctor']} الأطباء"),
        ],
        [
            KeyboardButton(f"{ICON['user']} المستخدمين"),
            KeyboardButton(f"{ICON['stats']} الطلبات"),
        ],
        [
            KeyboardButton(f"{ICON['money']} المعاملات"),
            KeyboardButton(f"{ICON['voucher']} أكواد الشحن"),
        ],
        [
            KeyboardButton(f"{ICON['trend']} الإحصائيات"),
            KeyboardButton(f"{ICON['settings']} الإعدادات"),
        ],
        [
            KeyboardButton(review_label),
            KeyboardButton(f"{ICON['bell']} الإشعارات"),
        ],
        [
            KeyboardButton(f"{ICON['back']}  رجوع"),
            KeyboardButton(f"{ICON['home']} الرئيسية"),
        ],
    ], resize_keyboard=True)


def new_order_keyboard() -> ReplyKeyboardMarkup:
    """لوحة بدء الطلب — تركيز على البحث وأهم المدن."""
    return ReplyKeyboardMarkup([
        # تنقّل
        [
            KeyboardButton(f"{ICON['home']} الرئيسية"),
            KeyboardButton(f"{ICON['back']}  رجوع"),
        ],
        # طرق البحث
        [KeyboardButton(f"{ICON['search']} بحث باسم المستشفى")],
        [
            KeyboardButton(f"{ICON['list']} كل المستشفيات"),
            KeyboardButton(f"{ICON['city']} بحث بالمدينة"),
        ],
        # اختصارات للمدن الكبرى
        [
            KeyboardButton("الرياض"),
            KeyboardButton("جدة"),
        ],
        [
            KeyboardButton("مكة"),
            KeyboardButton("المدينة المنورة"),
        ],
        [
            KeyboardButton("الدمام"),
            KeyboardButton("الطائف"),
        ],
    ], resize_keyboard=True)


def regions_keyboard(regions: list) -> ReplyKeyboardMarkup:
    """لوحة المناطق الإدارية — صفّين في كل صف."""
    rows = []
    for i in range(0, len(regions), 2):
        row = [KeyboardButton(f"{ICON['map']} {regions[i]}")]
        if i + 1 < len(regions):
            row.append(KeyboardButton(f"{ICON['map']} {regions[i+1]}"))
        rows.append(row)
    rows.append([
        KeyboardButton(f"{ICON['back']}  رجوع"),
        KeyboardButton(f"{ICON['home']} الرئيسية"),
    ])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def cities_keyboard(cities: list) -> ReplyKeyboardMarkup:
    """مدن منطقة معيّنة — صفّان من المدن في كل صف."""
    rows = []
    for i in range(0, len(cities), 2):
        row = [KeyboardButton(cities[i])]
        if i + 1 < len(cities):
            row.append(KeyboardButton(cities[i+1]))
        rows.append(row)
    rows.append([
        KeyboardButton(f"{ICON['back']}  رجوع"),
        KeyboardButton(f"{ICON['home']} الرئيسية"),
    ])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def hospitals_select_keyboard(hospitals: list, has_logo_fn) -> ReplyKeyboardMarkup:
    """لوحة اختيار المستشفى — مع علامة ✓ للذي لديه شعار."""
    rows = [[
        KeyboardButton(f"{ICON['back']}  رجوع"),
        KeyboardButton(f"{ICON['home']} الرئيسية"),
    ]]
    for hosp in hospitals:
        prefix = "✦ " if has_logo_fn(hosp) else "  "
        rows.append([KeyboardButton(f"{prefix}{hosp['name']}")])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def doctors_select_keyboard(doctors: list) -> ReplyKeyboardMarkup:
    """قائمة أطباء — تنسيق متناسق مع الأيقونة."""
    rows = [
        [
            KeyboardButton(f"{ICON['home']} الرئيسية"),
            KeyboardButton(f"{ICON['back']}  رجوع"),
        ],
        [KeyboardButton(f"{ICON['edit']} إدخال طبيب يدويًا")],
    ]
    for d in doctors:
        rows.append([KeyboardButton(f"{ICON['doctor']} {d['name']} — {d['specialty']}")])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def confirm_order_inline_keyboard() -> InlineKeyboardMarkup:
    """أزرار تأكيد الطلب inline — أزرار حاسمة."""
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(f"{ICON['success']}  تأكيد وإصدار", callback_data="confirm_order"),
        InlineKeyboardButton(f"{ICON['cross']}  إلغاء",         callback_data="cancel_order"),
    ]])


def confirm_action_inline(action_id: str, label_yes: str = "تأكيد",
                           label_no: str = "إلغاء") -> InlineKeyboardMarkup:
    """قالب عام لتأكيدات Yes/No."""
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(f"{ICON['success']}  {label_yes}",
                             callback_data=f"yes_{action_id}"),
        InlineKeyboardButton(f"{ICON['cross']}  {label_no}",
                             callback_data=f"no_{action_id}"),
    ]])


def charge_keyboard(packages: dict) -> ReplyKeyboardMarkup:
    """قائمة باقات الشحن — مع أيقونة + سعر + عدد طلبات."""
    rows = []
    for name, info in packages.items():
        rows.append([KeyboardButton(
            f"{info['emoji']} {name} · {info['price']:.0f} ر.س "
            f"· {info['credits']} طلبات"
        )])
    rows.append([
        KeyboardButton(f"{ICON['voucher']} شحن بكود"),
        KeyboardButton(f"{ICON['history']} سجل المعاملات"),
    ])
    rows.append([
        KeyboardButton(f"{ICON['back']}  رجوع"),
        KeyboardButton(f"{ICON['home']} الرئيسية"),
    ])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def settings_keyboard() -> ReplyKeyboardMarkup:
    """إعدادات النظام."""
    return ReplyKeyboardMarkup([
        [KeyboardButton(f"{ICON['money']} تعديل سعر الطلب")],
        [KeyboardButton(f"{ICON['globe']} تعديل رابط التحقق")],
        [KeyboardButton(f"📷 تغيير صورة الباركود")],
        [KeyboardButton(f"{ICON['list']} عرض جميع الإعدادات")],
        [KeyboardButton(f"{ICON['back']}  رجوع")],
    ], resize_keyboard=True)


def users_admin_keyboard() -> ReplyKeyboardMarkup:
    """لوحة إدارة المستخدمين."""
    return ReplyKeyboardMarkup([
        [KeyboardButton(f"{ICON['user']} قائمة المستخدمين")],
        [KeyboardButton(f"{ICON['search']} بحث عن مستخدم")],
        [
            KeyboardButton(f"{ICON['error']} حظر مستخدم"),
            KeyboardButton(f"{ICON['success']} رفع الحظر"),
        ],
        [KeyboardButton(f"{ICON['premium']} إضافة رصيد")],
        [KeyboardButton(f"{ICON['back']}  رجوع")],
    ], resize_keyboard=True)


def hospital_type_keyboard() -> ReplyKeyboardMarkup:
    """نوع المنشأة — حكومي/خاص."""
    return ReplyKeyboardMarkup([
        [
            KeyboardButton("🏛 حكومي"),
            KeyboardButton("🏢 خاص"),
        ],
        [KeyboardButton(f"{ICON['back']}  رجوع")],
    ], resize_keyboard=True)


def edit_dates_keyboard() -> ReplyKeyboardMarkup:
    """قبل التأكيد: قرارات التواريخ."""
    return ReplyKeyboardMarkup([
        [KeyboardButton(f"{ICON['success']} متابعة")],
        [
            KeyboardButton(f"{ICON['calendar']} تعديل تاريخ الخروج يدويًا"),
        ],
        [KeyboardButton("جعل تاريخ الخروج = نهاية الإجازة")],
        [KeyboardButton(f"{ICON['back']}  رجوع")],
    ], resize_keyboard=True)


# ═══════════════════════════════════════════════════════════════════
# 📑 قوالب الرسائل (Message Templates)
# ═══════════════════════════════════════════════════════════════════

def build_order_preview(hospital: str, doctor: str, specialty: str,
                        full_name: str, id_number: str, workplace: str,
                        nationality: str, start_date: str, end_date: str,
                        days: int, exit_date: str, issue_time: str) -> str:
    """ملخّص الطلب قبل الإصدار — كروت بصرية مرتّبة."""
    return (
        f"<b>{DIAMOND}  ملخّص الطلب</b>  <i>قبل الإصدار</i>\n"
        f"{DIVIDER_THICK}\n"
        f"\n"
        f"{section('المنشأة الطبية')[1:]}\n"  # remove leading newline
        f"{ICON['hospital']}  المستشفى    <b>{h(hospital)}</b>\n"
        f"{ICON['doctor']}  الطبيب      <b>{h(doctor)}</b>\n"
        f"   التخصّص   <i>{h(specialty)}</i>\n"
        f"\n"
        f"{section('بيانات المريض')[1:]}\n"
        f"{ICON['user']}  الاسم        <b>{h(full_name)}</b>\n"
        f"{ICON['id']}  الهوية       <code>{h(id_number)}</code>\n"
        f"🏢  جهة العمل   <b>{h(workplace)}</b>\n"
        f"🌍  الجنسية      <b>{h(nationality)}</b>\n"
        f"\n"
        f"{section('تواريخ الإجازة')[1:]}\n"
        f"{ICON['calendar']}  من           <b>{h(start_date)}</b>\n"
        f"{ICON['calendar']}  إلى           <b>{h(end_date)}</b>\n"
        f"🗓  عدد الأيام    <b>{days}</b> يوم\n"
        f"{ICON['exit']}  تاريخ الخروج <b>{h(exit_date)}</b>\n"
        f"{ICON['time']}  وقت الإصدار <b>{h(issue_time)}</b>\n"
        f"\n"
        f"{DIVIDER_DOUBLE}\n"
        f"<i>{ACCENT} لتعديل أي بيان أرسله مباشرة، مثل:</i>\n"
        f"   <code>الجنسية: باكستاني</code>\n"
        f"<i>أو اضغط</i> ✓ متابعة <i>للتأكيد</i>"
    )


def build_charge_menu(packages: dict, current_balance: float) -> str:
    """قائمة الباقات — بأسلوب pricing card."""
    lines = [
        f"<b>{ICON['premium']}  شحن الرصيد</b>",
        DIVIDER_THICK,
        "",
        f"<b>الرصيد الحالي:</b>  <code>{current_balance:,.2f}</code>  ر.س",
        DIVIDER_THIN,
        "",
        f"<b>{ACCENT}  الباقات المتاحة</b>",
        DIVIDER_DOTTED,
    ]
    for name, info in packages.items():
        per_order = info['price'] / info['credits'] if info['credits'] else 0
        lines.append(
            f"\n{info['emoji']}  <b>باقة {h(name)}</b>"
        )
        lines.append(
            f"   {info['credits']} طلبات  ·  <b>{info['price']:,.0f}</b> ر.س"
            f"  <i>({per_order:.1f} ر.س/طلب)</i>"
        )
    lines.append("")
    lines.append(DIVIDER_THIN)
    lines.append(f"<i>اختر باقة من الأسفل، أو استخدم</i> {ICON['voucher']} <i>لشحن بكود</i>")
    return "\n".join(lines)


def build_my_orders_header(count: int, latest_date: str = None) -> str:
    """رأس قائمة الطلبات."""
    out = [
        f"<b>{ICON['list']}  طلباتي</b>",
        DIVIDER_THICK,
        "",
        f"{ICON['package']}  <b>{count}</b> طلب",
    ]
    if latest_date:
        out.append(f"{ICON['clock']}  آخر طلب: <i>{h(latest_date)}</i>")
    out.append(DIVIDER_DOTTED)
    return "\n".join(out)


def build_order_card(idx: int, hospital: str, doctor: str,
                     date: str, days: int, gsl: str = "") -> str:
    """بطاقة طلب واحد — تنسيق مدمج."""
    lines = [
        f"<b>#{idx} · {h(hospital)}</b>",
        f"{ICON['doctor']} {h(doctor)}",
        f"{ICON['calendar']} {h(date)}  ·  {days} يوم",
    ]
    if gsl:
        lines.append(f"{ICON['shield']} <code>{h(gsl)}</code>")
    return "\n".join(lines)


def build_hospitals_overview(stats: dict, total_db: int,
                              with_logo: int, my_pending: int = 0) -> str:
    """نظرة عامة على نظام المستشفيات."""
    region_lines = "\n".join([
        f"  {BULLET_SOFT} {h(r)}  <b>{c}</b>"
        for r, c in stats.get("by_region", {}).items()
    ])
    
    out = (
        f"<b>{ICON['hospital']}  نظام المستشفيات</b>\n"
        f"{DIVIDER_THICK}\n\n"
        f"<b>{ACCENT} إحصائيات النظام</b>\n"
        f"{DIVIDER_DOTTED}\n"
        f"{ICON['city']}  المدن            <b>{stats.get('cities_count', 0)}</b>\n"
        f"{ICON['hospital']}  المستشفيات       <b>{stats.get('total', 0)}</b>\n"
        f"🏛  حكومية   <b>{stats.get('by_type', {}).get('حكومي', 0)}</b>"
        f"   ·   🏢  خاصة   <b>{stats.get('by_type', {}).get('خاص', 0)}</b>\n\n"
        f"<b>{ACCENT} حسب المنطقة</b>\n"
        f"{DIVIDER_DOTTED}\n"
        f"{region_lines}\n\n"
        f"<b>{ACCENT} قاعدة البيانات</b>\n"
        f"{DIVIDER_DOTTED}\n"
        f"{ICON['hospital']}  مسجّلة         <b>{total_db}</b>\n"
        f"{ICON['logo_img']}  بشعار          <b>{with_logo}</b>\n"
    )
    
    if my_pending > 0:
        out += (
            f"\n{DIVIDER_THIN}\n"
            f"{ICON['pending']}  <i>عناصرك المعلقة</i>: <b>{my_pending}</b>\n"
        )
    
    out += (
        f"\n{DIVIDER_THIN}\n"
        f"<i>يمكنك إضافة مستشفى أو طبيب أو شعار من الأزرار {ARROW_DBL}</i>"
    )
    return out


def build_verify_system() -> str:
    """شرح منصّة التحقّق."""
    return (
        f"<b>{ICON['globe']}  منصّة التحقّق من الإجازات</b>\n"
        f"{DIVIDER_THICK}\n\n"
        f"<i>منصّة رسميّة للتحقّق من صحّة الإجازة الطبيّة</i>\n"
        f"<i>عبر رمز الخدمة المُصدَر مع كل إجازة.</i>\n\n"
        f"<b>{ACCENT}  خطوات التحقّق</b>\n"
        f"{DIVIDER_DOTTED}\n"
        f"<b>1.</b>  افتح الرابط أدناه\n"
        f"<b>2.</b>  أدخل <b>رمز الخدمة</b> (GSL + ١١ رقم)\n"
        f"      مثال: <code>GSL26021085457</code>\n"
        f"<b>3.</b>  أدخل <b>رقم الهوية</b> أو الإقامة\n"
        f"<b>4.</b>  اضغط <i>استعلام</i>\n\n"
        f"{ICON['success']}  <i>الرمز يظهر تلقائياً على كل إجازة طبيّة</i>"
    )


def build_success_message(title: str, lines: list = None) -> str:
    """رسالة نجاح بصيغة موحّدة."""
    out = [
        f"<b>{ICON['success']}  {h(title)}</b>",
        DIVIDER_THIN,
    ]
    if lines:
        for l in lines:
            out.append(f"{BULLET_SOFT} {h(l)}")
    return "\n".join(out)


def build_warning_message(title: str, body: str) -> str:
    """رسالة تنبيه."""
    return (
        f"<b>{ICON['warning']}  {h(title)}</b>\n"
        f"{DIVIDER_THIN}\n"
        f"{h(body)}"
    )


def build_error_message(title: str, body: str = "") -> str:
    """رسالة خطأ."""
    out = f"<b>{ICON['error']}  {h(title)}</b>"
    if body:
        out += f"\n{DIVIDER_THIN}\n{h(body)}"
    return out


def build_loading_message(action: str = "جارٍ المعالجة") -> str:
    """رسالة انتظار (للتأثير البصري قبل التحميل)."""
    return f"<i>{ICON['pending']}  {h(action)}…</i>"


# ═══════════════════════════════════════════════════════════════════
# 📐 إرشادات الاستخدام
# ═══════════════════════════════════════════════════════════════════
"""
دليل الدمج في bot.py:

1) في كل reply_text المرتبط بنص من هذه الوحدة، استخدم:
       parse_mode="HTML"
   بدلاً من "Markdown"

2) استبدل الاستدعاءات القديمة:
   
   قبل:
       text = build_main_menu_text(uid, name)
       reply_markup = main_menu_keyboard(is_admin_user(uid))
   
   بعد:
       from ui_design import build_main_menu_text, main_menu_keyboard
       user = db.get_user(uid)
       text = build_main_menu_text(
           name=user.get("name", name),
           user_id=uid,
           balance=user.get("balance", 0.0),
           price=get_scaffold_price(),
           total_orders=len(db.get_user_orders(uid))
       )
       reply_markup = main_menu_keyboard(is_admin_user(uid))

3) معالج الرسائل: إذا غيّرت نصوص الأزرار، حدّث شروط `if text == "..."`
   - اقتراح: استخدم بحث جزئي بدل المطابقة الحرفيّة، مثلاً:
       if "إصدار إجازة" in text or text == "/go":
       if "شحن الرصيد" in text:
       if "طلباتي" in text:
   هذا يُبقي البوت متسامحاً مع تغيير الأيقونات أو إعادة الترتيب.

4) لتحويل أي نص يحوي أحرف HTML خاصة (< > &)، استخدم:
       from html import escape
       safe = escape(user_input)
"""
