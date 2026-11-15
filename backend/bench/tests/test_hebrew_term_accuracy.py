"""hebrew_term_accuracy: term detection with the French dictionary, accuracy on folded words."""

import pytest

from bench.metrics import get_metric
from bench.metrics.hebrew_term_accuracy import is_hebrew_term

accuracy = get_metric("hebrew_term_accuracy")


class TestDetection:
    @pytest.mark.parametrize("word", ["mitsvoth", "pessa'h", "ha-miqdash", "ou-neqevah", "d'emounah",
                                      "qu'avraham", "'hazal", "torah", "שבת"])
    def test_hebrew(self, word):
        assert is_hebrew_term(word)

    @pytest.mark.parametrize("word", ["maison", "c'est", "qu'il", "l'homme", "moment-là", "aujourd'hui",
                                      "c'est-à-dire", "etc", "ii", "a", "1"])
    def test_french_or_ignored(self, word):
        assert not is_hebrew_term(word)

    def test_exclude(self):
        assert is_hebrew_term("fructifiez")
        assert not is_hebrew_term("fructifiez", exclude=frozenset({"fructifiez"}))


class TestAccuracy:
    REF = "la Parashah parle des mitsvoth et de Pessa'h"  # 3 terms

    def test_all_right(self):
        r = accuracy(self.REF, reference=self.REF)
        assert r.value == 1
        assert (r.details["terms"], r.details["right"]) == (3, 3)

    def test_transliteration_variants_are_right(self):
        assert accuracy("la parasha parle des mitsvot et de Pessah", reference=self.REF).value == 1

    def test_french_errors_are_not_counted(self):
        assert accuracy("le Parashah parlait de mitsvoth et de Pessa'h", reference=self.REF).value == 1

    def test_wrong_and_missing_terms(self):
        r = accuracy("la parasa parle des et de Pessa'h", reference=self.REF)
        assert r.value == pytest.approx(1 / 3)
        assert r.details["errors"] == 2
        assert set(r.details["top_errors"]) == {"parashah -> parasa", "mitsvoth -> ∅"}

    def test_no_term_is_undefined(self):
        assert accuracy("le chat", reference="le chat est noir").value is None

    def test_exclude_option(self):
        r = accuracy("la Parashah", reference="la Parashah", options={"exclude": ["Parashah"]})
        assert r.value is None
