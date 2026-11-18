from types import SimpleNamespace

import pytest

from bench.judge import JudgeModel, normalize_for_quotes, quote_found
from bench.metrics import faithfulness, idea_coverage

OUTPUT = """# La fête de Chavouot

Le Rav explique que **Chavouot** célèbre le don de la Torah au mont Sinaï.
Selon Rachi, le peuple campa « comme un seul homme, d'un seul cœur ».
"""
SOURCE = """- [1s - 8s] Chavouot, c'est la fête du don de la Torah au mont Sinaï.
- [9s - 15s] Rachi dit : le peuple campa comme un seul homme, d'un seul cœur.
"""


class FakeJudge:
    """Returns the queued answers, in order."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.prompts = []

    def ask(self, schema, prompt):
        self.prompts.append(prompt)
        return schema.model_validate(self.answers.pop(0))


def item(*ideas):
    return SimpleNamespace(ideas=[{"id": i + 1, "text": t, "importance": imp} for i, (t, imp) in enumerate(ideas)])


def test_quote_found_tolerates_accents_quotes_and_markdown():
    text = normalize_for_quotes(OUTPUT)
    assert quote_found("Le Rav explique que Chavouot celebre le don de la Torah", text)
    assert quote_found("le peuple campa \"comme un seul homme, d’un seul coeur\"", text)
    assert not quote_found("Moïse brisa les tables de la loi", text)
    assert not quote_found("Torah", text)  # too short to prove anything


def test_idea_coverage_weights_and_evidence():
    lesson = item(("Chavouot célèbre le don de la Torah", "high"),
                  ("Rachi : comme un seul homme", "medium"),
                  ("Les tables furent brisées", "high"),
                  ("On lit le livre de Ruth", "low"))
    judge = FakeJudge({"verdicts": [
        {"id": 1, "verdict": "present", "quote": "Chavouot célèbre le don de la Torah au mont Sinaï"},
        {"id": 2, "verdict": "partial", "quote": "le peuple campa « comme un seul homme"},
        {"id": 3, "verdict": "present", "quote": "Moïse brisa les tables en descendant"},  # invented quote
    ]})  # idea 4 forgotten by the judge
    result = idea_coverage.compute(OUTPUT, input_text=SOURCE, options={}, item=lesson, judge=judge)
    # (3*1 + 2*0.5 + 3*0 + 1*0) / 9
    assert result.value == pytest.approx(4 / 9)
    assert result.details["rejected_evidence"] == [3]
    assert result.details["missing_verdicts"] == [4]
    assert result.details["missed_high"] == 1
    assert result.details["missed_high_ideas"] == ["Les tables furent brisées"]
    assert (result.details["present"], result.details["partial"], result.details["absent"]) == (1, 1, 2)


def test_idea_coverage_without_ideas_is_undefined():
    assert idea_coverage.compute(OUTPUT, input_text=SOURCE, item=item(), judge=FakeJudge()).value is None


def test_faithfulness_counts_and_unverified_support():
    judge = FakeJudge(
        {"claims": ["Chavouot célèbre le don de la Torah.", "Rachi dit que le peuple campa comme un seul homme.",
                    "Chavouot dure deux jours en diaspora.", "Le Ramban dit que le peuple campa uni."]},
        {"verdicts": [
            {"id": 1, "verdict": "supported", "quote": "c'est la fête du don de la Torah au mont Sinaï"},
            {"id": 2, "verdict": "supported", "quote": "Rachi enseigne que tout Israël était uni"},  # not in the source
            {"id": 3, "verdict": "external_addition", "quote": ""},
            {"id": 4, "verdict": "misattribution", "quote": "Rachi dit : le peuple campa"},
        ]},
    )
    result = faithfulness.compute(OUTPUT, input_text=SOURCE, options={}, judge=judge)
    assert result.value == pytest.approx(1 / 4)
    d = result.details
    assert (d["claims"], d["supported"], d["unverified"], d["external_addition"], d["misattribution"]) == (4, 1, 1, 1, 1)
    assert [i["verdict"] for i in d["issues"]] == ["misattribution", "external_addition", "unverified"]
    assert "[1s - 8s]" not in judge.prompts[1]  # the source is sent without timestamps


def test_faithfulness_checks_claims_by_batches():
    claims = [f"Affirmation numéro {i}." for i in range(1, 6)]
    judge = FakeJudge(
        {"claims": claims},
        {"verdicts": [{"id": i, "verdict": "extrapolation", "quote": ""} for i in (1, 2)]},
        {"verdicts": [{"id": i, "verdict": "extrapolation", "quote": ""} for i in (3, 4)]},
        {"verdicts": [{"id": 5, "verdict": "contradicted", "quote": "Rachi dit : le peuple campa"}]},
    )
    result = faithfulness.compute(OUTPUT, input_text=SOURCE, options={"claims_per_call": 2}, judge=judge)
    assert result.value == 0
    assert result.details["contradicted"] == 1 and result.details["extrapolation"] == 4
    assert len(judge.prompts) == 4


def test_estimates_and_options():
    lesson = item(("Idée", "high"), ("Autre idée", "low"))
    tokens_in, tokens_out = idea_coverage.estimate_tokens(OUTPUT, input_text=SOURCE, item=lesson, options={})
    assert tokens_in > 0 and tokens_out > 0
    tokens_in, tokens_out = faithfulness.estimate_tokens(OUTPUT, input_text=SOURCE, item=lesson, options={})
    assert tokens_in > 0 and tokens_out > 0
    assert faithfulness.check_options({"claims_per_call": 0})
    assert idea_coverage.check_options({"evidence_threshold": 150})
    assert not faithfulness.check_options({})


def test_judge_signature_ignores_nothing_but_flex():
    base = dict(model_id="m", provider="openrouter", params={"temperature": 0}, timeout=60, max_retries=0,
                price=(1.0, 2.0))
    a, b = JudgeModel(**base), JudgeModel(**base, flex=True)
    assert a.signature("faithfulness", 1, {}) == b.signature("faithfulness", 1, {})
    assert a.signature("faithfulness", 1, {}) != a.signature("faithfulness", 2, {})
    assert a.signature("faithfulness", 1, {}) != JudgeModel(**{**base, "model_id": "n"}).signature("faithfulness", 1, {})
    assert a.cost(1_000_000, 500_000) == pytest.approx(2.0)
