import sys
from pathlib import Path

root = Path(__file__).parents[1]
sys.path.insert(0, str(root))
from medical_report import create_template_pdf
out = Path('/home/ubuntu/upload/medical_report_diagnosis_fixed.pdf')
data = {
    'patient_name': 'هيثم عقلان',
    'diagnosis': 'التهابات اللثة والأسنان مع ألم وتورم يحتاج إلى متابعة وعلاج',
    'visit_days': '2',
    'days': '2',
    'admission_date': '12/07/2026',
    'discharge_date': '14/07/2026',
    'hospital': 'المستشفى السعودي الألماني - مكة',
    'hospital_license': '6687117915791008',
    'full_name': 'هيثم عقلان',
    'id_number': '5635464545',
    'nationality': 'سعودي',
    'doctor': 'أحمد ناصر الحربي',
    'specialty': 'استشاري عظام',
}
create_template_pdf(data, out, root / 'templates' / 'medical_report_reference_a3.pdf')
print(out)
