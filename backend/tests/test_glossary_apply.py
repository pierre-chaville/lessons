from importlib import util
from pathlib import Path
import sys
import types


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "services" / "glossary_apply.py"

# Avoid importing backend.services package side effects (LLM/config/db setup)
# by loading glossary_apply directly from file.
_crud_stub = types.ModuleType("crud")
_crud_stub.get_all_glossary_entries = lambda session: []
sys.modules.setdefault("crud", _crud_stub)

_spec = util.spec_from_file_location("glossary_apply_test_module", MODULE_PATH)
assert _spec and _spec.loader
_module = util.module_from_spec(_spec)
sys.modules[_spec.name] = _module
_spec.loader.exec_module(_module)

GlossaryRule = _module.GlossaryRule
apply_glossary_to_text_with_report = _module.apply_glossary_to_text_with_report


def test_glossary_replacements_do_not_cascade_between_rules():
    # If replacements cascade, this would become "Aquiva".
    rules = [
        GlossaryRule(standard="Akiva", variations=("Aqiva",), exact_case=False),
        GlossaryRule(standard="Aquiva", variations=("Akiva",), exact_case=False),
    ]

    normalized, report = apply_glossary_to_text_with_report("Aqiva taught.", rules)

    assert normalized == "Akiva taught."
    assert any(item["standard"] == "Akiva" and item["variation"] == "Aqiva" for item in report)
    assert not any(item["standard"] == "Aquiva" for item in report)


def test_glossary_handles_variation_with_apostrophe_boundary():
    rules = [
        GlossaryRule(standard="R. Akiva", variations=("R' Akiva",), exact_case=False),
    ]

    normalized, report = apply_glossary_to_text_with_report("R' Akiva said ...", rules)

    assert normalized == "R. Akiva said ..."
    assert report == [
        {
            "standard": "R. Akiva",
            "variation": "R' Akiva",
            "exact_case": False,
            "count": 1,
        }
    ]


def test_glossary_does_not_double_apostrophe_on_prefixed_variant():
    rules = [
        GlossaryRule(
            standard="'Aqiva",
            variations=("'Aqiva", "Aqiva", "'Akiva", "Akiva", "Akiba"),
            exact_case=False,
        ),
    ]

    normalized, report = apply_glossary_to_text_with_report("Rabbi 'Akiva", rules)

    assert normalized == "Rabbi 'Aqiva"
    assert report == [
        {
            "standard": "'Aqiva",
            "variation": "'Akiva",
            "exact_case": False,
            "count": 1,
        }
    ]


def test_glossary_does_not_add_third_apostrophe_when_double_prefixed():
    rules = [
        GlossaryRule(
            standard="'Aqiva",
            variations=("'Aqiva", "Aqiva", "'Akiva", "Akiva", "Akiba"),
            exact_case=False,
        ),
    ]

    normalized, _ = apply_glossary_to_text_with_report("Rabbi ''Akiva", rules)

    assert normalized == "Rabbi ''Akiva"


def test_glossary_treats_modifier_apostrophe_as_prefix_boundary():
    rules = [
        GlossaryRule(standard="'Aqiva", variations=("Akiva",), exact_case=False),
    ]

    normalized, _ = apply_glossary_to_text_with_report("Rabbi ʼAkiva", rules)

    assert normalized == "Rabbi ʼAkiva"
