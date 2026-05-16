#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
smart_cache.py — نظام الكاش الذكي عالي الأداء
═══════════════════════════════════════════════════
Production-Level High-Performance Cache System

الميزات:
- LRU Cache ذكي مع TTL
- Thread-safe لبيئة Async
- Cache Invalidation تلقائي
- Memory Management
- Cache Statistics
- Lazy Loading
- Debouncing لمنع الضغط الزائد
"""

import time
import asyncio
import threading
from typing import Any, Optional, Dict, Callable, Tuple
from functools import wraps
from collections import OrderedDict


# ═══════════════════════════════════════════════════════════════
# LRU Cache مع TTL
# ═══════════════════════════════════════════════════════════════

class TTLCache:
    """
    LRU Cache مع دعم TTL (Time-To-Live).
    Thread-safe للاستخدام في بيئات Async.
    """
    
    def __init__(self, maxsize: int = 512, ttl: float = 300.0):
        """
        maxsize: الحد الأقصى لعدد العناصر
        ttl: مدة صلاحية العنصر بالثواني (افتراضي 5 دقائق)
        """
        self.maxsize = maxsize
        self.ttl = ttl
        self._cache: OrderedDict[str, Tuple[Any, float]] = OrderedDict()
        self._lock = threading.RLock()
        self._hits = 0
        self._misses = 0
    
    def get(self, key: str) -> Optional[Any]:
        """يجلب عنصراً من الكاش."""
        with self._lock:
            if key not in self._cache:
                self._misses += 1
                return None
            
            value, expires_at = self._cache[key]
            
            # فحص الانتهاء
            if time.monotonic() > expires_at:
                del self._cache[key]
                self._misses += 1
                return None
            
            # LRU: نقل للنهاية
            self._cache.move_to_end(key)
            self._hits += 1
            return value
    
    def set(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        """يضيف أو يُحدّث عنصراً في الكاش."""
        with self._lock:
            effective_ttl = ttl if ttl is not None else self.ttl
            expires_at = time.monotonic() + effective_ttl
            
            if key in self._cache:
                self._cache.move_to_end(key)
            self._cache[key] = (value, expires_at)
            
            # إزالة العناصر القديمة إذا تجاوز الحجم
            while len(self._cache) > self.maxsize:
                self._cache.popitem(last=False)
    
    def delete(self, key: str) -> bool:
        """يحذف عنصراً من الكاش."""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False
    
    def clear(self) -> None:
        """يمسح الكاش بالكامل."""
        with self._lock:
            self._cache.clear()
    
    def invalidate_prefix(self, prefix: str) -> int:
        """يُبطل جميع المفاتيح التي تبدأ بـ prefix."""
        with self._lock:
            to_delete = [k for k in self._cache if k.startswith(prefix)]
            for k in to_delete:
                del self._cache[k]
            return len(to_delete)
    
    def cleanup_expired(self) -> int:
        """يحذف العناصر منتهية الصلاحية."""
        with self._lock:
            now = time.monotonic()
            expired = [k for k, (_, exp) in self._cache.items() if exp <= now]
            for k in expired:
                del self._cache[k]
            return len(expired)
    
    @property
    def stats(self) -> dict:
        """إحصائيات الكاش."""
        with self._lock:
            total = self._hits + self._misses
            hit_rate = (self._hits / total * 100) if total > 0 else 0
            return {
                'size': len(self._cache),
                'maxsize': self.maxsize,
                'hits': self._hits,
                'misses': self._misses,
                'hit_rate': f'{hit_rate:.1f}%',
                'ttl': self.ttl,
            }


# ═══════════════════════════════════════════════════════════════
# الكاشات المتخصصة للبوت
# ═══════════════════════════════════════════════════════════════

# كاش المستشفيات (تغيير نادر)
_hospitals_cache = TTLCache(maxsize=256, ttl=600.0)  # 10 دقائق

# كاش الأطباء (تغيير متوسط)
_doctors_cache = TTLCache(maxsize=512, ttl=300.0)    # 5 دقائق

# كاش قوائم المدن والأزرار (تغيير نادر جداً)
_buttons_cache = TTLCache(maxsize=128, ttl=1800.0)   # 30 دقيقة

# كاش الإعدادات (تغيير نادر)
_settings_cache = TTLCache(maxsize=64, ttl=120.0)    # دقيقتان

# كاش المستخدمين (تغيير متكرر)
_users_cache = TTLCache(maxsize=1024, ttl=60.0)      # دقيقة واحدة

# كاش الشعارات (تغيير نادر)
_logos_cache = TTLCache(maxsize=256, ttl=900.0)      # 15 دقيقة


# ═══════════════════════════════════════════════════════════════
# دوال Wrapper للكاشات
# ═══════════════════════════════════════════════════════════════

def get_hospitals_cached(city: str = None, h_type: str = None) -> Optional[Any]:
    """يجلب مستشفيات مدينة من الكاش."""
    key = f'hosp:{city or "all"}:{h_type or "all"}'
    return _hospitals_cache.get(key)


def set_hospitals_cached(value: Any, city: str = None, h_type: str = None) -> None:
    """يحفظ مستشفيات مدينة في الكاش."""
    key = f'hosp:{city or "all"}:{h_type or "all"}'
    _hospitals_cache.set(key, value)


def get_doctors_cached(hospital_name: str) -> Optional[Any]:
    """يجلب أطباء مستشفى من الكاش."""
    key = f'doc:{hospital_name}'
    return _doctors_cache.get(key)


def set_doctors_cached(hospital_name: str, value: Any) -> None:
    """يحفظ أطباء مستشفى في الكاش."""
    key = f'doc:{hospital_name}'
    _doctors_cache.set(key, value)


def get_setting_cached(setting_key: str) -> Optional[Any]:
    """يجلب إعداداً من الكاش."""
    return _settings_cache.get(f'setting:{setting_key}')


def set_setting_cached(setting_key: str, value: Any) -> None:
    """يحفظ إعداداً في الكاش."""
    _settings_cache.set(f'setting:{setting_key}', value)


def get_user_cached(user_id: int) -> Optional[Any]:
    """يجلب بيانات مستخدم من الكاش."""
    return _users_cache.get(f'user:{user_id}')


def set_user_cached(user_id: int, value: Any) -> None:
    """يحفظ بيانات مستخدم في الكاش."""
    _users_cache.set(f'user:{user_id}', value)


def get_logo_cached(hospital_name: str) -> Optional[Any]:
    """يجلب شعار مستشفى من الكاش."""
    return _logos_cache.get(f'logo:{hospital_name}')


def set_logo_cached(hospital_name: str, value: Any) -> None:
    """يحفظ شعار مستشفى في الكاش."""
    _logos_cache.set(f'logo:{hospital_name}', value)


# ═══════════════════════════════════════════════════════════════
# Invalidation (إبطال الكاش عند التحديث)
# ═══════════════════════════════════════════════════════════════

def invalidate_hospital_cache(city: str = None) -> None:
    """يُبطل كاش المستشفيات بعد التعديل."""
    if city:
        _hospitals_cache.invalidate_prefix(f'hosp:{city}')
    else:
        _hospitals_cache.clear()
    # أبطل أيضاً كاش الأزرار
    _buttons_cache.clear()


def invalidate_doctor_cache(hospital_name: str = None) -> None:
    """يُبطل كاش الأطباء بعد التعديل."""
    if hospital_name:
        _doctors_cache.delete(f'doc:{hospital_name}')
    else:
        _doctors_cache.clear()


def invalidate_user_cache(user_id: int = None) -> None:
    """يُبطل كاش المستخدم بعد التعديل."""
    if user_id:
        _users_cache.delete(f'user:{user_id}')
    else:
        _users_cache.clear()


def invalidate_logo_cache(hospital_name: str = None) -> None:
    """يُبطل كاش الشعارات بعد التعديل."""
    if hospital_name:
        _logos_cache.delete(f'logo:{hospital_name}')
    else:
        _logos_cache.clear()


def invalidate_setting_cache(key: str = None) -> None:
    """يُبطل كاش الإعدادات."""
    if key:
        _settings_cache.delete(f'setting:{key}')
    else:
        _settings_cache.clear()


def invalidate_all_caches() -> None:
    """يُبطل جميع الكاشات."""
    _hospitals_cache.clear()
    _doctors_cache.clear()
    _buttons_cache.clear()
    _settings_cache.clear()
    _users_cache.clear()
    _logos_cache.clear()


# ═══════════════════════════════════════════════════════════════
# Decorator للكاش التلقائي
# ═══════════════════════════════════════════════════════════════

def cached(cache_obj: TTLCache, key_func: Callable = None, ttl: float = None):
    """
    Decorator يضيف كاش تلقائي لأي دالة.
    
    مثال:
        @cached(_hospitals_cache, key_func=lambda city: f'hosp:{city}')
        def get_hospitals(city):
            ...
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                cache_key = f'{func.__name__}:{args}:{sorted(kwargs.items())}'
            
            # محاولة جلب من الكاش
            cached_val = cache_obj.get(cache_key)
            if cached_val is not None:
                return cached_val
            
            # تنفيذ الدالة الأصلية
            result = func(*args, **kwargs)
            
            # حفظ النتيجة
            if result is not None:
                cache_obj.set(cache_key, result, ttl=ttl)
            
            return result
        
        # إضافة دالة للإبطال
        wrapper.invalidate = lambda *args, **kwargs: (
            cache_obj.delete(key_func(*args, **kwargs)) if key_func
            else cache_obj.invalidate_prefix(func.__name__)
        )
        
        return wrapper
    return decorator


# ═══════════════════════════════════════════════════════════════
# Debounce لمنع الضغط الزائد
# ═══════════════════════════════════════════════════════════════

class Debouncer:
    """
    يُؤخّر تنفيذ الدالة حتى يستقر المدخل.
    مفيد لعمليات البحث في قواعد البيانات.
    """
    
    def __init__(self, delay: float = 0.5):
        self.delay = delay
        self._timers: Dict[str, asyncio.Task] = {}
    
    async def debounce(self, key: str, coro_func, *args, **kwargs):
        """
        يُؤخّر تنفيذ coro_func بمقدار delay ثانية.
        إذا نُودي مجدداً قبل انتهاء المهلة، يُلغي الطلب السابق.
        """
        # إلغاء المهمة السابقة إن وُجدت
        if key in self._timers:
            try:
                self._timers[key].cancel()
            except Exception:
                pass
        
        # إنشاء مهمة جديدة
        async def delayed():
            await asyncio.sleep(self.delay)
            return await coro_func(*args, **kwargs)
        
        task = asyncio.ensure_future(delayed())
        self._timers[key] = task
        
        try:
            return await task
        except asyncio.CancelledError:
            return None


# ═══════════════════════════════════════════════════════════════
# تنظيف دوري للكاش
# ═══════════════════════════════════════════════════════════════

async def periodic_cache_cleanup(interval: float = 300.0):
    """
    يُنظّف العناصر منتهية الصلاحية من الكاش كل interval ثانية.
    يجب تشغيله كـ Background Task.
    """
    while True:
        try:
            await asyncio.sleep(interval)
            caches = [
                _hospitals_cache, _doctors_cache, _buttons_cache,
                _settings_cache, _users_cache, _logos_cache
            ]
            total_cleaned = sum(c.cleanup_expired() for c in caches)
        except asyncio.CancelledError:
            break
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════
# إحصائيات الكاش الشاملة
# ═══════════════════════════════════════════════════════════════

def get_cache_stats() -> dict:
    """يُعيد إحصائيات جميع الكاشات."""
    return {
        'hospitals': _hospitals_cache.stats,
        'doctors':   _doctors_cache.stats,
        'buttons':   _buttons_cache.stats,
        'settings':  _settings_cache.stats,
        'users':     _users_cache.stats,
        'logos':     _logos_cache.stats,
    }
