import { useState, useEffect, useRef, useCallback } from "react";

// ─── Styles ────────────────────────────────────────────────────────────────
const styles = `
  @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+Arabic:wght@300;400;500;600;700&family=Playfair+Display:wght@400;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    --navy: #0a0e1a;
    --navy-2: #111827;
    --navy-3: #1a2235;
    --navy-4: #1e2d40;
    --gold: #c9a84c;
    --gold-light: #e2c06b;
    --gold-dim: rgba(201,168,76,0.15);
    --gold-border: rgba(201,168,76,0.25);
    --teal: #0ea5a0;
    --teal-dim: rgba(14,165,160,0.12);
    --red: #e05252;
    --red-dim: rgba(224,82,82,0.12);
    --green: #4ade80;
    --green-dim: rgba(74,222,128,0.12);
    --text: #e8eaf0;
    --text-2: #9ba3af;
    --text-3: #4b5563;
    --border: rgba(255,255,255,0.07);
    --border-2: rgba(255,255,255,0.12);
  }

  body {
    font-family: 'IBM Plex Sans Arabic', sans-serif;
    background: var(--navy);
    color: var(--text);
    min-height: 100vh;
    overflow-x: hidden;
  }

  /* Grid background */
  body::before {
    content: '';
    position: fixed;
    inset: 0;
    background-image:
      linear-gradient(rgba(201,168,76,0.03) 1px, transparent 1px),
      linear-gradient(90deg, rgba(201,168,76,0.03) 1px, transparent 1px);
    background-size: 40px 40px;
    pointer-events: none;
    z-index: 0;
  }

  .app {
    position: relative;
    z-index: 1;
    max-width: 1200px;
    margin: 0 auto;
    padding: 24px 20px;
  }

  /* ── Header ── */
  .header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 32px;
    padding-bottom: 20px;
    border-bottom: 1px solid var(--gold-border);
  }
  .header-left { display: flex; align-items: center; gap: 14px; }
  .logo-badge {
    width: 46px; height: 46px;
    background: linear-gradient(135deg, var(--gold) 0%, #8b6914 100%);
    border-radius: 10px;
    display: flex; align-items: center; justify-content: center;
    font-size: 22px; font-weight: 700;
    color: var(--navy); font-family: 'Playfair Display', serif;
    box-shadow: 0 4px 16px rgba(201,168,76,0.3);
  }
  .header-title h1 {
    font-family: 'Playfair Display', serif;
    font-size: 20px; font-weight: 700;
    color: var(--gold-light);
    letter-spacing: 0.3px;
  }
  .header-title p { font-size: 11px; color: var(--text-2); margin-top: 1px; letter-spacing: 0.5px; }
  .header-badge {
    background: var(--gold-dim);
    border: 1px solid var(--gold-border);
    color: var(--gold);
    font-size: 10px; font-weight: 600;
    padding: 4px 10px; border-radius: 20px;
    letter-spacing: 1px; text-transform: uppercase;
  }

  /* ── Tabs ── */
  .tabs {
    display: flex; gap: 4px;
    background: var(--navy-2);
    border: 1px solid var(--border);
    border-radius: 12px; padding: 4px;
    margin-bottom: 24px;
  }
  .tab {
    flex: 1; padding: 9px 12px;
    background: none; border: none; cursor: pointer;
    color: var(--text-2); font-size: 13px; font-weight: 500;
    border-radius: 9px; transition: all 0.2s;
    font-family: 'IBM Plex Sans Arabic', sans-serif;
    display: flex; align-items: center; justify-content: center; gap: 6px;
  }
  .tab:hover { color: var(--text); background: var(--navy-3); }
  .tab.active {
    background: var(--gold-dim);
    border: 1px solid var(--gold-border);
    color: var(--gold);
  }

  /* ── Panel ── */
  .panel {
    background: var(--navy-2);
    border: 1px solid var(--border);
    border-radius: 16px; overflow: hidden;
    box-shadow: 0 8px 32px rgba(0,0,0,0.4);
  }

  /* ── Direction Bar ── */
  .dir-bar {
    display: flex; align-items: center; gap: 0;
    border-bottom: 1px solid var(--border);
  }
  .lang-btn {
    flex: 1; padding: 14px 20px;
    background: none; border: none; cursor: default;
    color: var(--text); font-size: 13px; font-weight: 600;
    font-family: 'IBM Plex Sans Arabic', sans-serif;
    display: flex; align-items: center; gap: 8px;
  }
  .lang-flag { font-size: 18px; }
  .swap-btn {
    padding: 10px 16px;
    background: var(--navy-3);
    border: 1px solid var(--border-2);
    border-radius: 8px; cursor: pointer;
    color: var(--gold); font-size: 16px;
    transition: all 0.2s; margin: 0 12px;
  }
  .swap-btn:hover { background: var(--gold-dim); transform: rotate(180deg); }

  /* ── Context Types ── */
  .context-row {
    display: flex; gap: 6px; flex-wrap: wrap;
    padding: 12px 16px;
    border-bottom: 1px solid var(--border);
    background: rgba(0,0,0,0.15);
  }
  .ctx-btn {
    padding: 5px 12px; border-radius: 20px;
    border: 1px solid var(--border-2);
    background: none; cursor: pointer;
    font-size: 11px; font-weight: 500;
    color: var(--text-2); transition: all 0.18s;
    font-family: 'IBM Plex Sans Arabic', sans-serif;
    display: flex; align-items: center; gap: 5px;
  }
  .ctx-btn:hover { border-color: var(--gold-border); color: var(--gold); }
  .ctx-btn.active {
    background: var(--gold-dim);
    border-color: var(--gold-border);
    color: var(--gold);
  }
  .ctx-btn.auto-detected {
    background: var(--teal-dim);
    border-color: rgba(14,165,160,0.3);
    color: var(--teal);
    animation: pulse-teal 2s infinite;
  }
  @keyframes pulse-teal {
    0%,100% { box-shadow: 0 0 0 0 rgba(14,165,160,0.3); }
    50% { box-shadow: 0 0 0 4px rgba(14,165,160,0); }
  }

  /* ── Translation Area ── */
  .translate-grid {
    display: grid; grid-template-columns: 1fr 1fr;
    min-height: 220px;
  }
  .t-pane { padding: 20px; position: relative; }
  .t-pane:first-child { border-right: 1px solid var(--border); }
  .t-label {
    font-size: 10px; letter-spacing: 1.2px; text-transform: uppercase;
    color: var(--text-3); font-weight: 600; margin-bottom: 10px;
  }
  .t-textarea {
    width: 100%; background: none; border: none; outline: none;
    color: var(--text); font-size: 18px; font-weight: 400;
    font-family: 'IBM Plex Sans Arabic', sans-serif;
    resize: none; line-height: 1.7; min-height: 140px;
  }
  .t-textarea::placeholder { color: var(--text-3); font-size: 15px; }
  .t-textarea[dir="rtl"] { font-size: 18px; }

  .output-area {
    min-height: 140px; font-size: 18px; line-height: 1.7;
    color: var(--text); word-break: break-word;
  }
  .output-area.loading { color: var(--text-3); }
  .output-placeholder { color: var(--text-3); font-size: 15px; }

  /* ── Detected Type Badge ── */
  .detected-badge {
    position: absolute; top: 14px; right: 16px;
    background: var(--teal-dim);
    border: 1px solid rgba(14,165,160,0.3);
    color: var(--teal); font-size: 10px; font-weight: 600;
    padding: 3px 9px; border-radius: 20px; letter-spacing: 0.8px;
  }

  /* ── Alternatives ── */
  .alternatives {
    border-top: 1px solid var(--border);
    padding: 12px 16px;
  }
  .alt-label { font-size: 10px; color: var(--text-3); letter-spacing: 1px; text-transform: uppercase; margin-bottom: 8px; }
  .alt-chips { display: flex; gap: 6px; flex-wrap: wrap; }
  .alt-chip {
    padding: 5px 12px; border-radius: 20px;
    border: 1px solid var(--border-2);
    background: var(--navy-3); cursor: pointer;
    font-size: 13px; color: var(--text-2);
    transition: all 0.15s; font-family: 'IBM Plex Sans Arabic', sans-serif;
  }
  .alt-chip:hover {
    background: var(--gold-dim); border-color: var(--gold-border);
    color: var(--gold);
  }

  /* ── Action Bar ── */
  .action-bar {
    display: flex; align-items: center; justify-content: space-between;
    padding: 12px 16px;
    border-top: 1px solid var(--border);
    background: rgba(0,0,0,0.1);
  }
  .action-left { display: flex; gap: 8px; align-items: center; }
  .char-count { font-size: 11px; color: var(--text-3); }
  .icon-btn {
    padding: 7px 10px; background: var(--navy-3);
    border: 1px solid var(--border-2); border-radius: 8px;
    cursor: pointer; color: var(--text-2); font-size: 14px;
    transition: all 0.15s;
  }
  .icon-btn:hover { color: var(--gold); border-color: var(--gold-border); background: var(--gold-dim); }
  .translate-btn {
    padding: 10px 24px;
    background: linear-gradient(135deg, var(--gold) 0%, #a07020 100%);
    border: none; border-radius: 10px; cursor: pointer;
    color: var(--navy); font-size: 13px; font-weight: 700;
    font-family: 'IBM Plex Sans Arabic', sans-serif;
    transition: all 0.2s; letter-spacing: 0.3px;
    box-shadow: 0 4px 12px rgba(201,168,76,0.25);
  }
  .translate-btn:hover { transform: translateY(-1px); box-shadow: 0 6px 20px rgba(201,168,76,0.35); }
  .translate-btn:active { transform: translateY(0); }
  .translate-btn:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }

  /* ── Spinner ── */
  .spinner {
    display: inline-block; width: 18px; height: 18px;
    border: 2px solid rgba(201,168,76,0.3);
    border-top-color: var(--gold);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
    vertical-align: middle;
  }
  @keyframes spin { to { transform: rotate(360deg); } }

  /* ── Explanation Card ── */
  .explain-card {
    margin-top: 16px;
    background: var(--navy-3);
    border: 1px solid var(--border-2);
    border-radius: 12px; padding: 16px;
    font-size: 13px; color: var(--text-2); line-height: 1.7;
  }
  .explain-card .explain-title {
    font-size: 10px; text-transform: uppercase; letter-spacing: 1px;
    color: var(--gold); font-weight: 700; margin-bottom: 8px;
  }

  /* ── Batch Tab ── */
  .batch-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; padding: 20px; }
  .batch-input-wrap { display: flex; flex-direction: column; gap: 10px; }
  .batch-label { font-size: 11px; color: var(--text-2); text-transform: uppercase; letter-spacing: 1px; }
  .batch-textarea {
    width: 100%; background: var(--navy-3);
    border: 1px solid var(--border-2); border-radius: 10px;
    outline: none; padding: 14px 16px;
    color: var(--text); font-size: 14px;
    font-family: 'IBM Plex Sans Arabic', sans-serif;
    resize: vertical; min-height: 200px; line-height: 1.8;
  }
  .batch-textarea:focus { border-color: var(--gold-border); }
  .batch-run-btn {
    width: 100%; padding: 12px;
    background: linear-gradient(135deg, var(--gold) 0%, #a07020 100%);
    border: none; border-radius: 10px; cursor: pointer;
    color: var(--navy); font-size: 14px; font-weight: 700;
    font-family: 'IBM Plex Sans Arabic', sans-serif;
    transition: all 0.2s;
  }
  .batch-run-btn:hover { opacity: 0.9; }
  .batch-result-line {
    display: flex; align-items: baseline; gap: 10px;
    padding: 8px 0; border-bottom: 1px solid var(--border);
  }
  .batch-src { font-size: 13px; color: var(--text-2); min-width: 90px; direction: rtl; }
  .batch-arrow { color: var(--gold); font-size: 12px; }
  .batch-dst { font-size: 14px; color: var(--text); font-weight: 500; }
  .batch-type-tag {
    font-size: 10px; padding: 2px 7px; border-radius: 20px;
    background: var(--gold-dim); border: 1px solid var(--gold-border);
    color: var(--gold); font-weight: 600; letter-spacing: 0.5px; white-space: nowrap;
  }

  /* ── History Tab ── */
  .history-list { padding: 16px; display: flex; flex-direction: column; gap: 10px; }
  .history-item {
    background: var(--navy-3); border: 1px solid var(--border);
    border-radius: 12px; padding: 14px 16px;
    display: grid; grid-template-columns: 1fr 24px 1fr;
    gap: 10px; align-items: center;
    transition: border-color 0.2s; cursor: default;
  }
  .history-item:hover { border-color: var(--gold-border); }
  .h-src { font-size: 14px; direction: rtl; text-align: right; }
  .h-dst { font-size: 14px; font-weight: 500; }
  .h-arrow { color: var(--gold); text-align: center; font-size: 12px; }
  .h-meta { margin-top: 6px; font-size: 10px; color: var(--text-3); display: flex; gap: 8px; }
  .h-type {
    background: var(--gold-dim); border: 1px solid var(--gold-border);
    color: var(--gold); padding: 1px 7px; border-radius: 10px;
    font-size: 9px; font-weight: 700; letter-spacing: 0.8px;
  }

  /* ── Empty State ── */
  .empty-state {
    text-align: center; padding: 60px 20px;
    color: var(--text-3); font-size: 14px;
  }
  .empty-state .empty-icon { font-size: 40px; margin-bottom: 12px; opacity: 0.4; }

  /* ── Error ── */
  .error-toast {
    background: var(--red-dim); border: 1px solid rgba(224,82,82,0.3);
    color: #f87171; border-radius: 10px; padding: 10px 16px;
    font-size: 13px; margin-top: 12px;
    display: flex; align-items: center; gap: 8px;
  }

  /* ── Responsiveness ── */
  @media (max-width: 640px) {
    .translate-grid { grid-template-columns: 1fr; }
    .t-pane:first-child { border-right: none; border-bottom: 1px solid var(--border); }
    .batch-grid { grid-template-columns: 1fr; }
    .history-item { grid-template-columns: 1fr; }
    .h-arrow { transform: rotate(90deg); }
    .tabs { overflow-x: auto; }
  }
`;

// ─── Context Types Config ──────────────────────────────────────────────────
const CONTEXT_TYPES = [
  { id: "auto",    label: "كشف تلقائي",     icon: "🤖", en: "Auto Detect" },
  { id: "name",    label: "أسماء أشخاص",    icon: "👤", en: "Person Names" },
  { id: "country", label: "دول / جنسيات",   icon: "🌍", en: "Countries/Nationalities" },
  { id: "medical", label: "مصطلحات طبية",   icon: "🏥", en: "Medical Terms" },
  { id: "date",    label: "تواريخ",         icon: "📅", en: "Dates" },
  { id: "city",    label: "مدن وأماكن",     icon: "🏙️", en: "Cities/Places" },
  { id: "report",  label: "تقارير رسمية",   icon: "📋", en: "Official Reports" },
  { id: "general", label: "نص عام",         icon: "📝", en: "General Text" },
];

// ─── Translation Cache ─────────────────────────────────────────────────────
const cache = new Map();
const getCacheKey = (text, ctx, dir) => `${dir}::${ctx}::${text.trim().toLowerCase()}`;

// ─── Build System Prompt ───────────────────────────────────────────────────
function buildSystemPrompt(direction) {
  const isAR2EN = direction === "ar-en";
  return `You are an elite professional translation engine used by governments and hospitals in the Arab world.
You perform intelligent, context-aware translation with zero tolerance for literal/wrong translations.

Direction: ${isAR2EN ? "Arabic → English" : "English → Arabic"}

CRITICAL RULES:
1. NAMES (person names): Use professional TRANSLITERATION (romanization), NOT semantic translation.
   - حكيم → Hakim (NOT "Sage")
   - عبدالله → Abdullah
   - فاطمة → Fatima
   - محمد → Mohammed
   - خالد → Khalid
   - هند → Hind
   - نورة → Noura

2. COUNTRIES & NATIONALITIES: Use official internationally recognized English names.
   - اليمن → Yemen | يمني → Yemeni
   - المملكة العربية السعودية → Saudi Arabia | سعودي → Saudi
   - مصر → Egypt | مصري → Egyptian
   - الكويت → Kuwait | كويتي → Kuwaiti
   - الإمارات → UAE / United Arab Emirates | إماراتي → Emirati

3. MEDICAL TERMS: Use precise medical/clinical English terminology.
   - ضغط الدم → Blood Pressure
   - السكري → Diabetes Mellitus
   - إجازة مرضية → Medical Leave / Sick Leave
   - التهاب → Inflammation
   - فحص طبي → Medical Examination

4. DATES: Convert to standard formats.
   - Arabic Hijri: preserve and note "(Hijri)" if specified
   - Gregorian: use DD/MM/YYYY or write out month name

5. CITIES/PLACES: Use official romanized/English place names.
   - الرياض → Riyadh
   - جدة → Jeddah
   - مكة المكرمة → Makkah Al-Mukarramah

6. OFFICIAL REPORTS: Use formal, bureaucratic English appropriate for government documents.

RESPONSE FORMAT (JSON only, no markdown):
{
  "translation": "main translation result",
  "detected_type": "name|country|medical|date|city|report|general",
  "alternatives": ["alt1", "alt2"],
  "explanation": "Brief note about translation approach (1-2 sentences, in Arabic)",
  "confidence": "high|medium|low"
}`;
}

// ─── Claude API Call ───────────────────────────────────────────────────────
async function callClaudeTranslate(text, contextType, direction) {
  const cacheKey = getCacheKey(text, contextType, direction);
  if (cache.has(cacheKey)) return { ...cache.get(cacheKey), cached: true };

  const userMsg = contextType === "auto"
    ? `Translate this text: "${text}"\nAuto-detect the content type and apply the appropriate translation strategy.`
    : `Translate this text: "${text}"\nContent type: ${contextType}\nApply the ${contextType} translation rules strictly.`;

  const res = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      model: "claude-sonnet-4-20250514",
      max_tokens: 1000,
      system: buildSystemPrompt(direction),
      messages: [{ role: "user", content: userMsg }],
    }),
  });

  if (!res.ok) throw new Error(`API Error ${res.status}`);
  const data = await res.json();
  const raw = data.content.map(b => b.text || "").join("").trim();
  const clean = raw.replace(/```json|```/g, "").trim();
  const parsed = JSON.parse(clean);
  cache.set(cacheKey, parsed);
  return parsed;
}

// ─── Batch Translate ───────────────────────────────────────────────────────
async function callBatchTranslate(lines, direction) {
  const res = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      model: "claude-sonnet-4-20250514",
      max_tokens: 2000,
      system: `You are a professional batch translation engine. Direction: ${direction === "ar-en" ? "Arabic → English" : "English → Arabic"}.
Apply intelligent context detection for each item separately. Names→transliterate, countries→official, medical→clinical.
Return ONLY a JSON array with objects: [{src, translation, type}]
No markdown, no explanation outside JSON.`,
      messages: [{
        role: "user",
        content: `Translate each line separately, applying appropriate rules:\n${lines.map((l, i) => `${i + 1}. ${l}`).join("\n")}`,
      }],
    }),
  });
  if (!res.ok) throw new Error(`API Error ${res.status}`);
  const data = await res.json();
  const raw = data.content.map(b => b.text || "").join("").trim();
  const clean = raw.replace(/```json|```/g, "").trim();
  return JSON.parse(clean);
}

// ─── Main Component ────────────────────────────────────────────────────────
export default function TranslationSystem() {
  const [activeTab, setActiveTab] = useState("translate");
  const [direction, setDirection] = useState("ar-en");
  const [contextType, setContextType] = useState("auto");
  const [inputText, setInputText] = useState("");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [history, setHistory] = useState([]);
  const [copied, setCopied] = useState(false);
  const [batchInput, setBatchInput] = useState("");
  const [batchResults, setBatchResults] = useState([]);
  const [batchLoading, setBatchLoading] = useState(false);
  const inputRef = useRef(null);

  const isAR = direction === "ar-en";

  const handleTranslate = useCallback(async () => {
    if (!inputText.trim()) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await callClaudeTranslate(inputText, contextType, direction);
      setResult(res);
      setHistory(prev => [{
        src: inputText, dst: res.translation,
        type: res.detected_type, direction, ts: Date.now(),
      }, ...prev.slice(0, 49)]);
    } catch (e) {
      setError(e.message || "حدث خطأ في الترجمة");
    } finally { setLoading(false); }
  }, [inputText, contextType, direction]);

  const handleBatch = useCallback(async () => {
    const lines = batchInput.split("\n").map(l => l.trim()).filter(Boolean);
    if (!lines.length) return;
    setBatchLoading(true);
    setBatchResults([]);
    try {
      const res = await callBatchTranslate(lines, direction);
      setBatchResults(res);
    } catch (e) {
      setError(e.message);
    } finally { setBatchLoading(false); }
  }, [batchInput, direction]);

  const handleCopy = () => {
    if (result?.translation) {
      navigator.clipboard.writeText(result.translation);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handleClear = () => {
    setInputText(""); setResult(null); setError(null);
    inputRef.current?.focus();
  };

  const swapDirection = () => {
    setDirection(d => d === "ar-en" ? "en-ar" : "ar-en");
    setResult(null); setError(null);
  };

  const handleKeyDown = (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") handleTranslate();
  };

  const sourceLabel = isAR ? "🇸🇦 العربية" : "🇬🇧 English";
  const targetLabel = isAR ? "🇬🇧 English" : "🇸🇦 العربية";

  return (
    <>
      <style>{styles}</style>
      <div className="app">
        {/* ── Header ── */}
        <div className="header">
          <div className="header-left">
            <div className="logo-badge">T</div>
            <div className="header-title">
              <h1>TranslaAI Pro</h1>
              <p>INTELLIGENT CONTEXT-AWARE TRANSLATION ENGINE</p>
            </div>
          </div>
          <span className="header-badge">AI POWERED</span>
        </div>

        {/* ── Tabs ── */}
        <div className="tabs">
          {[
            { id: "translate", icon: "⚡", label: "ترجمة فورية" },
            { id: "batch",     icon: "📋", label: "ترجمة مجمّعة" },
            { id: "history",   icon: "🕐", label: `السجل (${history.length})` },
          ].map(t => (
            <button key={t.id}
              className={`tab ${activeTab === t.id ? "active" : ""}`}
              onClick={() => setActiveTab(t.id)}>
              <span>{t.icon}</span> {t.label}
            </button>
          ))}
        </div>

        {/* ══════════════════════════ TAB: TRANSLATE ══════════════════════ */}
        {activeTab === "translate" && (
          <div className="panel">
            {/* Direction Bar */}
            <div className="dir-bar">
              <div className="lang-btn">
                <span className="lang-flag">{isAR ? "🇸🇦" : "🇬🇧"}</span>
                <span>{isAR ? "العربية" : "English"}</span>
              </div>
              <button className="swap-btn" onClick={swapDirection} title="تبديل الاتجاه">⇄</button>
              <div className="lang-btn">
                <span className="lang-flag">{isAR ? "🇬🇧" : "🇸🇦"}</span>
                <span>{isAR ? "English" : "العربية"}</span>
              </div>
            </div>

            {/* Context Types */}
            <div className="context-row">
              {CONTEXT_TYPES.map(ct => (
                <button key={ct.id}
                  className={`ctx-btn ${contextType === ct.id ? "active" : ""} ${result?.detected_type === ct.id && contextType === "auto" ? "auto-detected" : ""}`}
                  onClick={() => setContextType(ct.id)}>
                  {ct.icon} {ct.label}
                </button>
              ))}
            </div>

            {/* Main Translate Grid */}
            <div className="translate-grid">
              {/* Input */}
              <div className="t-pane">
                <div className="t-label">{isAR ? "النص المصدر" : "SOURCE TEXT"}</div>
                <textarea
                  ref={inputRef}
                  className="t-textarea"
                  dir={isAR ? "rtl" : "ltr"}
                  placeholder={isAR ? "اكتب النص هنا للترجمة…" : "Enter text to translate…"}
                  value={inputText}
                  onChange={e => setInputText(e.target.value)}
                  onKeyDown={handleKeyDown}
                  rows={6}
                />
              </div>

              {/* Output */}
              <div className="t-pane" style={{ position: "relative" }}>
                <div className="t-label">{isAR ? "TRANSLATION RESULT" : "نتيجة الترجمة"}</div>
                {result && (
                  <span className="detected-badge">
                    {CONTEXT_TYPES.find(c => c.id === result.detected_type)?.icon}{" "}
                    {CONTEXT_TYPES.find(c => c.id === result.detected_type)?.label || result.detected_type}
                  </span>
                )}
                <div className={`output-area ${loading ? "loading" : ""}`}
                  dir={isAR ? "ltr" : "rtl"}>
                  {loading
                    ? <span><span className="spinner" /> جارٍ الترجمة…</span>
                    : result
                      ? result.translation
                      : <span className="output-placeholder">{isAR ? "ستظهر الترجمة هنا…" : "Translation appears here…"}</span>
                  }
                </div>
              </div>
            </div>

            {/* Error */}
            {error && (
              <div style={{ padding: "0 20px 12px" }}>
                <div className="error-toast">⚠️ {error}</div>
              </div>
            )}

            {/* Alternatives */}
            {result?.alternatives?.length > 0 && (
              <div className="alternatives">
                <div className="alt-label">بدائل للترجمة</div>
                <div className="alt-chips">
                  {result.alternatives.map((alt, i) => (
                    <button key={i} className="alt-chip"
                      onClick={() => setResult(r => ({ ...r, translation: alt }))}>
                      {alt}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Explanation */}
            {result?.explanation && (
              <div style={{ padding: "0 16px 16px" }}>
                <div className="explain-card">
                  <div className="explain-title">📌 ملاحظة الترجمة</div>
                  {result.explanation}
                </div>
              </div>
            )}

            {/* Action Bar */}
            <div className="action-bar">
              <div className="action-left">
                <span className="char-count">{inputText.length} / 2000</span>
                {inputText && (
                  <button className="icon-btn" onClick={handleClear} title="مسح">✕</button>
                )}
                {result && (
                  <button className="icon-btn" onClick={handleCopy} title="نسخ">
                    {copied ? "✓" : "⎘"}
                  </button>
                )}
              </div>
              <button
                className="translate-btn"
                onClick={handleTranslate}
                disabled={loading || !inputText.trim()}>
                {loading ? <><span className="spinner" /> يترجم…</> : "⚡ ترجمة فورية"}
              </button>
            </div>
          </div>
        )}

        {/* ══════════════════════════ TAB: BATCH ═════════════════════════ */}
        {activeTab === "batch" && (
          <div className="panel">
            <div style={{ padding: "16px 20px", borderBottom: "1px solid var(--border)" }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <div>
                  <div style={{ fontWeight: 600, fontSize: 14 }}>الترجمة المجمّعة</div>
                  <div style={{ fontSize: 12, color: "var(--text-2)", marginTop: 3 }}>
                    ترجمة قائمة من النصوص دفعة واحدة — كل سطر يُترجم مستقلاً
                  </div>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{ fontSize: 12, color: "var(--text-2)" }}>الاتجاه:</span>
                  <button className="swap-btn" onClick={swapDirection} style={{ margin: 0 }}>
                    {isAR ? "عربي → EN" : "EN → عربي"} ⇄
                  </button>
                </div>
              </div>
            </div>

            <div className="batch-grid">
              <div className="batch-input-wrap">
                <div className="batch-label">النصوص المصدر (سطر لكل نص)</div>
                <textarea
                  className="batch-textarea"
                  dir={isAR ? "rtl" : "ltr"}
                  placeholder={isAR
                    ? "حكيم\nاليمن\nضغط الدم\nالرياض\nمحمد عبدالله\nسعودي\nالتهاب الرئة"
                    : "Mohammed\nRiyadh\nBlood Pressure\nSaudi Arabia"}
                  value={batchInput}
                  onChange={e => setBatchInput(e.target.value)}
                />
                <button className="batch-run-btn" onClick={handleBatch} disabled={batchLoading}>
                  {batchLoading ? <><span className="spinner" /> يعالج…</> : "⚡ ترجمة الكل"}
                </button>
              </div>

              <div>
                <div className="batch-label" style={{ marginBottom: 10 }}>
                  النتائج {batchResults.length > 0 && `(${batchResults.length})`}
                </div>
                {batchLoading && (
                  <div style={{ color: "var(--text-3)", fontSize: 13, padding: "20px 0" }}>
                    <span className="spinner" /> يحلل ويترجم…
                  </div>
                )}
                {batchResults.map((r, i) => (
                  <div key={i} className="batch-result-line">
                    <span className="batch-src">{r.src}</span>
                    <span className="batch-arrow">→</span>
                    <span className="batch-dst">{r.translation}</span>
                    <span className="batch-type-tag">
                      {CONTEXT_TYPES.find(c => c.id === r.type)?.icon} {r.type}
                    </span>
                  </div>
                ))}
                {!batchLoading && batchResults.length === 0 && (
                  <div className="empty-state" style={{ padding: "30px 0" }}>
                    <div className="empty-icon">📋</div>
                    أدخل النصوص وابدأ الترجمة
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* ══════════════════════════ TAB: HISTORY ═══════════════════════ */}
        {activeTab === "history" && (
          <div className="panel">
            <div style={{ padding: "14px 20px", borderBottom: "1px solid var(--border)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontSize: 14, fontWeight: 600 }}>سجل الترجمات</span>
              {history.length > 0 && (
                <button className="icon-btn" style={{ fontSize: 12 }} onClick={() => setHistory([])}>
                  مسح الكل
                </button>
              )}
            </div>
            {history.length === 0 ? (
              <div className="empty-state">
                <div className="empty-icon">🕐</div>
                لا توجد ترجمات بعد
              </div>
            ) : (
              <div className="history-list">
                {history.map((h, i) => (
                  <div key={i} className="history-item"
                    onClick={() => { setActiveTab("translate"); setInputText(h.src); setResult(null); }}>
                    <div>
                      <div className="h-src">{h.src}</div>
                      <div className="h-meta">
                        <span className="h-type">
                          {CONTEXT_TYPES.find(c => c.id === h.type)?.icon} {h.type}
                        </span>
                        <span>{h.direction === "ar-en" ? "AR→EN" : "EN→AR"}</span>
                      </div>
                    </div>
                    <div className="h-arrow">→</div>
                    <div>
                      <div className="h-dst">{h.dst}</div>
                      <div className="h-meta">
                        {new Date(h.ts).toLocaleTimeString("ar-SA")}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Footer */}
        <div style={{ textAlign: "center", marginTop: 24, fontSize: 11, color: "var(--text-3)", letterSpacing: "0.5px" }}>
          TRANSLAAI PRO  ·  CONTEXT-AWARE AI TRANSLATION  ·  Ctrl+Enter للترجمة السريعة
        </div>
      </div>
    </>
  );
}
