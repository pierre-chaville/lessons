from types import SimpleNamespace

import pytest

from bench.judge import JudgeModel, QuoteIndex, judge_options, normalize_for_quotes, quote_found
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
    present = [{"element": "fête du don de la Torah", "status": "present"}]
    judge = FakeJudge({"verdicts": [
        {"id": 1, "elements": present, "verdict": "present", "missing": None,
         "quotes": ["Chavouot célèbre le don de la Torah au mont Sinaï"]},
        {"id": 2, "elements": [{"element": "comme un seul homme", "status": "present"},
                               {"element": "le cœur unique", "status": "implicit"}],
         "verdict": "partial", "missing": "L'unité des cœurs n'est que suggérée.",
         "quotes": ["introuvable dans la sortie", "le peuple campa « comme un seul homme"]},
        {"id": 3, "elements": present, "verdict": "present", "missing": None,
         "quotes": ["Moïse brisa les tables en descendant"]},  # invented quote
    ]})  # idea 4 forgotten by the judge
    result = idea_coverage.compute(OUTPUT, input_text=SOURCE, options={}, item=lesson, judge=judge)
    # (3*1 + 2*0.5 + 3*0 + 1*0) / 9
    assert result.value == pytest.approx(4 / 9)
    assert result.details["rejected_evidence"] == [3]
    assert result.details["missing_verdicts"] == [4]
    assert result.details["missed_high"] == 1
    assert result.details["missed_high_ideas"] == ["Les tables furent brisées"]
    assert (result.details["present"], result.details["partial"], result.details["absent"]) == (1, 1, 2)
    assert result.details["present_rate"] == 0.25 and result.details["absent_rate"] == 0.5
    assert result.details["elements"] == {"present": 3, "implicit": 1, "distorted": 0, "missing": 0}
    quotes = result.details["verdicts"][1]["quotes"]
    assert [q["found"] for q in quotes] == [False, True]
    assert OUTPUT[quotes[1]["start"]:quotes[1]["end"]].startswith("le peuple campa")
    assert result.details["verdicts"][1]["missing"] == "L'unité des cœurs n'est que suggérée."
    assert result.details["verdicts"][0]["elements_source"] == "judge"


def test_idea_coverage_present_needs_every_element_and_uses_dataset_elements():
    lesson = item(("Chavouot célèbre le don de la Torah au Sinaï", "high"))
    lesson.ideas[0]["elements"] = ["fête du don de la Torah", "au mont Sinaï"]
    judge = FakeJudge({"verdicts": [
        {"id": 1, "elements": [{"element": "fête du don de la Torah", "status": "present"},
                               {"element": "au mont Sinaï", "status": "implicit"}],
         "verdict": "present", "missing": None, "quotes": ["Chavouot célèbre le don de la Torah"]},
    ]})
    result = idea_coverage.compute(OUTPUT, input_text=SOURCE, options={}, item=lesson, judge=judge)
    assert "essential elements: fête du don de la Torah | au mont Sinaï" in judge.prompts[0]
    assert result.value == 0.5
    assert result.details["downgraded"] == [1]
    verdict = result.details["verdicts"][0]
    assert (verdict["verdict"], verdict["judge_verdict"], verdict["elements_source"]) == ("partial", "present", "dataset")
    other = item(("Chavouot célèbre le don de la Torah au Sinaï", "high"))
    assert idea_coverage.judge_inputs(lesson) != idea_coverage.judge_inputs(other)


def test_quotes_ignore_markdown_and_niqqud():
    output = "La *teshouvah* apporte la כַּפָּרָה ; le בֵּית־הַמִּקְדָּשׁ viendra ensuite."
    index = QuoteIndex(output)
    assert index.locate("La teshouvah apporte la כפרה", 85) is not None
    assert index.locate("le בית המקדש viendra ensuite", 85) is not None


def test_idea_coverage_without_ideas_is_undefined():
    assert idea_coverage.compute(OUTPUT, input_text=SOURCE, item=item(), judge=FakeJudge()).value is None


def verdict(id, verdict, subtype=None, source_quote=None, severity="minor", believes=None, reference=None,
            explanation=""):
    return {"id": id, "verdict": verdict, "subtype": subtype, "source_quote": source_quote, "severity": severity,
            "believes": believes, "reference": reference, "explanation": explanation}


def claim(text, quote):
    return {"claim": text, "output_quote": quote}


FAITH_OUTPUT = OUTPUT + "Comme le dit le prophète Osée (14, 3) : « à la place des taureaux, nous paierons par nos lèvres ».\n"
FAITH_SOURCE = SOURCE + "- [724s - 731s] Il y a un passage dans les Tehilim où on dit : à la place des taureaux, on va payer par nos lèvres.\n"


@pytest.fixture
def fake_sefaria(monkeypatch):
    texts = {"Hosea 14:3": {"slug": "Hosea.14.3", "found": True, "ref": "Hosea 14:3", "he": "...",
                            "en": "Instead of bulls we will pay [the offering of] our lips."}}
    monkeypatch.setattr(faithfulness.sefaria, "fetch",
                        lambda ref: texts.get(ref, {"slug": "x", "found": False, "error": "not found"}))


def faithfulness_judge():
    return FakeJudge(
        {"claims": [
            claim("Chavouot célèbre le don de la Torah.", "Chavouot** célèbre le don de la Torah au mont Sinaï"),
            claim("Rachi dit que le peuple campa comme un seul homme.", "Selon Rachi, le peuple campa"),
            claim("Chavouot dure deux jours en diaspora.", "Chavouot dure deux jours"),  # not in the output
            claim("Le verset d'Osée 14, 3 dit : à la place des taureaux, nous paierons par nos lèvres.",
                  "le prophète Osée (14, 3) : « à la place des taureaux… »"),
            claim("Le Ramban dit que le peuple campa uni.", "Selon Rachi, le peuple campa"),
        ]},
        {"verdicts": [
            verdict(1, "supported", source_quote="c'est la fête du don de la Torah au mont Sinaï"),
            verdict(2, "supported", source_quote="Rachi enseigne que tout Israël était uni"),  # not in the source
            verdict(3, "external_addition", "content_added", severity="major", explanation="Non dit."),
            verdict(4, "misattribution", "model_error", believes="speaker", reference="Hosea 14:3",
                    source_quote="Il y a un passage dans les Tehilim où on dit ... à la place des taureaux",
                    explanation="Le Rav attribue le verset aux Tehilim ; la sortie l'attribue à Osée 14, 3."),
            verdict(5, "misattribution", "model_error", severity="major", reference="Shemot 99:1",
                    source_quote="Rachi dit : le peuple campa comme un seul homme"),
        ]},
        {"checks": [{"id": 4, "match": "matches", "explanation": "Osée 14, 3 contient bien ce verset."}]},
    )


def test_faithfulness_findings_policy_and_references(fake_sefaria):
    judge = faithfulness_judge()
    result = faithfulness.compute(FAITH_OUTPUT, input_text=FAITH_SOURCE, options={}, judge=judge)
    d = result.details
    by_id = {i["id"]: i for i in d["issues"]}
    # Sefaria confirms Osée 14, 3: the output corrected the Rav, whatever the judge believed
    assert by_id[4]["category"] == "speaker_corrected" and not by_id[4]["penalized"]
    assert by_id[4]["source_time"] == "12m 04s - 12m 11s"
    assert by_id[4]["reference"]["match"] == "matches" and by_id[4]["output_found"]
    # a reference that does not exist is a major error
    assert by_id[5]["category"] == "wrong_reference" and by_id[5]["severity"] == "major"
    assert by_id[2]["category"] == "unverified" and not by_id[2]["source_found"]
    assert by_id[3]["category"] == "content_added" and not by_id[3]["output_found"]
    # default policy: content_added, wrong_reference and unverified penalized
    assert (d["claims"], d["supported"], d["penalized"], d["reported"]) == (5, 1, 3, 1)
    assert result.value == pytest.approx(1 - 3 / 5)
    assert [i["id"] for i in d["issues"]][:3] == [5, 3, 2]  # penalized first, most serious first
    assert {h["id"] for h in d["highlights"]} == {2, 4, 5}
    h = next(h for h in d["highlights"] if h["id"] == 4)
    assert FAITH_OUTPUT[h["start"]:h["end"]].startswith("le prophète Osée (14, 3)")
    assert "[1s - 8s]" not in judge.prompts[1]  # the source is sent without timestamps
    assert len(judge.prompts) == 3  # split, check, references (only Hosea 14:3 exists)


def test_faithfulness_policy_change_needs_no_judge_call(fake_sefaria):
    judgment = faithfulness.judge(FAITH_OUTPUT, input_text=FAITH_SOURCE, options={}, judge=faithfulness_judge())
    strict = faithfulness.score(judgment, FAITH_OUTPUT, input_text=FAITH_SOURCE,
                                options={"penalize": list(faithfulness.CATEGORIES[1:])})
    lenient = faithfulness.score(judgment, FAITH_OUTPUT, input_text=FAITH_SOURCE,
                                 options={"penalize": ["wrong_reference"], "report_only": ["unverified"]})
    assert strict.value == pytest.approx(1 / 5)
    assert lenient.value == pytest.approx(4 / 5)


def test_faithfulness_checks_claims_by_batches():
    claims = [claim(f"Affirmation numéro {i}.", "") for i in range(1, 6)]
    judge = FakeJudge(
        {"claims": claims},
        {"verdicts": [verdict(i, "extrapolation") for i in (1, 2)]},
        {"verdicts": [verdict(i, "extrapolation") for i in (3, 4)]},
        {"verdicts": [verdict(5, "contradicted", source_quote="Rachi dit : le peuple campa")]},
    )
    result = faithfulness.compute(OUTPUT, input_text=SOURCE, options={"claims_per_call": 2}, judge=judge)
    assert result.value == 0
    assert result.details["contradicted"] == 1 and result.details["extrapolation"] == 4
    assert len(judge.prompts) == 4  # no reference to check


def test_faithfulness_policy_options_are_checked():
    assert faithfulness.check_options({"penalize": ["content_added"], "report_only": ["content_added"]})
    assert faithfulness.check_options({"penalize": ["typo"]})
    assert not faithfulness.check_options({"penalize": ["content_added", "model_error"],
                                           "report_only": ["reference_added", "speaker_corrected"]})


def test_quote_index_locates_in_the_original_text():
    index = QuoteIndex(OUTPUT)
    found = index.locate("le Rav explique que Chavouot celebre le don ... au mont Sinai")
    assert OUTPUT[found["start"]:found["end"]] == "Le Rav explique que **Chavouot** célèbre le don de la Torah au mont Sinaï"
    assert index.locate("Moïse brisa les tables de la loi") is None


def test_judge_signature_ignores_scoring_options():
    model = JudgeModel(model_id="m", provider="openai", params={}, timeout=60, max_retries=0, price=None)
    signature = lambda options: model.signature("faithfulness", 2, judge_options(faithfulness, options))
    assert signature({"penalize": ["content_added"], "evidence_threshold": 90}) == signature({})
    assert signature({"claims_per_call": 10}) != signature({})


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
