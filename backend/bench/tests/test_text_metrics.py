"""Edition / summary deterministic metrics on small hand-made examples with known results."""

import pytest

from bench.metrics import get_metric, get_metric_module
from bench.metrics.hebrew_quotes_preserved import hebrew_spans
from bench.metrics.text import count_words

length_ratio = get_metric("length_ratio")
length_words = get_metric("length_words")
hebrew = get_metric("hebrew_quotes_preserved")

NO_GLOSSARY = {"glossary": False}


def transcript(*texts: str) -> str:
    return "".join(f"- [{2 * i}s - {2 * i + 2}s] {t}\n" for i, t in enumerate(texts))


class TestCountWords:
    def test_transcript_without_timestamps_and_speaker_tags(self):
        assert count_words(transcript("[audience] Oui, c'est ça.", "le texte")) == 5  # oui c'est ça le texte

    def test_markdown_symbols_are_not_words(self):
        assert count_words("## Le titre\n\nUn **mot** en *italique* – fin.") == 7


class TestLengthRatio:
    INPUT = transcript("un deux trois quatre", "cinq six sept huit neuf dix")  # 10 words

    def test_ratio_in_range(self):
        result = length_ratio("un deux trois quatre cinq six sept huit", input_text=self.INPUT,
                              options={"min": 0.6, "max": 1.1})
        assert result.value == pytest.approx(0.8)
        assert result.details["in_range"] == 1.0
        assert (result.details["words_output"], result.details["words_input"]) == (8, 10)

    def test_ratio_below_min(self):
        result = length_ratio("un deux trois quatre cinq", input_text=self.INPUT, options={"min": 0.6, "max": 1.1})
        assert result.value == pytest.approx(0.5)
        assert result.details["in_range"] == 0.0

    def test_no_range_no_in_range(self):
        result = length_ratio("un deux", input_text=self.INPUT, options={})
        assert result.value == pytest.approx(0.2)
        assert "in_range" not in result.details

    def test_empty_input_is_undefined(self):
        assert length_ratio("un", input_text="", options={}).value is None

    def test_check_options(self):
        check = get_metric_module("length_ratio").check_options
        assert check({"min": 0.6, "max": 1.1}) == []
        assert len(check({"min": 1.2, "max": 1.1})) == 1


class TestLengthWords:
    def test_within_tolerance(self):
        result = length_words("mot " * 220, input_text="", options={"target": 250, "tolerance": 0.2})
        assert result.value == 220
        assert result.details["deviation"] == pytest.approx(-0.12)
        assert result.details["abs_deviation"] == pytest.approx(0.12)
        assert result.details["in_range"] == 1.0

    def test_limit_of_tolerance_is_in_range(self):
        assert length_words("mot " * 300, options={"target": 250, "tolerance": 0.2}).details["in_range"] == 1.0

    def test_too_long(self):
        result = length_words("mot " * 301, options={"target": 250, "tolerance": 0.2})
        assert result.details["in_range"] == 0.0

    def test_default_tolerance(self):
        assert length_words("mot " * 79, options={"target": 100}).details["in_range"] == 0.0

    def test_check_options_target_required(self):
        check = get_metric_module("length_words").check_options
        assert check({"target": 250}) == []
        assert len(check({})) == 1


class TestHebrewSpans:
    def test_vowel_points_removed_and_words_grouped(self):
        assert hebrew_spans("Il dit : וְאָהַבְתָּ לְרֵעֲךָ כָּמוֹךָ, puis מִשְׁכָּן.") == ["ואהבת לרעך כמוך", "משכן"]

    def test_single_letters_ignored_and_duplicates_once(self):
        assert hebrew_spans("la lettre ה puis משכן et משכן") == ["משכן"]


class TestHebrewQuotesPreserved:
    def test_spans_found_without_vowel_points(self):
        result = hebrew(
            "Le verset « ואהבת לרעך כמוך » enseigne...",
            input_text=transcript("comme dit le verset וְאָהַבְתָּ לְרֵעֲךָ כָּמוֹךָ", "et aussi מִשְׁכָּן"),
            options=NO_GLOSSARY,
        )
        assert result.value == pytest.approx(0.5)  # 1 of 2 spans
        assert result.details["missing_hebrew"] == ["משכן"]

    def test_fuzzy_match_tolerates_a_small_spelling_difference(self):
        # כמוך -> כמוכה: partial_ratio stays above 85
        result = hebrew("ואהבת לרעך כמוכה", input_text="ואהבת לרעך כמוך", options=NO_GLOSSARY)
        assert result.value == 1.0

    def test_terms_any_spelling_case_and_italics(self):
        options = {"glossary": False, "terms": ["galouth", "Guehinom"]}
        result = hebrew("Il a choisi la *Galouth*.", input_text=transcript("la galouth", "le guehinom"), options=options)
        assert result.details["terms"] == 2
        assert result.details["terms_found"] == 1
        assert result.details["missing_terms"] == ["Guehinom"]
        assert result.value == pytest.approx(0.5)

    def test_terms_ignore_hyphens_and_apostrophes(self):
        options = {"glossary": False, "terms": ["HaMiqdash", "'Hama"]}
        result = hebrew("le Beit ha-Miqdash, Rav Hama", input_text="Beit HaMiqdash, Rav 'Hama", options=options)
        assert result.value == 1.0

    def test_terms_absent_from_input_are_not_expected(self):
        options = {"glossary": False, "terms": ["galouth", "teshouvah"]}
        result = hebrew("la galouth", input_text="la galouth", options=options)
        assert result.details["terms"] == 1
        assert result.value == 1.0

    def test_multi_word_term(self):
        options = {"glossary": False, "terms": ["HaQadosh Baroukh Hou"]}
        assert hebrew("HaQadosh Baroukh Hou a dit", input_text="haqadosh baroukh hou", options=options).value == 1.0
        assert hebrew("HaQadosh a dit", input_text="haqadosh baroukh hou", options=options).value == 0.0

    def test_nothing_to_preserve_is_undefined(self):
        assert hebrew("texte", input_text="texte en français", options=NO_GLOSSARY).value is None
