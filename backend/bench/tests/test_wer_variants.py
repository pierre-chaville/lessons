"""wer / wer_norm / wer_fold on hand-made examples: each level removes one kind of difference."""

import pytest

from bench.metrics import get_metric
from bench.metrics.text import fold_word, norm_word

wer = get_metric("wer")
wer_norm = get_metric("wer_norm")
wer_fold = get_metric("wer_fold")


def transcript(*texts: str) -> str:
    return "".join(f"- [{2 * i}s - {2 * i + 2}s] {t}\n" for i, t in enumerate(texts))


class TestWords:
    def test_norm_word(self):
        assert norm_word("sinaï") == "sinai"
        assert norm_word("ha-nahar") == "hanahar"
        assert norm_word("'hazal") == "hazal"
        assert norm_word("מִשְׁכָּן") == "משכן"

    def test_fold_word(self):
        assert fold_word("parashah") == fold_word("parasha")
        assert fold_word("passouq") == fold_word("pasuk")
        assert fold_word("shabbath") == fold_word("shabat")
        assert fold_word("tsitsith") == fold_word("tzitzit")

    def test_fold_keeps_different_words_apart(self):
        assert fold_word("galouth") != fold_word("guehinom")


class TestLevels:
    REF = "la Parashah du Sinaï et ha-Nahar"  # 6 words

    def test_identical_text_is_zero_everywhere(self):
        for metric in (wer, wer_norm, wer_fold):
            assert metric(self.REF, reference=self.REF).value == 0

    def test_accent_counts_only_in_wer(self):
        output = "la Parashah du Sinai et ha-Nahar"
        assert wer(output, reference=self.REF).value == pytest.approx(1 / 6)
        assert wer_norm(output, reference=self.REF).value == 0
        assert wer_fold(output, reference=self.REF).value == 0

    def test_hyphen_counts_only_in_wer(self):
        output = "la Parashah du Sinaï et HaNahar"
        assert wer(output, reference=self.REF).value == pytest.approx(1 / 6)
        assert wer_norm(output, reference=self.REF).value == 0

    def test_transliteration_counts_until_fold(self):
        output = "la parasha du Sinaï et ha-Nahar"
        assert wer(output, reference=self.REF).value == pytest.approx(1 / 6)
        assert wer_norm(output, reference=self.REF).value == pytest.approx(1 / 6)
        assert wer_fold(output, reference=self.REF).value == 0

    def test_real_error_counts_at_every_level(self):
        output = "la Parashah du Sinaï et le fleuve"  # ha-Nahar -> le fleuve: 1 sub + 1 ins
        for metric in (wer, wer_norm, wer_fold):
            assert metric(output, reference=self.REF).value == pytest.approx(2 / 6)

    def test_levels_never_increase(self):
        output = "la parasha du Sinai et HaNahar fin"
        values = [m(output, reference=self.REF).value for m in (wer, wer_norm, wer_fold)]
        assert values == sorted(values, reverse=True)
        assert values == [pytest.approx(4 / 6), pytest.approx(2 / 6), pytest.approx(1 / 6)]

    def test_segment_alignment_is_kept(self):
        r = wer_fold(transcript("la parasha", "du Sinai"), reference=transcript("la Parashah", "du Sinaï"))
        assert r.value == 0
        assert r.details["segment_aligned"] is True
        assert r.details["per_segment_rate"] == 0

    def test_strict_option_does_not_apply_to_variants(self):
        output = "la parashah du sinai et hanahar"
        assert wer_norm(output, reference=self.REF, options={"strict": True}).value == 0
