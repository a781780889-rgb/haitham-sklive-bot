#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
web.py — الإجازات المرضية
واجهة النتيجة: HTML/CSS كاملة مبنية على تصميم منصة صحة الرسمي
"""

import os, sys, base64
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, redirect
import json
from urllib.request import urlopen

# ══════════════════════════════════════════════
# [Cloudflare Fix] ProxyFix — مطلوب خلف Cloudflare
# ══════════════════════════════════════════════
from werkzeug.middleware.proxy_fix import ProxyFix

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _THIS_DIR)
import database as db

app = Flask(__name__)

# ══════════════════════════════════════════════
# [Cloudflare Fix] تطبيق ProxyFix
# x_for=1   → يقرأ X-Forwarded-For (IP الحقيقي)
# x_proto=1 → يقرأ X-Forwarded-Proto (https/http)
# x_host=1  → يقرأ X-Forwarded-Host
# ══════════════════════════════════════════════
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)


# رابط المحادثة العائم: يُفضّل ضبط TELEGRAM_BOT_URL أو BOT_USERNAME،
# مع استخدام BOT_TOKEN كحل احتياطي لاستخراج اسم البوت من Telegram API.
_BOT_CHAT_URL = None


def resolve_bot_chat_url():
    global _BOT_CHAT_URL
    if _BOT_CHAT_URL:
        return _BOT_CHAT_URL

    configured_url = os.environ.get("TELEGRAM_BOT_URL", "").strip()
    if configured_url.startswith(("https://t.me/", "http://t.me/", "tg://")):
        _BOT_CHAT_URL = configured_url
        return _BOT_CHAT_URL

    username = os.environ.get("BOT_USERNAME", "").strip().lstrip("@")
    if username:
        _BOT_CHAT_URL = f"https://t.me/{username}"
        return _BOT_CHAT_URL

    token = os.environ.get("BOT_TOKEN", "").strip()
    if not token:
        return ""

    try:
        with urlopen(f"https://api.telegram.org/bot{token}/getMe", timeout=5) as response:
            payload = json.load(response)
        username = str(payload.get("result", {}).get("username", "")).strip()
        if username:
            _BOT_CHAT_URL = f"https://t.me/{username}"
    except Exception:
        return ""
    return _BOT_CHAT_URL or ""


@app.route("/chat")
def open_chat():
    """فتح محادثة البوت دون كشف BOT_TOKEN للمتصفح."""
    chat_url = resolve_bot_chat_url()
    if chat_url:
        return redirect(chat_url, code=302)
    return jsonify({
        "success": False,
        "message": "رابط محادثة البوت غير مهيّأ بعد. اضبط TELEGRAM_BOT_URL أو BOT_USERNAME."
    }), 503


# ══════════════════════════════════════════════
# [Cloudflare Fix] Security Headers تلقائية
# ══════════════════════════════════════════════
@app.after_request
def add_security_headers(response):
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    if request.is_secure:
        response.headers['Strict-Transport-Security'] = (
            'max-age=31536000; includeSubDomains'
        )
    return response


def get_bg_b64():
    p = os.path.join(_THIS_DIR, "design_result.jpg")
    if os.path.exists(p):
        with open(p, "rb") as f:
            return "data:image/jpeg;base64," + base64.b64encode(f.read()).decode()
    return ""


def get_logo_b64():
    for name in ["seha_logo.png", "logo_extracted_0.png", "nhic_logo.png"]:
        p = os.path.join(_THIS_DIR, name)
        if os.path.exists(p):
            ext = name.split(".")[-1]
            mime = "image/png" if ext == "png" else "image/jpeg"
            with open(p, "rb") as f:
                return f"data:{mime};base64," + base64.b64encode(f.read()).decode()
    return ""


def build_html():
    """تحميل واجهة منصة صحة الجديدة مع إبقاء نقاط API الحالية دون تغيير."""
    template_path = os.path.join(_THIS_DIR, "templates", "seha_new.html")
    with open(template_path, "r", encoding="utf-8") as template_file:
        return template_file.read()


_HTML_CACHE = None
def get_html():
    global _HTML_CACHE
    if _HTML_CACHE is None:
        _HTML_CACHE = build_html()
    return _HTML_CACHE


@app.route("/")
@app.route("/verify")
@app.route("/verify/<path:gsl_code>")
def index(gsl_code=None):
    return get_html()

@app.errorhandler(404)
def not_found(e):
    return get_html(), 200


@app.route("/api/verify")
def api_verify():
    gsl_code  = (request.args.get("gsl") or "").strip().upper()
    id_number = (request.args.get("id")  or "").strip()
    if not gsl_code or not id_number:
        return jsonify({"success": False, "message": "يجب إرسال gsl و id"}), 400
    try:
        conn = db.get_conn()
        row = conn.execute(
            "SELECT * FROM orders WHERE UPPER(TRIM(gsl_code))=? AND TRIM(id_number)=? AND status='done'",
            (gsl_code, id_number)
        ).fetchone()
        if not row:
            row_dbg = conn.execute("SELECT status FROM orders WHERE UPPER(TRIM(gsl_code))=?",(gsl_code,)).fetchone()
            conn.close()
            if row_dbg:
                return jsonify({"success":False,"message":"رقم الهوية غير صحيح أو الطلب لم يكتمل بعد"}), 404
            return jsonify({"success":False,"message":"لم يُعثر على العذر الطبي"}), 404
        order = dict(row)
        conn.close()
        try:
            db.add_order_log(order["id"], "verified", f"IP:{request.remote_addr}")
        except Exception:
            pass
        # ── حساب تاريخ النهاية مع دعم جميع صيغ التاريخ المخزَّنة ──
        end_date = order.get("excuse_date", "")
        try:
            raw_excuse = (order.get("excuse_date") or "").strip()
            raw_days   = order.get("days_count", 1)
            days_int   = max(int(raw_days) - 1, 0) if raw_days else 0
            start      = None
            for _fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y"):
                try:
                    start = datetime.strptime(raw_excuse, _fmt)
                    break
                except Exception:
                    continue
            if start:
                end_date = (start + timedelta(days=days_int)).strftime("%d-%m-%Y")
        except Exception:
            pass  # end_date بقيت = excuse_date كقيمة احتياطية
        # ── تاريخ الإصدار: issue_date_input (المُدخَل) أو created_at كاحتياطي ──
        _iss_raw = (order.get("issue_date_input") or "").strip() or order.get("created_at", "")
        _iss_iso = _iss_raw
        for _ifmt in ("%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y"):
            try:
                _iss_iso = datetime.strptime(_iss_raw.strip(), _ifmt).strftime("%Y-%m-%d")
                break
            except Exception:
                pass
        return jsonify({"success":True,"data":{
            "gsl_code":    order["gsl_code"],
            "full_name":   order.get("full_name",""),
            "hospital":    order.get("hospital",""),
            "doctor":      order.get("doctor",""),
            "specialty":   order.get("specialty",""),
            "excuse_date": order.get("excuse_date",""),
            "end_date":    end_date,
            "days_count":  order.get("days_count",1),
            "workplace":   order.get("workplace",""),
            "issued_at":   _iss_iso
        }})
    except Exception as ex:
        return jsonify({"success":False,"message":f"خطأ: {str(ex)}"}), 500


@app.route("/health")
def health():
    try:
        conn = db.get_conn()
        done = conn.execute("SELECT COUNT(*) FROM orders WHERE status='done'").fetchone()[0]
        conn.close()
        return jsonify({"status":"ok","done_orders":done,"ts":datetime.now().isoformat()})
    except Exception as ex:
        return jsonify({"status":"error","error":str(ex)}), 500


@app.route("/api/stats")
def api_stats():
    try:
        d = db.get_analytics()
        return jsonify({k:d.get(k,0) for k in ["total_orders","done_orders","total_hospitals","today_orders"]})
    except Exception as ex:
        return jsonify({"error":str(ex)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)


# ── DEBUG ENDPOINT مؤقت — احذفه بعد حل المشكلة ──────────────
@app.route("/api/debug-orders")
def debug_orders():
    try:
        conn = db.get_conn()
        rows = conn.execute(
            "SELECT id, gsl_code, id_number, status, full_name, created_at FROM orders ORDER BY id DESC LIMIT 10"
        ).fetchall()
        conn.close()
        result = []
        for r in rows:
            row = dict(r)
            idn = str(row.get("id_number", "") or "")
            row["id_number"] = idn[:3] + "****" + idn[-2:] if len(idn) > 5 else idn
            result.append(row)
        return jsonify({"orders": result, "count": len(result)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
