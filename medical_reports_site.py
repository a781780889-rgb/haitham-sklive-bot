# -*- coding: utf-8 -*-
"""بوابة التقارير الطبية المستقلة، معزولة عن بوابات التطعيم وبقية الأقسام."""
import re
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

from flask import Blueprint, jsonify, render_template, request

import database as db

medical_reports_bp = Blueprint("medical_reports", __name__, url_prefix="/medical-reports")
_VERIFY_LIMIT = 12
_VERIFY_WINDOW = 300
_attempts = {}
_attempts_lock = threading.Lock()


def _limited(key):
    now = time.monotonic()
    with _attempts_lock:
        values = [item for item in _attempts.get(key, []) if now - item < _VERIFY_WINDOW]
        if len(values) >= _VERIFY_LIMIT:
            _attempts[key] = values
            return True
        values.append(now)
        _attempts[key] = values
        return False


def _mask(value):
    value = "".join(ch for ch in str(value or "") if ch.isdigit())
    return "********" + value[-4:] if len(value) >= 4 else "********"


def _date(value, fallback=""):
    raw = str(value or fallback or "").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(raw[:19], fmt).strftime("%d/%m/%Y")
        except ValueError:
            continue
    return raw


def _report_from_order(order, identity):
    start_raw = str(order.get("excuse_date") or "")
    start = None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y"):
        try:
            start = datetime.strptime(start_raw[:19], fmt)
            break
        except ValueError:
            continue
    days = max(int(order.get("days_count") or 1), 1)
    end = (start + timedelta(days=days - 1)).strftime("%d/%m/%Y") if start else start_raw
    return {
        "status": "ساري",
        "referenceNumber": order.get("gsl_code") or "",
        "reportType": "إجازة مرضية",
        "issueDate": _date(order.get("issue_date_input"), order.get("created_at")),
        "startDate": _date(start_raw),
        "endDate": end,
        "duration": days,
        "facility": order.get("hospital") or "—",
        "fullName": order.get("full_name") or "—",
        "identityMasked": _mask(identity),
        "nationality": order.get("nationality") or "",
        "physician": order.get("doctor") or "",
        "specialty": order.get("specialty") or "",
        "verifiedAt": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "verificationUrl": request.url_root.rstrip("/") + "/medical-reports/",
    }


@medical_reports_bp.get("/")
@medical_reports_bp.get("/verify")
def medical_reports_home():
    return render_template("medical_reports_only.html")


@medical_reports_bp.post("/api/verify")
def verify_medical_report():
    if _limited(request.remote_addr or "unknown"):
        return jsonify({"success": False, "message": "تم تجاوز عدد المحاولات المسموح بها، يرجى المحاولة لاحقًا."}), 429
    payload = request.get_json(silent=True) or {}
    reference = str(payload.get("referenceNumber") or "").strip().upper()
    identity = "".join(ch for ch in str(payload.get("identityNumber") or "") if ch.isdigit())
    if not re.fullmatch(r"(?:GSL|PSL)\d{11}", reference) or not re.fullmatch(r"\d{10}", identity):
        return jsonify({"success": False, "message": "بيانات الاستعلام غير صحيحة."}), 400
    try:
        conn = db.get_conn()
        row = conn.execute(
            "SELECT * FROM orders WHERE UPPER(TRIM(gsl_code))=? AND TRIM(id_number)=? AND status='done' LIMIT 1",
            (reference, identity),
        ).fetchone()
        conn.close()
        if not row:
            return jsonify({"success": False, "message": "لم يتم العثور على تقرير مطابق للبيانات المدخلة."}), 404
        order = dict(row)
        try:
            db.add_order_log(order["id"], "medical_reports_site_verified", f"IP:{request.remote_addr or 'unknown'}")
        except Exception:
            pass
        return jsonify({"success": True, "report": _report_from_order(order, identity)})
    except Exception:
        return jsonify({"success": False, "message": "تعذر إتمام الاستعلام حاليًا."}), 500
