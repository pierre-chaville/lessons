"""Correction metrics on small hand-made examples whose expected values are computed by hand."""

import pytest

from bench.metrics import get_metric
from bench.metrics.text import edits, tokenize, Edit

wer = get_metric("wer")
cer = get_metric("cer")
edit_pr = get_metric("edit_precision_recall")
overcorrection = get_metric("overcorrection_rate")


def transcript(*texts: str, shift: int = 0) -> str:
    """Segments of 2 s: `- [0s - 2s] a`, `- [2s - 4s] b`, ..."""
    return "".join(f"- [{2 * i + shift}s - {2 * i + 2 + shift}s] {t}\n" for i, t in enumerate(texts))


# --------------------------------------------------------------------------- #
# Normalization
# --------------------------------------------------------------------------- #


class TestTokenize:
    def test_case_punctuation_and_apostrophes(self):
        assert tokenize("Alors, le TEXTE… « on l’a fini » !") == ["alors", "le", "texte", "on", "l'a", "fini"]

    def test_hyphens_and_leading_apostrophe_are_kept_inside_words(self):
        assert tokenize("'Hazal dit : ha-Nahar - oui") == ["'hazal", "dit", "ha-nahar", "oui"]

    def test_hebrew_with_vowel_points_is_one_word(self):
        assert tokenize("le מִשְׁכָּן est") == ["le", "מִשְׁכָּן", "est"]

    def test_strict_keeps_case_and_punctuation(self):
        assert tokenize("Oui, HaShem.", strict=True) == ["Oui,", "HaShem."]


class TestEdits:
    def test_adjacent_changes_are_one_edit(self):
        # vaudor -> veau d'or: one substitution + one insertion, merged into one edit
        assert edits(["le", "vaudor", "et"], ["le", "veau", "d'or", "et"]) == [Edit(1, 2, ("veau", "d'or"))]

    def test_separate_changes_are_separate_edits(self):
        assert edits(["a", "b", "c", "d"], ["x", "b", "c"]) == [Edit(0, 1, ("x",)), Edit(3, 4, ())]

    def test_insertion_has_an_empty_span(self):
        assert edits(["a", "b"], ["a", "z", "b"]) == [Edit(1, 1, ("z",))]


# --------------------------------------------------------------------------- #
# WER
# --------------------------------------------------------------------------- #


class TestWer:
    REF = "le chat est noir"

    def test_identical(self):
        assert wer("le chat est noir", reference=self.REF).value == 0

    def test_substitution(self):
        r = wer("le chien est noir", reference=self.REF)
        assert r.value == pytest.approx(1 / 4)
        assert (r.details["substitutions"], r.details["deletions"], r.details["insertions"]) == (1, 0, 0)

    def test_deletion(self):
        r = wer("le chat noir", reference=self.REF)
        assert r.value == pytest.approx(1 / 4)
        assert r.details["deletions"] == 1

    def test_insertion(self):
        r = wer("le chat est très noir", reference=self.REF)
        assert r.value == pytest.approx(1 / 4)
        assert r.details["insertions"] == 1

    def test_substitution_and_insertion(self):
        # a b c d -> a x c d e: 1 substitution + 1 insertion = 2 errors / 4 words
        assert wer("a x c d e", reference="a b c d").value == pytest.approx(0.5)

    def test_can_exceed_one(self):
        # a -> b c d: 1 substitution + 2 insertions = 3 errors / 1 word
        assert wer("b c d", reference="a").value == pytest.approx(3.0)

    def test_case_and_punctuation_are_ignored(self):
        assert wer("le chat est noir", reference="Le chat, est noir.").value == 0

    def test_strict_counts_case_and_punctuation(self):
        # Le/le and chat,/chat differ: 2 errors / 4 words
        assert wer("le chat est noir", reference="Le chat, est noir", options={"strict": True}).value == 0.5

    def test_timestamps_and_speaker_tags_are_ignored(self):
        assert wer(transcript("[audience] le chat"), reference=transcript("le chat")).value == 0

    def test_empty_reference_is_undefined(self):
        assert wer("quelque chose", reference="").value is None

    def test_per_segment_counts_words_moved_across_segments(self):
        # Same words overall, but "b" moved from segment 1 to segment 2:
        # whole text: 0 error; per segment: deletion in segment 1 + insertion in segment 2 = 2 / 4
        r = wer(transcript("a", "b c d"), reference=transcript("a b", "c d"))
        assert r.value == 0
        assert r.details["segment_aligned"] is True
        assert r.details["per_segment_rate"] == pytest.approx(0.5)
        assert [s["index"] for s in r.details["worst_segments"]] == [0, 1]

    def test_per_segment_is_skipped_when_timestamps_differ(self):
        r = wer(transcript("a b", "c d", shift=1), reference=transcript("a b", "c d"))
        assert r.value == 0
        assert r.details["segment_aligned"] is False
        assert r.details["per_segment_rate"] is None


# --------------------------------------------------------------------------- #
# CER
# --------------------------------------------------------------------------- #


class TestCer:
    def test_identical(self):
        assert cer("le chat", reference="le chat").value == 0

    def test_one_extra_character(self):
        # chat -> chats: 1 insertion / 4 characters
        assert cer("chats", reference="chat").value == pytest.approx(1 / 4)

    def test_merged_words_cost_one_character(self):
        # "ab cd" -> "abcd": the space is deleted, 1 / 5 characters ...
        assert cer("abcd", reference="ab cd").value == pytest.approx(1 / 5)
        # ... whereas WER counts 1 substitution + 1 deletion = 2 / 2 words
        assert wer("abcd", reference="ab cd").value == pytest.approx(1.0)

    def test_normalization_applies(self):
        assert cer("l'a fini", reference="L’a fini !").value == 0


# --------------------------------------------------------------------------- #
# Edit precision / recall
# --------------------------------------------------------------------------- #


class TestEditPrecisionRecall:
    INITIAL = "il a fait le vaudor hier"
    GOLD = "il a fait le veau d'or hier"  # 1 expected edit: vaudor -> veau d'or

    def test_perfect_correction(self):
        r = edit_pr(self.GOLD, input_text=self.INITIAL, reference=self.GOLD)
        assert r.value == 1
        assert (r.details["precision"], r.details["recall"]) == (1, 1)

    def test_no_correction(self):
        r = edit_pr(self.INITIAL, input_text=self.INITIAL, reference=self.GOLD)
        assert r.details["precision"] is None  # the model made no edit
        assert r.details["recall"] == 0
        assert r.value == 0
        assert r.details["missed"] == ["vaudor -> veau d'or"]

    def test_wrong_correction_of_the_right_word(self):
        r = edit_pr("il a fait le veau dort hier", input_text=self.INITIAL, reference=self.GOLD)
        assert (r.details["precision"], r.details["recall"], r.value) == (0, 0, 0)
        assert r.details["wrong"] == ["vaudor -> veau dort"]

    INITIAL_2 = "rachi a dit que le michkan est"
    GOLD_2 = "Rashi a dit que le Mishkan est"  # 2 expected edits (case is ignored)

    def test_one_right_one_wrong(self):
        # model edits: rachi -> rashi (right), le -> la (wrong); michkan not fixed
        r = edit_pr("rashi a dit que la michkan est", input_text=self.INITIAL_2, reference=self.GOLD_2)
        assert r.details["model_edits"] == 2
        assert r.details["expected_edits"] == 2
        assert r.details["correct_edits"] == 1
        assert r.details["precision"] == pytest.approx(1 / 2)
        assert r.details["recall"] == pytest.approx(1 / 2)
        assert r.value == pytest.approx(1 / 2)  # 2 * 1 / (2 + 2)

    def test_all_expected_edits_plus_an_extra_one(self):
        # 3 model edits (rashi, mishkan, + inserted "là"), 2 of them correct
        r = edit_pr("rashi a dit que le mishkan est là", input_text=self.INITIAL_2, reference=self.GOLD_2)
        assert r.details["precision"] == pytest.approx(2 / 3)
        assert r.details["recall"] == 1
        assert r.value == pytest.approx(0.8)  # 2 * 2 / (3 + 2)
        assert r.details["wrong"] == ["∅ -> là"]

    def test_case_only_edits_need_strict(self):
        initial, gold = "hashem est un", "HaShem est un"
        r = edit_pr(initial, input_text=initial, reference=gold)
        assert r.value is None  # nothing expected, nothing done
        r = edit_pr(initial, input_text=initial, reference=gold, options={"strict": True})
        assert r.details["expected_edits"] == 1
        assert r.value == 0

    def test_edit_in_the_wrong_segment_is_not_correct(self):
        # the gold fixes segment 2, the model fixes the same words in segment 1
        initial = transcript("le vaudor", "le vaudor")
        gold = transcript("le vaudor", "le veau d'or")
        output = transcript("le veau d'or", "le vaudor")
        r = edit_pr(output, input_text=initial, reference=gold)
        assert r.details["segment_aligned"] is True
        assert (r.details["precision"], r.details["recall"]) == (0, 0)


# --------------------------------------------------------------------------- #
# Overcorrection rate
# --------------------------------------------------------------------------- #


class TestOvercorrectionRate:
    INITIAL = "rachi a dit que le michkan est"
    GOLD = "rashi a dit que le mishkan est"  # correct words: a, dit, que, le, est (5)

    def test_perfect_correction(self):
        r = overcorrection(self.GOLD, input_text=self.INITIAL, reference=self.GOLD)
        assert r.value == 0
        assert r.details["correct_words"] == 5

    def test_one_correct_word_modified(self):
        # le -> la modifies 1 of the 5 correct words (rachi -> rashi is an expected edit)
        r = overcorrection("rashi a dit que la michkan est", input_text=self.INITIAL, reference=self.GOLD)
        assert r.value == pytest.approx(1 / 5)
        assert r.details["examples"] == ["le"]

    def test_full_rewrite(self):
        r = overcorrection("x y z", input_text=self.INITIAL, reference=self.GOLD)
        assert r.value == 1

    def test_insertion_does_not_modify_a_correct_word(self):
        r = overcorrection("rashi a vraiment dit que le mishkan est", input_text=self.INITIAL, reference=self.GOLD)
        assert r.value == 0

    def test_no_correct_word_is_undefined(self):
        assert overcorrection("b", input_text="a", reference="c").value is None


def test_unknown_metric():
    with pytest.raises(KeyError):
        get_metric("bleu")
