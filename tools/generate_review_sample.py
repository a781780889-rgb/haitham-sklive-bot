# -*- coding: utf-8 -*-
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup  # noqa: F401
except ModuleNotFoundError:
    import types
    telegram = types.ModuleType("telegram")
    telegram.InlineKeyboardButton = object
    telegram.InlineKeyboardMarkup = object
    telegram.ext = types.ModuleType("telegram.ext")
    telegram.ext.ContextTypes = object
    sys.modules["telegram"] = telegram
    sys.modules["telegram.ext"] = telegram.ext

from review_scene import _pdf

DATA = {
    "leave_id": "GSL26081328101",
    "entry_date": "12-07-2026",
    "entry_time": "22:00",
    "exit_date": "14-07-2026",
    "exit_time": "20:00",
    "waiting_period": "46 ساعة و0 دقيقة",
    "issue_date": "14-07-2026",
    "issue_time": "23:00",
    "name_ar": "ناصر اليامي",
    "name_en": "NASSER AL-YAMI",
    "id_number": "5364657465",
    "nationality_ar": "سعودي",
    "nationality_en": "Saudi Arabia",
    "workplace_ar": "الرياض",
    "workplace_en": "",
    "doctor_ar": "آلاء محمد باعمره",
    "doctor_en": "ALAA MOHAMMED BA ARMAH",
    "specialty_ar": "استشاري",
    "specialty_en": "Consultant",
    "visit_type_ar": "مراجعه",
    "visit_type_en": "General Practitioner",
}

if __name__ == "__main__":
    out = Path(__file__).resolve().parent.parent / "artifacts" / "review_scene_sample.pdf"
    out.parent.mkdir(parents=True, exist_ok=True)
    _pdf(str(out), DATA)
    print(out)
