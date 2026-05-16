#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
duplicate_detector.py — نظام كشف التكرار الذكي
═══════════════════════════════════════════════════
Production-Level Smart Duplicate Detection

يعتمد على:
- Levenshtein Distance
- Cosine Similarity (Token-based)
- Normalized Text Comparison
- Phonetic-like Arabic Comparison
- Abbreviation Detection

يكشف التكرار حتى مع:
- اختلاف الهمزات (أ/إ/آ/ا)
- اختلاف التاء المربوطة (ة/ه)
- اختلاف المسافات
- الاختصارات (Hosp. → مستشفى)
- الترجمة (King → الملك)
- الأحرف الكبيرة/الصغيرة
- أخطاء إملائية بسيطة
"""

import re
from typing import List, Tuple, Optional, Dict
from normalizer import normalize_hospital_name, normalize_for_comparison, to_western_digits


# ═══════════════════════════════════════════════════════════════
# خوارزمية Levenshtein Distance
# ═══════════════════════════════════════════════════════════════

def levenshtein_distance(s1: str, s2: str) -> int:
    """يحسب مسافة Levenshtein بين نصّين."""
    if s1 == s2:
        return 0
    if not s1:
        return len(s2)
    if not s2:
        return len(s1)
    
    # استخدام DP Matrix
    m, n = len(s1), len(s2)
    # تحسين: استخدام صفّين فقط (space O(n))
    prev = list(range(n + 1))
    curr = [0] * (n + 1)
    
    for i in range(1, m + 1):
        curr[0] = i
        for j in range(1, n + 1):
            cost = 0 if s1[i-1] == s2[j-1] else 1
            curr[j] = min(
                prev[j] + 1,      # حذف
                curr[j-1] + 1,    # إضافة
                prev[j-1] + cost  # استبدال
            )
        prev, curr = curr, [0] * (n + 1)
    
    return prev[n]


def similarity_ratio(s1: str, s2: str) -> float:
    """
    يحسب نسبة التشابه بين نصّين (0.0 إلى 1.0).
    يعتمد على Levenshtein مع تطبيع للطول.
    """
    if not s1 and not s2:
        return 1.0
    if not s1 or not s2:
        return 0.0
    
    max_len = max(len(s1), len(s2))
    dist = levenshtein_distance(s1, s2)
    return 1.0 - (dist / max_len)


# ═══════════════════════════════════════════════════════════════
# Token-Based Similarity (Cosine-like)
# ═══════════════════════════════════════════════════════════════

def _tokenize(text: str) -> set:
    """يقسّم النص إلى كلمات."""
    if not text:
        return set()
    # إزالة الكلمات الوقفية الشائعة
    STOP_WORDS = {
        'مستشفى', 'مستشفي', 'hospital', 'medical', 'center', 'centre',
        'مركز', 'عيادة', 'عياده', 'clinic', 'health',
        'الطبي', 'الطبية', 'الطبيه',
    }
    tokens = set(text.split())
    return tokens - STOP_WORDS


def token_similarity(s1: str, s2: str) -> float:
    """
    يحسب تشابه Jaccard بين مجموعتي الكلمات.
    مفيد لأسماء طويلة تشترك في معظم الكلمات.
    """
    t1 = _tokenize(s1)
    t2 = _tokenize(s2)
    if not t1 and not t2:
        return 1.0
    if not t1 or not t2:
        return 0.0
    
    intersection = len(t1 & t2)
    union = len(t1 | t2)
    return intersection / union if union > 0 else 0.0


# ═══════════════════════════════════════════════════════════════
# الكلمات المترجمة (عربي-إنجليزي)
# ═══════════════════════════════════════════════════════════════

_TRANSLATIONS = {
    # عربي → إنجليزي
    'الملك': 'king', 'الأمير': 'prince', 'الأميرة': 'princess',
    'الملكة': 'queen', 'الأمير': 'prince',
    'مستشفى': 'hospital', 'مستشفي': 'hospital',
    'مدينة': 'city', 'مركز': 'center',
    'فهد': 'fahad', 'عبدالله': 'abdullah', 'عبد الله': 'abdullah',
    'عبدالعزيز': 'abdulaziz', 'عبد العزيز': 'abdulaziz',
    'سلمان': 'salman', 'خالد': 'khalid', 'سعود': 'saud',
    'فيصل': 'faisal', 'محمد': 'mohammed',
    'التخصصي': 'specialist', 'الجامعي': 'university',
    'العسكري': 'military', 'الوطني': 'national',
    'العام': 'general', 'الدولي': 'international',
    'الخاص': 'private', 'الحكومي': 'government',
    # إنجليزي → عربي (العكس)
    'king': 'الملك', 'prince': 'الأمير', 'hospital': 'مستشفى',
    'fahad': 'فهد', 'fahd': 'فهد',
    'abdullah': 'عبدالله', 'abdulaziz': 'عبدالعزيز',
    'salman': 'سلمان', 'khalid': 'خالد',
    'specialist': 'التخصصي', 'general': 'العام',
    'national': 'الوطني', 'military': 'العسكري',
    'university': 'الجامعي', 'international': 'الدولي',
    'hosp': 'مستشفى', 'med': 'طبي',
    'dr': 'دكتور', 'dr.': 'دكتور',
}

_ABBREVIATIONS = {
    'hosp.': 'hospital', 'hosp': 'hospital',
    'med.': 'medical', 'med': 'medical',
    'univ.': 'university', 'univ': 'university',
    'gen.': 'general', 'gen': 'general',
    'intl': 'international', 'intl.': 'international',
    'ctr': 'center', 'ctr.': 'center',
    'dr.': 'doctor', 'dr': 'doctor',
}


def _normalize_translations(text: str) -> str:
    """يُوحّد الترجمات بين العربي والإنجليزي."""
    words = text.split()
    result = []
    for word in words:
        # توسيع الاختصارات أولاً
        expanded = _ABBREVIATIONS.get(word, word)
        # ثم الترجمة
        translated = _TRANSLATIONS.get(expanded, expanded)
        result.append(translated)
    return ' '.join(result)


# ═══════════════════════════════════════════════════════════════
# الدالة الرئيسية للتشابه
# ═══════════════════════════════════════════════════════════════

def compute_similarity(name1: str, name2: str) -> float:
    """
    يحسب نسبة التشابه الشاملة بين اسمي مستشفيَين.
    يُعيد قيمة من 0.0 (مختلف تماماً) إلى 1.0 (متطابق).
    
    يجمع بين:
    - مقارنة النص المطبَّع
    - Token similarity
    - Levenshtein
    - مقارنة بعد الترجمة
    """
    if not name1 or not name2:
        return 0.0
    
    # تطبيع الاسمين
    n1 = normalize_hospital_name(name1)
    n2 = normalize_hospital_name(name2)
    
    if not n1 or not n2:
        return 0.0
    
    # تطابق تام بعد التطبيع
    if n1 == n2:
        return 1.0
    
    scores = []
    
    # 1. Levenshtein ratio
    lev_score = similarity_ratio(n1, n2)
    scores.append(lev_score * 0.35)
    
    # 2. Token Jaccard
    tok_score = token_similarity(n1, n2)
    scores.append(tok_score * 0.30)
    
    # 3. Prefix matching (الاسم المشترك في البداية)
    min_len = min(len(n1), len(n2))
    prefix_len = 0
    for i in range(min_len):
        if n1[i] == n2[i]:
            prefix_len += 1
        else:
            break
    prefix_score = prefix_len / max(len(n1), len(n2)) if max(len(n1), len(n2)) > 0 else 0
    scores.append(prefix_score * 0.15)
    
    # 4. مقارنة بعد الترجمة
    t1 = _normalize_translations(n1)
    t2 = _normalize_translations(n2)
    if t1 != n1 or t2 != n2:  # تمت ترجمة شيء
        trans_score = similarity_ratio(t1, t2)
        scores.append(trans_score * 0.20)
    else:
        scores.append(0.0)
    
    return sum(scores)


# ═══════════════════════════════════════════════════════════════
# الكشف عن التكرار في القائمة
# ═══════════════════════════════════════════════════════════════

def find_duplicates(
    new_name: str,
    existing_names: List[str],
    threshold: float = 0.75
) -> List[Tuple[str, float]]:
    """
    يبحث عن أسماء مشابهة لـ new_name في قائمة existing_names.
    
    threshold: الحد الأدنى لنسبة التشابه (افتراضي 75%)
    
    يُعيد قائمة من (اسم_موجود, نسبة_تشابه) مرتبة تنازلياً.
    """
    if not new_name or not existing_names:
        return []
    
    results = []
    for existing in existing_names:
        if not existing:
            continue
        score = compute_similarity(new_name, existing)
        if score >= threshold:
            results.append((existing, score))
    
    # ترتيب تنازلي حسب التشابه
    results.sort(key=lambda x: x[1], reverse=True)
    return results


def is_duplicate(
    new_name: str,
    existing_names: List[str],
    threshold: float = 0.80
) -> Tuple[bool, Optional[str], float]:
    """
    يتحقق هل new_name مكرّر في existing_names.
    
    يُعيد: (is_dup, best_match, score)
    """
    duplicates = find_duplicates(new_name, existing_names, threshold)
    if duplicates:
        best_match, score = duplicates[0]
        return True, best_match, score
    return False, None, 0.0


# ═══════════════════════════════════════════════════════════════
# رسائل الخطأ الذكية
# ═══════════════════════════════════════════════════════════════

def format_duplicate_warning(
    new_name: str,
    similar_names: List[Tuple[str, float]]
) -> str:
    """
    يُنشئ رسالة تحذير ذكية عند وجود أسماء مشابهة.
    """
    if not similar_names:
        return ''
    
    lines = [
        f'⚠️ *تحذير: أسماء مشابهة موجودة مسبقاً!*\n',
        f'🔍 الاسم الذي أدخلته: *{new_name}*\n',
        '📋 الأسماء المشابهة في النظام:\n',
    ]
    
    for name, score in similar_names[:5]:
        pct = int(score * 100)
        if score >= 0.95:
            icon = '🔴'
            label = 'شبه متطابق'
        elif score >= 0.85:
            icon = '🟠'
            label = 'متشابه جداً'
        elif score >= 0.75:
            icon = '🟡'
            label = 'متشابه'
        else:
            icon = '🟢'
            label = 'قريب'
        
        lines.append(f'  {icon} *{name}* — {label} ({pct}%)')
    
    lines.append('\n💡 هل تريد استخدام الاسم الموجود أم إضافة اسم جديد؟')
    
    return '\n'.join(lines)


# ═══════════════════════════════════════════════════════════════
# فحص سريع بدون حساب (Hash-based)
# ═══════════════════════════════════════════════════════════════

class DuplicateIndex:
    """
    فهرس سريع للكشف عن التكرار.
    يُبنى مرة واحدة ويُستعلم منه بشكل متكرر.
    
    يستخدم Hash على النص المطبَّع لبحث O(1) المبدئي،
    ثم Levenshtein للتأكيد.
    """
    
    def __init__(self, names: List[str], threshold: float = 0.80):
        self.threshold = threshold
        self.names = list(names)
        self._normalized = {
            normalize_hospital_name(n): n
            for n in names if n
        }
    
    def add(self, name: str):
        """يضيف اسماً جديداً للفهرس."""
        if name:
            self.names.append(name)
            self._normalized[normalize_hospital_name(name)] = name
    
    def remove(self, name: str):
        """يزيل اسماً من الفهرس."""
        if name in self.names:
            self.names.remove(name)
        norm = normalize_hospital_name(name)
        self._normalized.pop(norm, None)
    
    def check(self, new_name: str) -> List[Tuple[str, float]]:
        """
        يبحث عن تكرارات الاسم الجديد.
        يُعيد قائمة (اسم_موجود, نسبة_تشابه).
        """
        # فحص سريع بالتطبيع
        norm_new = normalize_hospital_name(new_name)
        if norm_new in self._normalized:
            original = self._normalized[norm_new]
            return [(original, 1.0)]
        
        # فحص شامل بالتشابه
        return find_duplicates(new_name, self.names, self.threshold)
    
    def is_unique(self, new_name: str) -> bool:
        """يُعيد True إذا كان الاسم غير مكرر."""
        return len(self.check(new_name)) == 0
    
    def get_suggestion(self, new_name: str) -> Optional[str]:
        """يُعيد أفضل تطابق إن وُجد."""
        results = self.check(new_name)
        return results[0][0] if results else None
