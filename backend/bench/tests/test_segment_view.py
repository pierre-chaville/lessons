"""Review app segment view (correction in Hebrew script): pieces, bidi isolation, and counters equal
to the metric details."""

import pytest

from bench.metrics import get_metric, hebrew
from bench.metrics.hebrew import CATEGORIES, Glossary, analyze, doubts, tokens
from bench.review_app import segment_view
from bench.review_app.segment_view import RenderOptions

OPTIONS = RenderOptions(Glossary(()))


@pytest.fixture(autouse=True)
def no_app_glossary(monkeypatch):
    monkeypatch.setattr(hebrew, "_app_glossary_index", lambda: Glossary(()))
    analyze.cache_clear()
    yield
    analyze.cache_clear()


def flat(pieces):
    return "".join(p["t"] if "t" in p else "".join(q["t"] for q in p["rtl"]) for p in pieces)


def marked(pieces):
    result = []
    for p in pieces:
        for q in p.get("rtl", [p]):
            if q.get("c"):
                result.append((q["t"], q["c"]))
    return result


class TestPieces:
    def test_doubt_spans_and_positions(self):
        clean, spans = doubts('du <d i="Shurim" alt="a|b">שִׁיעוּר</d> de')
        assert clean == "du שִׁיעוּר de"
        assert clean[spans[0].start:spans[0].end] == "שִׁיעוּר" and spans[0].attributes == {"i": "Shurim", "alt": "a|b"}
        words = tokens('du <d i="Shurim">שִׁיעוּר</d> de')
        assert [clean[w.start:w.end] for w in words] == ["du", "שִׁיעוּר", "de"]

    def test_hebrew_passage_isolated_without_its_punctuation(self):
        pieces, n = segment_view.gold_column("le don des מִצְווֹת, c'est « זְמַן חֵרוּתֵנוּ », le temps")
        assert n == 0 and flat(pieces) == "le don des מִצְווֹת, c'est « זְמַן חֵרוּתֵנוּ », le temps"
        runs = ["".join(q["t"] for q in p["rtl"]) for p in pieces if "rtl" in p]
        assert runs == ["מִצְווֹת", "זְמַן חֵרוּתֵנוּ"]

    def test_gold_doubts_are_marked(self):
        pieces, n = segment_view.gold_column('du <d alt="שִׁעוּר">שִׁיעוּר</d> de פֶּסַח')
        assert n == 1 and marked(pieces) == [("שִׁיעוּר", "gold_doubt")]

    def test_initial_words_changed_by_the_gold(self):
        pieces, changes = segment_view.initial_column("du Shurim de Pesach", "du שִׁיעוּר de פֶּסַח")
        assert changes == 2 and marked(pieces) == [("Shurim", "gold_changed"), ("Pesach", "gold_changed")]

    def test_output_cell(self):
        cell = segment_view.output_cell(0, "des מִצְוֹת du עֹמֶר reçues ici", "des מִצְווֹת du Omer reçus là", "",
                                        OPTIONS, True)
        assert marked(cell["pieces"]) == [("מִצְווֹת", "spelling_variant"), ("Omer", "latin_correct"),
                                          ("reçus", "french_variant"), ("là", "french_error")]
        assert cell["worst"] == "error"
        assert cell["counts"] == {"spelling_variant": 1, "latin_correct": 1, "french_variant": 1, "french_error": 1}
        reçus = next(p for p in cell["pieces"] if p.get("t") == "reçus")
        assert (reçus["s"], reçus["h"]) == ("variant", "one-letter difference (French): gold «reçues»")
        omer = next(p for p in cell["pieces"] if p.get("t") == "Omer")
        assert omer["s"] == "form" and omer["h"].startswith("right word, Latin script: עֹמֶר → Omer")

    def test_missing_word_is_a_gap(self):
        cell = segment_view.output_cell(0, "le פֶּסַח arrive", "le arrive", "", OPTIONS, True)
        gaps = [p for p in cell["pieces"] if p.get("gap")]
        assert [(g["c"], g["h"]) for g in gaps] == [("missing", "missing: פֶּסַח")]  # not also a French error


class TestCountersEqualMetrics:
    GOLD = ("- [0s - 2s] des מִצְוֹת de פֶּסַח reçues à מָרָה\n"
            "- [2s - 4s] qui se déroule sur la terre du שִׁיעוּר\n"
            "- [4s - 6s] Le 2 et הַשֵּׁם\n")
    OUTPUT = ("- [0s - 2s] des מִצְווֹת de Pessaḥ reçus Amara\n"
              "- [2s - 4s] qui rampe dans les grands champs du שִׁיעוּרִים\n"
              "- [4s - 6s] Le deux et ה'\n")
    INPUT = "- [0s - 2s] des mitsvot de Pesach reçu Amara\n- [2s - 4s] qui se déroule\n- [4s - 6s] le deux et Hachem\n"

    def test_same_counts(self):
        totals: dict[str, int] = {}
        for gold, output, initial in zip(self.GOLD.splitlines(), self.OUTPUT.splitlines(), self.INPUT.splitlines()):
            text = lambda line: line.split("] ", 1)[1]
            cell = segment_view.output_cell(0, text(gold), text(output), text(initial), OPTIONS, True)
            for category, n in cell["counts"].items():
                totals[category] = totals.get(category, 0) + n
        a = get_metric("hebrew_identification")(self.OUTPUT, input_text=self.INPUT, reference=self.GOLD).details
        b = get_metric("wer_french")(self.OUTPUT, input_text=self.INPUT, reference=self.GOLD).details
        metric = {**{c: a[c] for c in CATEGORIES if c != "exact"}, "exact_niqqud": a["exact_niqqud"],
                  "french_error": b["french_errors"], "drift": b["large_edits"], "minor": b["minor"],
                  "french_variant": b["french_variants"]}
        assert totals == {k: v for k, v in metric.items() if v}
        assert {"latin_correct", "latin_uncorrected", "form_variant", "spelling_variant", "drift", "minor"} <= set(totals)


class TestJudgeLevels:
    GOLD = ("- [0s - 2s] Un temps qui est פֶּסַח\n"
            "- [2s - 4s] et les מִצְוֹת de שָׁבוּעוֹת reçues ici\n"
            "- [4s - 6s] c'est la fin du עֹמֶר\n")
    OUTPUT = ("- [0s - 2s] Un temps qui est סְפִירַת\n"
              "- [2s - 4s] et les מִצְווֹת de l'échappement reçus là\n"
              "- [4s - 6s] c'est la fin du Omer\n")
    INITIAL = "- [0s - 2s] un temps\n- [2s - 4s] et les mitsvot\n- [4s - 6s] c'est la fin du Homère\n"
    VERDICTS = [  # 1: פֶּסַח → סְפִירַת, 2: שָׁבוּעוֹת → l'échappement, 3: ici → là
        {"diff_id": 1, "severity": 3, "recoverable_from_context": False, "who_is_right": "gold", "explanation": "a"},
        {"diff_id": 2, "severity": 2, "recoverable_from_context": True, "who_is_right": "unsure", "explanation": "b"},
        {"diff_id": 3, "severity": 1, "recoverable_from_context": True, "who_is_right": "model", "explanation": "c"},
    ]

    def judgment(self):
        from bench.dataset import LessonItem, parse_transcript
        from bench.metrics import correction_judge

        class FakeJudge:
            def ask(_, schema, prompt):
                return schema(verdicts=self.VERDICTS)

        item = LessonItem("x", "extracts", None, corrected=parse_transcript(self.GOLD)[0])
        return correction_judge.compute(self.OUTPUT, input_text=self.INITIAL, item=item, options={}, judge=FakeJudge())

    def cells(self, details):
        from bench.dataset import parse_transcript
        from bench.metrics.correction_judge import segment_label
        from bench.review_app.data import _segment_verdicts

        verdicts = _segment_verdicts(details)
        cells = []
        for gold, output, initial in zip(*(parse_transcript(t)[0] for t in (self.GOLD, self.OUTPUT, self.INITIAL))):
            cells.append(segment_view.output_cell(gold.start, gold.text, output.text, initial.text, OPTIONS, False, True,
                                                  verdicts.get(segment_label(gold.start, gold.end), {})))
        return cells

    def test_levels_and_counters_equal_the_metric(self):
        result = self.judgment()
        cells = self.cells(result.details)
        assert [c["judge_worst"] for c in cells] == ["critical", "significant", "minor"]
        levels = [(q["t"], q["j"]) for c in cells for q in marked_pieces(c["pieces"])]
        assert levels == [("סְפִירַת", "critical"), ("מִצְווֹת", "none"),  # spelling variant: grey, not judged
                          ("‸", "significant"), ("l'échappement", "significant"),  # one discrepancy: gap + words
                          ("reçus", "none"), ("là", "none"),  # one-letter variant; là: the output is right
                          ("Omer", "minor")]  # right word in Latin script (orange before): yellow, not judged
        totals = {}
        for cell in cells:
            for key, n in cell["judge_counts"].items():
                totals[key] = totals.get(key, 0) + n
        counts = result.details["severity_counts"]
        assert (totals["critical"], totals["significant"]) == (counts["3"], counts["2"]) == (1, 1)
        assert totals["gold_suspect"] == result.details["gold_suspects"] == 1
        assert totals["unjudged"] == 0 and totals["minor_form"] == 1 and totals["none_variant"] >= 2
        la = next(q for c in cells for q in marked_pieces(c["pieces"]) if q["t"] == "là")
        assert la["gs"] and "the output is right" in la["jh"]

    def test_no_verdict_after_a_gold_change(self):
        details = self.judgment().details
        for verdict in details["verdicts"]:
            if verdict["gold"] == "פֶּסַח":
                verdict["gold"] = "something else"  # the gold changed since the judgment
        cells = self.cells(details)
        assert cells[0]["judge_worst"] == "unjudged" and cells[0]["judge_counts"]["unjudged"] == 1


def marked_pieces(pieces):
    return [q for p in pieces for q in p.get("rtl", [p]) if q.get("c")]
