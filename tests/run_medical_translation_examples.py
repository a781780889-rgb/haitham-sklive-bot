import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from test_medical_translation_examples import (
    test_hospital_translation_is_semantic,
    test_nationality_translation_is_canonical,
    test_title_translation_uses_professional_term,
    test_identifiers_are_not_translated,
)

for test in (
    test_hospital_translation_is_semantic,
    test_nationality_translation_is_canonical,
    test_title_translation_uses_professional_term,
    test_identifiers_are_not_translated,
):
    test()
    print(f"PASS {test.__name__}")
