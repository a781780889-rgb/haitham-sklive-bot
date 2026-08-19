from pathlib import Path

html = (Path(__file__).parents[1] / "templates" / "medical_reports_portal.html").read_text(encoding="utf-8")
start = html.index("<script>") + len("<script>")
end = html.index("</script>", start)
(Path(__file__).parents[1] / ".portal_inline.js").write_text(html[start:end], encoding="utf-8")
print("extracted inline JavaScript")
