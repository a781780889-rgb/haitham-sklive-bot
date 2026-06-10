#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
web_server.py — تشغيل خادم الويب فقط (بدون البوت)
يُستخدم للخدمة cheerful-mindfulness في Railway
"""
import os
import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _THIS_DIR)

from web import app

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    try:
        import gunicorn.app.base
        from gunicorn.app.base import BaseApplication

        class StandaloneApp(BaseApplication):
            def __init__(self, _app, options=None):
                self.options = options or {}
                self.application = _app
                super().__init__()

            def load_config(self):
                for k, v in self.options.items():
                    self.cfg.set(k.lower(), v)

            def load(self):
                return self.application

        StandaloneApp(app, {
            "bind": f"0.0.0.0:{port}",
            "workers": 2,
            "timeout": 120,
        }).run()
    except Exception:
        app.run(host="0.0.0.0", port=port, debug=False)
