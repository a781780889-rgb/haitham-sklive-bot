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

# هذه هي بنية state التي تصل إلى _pdf من ReviewSceneFlow قبل الإصدار.
BOT_STATE = {
    "leave_id": "GSL26081328101",
    "entry_date": "12-07-2026", "entry_time": "22:00",
    "exit_date": "14-07-2026", "exit_time": "20:00",
    "waiting_period": "46 ساعة و0 دقيقة", "issue_date": "14-07-2026", "issue_time": "23:00",
    "name": "ناصر اليامي", "id_number": "5364657465", "nationality": "سعودي",
    "workplace": "الرياض", "doctor": "آلاء محمد باعمره", "specialty": "استشاري",
    "visit_type": "مراجعه",
}

if __name__ == "__main__":
    out = Path(__file__).resolve().parent.parent / "artifacts" / "review_scene_bot_path_sample.pdf"
    out.parent.mkdir(parents=True, exist_ok=True)
    _pdf(str(out), BOT_STATE)
    print(out)
