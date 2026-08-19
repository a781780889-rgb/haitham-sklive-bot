# -*- coding: utf-8 -*-
"""خادم مستقل لبوابة التقارير الطبية فقط.

يُشغّل كخدمة Railway منفصلة باستخدام: python3 medical_reports_server.py
"""
import os
from flask import Flask
from medical_reports_site import medical_reports_bp

app = Flask(__name__)
app.register_blueprint(medical_reports_bp)


@app.after_request
def security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5050")), debug=False)
