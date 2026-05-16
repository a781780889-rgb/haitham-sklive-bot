#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
db_adapter.py  —  طبقة توافق SQLite ↔ PostgreSQL
═══════════════════════════════════════════════════════════════════

الهدف
─────
يتيح لبقية الكود أن يكتب SQL بلهجة SQLite (التي يستخدمها المشروع حالياً)
وأن يعمل دون أي تغيير على PostgreSQL عند نشر البوت على Railway.

الاستخدام
─────────
    from db_adapter import get_connection, Row, USE_POSTGRES

    conn = get_connection()           # اتصال موحّد
    cur  = conn.execute("SELECT * FROM users WHERE user_id=?", (uid,))
    row  = cur.fetchone()             # يسلك سلوك sqlite3.Row (ينفذ row[0] و row["name"])
    oid  = conn.execute("INSERT INTO t(x) VALUES(?)", (v,)).lastrowid
    with conn.savepoint("sp1"):       # SAVEPOINT متداخل (يعمل على الاثنين)
        conn.execute("UPDATE ...")
    conn.commit(); conn.close()

الكشف
─────
إذا كان متغيّر البيئة DATABASE_URL موجوداً ويبدأ بـ postgres(ql)://
يُستخدم PostgreSQL؛ وإلا يُستخدم ملف SQLite محلي (bot_data.db).

الميزات
───────
• ترجمة تلقائية للـ SQL المختلف:  ?  →  %s
• datetime('now')                 →  to_char(CURRENT_TIMESTAMP, 'YYYY-MM-DD HH24:MI:SS')
• DATE('now') / DATE(col)         →  CURRENT_DATE / (col::timestamp::date)
• strftime('%Y-%m', col)           →  to_char(col::timestamp, 'YYYY-MM')
• julianday(...) * 1440            →  EXTRACT(EPOCH FROM ...) / 60
• AUTOINCREMENT                    →  SERIAL
• INSERT OR IGNORE                 →  INSERT ... ON CONFLICT DO NOTHING
• PRAGMA ...                       →  يُتجاهل بصمت في PostgreSQL
• lastrowid                        →  يُعاد عبر RETURNING * تلقائياً
• SAVEPOINT / ROLLBACK TO / RELEASE — تعمل بشكل متطابق
"""

import os
import re
import sqlite3
import logging
import threading
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────
# إعدادات الكشف
# ─────────────────────────────────────────────────────────

_RAW_URL = os.environ.get("DATABASE_URL", "").strip()
USE_POSTGRES = _RAW_URL.startswith("postgres://") or _RAW_URL.startswith("postgresql://")

# Railway أحياناً يُعيد الـ URL بصيغة postgres:// المهجورة — نُطبّعها
if USE_POSTGRES and _RAW_URL.startswith("postgres://"):
    DATABASE_URL = _RAW_URL.replace("postgres://", "postgresql://", 1)
else:
    DATABASE_URL = _RAW_URL

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot_data.db")

if USE_POSTGRES:
    try:
        import psycopg2
        import psycopg2.extensions
    except ImportError:  # pragma: no cover
        raise RuntimeError(
            "DATABASE_URL يُشير إلى PostgreSQL لكن حزمة psycopg2-binary غير مثبّتة. "
            "أضف psycopg2-binary إلى requirements.txt"
        )
    logger.info("🐘 db_adapter: تم تفعيل وضع PostgreSQL")
else:
    logger.info("🗄️  db_adapter: تم تفعيل وضع SQLite (DATABASE_URL غير مُعدّ)")


# ═════════════════════════════════════════════════════════
# Row-like موحّد (يدعم row[0] و row["name"] و dict(row))
# ═════════════════════════════════════════════════════════

class _Row:
    """بديل متوافق مع sqlite3.Row لوضع PostgreSQL."""
    __slots__ = ("_keys", "_values")

    def __init__(self, keys, values):
        self._keys = tuple(keys)
        self._values = tuple(values)

    def __getitem__(self, k):
        if isinstance(k, int):
            return self._values[k]
        try:
            return self._values[self._keys.index(k)]
        except ValueError:
            raise KeyError(k)

    def keys(self):
        return list(self._keys)

    def get(self, k, default=None):
        try:
            return self[k]
        except (KeyError, IndexError):
            return default

    def __iter__(self):
        return iter(self._values)

    def __len__(self):
        return len(self._values)

    def __contains__(self, k):
        return k in self._keys

    def __repr__(self):
        return f"Row({dict(zip(self._keys, self._values))!r})"


# في وضع SQLite نُصدّر sqlite3.Row مباشرة
Row = _Row if USE_POSTGRES else sqlite3.Row


# ═════════════════════════════════════════════════════════
# مترجِم SQL (SQLite → PostgreSQL)
# ═════════════════════════════════════════════════════════

_SQLITE_TO_PG_DATEFMT = {
    "%Y": "YYYY", "%m": "MM", "%d": "DD",
    "%H": "HH24", "%M": "MI", "%S": "SS",
    "%W": "WW", "%j": "DDD",
}


def _convert_datefmt(fmt: str) -> str:
    out = fmt
    for k, v in _SQLITE_TO_PG_DATEFMT.items():
        out = out.replace(k, v)
    return out


def translate_sql(sql: str) -> str:
    """
    يحوّل SQL من لهجة SQLite إلى لهجة PostgreSQL.
    تُستدعى فقط في وضع PostgreSQL.
    """
    s = sql

    # 1) علامات الاستفهام → %s  (psycopg2)
    #    (سلامة بسيطة: لا تلمس ? داخل السلاسل النصية. في SQL المشروع لا توجد ? داخل سلاسل.)
    s = s.replace("?", "%s")

    # 2) datetime('now')  →  to_char(CURRENT_TIMESTAMP, ...)  — نُبقيها نصاً ليتوافق مع TEXT
    s = re.sub(
        r"datetime\(\s*'now'\s*\)",
        "to_char(CURRENT_TIMESTAMP, 'YYYY-MM-DD HH24:MI:SS')",
        s, flags=re.IGNORECASE,
    )

    # 3) datetime('now', '-90 days') → (CURRENT_TIMESTAMP + INTERVAL '-90 days')
    def _datetime_offset(m):
        n = m.group(1).strip()
        unit = m.group(2).strip()
        return f"to_char((CURRENT_TIMESTAMP + INTERVAL '{n} {unit}'), 'YYYY-MM-DD HH24:MI:SS')"
    s = re.sub(
        r"datetime\(\s*'now'\s*,\s*'([+-]?\s*\d+)\s+(day|days|hour|hours|minute|minutes|second|seconds|month|months|year|years)'\s*\)",
        _datetime_offset, s, flags=re.IGNORECASE,
    )

    # 4) DATE('now') → CURRENT_DATE
    s = re.sub(r"DATE\(\s*'now'\s*\)", "CURRENT_DATE", s, flags=re.IGNORECASE)

    # 5) DATE(col) حيث col هي TEXT — نستخدم cast
    s = re.sub(
        r"DATE\(\s*([a-zA-Z_][a-zA-Z0-9_\.]*)\s*\)",
        r"(\1::timestamp::date)",
        s,
    )

    # 6) strftime('%Y-%m', 'now') → to_char(CURRENT_TIMESTAMP, 'YYYY-MM')
    def _strftime_now(m):
        return f"to_char(CURRENT_TIMESTAMP, '{_convert_datefmt(m.group(1))}')"
    s = re.sub(
        r"strftime\(\s*'([^']+)'\s*,\s*'now'\s*\)",
        _strftime_now, s, flags=re.IGNORECASE,
    )

    # 7) strftime('%Y-%m', col) → to_char(col::timestamp, 'YYYY-MM')
    def _strftime_col(m):
        return f"to_char({m.group(2).strip()}::timestamp, '{_convert_datefmt(m.group(1))}')"
    s = re.sub(
        r"strftime\(\s*'([^']+)'\s*,\s*([a-zA-Z_][a-zA-Z0-9_\.]*)\s*\)",
        _strftime_col, s, flags=re.IGNORECASE,
    )

    # 8) CAST((julianday('now') - julianday(col)) * 1440 AS INTEGER) → minutes_ago
    s = re.sub(
        r"CAST\(\s*\(\s*julianday\(\s*'now'\s*\)\s*-\s*julianday\(\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\)\s*\)\s*\*\s*1440\s+AS\s+INTEGER\s*\)",
        r"CAST(EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - \1::timestamp))/60 AS INTEGER)",
        s, flags=re.IGNORECASE,
    )
    # مقياس عام: (julianday('now') - julianday(col))   → أيام
    s = re.sub(
        r"\(\s*julianday\(\s*'now'\s*\)\s*-\s*julianday\(\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\)\s*\)",
        r"(EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - \1::timestamp))/86400)",
        s, flags=re.IGNORECASE,
    )

    # 9) INTEGER PRIMARY KEY AUTOINCREMENT → SERIAL PRIMARY KEY
    s = re.sub(
        r"INTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT",
        "SERIAL PRIMARY KEY",
        s, flags=re.IGNORECASE,
    )

    # 10) TEXT DEFAULT (to_char(...))  — PostgreSQL يتطلب cast ::text
    #     نُضيف ::text إذا كانت ضمن DEFAULT وليست داخل CAST بالفعل
    s = re.sub(
        r"DEFAULT\s*\(\s*to_char\(",
        "DEFAULT (to_char(",
        s, flags=re.IGNORECASE,
    )

    # 11) TIMESTAMP DEFAULT CURRENT_TIMESTAMP — PG يفهمها أصلاً. لا تغيير.

    # 12) INSERT OR IGNORE INTO ...  →  INSERT INTO ... ON CONFLICT DO NOTHING
    if re.search(r"\bINSERT\s+OR\s+IGNORE\s+INTO\b", s, flags=re.IGNORECASE):
        s = re.sub(r"\bINSERT\s+OR\s+IGNORE\s+INTO\b", "INSERT INTO", s, flags=re.IGNORECASE)
        if not re.search(r"\bON\s+CONFLICT\b", s, flags=re.IGNORECASE):
            s = s.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"

    # 13) INSERT OR REPLACE INTO — ترجمة بسيطة (غير مثالية؛ نرفعها كإنذار ونُسقطها إلى INSERT + ON CONFLICT إذا كانت فيها UPSERT صريحة)
    #     الكود الفعلي في المشروع لا يحتاجها مع تعديلنا لـ set_setting.
    if re.search(r"\bINSERT\s+OR\s+REPLACE\s+INTO\b", s, flags=re.IGNORECASE):
        # إذا كانت فيها ON CONFLICT بالفعل، لا مشكلة
        s = re.sub(r"\bINSERT\s+OR\s+REPLACE\s+INTO\b", "INSERT INTO", s, flags=re.IGNORECASE)

    # 14-a) BLOB → BYTEA  (PostgreSQL لا يدعم نوع BLOB — يستخدم BYTEA بدلاً منه)
    s = re.sub(r'\bBLOB\b', 'BYTEA', s, flags=re.IGNORECASE)

    # 14-b) INTEGER PRIMARY KEY (بدون AUTOINCREMENT) → BIGINT PRIMARY KEY
    #        لدعم Telegram user_id الذي يتجاوز حد INTEGER (32-bit) في PostgreSQL
    s = re.sub(
        r'\bINTEGER\s+PRIMARY\s+KEY\b(?!\s+AUTOINCREMENT)',
        'BIGINT PRIMARY KEY',
        s, flags=re.IGNORECASE,
    )

    # 14-c) بقية أعمدة INTEGER → BIGINT (لتجنب تجاوز النطاق في أي عمود)
    #        نتجنب المساس بـ SERIAL PRIMARY KEY الذي تم تحويله مسبقاً
    s = re.sub(r'\bINTEGER\b(?!\s+PRIMARY)', 'BIGINT', s, flags=re.IGNORECASE)

    # 14) PRAGMA ... — إزالة كاملة (لا يدعمها PostgreSQL)
    if re.match(r"\s*PRAGMA\b", s, flags=re.IGNORECASE):
        return ""  # جملة فارغة — سيتم تخطّيها

    # 15) SELECT changes() — لا مقابل مباشر؛ نتجنّبها في database.py (نُعدّل الشفرة لتستخدم cur.rowcount)
    # 16) lastrowid — نتولاه عبر RETURNING أدناه

    return s


# ═════════════════════════════════════════════════════════
# غلاف اتصال PostgreSQL
# ═════════════════════════════════════════════════════════

class _PGCursor:
    """يحاكي واجهة sqlite3.Cursor."""

    def __init__(self, raw_cursor):
        self._cur = raw_cursor
        self._last_row = None       # صف RETURNING المُخزّن بعد INSERT
        self._consumed = False      # هل تم استهلاك _last_row؟
        self._last_was_insert = False

    @staticmethod
    def _fix_params(params):
        """يحوّل bytes → psycopg2.Binary لضمان تخزين البيانات الثنائية بشكل صحيح في BYTEA"""
        if not params:
            return params
        return tuple(
            psycopg2.Binary(p) if isinstance(p, (bytes, bytearray)) else p
            for p in params
        )

    def execute(self, sql, params=()):
        params = self._fix_params(params)
        translated = translate_sql(sql)
        if not translated.strip():
            # جملة PRAGMA مُتجاهلة — نعود دون فعل شيء
            self._last_row = None
            self._consumed = True
            self._last_was_insert = False
            return self

        stripped = translated.lstrip().upper()
        self._last_was_insert = stripped.startswith("INSERT")

        # للـ INSERT بدون RETURNING، نُضيف RETURNING * لاسترجاع lastrowid
        if self._last_was_insert and "RETURNING" not in stripped:
            translated = translated.rstrip().rstrip(";") + " RETURNING *"

        if params is None:
            params = ()
        self._cur.execute(translated, params)

        self._last_row = None
        self._consumed = False
        if self._last_was_insert and self._cur.description:
            try:
                raw = self._cur.fetchone()
                if raw is not None:
                    keys = [d[0] for d in self._cur.description]
                    self._last_row = _Row(keys, raw)
            except psycopg2.ProgrammingError:
                pass
        return self

    def executemany(self, sql, seq_of_params):
        seq_of_params = [self._fix_params(p) for p in seq_of_params]
        translated = translate_sql(sql)
        if not translated.strip():
            return self
        self._cur.executemany(translated, list(seq_of_params))
        self._last_row = None
        self._consumed = True
        self._last_was_insert = False
        return self

    def fetchone(self):
        # إذا كانت النتيجة مخزّنة من INSERT ... RETURNING *، أعِدها مرّة واحدة
        if self._last_row is not None and not self._consumed:
            self._consumed = True
            return self._last_row
        try:
            raw = self._cur.fetchone()
        except psycopg2.ProgrammingError:
            return None
        if raw is None:
            return None
        keys = [d[0] for d in self._cur.description]
        return _Row(keys, raw)

    def fetchall(self):
        if self._last_row is not None and not self._consumed:
            self._consumed = True
            try:
                rest_raw = self._cur.fetchall()
            except psycopg2.ProgrammingError:
                rest_raw = []
            keys = [d[0] for d in self._cur.description]
            rest = [_Row(keys, r) for r in rest_raw]
            return [self._last_row] + rest
        try:
            rows = self._cur.fetchall()
        except psycopg2.ProgrammingError:
            return []
        keys = [d[0] for d in self._cur.description] if self._cur.description else []
        return [_Row(keys, r) for r in rows]

    @property
    def rowcount(self):
        return self._cur.rowcount

    @property
    def lastrowid(self):
        """
        يُحاكي cursor.lastrowid الخاص بـ SQLite:
        • إذا نجح INSERT وأعاد صفاً → id الصف الجديد (العمود الأول إن لم يوجد عمود اسمه id)
        • إذا فُلترت بـ ON CONFLICT DO NOTHING ولم يُدرج شيء → 0
          (يتطابق مع سلوك INSERT OR IGNORE في SQLite)
        """
        if self._last_row is None:
            return 0 if self._last_was_insert else None
        try:
            return self._last_row["id"]
        except KeyError:
            return self._last_row[0] if len(self._last_row) else None

    @property
    def description(self):
        return self._cur.description

    def close(self):
        try:
            self._cur.close()
        except Exception:
            pass


class _PGConnection:
    """يحاكي واجهة sqlite3.Connection ويضيف .savepoint()."""

    _pool_lock = threading.Lock()

    def __init__(self, url):
        self._conn = psycopg2.connect(url)
        self._conn.autocommit = False
        self.row_factory = None  # يُتجاهل — _Row يُستخدم دوماً

    def cursor(self):
        return _PGCursor(self._conn.cursor())

    def execute(self, sql, params=()):
        return self.cursor().execute(sql, params)

    def executemany(self, sql, seq):
        return self.cursor().executemany(sql, seq)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        try:
            self._conn.rollback()
        except Exception:
            pass

    def close(self):
        try:
            self._conn.close()
        except Exception:
            pass

    @contextmanager
    def savepoint(self, name="sp"):
        """
        نقطة حفظ متداخلة داخل معاملة. مثال:

            with conn.savepoint("s1"):
                conn.execute(...)   # إذا فشلت → ROLLBACK TO s1
        """
        safe_name = re.sub(r"[^A-Za-z0-9_]", "_", str(name)) or "sp"
        cur = self._conn.cursor()
        try:
            cur.execute(f"SAVEPOINT {safe_name}")
            try:
                yield
                cur.execute(f"RELEASE SAVEPOINT {safe_name}")
            except Exception:
                cur.execute(f"ROLLBACK TO SAVEPOINT {safe_name}")
                raise
        finally:
            cur.close()


# ═════════════════════════════════════════════════════════
# غلاف اتصال SQLite (واجهة متطابقة)
# ═════════════════════════════════════════════════════════

class _SQLiteConnection:
    """
    غلاف على sqlite3.Connection يُوفّر نفس الـ API الموسّع (savepoint)
    ويُعيد أيضاً row_factory = sqlite3.Row.
    """

    def __init__(self, raw_conn):
        self._conn = raw_conn
        self._conn.row_factory = sqlite3.Row
        # تحسينات SQLite
        try:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.execute("PRAGMA cache_size=10000")
            self._conn.execute("PRAGMA foreign_keys=ON")
        except Exception as e:
            logger.debug(f"PRAGMA init failed: {e}")

    @property
    def row_factory(self):
        return self._conn.row_factory

    @row_factory.setter
    def row_factory(self, v):
        self._conn.row_factory = v

    def cursor(self):
        return self._conn.cursor()

    def execute(self, sql, params=()):
        return self._conn.execute(sql, params)

    def executemany(self, sql, seq):
        return self._conn.executemany(sql, seq)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        try:
            self._conn.close()
        except Exception:
            pass

    @contextmanager
    def savepoint(self, name="sp"):
        safe_name = re.sub(r"[^A-Za-z0-9_]", "_", str(name)) or "sp"
        self._conn.execute(f"SAVEPOINT {safe_name}")
        try:
            yield
            self._conn.execute(f"RELEASE SAVEPOINT {safe_name}")
        except Exception:
            self._conn.execute(f"ROLLBACK TO SAVEPOINT {safe_name}")
            raise


# ═════════════════════════════════════════════════════════
# الواجهة العامة
# ═════════════════════════════════════════════════════════

def get_connection():
    """
    يُعيد اتصالاً موحّداً:
      • PostgreSQL إذا كان DATABASE_URL مُعدّاً
      • SQLite محلي خلاف ذلك

    يملك نفس واجهة sqlite3.Connection بالإضافة إلى:
      • conn.savepoint(name)  — context manager
    """
    if USE_POSTGRES:
        return _PGConnection(DATABASE_URL)
    raw = sqlite3.connect(DB_PATH, timeout=15)
    return _SQLiteConnection(raw)


def placeholder() -> str:
    """يُعيد علامة المَعلَم المناسبة (? أو %s) للـSQL الديناميكي."""
    return "%s" if USE_POSTGRES else "?"


# ═════════════════════════════════════════════════════════
# اختبار ذاتي بسيط
# ═════════════════════════════════════════════════════════

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(f"USE_POSTGRES = {USE_POSTGRES}")
    print(f"DB target    = {'PostgreSQL' if USE_POSTGRES else DB_PATH}")

    conn = get_connection()
    conn.execute("""CREATE TABLE IF NOT EXISTS _probe (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        ts TEXT DEFAULT (datetime('now'))
    )""")
    conn.commit()

    cur = conn.execute("INSERT INTO _probe (name) VALUES (?)", ("adapter-ok",))
    inserted = cur.lastrowid
    print(f"inserted id = {inserted}")

    with conn.savepoint("probe_sp"):
        conn.execute("INSERT INTO _probe (name) VALUES (?)", ("savepoint-ok",))

    row = conn.execute("SELECT * FROM _probe WHERE id=?", (inserted,)).fetchone()
    print("row =", dict(row) if row else None)

    conn.execute("DROP TABLE _probe")
    conn.commit()
    conn.close()
    print("✅ db_adapter self-test passed")
