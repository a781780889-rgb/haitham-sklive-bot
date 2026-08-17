# -*- coding: utf-8 -*-
import sys
import types
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
telegram = types.ModuleType("telegram")
telegram.InlineKeyboardButton = object
telegram.InlineKeyboardMarkup = object
telegram.ext = types.ModuleType("telegram.ext")
telegram.ext.ContextTypes = object
sys.modules.setdefault("telegram", telegram)
sys.modules.setdefault("telegram.ext", telegram.ext)
from review_scene import _pdf

DATA = {
    "leave_id": "GSL260817201725", "entry_date": "12-07-2026", "entry_time": "10:00",
    "exit_date": "14-07-2026", "exit_time": "08:00", "waiting_period": "46 ساعة و0 دقيقة",
    "issue_date": "17-08-2026", "issue_time": "11:00", "name": "هيثم عبده عقلان",
    "id_number": "2324245678", "nationality": "سعودي", "workplace": "الرياض",
    "doctor": "عبدالله", "specialty": "طبيب عام", "visit_type": "عوده",
}
if __name__ == "__main__":
    out = Path(__file__).resolve().parent.parent / "artifacts" / "review_scene_attached_case_fixed.pdf"
    out.parent.mkdir(parents=True, exist_ok=True)
    _pdf(str(out), DATA)
    print(out)
