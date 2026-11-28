"""correction_judge: only the red / purple discrepancies are sent, grouped by segment with their
context; scoring per 1,000 gold words, gold suspects and both-acceptable not counted as errors."""

import pytest

from bench.dataset import LessonItem, parse_transcript
from bench.metrics import correction_judge as cj
from bench.metrics import hebrew
from bench.metrics.hebrew import Glossary, analyze

GOLD = ("- [0s - 2s] Un temps qui est פֶּסַח\n"
        "- [2s - 4s] et les מִצְוֹת de <d alt=\"עוֹמֶר\">שָׁבוּעוֹת</d> reçues ici\n"
        "- [4s - 6s] c'est la fin\n")
OUTPUT = ("- [0s - 2s] Un temps qui est סְפִירַת\n"
          "- [2s - 4s] et les מִצְווֹת de l'échappement reçus là\n"
          "- [4s - 6s] c'est la fin\n")
INITIAL = "- [0s - 2s] un temps qui est Pessah\n- [2s - 4s] et les mitsvot de l'échappement reçu là\n- [4s - 6s] c'est la fin\n"


@pytest.fixture(autouse=True)
def no_app_glossary(monkeypatch):
    monkeypatch.setattr(hebrew, "_app_glossary_index", lambda: Glossary(()))
    analyze.cache_clear()
    yield
    analyze.cache_clear()


def item() -> LessonItem:
    return LessonItem("x", "extracts", None, corrected=parse_transcript(GOLD)[0])


class FakeJudge:
    def __init__(self, verdicts):
        self.verdicts, self.prompts = verdicts, []

    def ask(self, schema, prompt):
        self.prompts.append(prompt)
        return schema(verdicts=self.verdicts)


def test_only_serious_discrepancies_with_context():
    _, found = cj.discrepancies(OUTPUT, GOLD, INITIAL, {})
    assert [(d.id, d.category, d.gold, d.output, d.segment) for d in found] == [
        (1, "wrong_word", "פֶּסַח", "סְפִירַת", "0s - 2s"),
        (2, "french_error", "שָׁבוּעוֹת", "l'échappement", "2s - 4s"),  # missing Hebrew + French edit: one item
        (3, "french_error", "ici", "là", "2s - 4s"),  # reçues / reçus: one-letter variant, not sent
    ]
    text = cj._segments_text(found, GOLD, OUTPUT, INITIAL, 1)
    assert "### Segment [2s - 4s]" in text and "previous (gold): Un temps qui est פֶּסַח" in text
    assert "raw transcription: et les mitsvot de l'échappement reçu là" in text
    assert "alternatives: עוֹמֶר" in text and "next (gold): c'est la fin" in text
    assert "  3. French error: ici → là" in text and "מִצְווֹת →" not in text  # variant: not sent


def test_one_call_and_scoring():
    verdicts = [
        {"diff_id": 1, "severity": 3, "recoverable_from_context": False, "who_is_right": "gold", "explanation": "a"},
        {"diff_id": 2, "severity": 2, "recoverable_from_context": True, "who_is_right": "unsure", "explanation": "b"},
        {"diff_id": 3, "severity": 0, "recoverable_from_context": True, "who_is_right": "model", "explanation": "c"},
    ]
    fake = FakeJudge(verdicts)
    result = cj.compute(OUTPUT, input_text=INITIAL, item=item(), options={}, judge=fake)
    assert len(fake.prompts) == 1
    words = result.details["gold_words"]
    assert result.value == pytest.approx(5 * 1000 / words)
    assert result.details["critical_errors"] == pytest.approx(1000 / words)
    assert result.details["significant_errors"] == pytest.approx(1000 / words)
    assert result.details["unrecoverable_rate"] == pytest.approx(1 / 2)
    assert result.details["gold_suspects"] == 1 and result.details["gold_suspect_list"][0]["gold"] == "ici"
    assert result.details["verdicts"][0]["id"] == 1  # most severe first


def test_no_discrepancy_no_call():
    fake = FakeJudge([])
    result = cj.compute(GOLD, input_text=INITIAL, item=item(), options={}, judge=fake)
    assert fake.prompts == [] and result.value == 0


def test_batches_never_split_a_segment():
    _, found = cj.discrepancies(OUTPUT, GOLD, INITIAL, {})
    assert [[d.id for d in b] for b in cj._batches(found, 1)] == [[1], [2, 3]]


def test_options():
    assert cj.check_options({"context_segments": 2, "batch_size": 50}) == []
    assert cj.check_options({"batch_size": 0})
