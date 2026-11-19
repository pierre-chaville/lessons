from types import SimpleNamespace

import pytest

from bench.metrics import get_metric_module
from bench.metrics.text import count_words
from bench.review_app.data import _rubric_warnings, spearman
from bench.tests.test_judge_metrics import FakeJudge

judge_rubric = get_metric_module("judge_rubric")

RUBRIC = """name: test_style
version: 1
scale: [1, 5]
criteria:
  - id: structure
    weight: 2
    definition: "Paragraphes de quelques phrases."
    anchors:
      1: "Bloc continu."
      3: "Quelques paragraphes d'une phrase."
      5: "Paragraphes cohérents."
  - id: oral_cleanup
    weight: 1
    definition: "Marques de l'oral supprimées."
    checks:
      - question: "Reste-t-il des « euh » ?"
        expected: no
      - question: "Reste-t-il des répétitions ?"
        expected: "no"
"""
OUTPUT = "Le Rav explique la fête.\n\nIl cite Rachi sur le verset."
SOURCE = "- [1s - 5s] Le Rav euh explique la fête, la fête.\n- [6s - 9s] Il cite Rachi sur le verset, voilà, donc."


@pytest.fixture
def options(tmp_path):
    path = tmp_path / "rubric.yaml"
    path.write_text(RUBRIC, encoding="utf-8")
    return {"rubric": str(path)}


def answer(structure=4, euh="no", repetitions="yes"):
    return {"criteria": [{"criterion": "structure", "justification": "Deux paragraphes courts.", "score": structure}],
            "checks": [{"id": "oral_cleanup.1", "answer": euh, "evidence": None},
                       {"id": "oral_cleanup.2", "answer": repetitions, "evidence": "la fête, la fête"}]}


def test_anchors_checks_and_weighted_grade(options):
    judge = FakeJudge(answer())
    result = judge_rubric.compute(OUTPUT, input_text=SOURCE, options=options, item=SimpleNamespace(), judge=judge)
    prompt = judge.prompts[0]
    assert "Length is not quality" in prompt and "oral_cleanup.2: Reste-t-il des répétitions ?" in prompt
    assert "3 = Quelques paragraphes d'une phrase." in prompt and "Transcript of the lesson" in prompt
    # structure 4 (judge), oral_cleanup 1 of 2 checks passed -> 1 + 4 * 0.5 = 3
    assert result.details["structure"] == 4 and result.details["oral_cleanup"] == 3
    assert result.value == pytest.approx((2 * 4 + 1 * 3) / 3)
    assert result.details["failed_checks"] == ["Reste-t-il des répétitions ?"]
    assert result.details["length_ratio"] == pytest.approx(count_words(OUTPUT) / count_words(SOURCE))
    assert result.details["length_ratio"] < 1
    checks = result.details["criteria"][1]["checks"]
    assert checks[1]["evidence"] == "la fête, la fête" and checks[1]["passed"] is False


def test_out_of_scale_and_missing_scores(options):
    result = judge_rubric.score({"criteria": [{"criterion": "structure", "justification": "x", "score": 9}], "checks": []},
                                OUTPUT, input_text=SOURCE, options=options)
    assert result.details["structure"] == 5  # clamped to the scale
    assert result.details["oral_cleanup"] is None and result.details["missing_criteria"] == ["oral_cleanup"]
    assert result.value == 5


def test_without_source(options):
    judge = FakeJudge(answer())
    judge_rubric.compute(OUTPUT, input_text=SOURCE, options={**options, "with_source": False}, item=None, judge=judge)
    assert "Transcript of the lesson" not in judge.prompts[0]


def test_rubric_checks_and_signature(options, tmp_path):
    assert judge_rubric.check_options(options) == []
    assert judge_rubric.check_options({}) and judge_rubric.check_options({"rubric": "missing.yaml"})
    bad = tmp_path / "bad.yaml"
    bad.write_text("scale: [0, 10]\ncriteria:\n  - id: a\n    definition: d\n    anchors: {0: x, 10: y}\n"
                   "    checks: [{question: q, expected: maybe}]\n", encoding="utf-8")
    problems = " ".join(judge_rubric.check_options({"rubric": str(bad)}))
    assert "scale" in problems and "either 'anchors'" in problems and "expected" in problems
    assert list(judge_rubric.report_details(options)) == ["structure", "oral_cleanup", "length_ratio"]
    before = judge_rubric.judge_inputs(None, options)
    (tmp_path / "rubric.yaml").write_text(RUBRIC.replace("version: 1", "version: 2"), encoding="utf-8")
    assert judge_rubric.judge_inputs(None, options) != before  # editing the rubric invalidates the judgments


def test_bias_warnings():
    assert spearman([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1.0)
    assert spearman([1, 2, 3, 4], [40, 30, 20, 10]) == pytest.approx(-1.0)
    clustered = [(4.0, {"length_ratio": 0.8 + i / 100, "criteria": [{"source": "judge", "judge_score": 4}] * 2})
                 for i in range(5)]
    warnings = _rubric_warnings(clustered)
    assert len(warnings) == 1 and "cluster" in warnings[0]
    spread = [(float(v), {"length_ratio": r, "criteria": [{"source": "judge", "judge_score": v}]})
              for v, r in [(2, 0.9), (5, 0.6), (3, 0.8), (4, 0.7), (1, 1.0)]]
    assert _rubric_warnings(spread) == []
    longer_better = [(float(v), {"length_ratio": v / 5, "criteria": []}) for v in (1, 2, 3, 4, 5)]
    assert any("length" in w for w in _rubric_warnings(longer_better))
