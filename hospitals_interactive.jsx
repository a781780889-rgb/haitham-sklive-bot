import { useState } from "react";

const hospitals = [
  { name: "مدينة الأمير سلطان الطبية العسكرية", region: "الرياض", ownership: "حكومي", type: "عسكري" },
  { name: "مدينة الملك عبدالعزيز الطبية للحرس الوطني", region: "الرياض", ownership: "حكومي", type: "عسكري" },
  { name: "مستشفى قوى الأمن", region: "الرياض", ownership: "حكومي", type: "عسكري" },
  { name: "مستشفى القوات المسلحة بوادي الدواسر", region: "الرياض", ownership: "حكومي", type: "عسكري" },
  { name: "مستشفى القوات المسلحة بالخرج", region: "الرياض", ownership: "حكومي", type: "عسكري" },
  { name: "مستشفى الملك سلمان", region: "الرياض", ownership: "حكومي", type: "عام" },
  { name: "مدينة الملك فهد الطبية", region: "الرياض", ownership: "حكومي", type: "مدينة طبية" },
  { name: "مستشفى الملك فيصل التخصصي", region: "الرياض", ownership: "حكومي", type: "تخصصي" },
  { name: "مستشفى الملك خالد التخصصي للعيون", region: "الرياض", ownership: "حكومي", type: "تخصصي" },
  { name: "مستشفى الإيمان العام", region: "الرياض", ownership: "حكومي", type: "عام" },
  { name: "مستشفى السليل العام", region: "الرياض", ownership: "حكومي", type: "عام" },
  { name: "مستشفى وادي الدواسر العام", region: "الرياض", ownership: "حكومي", type: "عام" },
  { name: "مستشفى الأفلاج العام", region: "الرياض", ownership: "حكومي", type: "عام" },
  { name: "مستشفى الحريق العام", region: "الرياض", ownership: "حكومي", type: "عام" },
  { name: "مستشفى القويعية العام", region: "الرياض", ownership: "حكومي", type: "عام" },
  { name: "مستشفى المزاحمية العام", region: "الرياض", ownership: "حكومي", type: "عام" },
  { name: "مستشفى الرين العام", region: "الرياض", ownership: "حكومي", type: "عام" },
  { name: "مستشفى الزلفي العام", region: "الرياض", ownership: "حكومي", type: "عام" },
  { name: "مستشفى شقراء العام", region: "الرياض", ownership: "حكومي", type: "عام" },
  { name: "مستشفى عفيف العام", region: "الرياض", ownership: "حكومي", type: "عام" },
  { name: "مجمع الملك فهد الطبي العسكري", region: "الشرقية", ownership: "حكومي", type: "عسكري" },
  { name: "مستشفى الدمام المركزي", region: "الشرقية", ownership: "حكومي", type: "مركزي" },
  { name: "مستشفى القطيف المركزي", region: "الشرقية", ownership: "حكومي", type: "مركزي" },
  { name: "مستشفى الخفجي العام", region: "الشرقية", ownership: "حكومي", type: "عام" },
  { name: "مستشفى النعيرية", region: "الشرقية", ownership: "حكومي", type: "عام" },
  { name: "مستشفى الجبيل العام", region: "الشرقية", ownership: "حكومي", type: "عام" },
  { name: "مستشفى صفوى العام", region: "الشرقية", ownership: "حكومي", type: "عام" },
  { name: "مستشفى عنك العام", region: "الشرقية", ownership: "حكومي", type: "عام" },
  { name: "مدينة الملك عبدالله الطبية", region: "مكة المكرمة", ownership: "حكومي", type: "مدينة طبية" },
  { name: "مدينة الملك عبدالعزيز الطبية", region: "مكة المكرمة", ownership: "حكومي", type: "مدينة طبية" },
  { name: "مستشفى الملك فهد للقوات المسلحة", region: "مكة المكرمة", ownership: "حكومي", type: "عسكري" },
  { name: "مستشفى قوى الأمن", region: "مكة المكرمة", ownership: "حكومي", type: "عسكري" },
  { name: "مستشفى حراء العام", region: "مكة المكرمة", ownership: "حكومي", type: "عام" },
  { name: "مستشفى رابغ العام", region: "مكة المكرمة", ownership: "حكومي", type: "عام" },
  { name: "مستشفى القنفذة العام", region: "مكة المكرمة", ownership: "حكومي", type: "عام" },
  { name: "مستشفى الموية العام", region: "مكة المكرمة", ownership: "حكومي", type: "عام" },
  { name: "مستشفى ميسان العام", region: "مكة المكرمة", ownership: "حكومي", type: "عام" },
  { name: "مدينة الملك سلمان بن عبدالعزيز الطبية", region: "المدينة المنورة", ownership: "حكومي", type: "مدينة طبية" },
  { name: "مستشفى الملك فيصل التخصصي", region: "المدينة المنورة", ownership: "حكومي", type: "تخصصي" },
  { name: "مستشفى الملك فهد", region: "المدينة المنورة", ownership: "حكومي", type: "عام" },
  { name: "مستشفى أحد", region: "المدينة المنورة", ownership: "حكومي", type: "عام" },
  { name: "مستشفى الأنصار", region: "المدينة المنورة", ownership: "حكومي", type: "عام" },
  { name: "مستشفى بدر العام", region: "المدينة المنورة", ownership: "حكومي", type: "عام" },
  { name: "مستشفى نجران العسكري", region: "نجران", ownership: "حكومي", type: "عسكري" },
  { name: "مستشفى نجران العام", region: "نجران", ownership: "حكومي", type: "عام" },
  { name: "مستشفى شرورة", region: "نجران", ownership: "حكومي", type: "عام" },
  { name: "مستشفى حبونا العام", region: "نجران", ownership: "حكومي", type: "عام" },
  { name: "مستشفى يدمة العام", region: "نجران", ownership: "حكومي", type: "عام" },
  { name: "مستشفى عرعر المركزي", region: "الحدود الشمالية", ownership: "حكومي", type: "مركزي" },
  { name: "مستشفى رفحاء المركزي", region: "الحدود الشمالية", ownership: "حكومي", type: "مركزي" },
  { name: "مستشفى طريف العام", region: "الحدود الشمالية", ownership: "حكومي", type: "عام" },
  { name: "مستشفى العويقيلة العام", region: "الحدود الشمالية", ownership: "حكومي", type: "عام" },
  { name: "مستشفى الملك فهد", region: "الباحة", ownership: "حكومي", type: "عام" },
  { name: "مستشفى العقيق العام", region: "الباحة", ownership: "حكومي", type: "عام" },
  { name: "مستشفى قلوة العام", region: "الباحة", ownership: "حكومي", type: "عام" },
  { name: "مستشفى المخواة العام", region: "الباحة", ownership: "حكومي", type: "عام" },
  { name: "مستشفى المندق العام", region: "الباحة", ownership: "حكومي", type: "عام" },
  { name: "مستشفى الملك عبدالله", region: "عسير", ownership: "حكومي", type: "عام" },
  { name: "مستشفى عسير المركزي", region: "عسير", ownership: "حكومي", type: "مركزي" },
  { name: "مستشفى أبها العام", region: "عسير", ownership: "حكومي", type: "عام" },
  { name: "مستشفى خميس مشيط العام", region: "عسير", ownership: "حكومي", type: "عام" },
  { name: "مستشفى بللسمر العام", region: "عسير", ownership: "حكومي", type: "عام" },
  { name: "مستشفى النماص العام", region: "عسير", ownership: "حكومي", type: "عام" },
  { name: "مستشفى الحرجة العام", region: "عسير", ownership: "حكومي", type: "عام" },
  { name: "مستشفى الفرشة العام", region: "عسير", ownership: "حكومي", type: "عام" },
  { name: "مستشفى الملك فهد التخصصي", region: "القصيم", ownership: "حكومي", type: "تخصصي" },
  { name: "مستشفى بريدة المركزي", region: "القصيم", ownership: "حكومي", type: "مركزي" },
  { name: "مستشفى الرس العام", region: "القصيم", ownership: "حكومي", type: "عام" },
  { name: "مستشفى البكيرية العام", region: "القصيم", ownership: "حكومي", type: "عام" },
  { name: "مستشفى المذنب العام", region: "القصيم", ownership: "حكومي", type: "عام" },
  { name: "مستشفى رياض الخبراء العام", region: "القصيم", ownership: "حكومي", type: "عام" },
  { name: "مستشفى البدائع العام", region: "القصيم", ownership: "حكومي", type: "عام" },
  { name: "مستشفى قصيباء العام", region: "القصيم", ownership: "حكومي", type: "عام" },
  { name: "مستشفى الملك سلمان التخصصي", region: "حائل", ownership: "حكومي", type: "تخصصي" },
  { name: "مستشفى الملك خالد", region: "حائل", ownership: "حكومي", type: "عام" },
  { name: "مستشفى حائل العام الجديد", region: "حائل", ownership: "حكومي", type: "عام" },
  { name: "مستشفى بقعاء العام", region: "حائل", ownership: "حكومي", type: "عام" },
  { name: "مستشفى الملك خالد المدني", region: "تبوك", ownership: "حكومي", type: "عام" },
  { name: "مستشفى الملك فهد", region: "تبوك", ownership: "حكومي", type: "عام" },
  { name: "مستشفى البدع", region: "تبوك", ownership: "حكومي", type: "عام" },
  { name: "مستشفى تيماء", region: "تبوك", ownership: "حكومي", type: "عام" },
  { name: "مستشفى الوجه", region: "تبوك", ownership: "حكومي", type: "عام" },
  { name: "مستشفى ضباء", region: "تبوك", ownership: "حكومي", type: "عام" },
  { name: "مستشفى حقل", region: "تبوك", ownership: "حكومي", type: "عام" },
  { name: "مستشفى الملك فهد المركزي", region: "جازان", ownership: "حكومي", type: "مركزي" },
  { name: "مستشفى جازان العام", region: "جازان", ownership: "حكومي", type: "عام" },
  { name: "مستشفى صبيا العام", region: "جازان", ownership: "حكومي", type: "عام" },
  { name: "مستشفى صامطة العام", region: "جازان", ownership: "حكومي", type: "عام" },
  { name: "مستشفى فرسان العام", region: "جازان", ownership: "حكومي", type: "عام" },
  { name: "مستشفى العارضة العام", region: "جازان", ownership: "حكومي", type: "عام" },
  { name: "مستشفى الموسم العام", region: "جازان", ownership: "حكومي", type: "عام" },
  { name: "مستشفى الطوال العام", region: "جازان", ownership: "حكومي", type: "عام" },
  { name: "مستشفى فيفا العام", region: "جازان", ownership: "حكومي", type: "عام" },
  { name: "مستشفى ضمد العام", region: "جازان", ownership: "حكومي", type: "عام" },
  { name: "مستشفى بني مالك العام", region: "جازان", ownership: "حكومي", type: "عام" },
  { name: "مستشفى الخوبة العام", region: "جازان", ownership: "حكومي", type: "عام" },
  { name: "مستشفى الريث العام", region: "جازان", ownership: "حكومي", type: "عام" },
];

const typeColors = {
  عسكري: { bg: "#1a2744", text: "#7eb8f7", border: "#2e4a8a" },
  عام: { bg: "#14391f", text: "#5dbb7a", border: "#1e5e30" },
  تخصصي: { bg: "#3b1f00", text: "#f5a623", border: "#7a4200" },
  "مدينة طبية": { bg: "#2a1a40", text: "#b57bee", border: "#5a2fa0" },
  مركزي: { bg: "#1a3040", text: "#4fc3f7", border: "#1e5070" },
};

const typeIcons = {
  عسكري: "🎖️",
  عام: "🏥",
  تخصصي: "🔬",
  "مدينة طبية": "🏙️",
  مركزي: "⭐",
};

export default function HospitalsApp() {
  const [activeFilter, setActiveFilter] = useState(null);
  const [search, setSearch] = useState("");
  const [regionFilter, setRegionFilter] = useState("الكل");
  const [expandedCard, setExpandedCard] = useState(null);

  const govHospitals = hospitals.filter((h) => h.ownership === "حكومي");
  const militaryHospitals = hospitals.filter((h) => h.type === "عسكري");

  const allRegions = ["الكل", ...Array.from(new Set(hospitals.map((h) => h.region)))];

  const displayed =
    activeFilter === "حكومي"
      ? govHospitals
      : activeFilter === "عسكري"
      ? militaryHospitals
      : hospitals;

  const filtered = displayed.filter((h) => {
    const matchSearch =
      !search ||
      h.name.includes(search) ||
      h.region.includes(search) ||
      h.type.includes(search);
    const matchRegion = regionFilter === "الكل" || h.region === regionFilter;
    return matchSearch && matchRegion;
  });

  const grouped = filtered.reduce((acc, h) => {
    if (!acc[h.region]) acc[h.region] = [];
    acc[h.region].push(h);
    return acc;
  }, {});

  return (
    <div dir="rtl" style={{
      minHeight: "100vh",
      background: "linear-gradient(135deg, #0a0f1e 0%, #0d1b2a 50%, #0a0f1e 100%)",
      fontFamily: "'Tajawal', 'Cairo', 'Segoe UI', sans-serif",
      padding: "0",
    }}>
      {/* Header */}
      <div style={{
        background: "linear-gradient(180deg, #0d1f3c 0%, #071428 100%)",
        borderBottom: "1px solid #1e3a5f",
        padding: "28px 24px 20px",
        position: "sticky",
        top: 0,
        zIndex: 50,
        backdropFilter: "blur(12px)",
      }}>
        <div style={{ maxWidth: 900, margin: "0 auto" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 18 }}>
            <span style={{ fontSize: 28 }}>🏥</span>
            <div>
              <h1 style={{ margin: 0, fontSize: 22, fontWeight: 800, color: "#e2eaf8", letterSpacing: 0.5 }}>
                دليل المستشفيات السعودية
              </h1>
              <p style={{ margin: 0, fontSize: 12, color: "#4a7ab5", marginTop: 2 }}>
                {hospitals.length} مستشفى موزعة على {allRegions.length - 1} منطقة
              </p>
            </div>
          </div>

          {/* Filter Buttons */}
          <div style={{ display: "flex", gap: 10, marginBottom: 14, flexWrap: "wrap" }}>
            <button
              onClick={() => { setActiveFilter(null); setRegionFilter("الكل"); }}
              style={{
                padding: "9px 20px",
                borderRadius: 10,
                border: activeFilter === null ? "1.5px solid #3a7bd5" : "1.5px solid #1e3a5f",
                background: activeFilter === null
                  ? "linear-gradient(135deg, #1a3a6e, #0e2448)"
                  : "rgba(14,36,72,0.4)",
                color: activeFilter === null ? "#7eb8f7" : "#4a6a8a",
                fontSize: 14,
                fontWeight: 700,
                cursor: "pointer",
                transition: "all 0.2s",
                display: "flex",
                alignItems: "center",
                gap: 6,
              }}
            >
              🗂️ الكل <span style={{
                background: "#0e2448",
                color: "#4a90d9",
                padding: "1px 8px",
                borderRadius: 20,
                fontSize: 11,
                border: "1px solid #1e4a8a"
              }}>{hospitals.length}</span>
            </button>

            <button
              onClick={() => { setActiveFilter("حكومي"); setRegionFilter("الكل"); }}
              style={{
                padding: "9px 20px",
                borderRadius: 10,
                border: activeFilter === "حكومي" ? "1.5px solid #2e7d46" : "1.5px solid #1a3a24",
                background: activeFilter === "حكومي"
                  ? "linear-gradient(135deg, #14391f, #0a2212)"
                  : "rgba(10,34,18,0.4)",
                color: activeFilter === "حكومي" ? "#5dbb7a" : "#2e5e3a",
                fontSize: 14,
                fontWeight: 700,
                cursor: "pointer",
                transition: "all 0.2s",
                display: "flex",
                alignItems: "center",
                gap: 6,
              }}
            >
              🏛️ المستشفيات الحكومية
              <span style={{
                background: "#0a2212",
                color: "#3a8a52",
                padding: "1px 8px",
                borderRadius: 20,
                fontSize: 11,
                border: "1px solid #1a5a2e"
              }}>{govHospitals.length}</span>
            </button>

            <button
              onClick={() => { setActiveFilter("عسكري"); setRegionFilter("الكل"); }}
              style={{
                padding: "9px 20px",
                borderRadius: 10,
                border: activeFilter === "عسكري" ? "1.5px solid #2e4a8a" : "1.5px solid #1a2440",
                background: activeFilter === "عسكري"
                  ? "linear-gradient(135deg, #1a2744, #0d1830)"
                  : "rgba(13,24,48,0.4)",
                color: activeFilter === "عسكري" ? "#7eb8f7" : "#2e4060",
                fontSize: 14,
                fontWeight: 700,
                cursor: "pointer",
                transition: "all 0.2s",
                display: "flex",
                alignItems: "center",
                gap: 6,
              }}
            >
              🎖️ المستشفيات العسكرية
              <span style={{
                background: "#0d1830",
                color: "#3a6aaa",
                padding: "1px 8px",
                borderRadius: 20,
                fontSize: 11,
                border: "1px solid #1e3a7a"
              }}>{militaryHospitals.length}</span>
            </button>
          </div>

          {/* Search + Region filter row */}
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="🔍 بحث باسم المستشفى أو المنطقة..."
              style={{
                flex: 1,
                minWidth: 200,
                padding: "9px 14px",
                borderRadius: 10,
                border: "1.5px solid #1e3a5f",
                background: "rgba(10,20,40,0.8)",
                color: "#c8dff5",
                fontSize: 13,
                outline: "none",
              }}
            />
            <select
              value={regionFilter}
              onChange={(e) => setRegionFilter(e.target.value)}
              style={{
                padding: "9px 14px",
                borderRadius: 10,
                border: "1.5px solid #1e3a5f",
                background: "rgba(10,20,40,0.9)",
                color: "#c8dff5",
                fontSize: 13,
                outline: "none",
                cursor: "pointer",
              }}
            >
              {allRegions.map((r) => (
                <option key={r} value={r} style={{ background: "#0d1b2a" }}>{r}</option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* Stats bar */}
      <div style={{
        background: "rgba(13,27,42,0.6)",
        borderBottom: "1px solid #0e2040",
        padding: "10px 24px",
      }}>
        <div style={{ maxWidth: 900, margin: "0 auto", display: "flex", gap: 20, flexWrap: "wrap" }}>
          {Object.entries(
            filtered.reduce((a, h) => { a[h.type] = (a[h.type] || 0) + 1; return a; }, {})
          ).map(([type, count]) => (
            <span key={type} style={{
              fontSize: 12,
              color: typeColors[type]?.text || "#aaa",
              display: "flex",
              alignItems: "center",
              gap: 4,
            }}>
              {typeIcons[type]} {type}: <strong>{count}</strong>
            </span>
          ))}
          <span style={{ fontSize: 12, color: "#4a7ab5", marginRight: "auto" }}>
            إجمالي النتائج: <strong style={{ color: "#7eb8f7" }}>{filtered.length}</strong>
          </span>
        </div>
      </div>

      {/* Content */}
      <div style={{ maxWidth: 900, margin: "0 auto", padding: "20px 16px 40px" }}>
        {Object.keys(grouped).length === 0 ? (
          <div style={{ textAlign: "center", color: "#2e4a6a", padding: "60px 20px", fontSize: 16 }}>
            لا توجد نتائج مطابقة للبحث
          </div>
        ) : (
          Object.entries(grouped).map(([region, list]) => (
            <div key={region} style={{ marginBottom: 28 }}>
              {/* Region Header */}
              <div style={{
                display: "flex",
                alignItems: "center",
                gap: 10,
                marginBottom: 12,
                padding: "8px 14px",
                borderRadius: 8,
                background: "linear-gradient(90deg, rgba(30,58,95,0.4), transparent)",
                borderRight: "3px solid #2e5a9a",
              }}>
                <span style={{ fontSize: 16 }}>📍</span>
                <h2 style={{ margin: 0, fontSize: 16, fontWeight: 800, color: "#7eb8f7" }}>{region}</h2>
                <span style={{
                  marginRight: "auto",
                  background: "rgba(14,36,72,0.8)",
                  color: "#4a90d9",
                  padding: "2px 10px",
                  borderRadius: 20,
                  fontSize: 12,
                  border: "1px solid #1e4a8a",
                }}>{list.length} مستشفى</span>
              </div>

              {/* Hospital Cards */}
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {list.map((h, i) => {
                  const tc = typeColors[h.type] || { bg: "#1a2030", text: "#8899aa", border: "#2a3a50" };
                  const cardId = `${region}-${i}`;
                  const isExpanded = expandedCard === cardId;

                  return (
                    <div
                      key={i}
                      onClick={() => setExpandedCard(isExpanded ? null : cardId)}
                      style={{
                        background: isExpanded
                          ? `linear-gradient(135deg, ${tc.bg}, #0a0f1e)`
                          : "linear-gradient(135deg, #0d1b2a, #091320)",
                        border: isExpanded ? `1.5px solid ${tc.border}` : "1.5px solid #0e2040",
                        borderRadius: 12,
                        padding: "14px 16px",
                        cursor: "pointer",
                        transition: "all 0.25s ease",
                        display: "flex",
                        alignItems: "center",
                        gap: 12,
                        flexWrap: "wrap",
                      }}
                    >
                      {/* Type Icon */}
                      <span style={{
                        fontSize: 20,
                        width: 36,
                        height: 36,
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        background: tc.bg,
                        borderRadius: 8,
                        border: `1px solid ${tc.border}`,
                        flexShrink: 0,
                      }}>{typeIcons[h.type]}</span>

                      {/* Name */}
                      <span style={{
                        flex: 1,
                        fontSize: 14,
                        fontWeight: 700,
                        color: isExpanded ? tc.text : "#b8cfe8",
                        minWidth: 180,
                      }}>{h.name}</span>

                      {/* Tags */}
                      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                        {/* Region */}
                        <span style={{
                          padding: "3px 10px",
                          borderRadius: 20,
                          fontSize: 11,
                          background: "rgba(14,36,72,0.6)",
                          color: "#4a90d9",
                          border: "1px solid #1a3a6e",
                          fontWeight: 600,
                        }}>📍 {h.region}</span>

                        {/* Ownership */}
                        <span style={{
                          padding: "3px 10px",
                          borderRadius: 20,
                          fontSize: 11,
                          background: "rgba(14,50,26,0.6)",
                          color: "#4ab86a",
                          border: "1px solid #1a4a28",
                          fontWeight: 600,
                        }}>🏛️ {h.ownership}</span>

                        {/* Type */}
                        <span style={{
                          padding: "3px 10px",
                          borderRadius: 20,
                          fontSize: 11,
                          background: tc.bg,
                          color: tc.text,
                          border: `1px solid ${tc.border}`,
                          fontWeight: 700,
                        }}>{typeIcons[h.type]} {h.type}</span>
                      </div>

                      <span style={{ color: isExpanded ? tc.text : "#1e3a5f", fontSize: 12 }}>
                        {isExpanded ? "▲" : "▼"}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
