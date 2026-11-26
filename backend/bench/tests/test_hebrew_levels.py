"""Correction in Hebrew script: keys, level A categories (hebrew_identification, hebrew_script_rate,
vocalized_rate), level B (wer_french) and level C (wer_rendered)."""

import pytest

from bench.metrics import get_metric
from bench.metrics import hebrew
from bench.metrics.hebrew import Glossary, GlossaryTerm, analyze, he_key, he_skeleton, tokens
from bench.metrics.text import fold
from hebrew_text import hebrew_consonants, normalize_hebrew

identification = get_metric("hebrew_identification")
script_rate = get_metric("hebrew_script_rate")
vocalized_rate = get_metric("vocalized_rate")
wer_french = get_metric("wer_french")
wer_rendered = get_metric("wer_rendered")


def transcript(*texts: str) -> str:
    return "".join(f"- [{2 * i}s - {2 * i + 2}s] {t}\n" for i, t in enumerate(texts))


def entry(id_: int, hebrew_: str, translit=None, aliases=(), type_="term", validated=False) -> GlossaryTerm:
    return GlossaryTerm(id_, hebrew_, translit, tuple(aliases), type_, validated,
                        normalize_hebrew(hebrew_), hebrew_consonants(hebrew_))


@pytest.fixture(autouse=True)
def glossary(monkeypatch):
    """App glossary replaced by a test one (empty by default): set_glossary(*entries)."""
    def set_glossary(*entries):
        monkeypatch.setattr(hebrew, "_app_glossary_index", lambda: Glossary(tuple(entries)))
        analyze.cache_clear()

    set_glossary()
    yield set_glossary
    analyze.cache_clear()


def categories(gold: str, output: str, input_text: str = "") -> list[tuple[str, str, str]]:
    result = analyze(transcript(output), transcript(gold), transcript(input_text) if input_text else "")
    return [(t.gold, t.output, t.category) for t in result.terms]


class TestKeys:
    def test_he_key_keeps_plene_spelling(self):
        assert he_key("מִצְוֹת") == "מצות" and he_key("מִצְווֹת") == "מצוות"

    def test_skeleton_ignores_inner_vowel_letters(self):
        assert he_skeleton("מִצְוֹת") == he_skeleton("מִצְווֹת") == "מצת"
        assert he_skeleton("הַלֻּחֹת") == he_skeleton("הַלּוּחוֹת") == "הלחת"

    def test_geresh_and_gershayim(self):
        assert he_key("ה'") == he_key("ה׳") and he_key('חז"ל') == he_key("חֲזַ״ל")

    def test_tokens_split_mixed_words(self):
        words = tokens('la guerre d\'הַשֵּׁם, <d i="Shurim">שִׁיעוּר</d> חֲזַ״ל')
        assert [(t.text, t.hebrew) for t in words] == [
            ("la", False), ("guerre", False), ("d", False), ("הַשֵּׁם", True), ("שִׁיעוּר", True), ("חֲזַ״ל", True)]

    def test_fold_scholarly_transliteration(self):
        assert fold("Pessaḥ") == fold("Pessah") and fold("ʿOmer") == fold("Omer") == fold("‘Omer")
        assert fold("Šabbat") == fold("Shabbat")


class TestCategories:
    def test_exact_ignores_vowel_points(self):
        assert categories("le פֶּסַח", "le פָּסַח") == [("פֶּסַח", "פָּסַח", "exact")]

    def test_spelling_variant(self):
        assert categories("des מִצְוֹת", "des מִצְווֹת")[0][2] == "spelling_variant"

    def test_abbreviation_and_divine_names_are_spelling_variants(self):
        assert categories("que הַשֵּׁם est", "que ה' est")[0][2] == "spelling_variant"
        assert categories("אֱלֹהִים a créé", "אֱלֹקִים a créé")[0][2] == "spelling_variant"

    def test_unvocalized(self):
        assert categories("des שִׁיעוּרִים", "des שיעורים")[0][2] == "unvocalized"

    def test_prefix_variant(self):
        assert categories("la période du עֹמֶר", "la période du הָעוֹמֶר")[0][2] == "prefix_variant"

    def test_latin_correct(self):
        assert categories("de פֶּסַח", "de Pessaḥ", "de Pesach") == [("פֶּסַח", "Pessaḥ", "latin_correct")]

    def test_latin_correct_through_the_glossary(self, glossary):
        assert categories("par פַּרְעֹה", "par Pharaon")[0][2] == "missing"  # not the same consonants
        glossary(entry(1, "פַּרְעֹה", "Par'oh", ["Pharaon"]))
        assert categories("par פַּרְעֹה", "par Pharaon")[0][2] == "latin_correct"

    def test_latin_left_from_the_input(self):
        assert categories("contre עֲמָלֵק", "contre Amalek", "contre Amalek")[0][2] == "latin_uncorrected"
        assert categories("reçu à מָרָה,", "reçu Amara,", "reçu Amara,") == [("מָרָה", "Amara", "latin_uncorrected")]

    def test_french_word_of_the_input_is_not_a_counterpart(self):
        assert categories("il יִהְיֶה un", "il est un", "il est un")[0][2] == "missing"

    def test_wrong_word(self):
        assert categories("le פֶּסַח", "le שָׁבוּעוֹת")[0][2] == "wrong_word"

    def test_missing(self):
        assert categories("le פֶּסַח arrive", "le arrive")[0][2] == "missing"

    def test_glossary_entries_decide_before_the_skeleton(self, glossary):
        glossary(entry(1, "מִצְוֹת"), entry(2, "מִצְווֹת"))
        assert categories("des מִצְוֹת", "des מִצְווֹת")[0][2] == "wrong_word"


class TestRates:
    GOLD = transcript("le פֶּסַח et les מִצְווֹת de שָׁבוּעוֹת")

    def test_identification(self):
        out = transcript("le Pessaḥ et les מצוות de שבועות")  # latin_correct, unvocalized x2
        r = identification(out, reference=self.GOLD)
        assert r.value == pytest.approx(1 / 3)
        assert (r.details["latin_correct"], r.details["unvocalized"]) == (1, 2)

    def test_script_and_vocalized_rates(self):
        out = transcript("le Pessaḥ et les מצוות de שָׁבוּעוֹת")
        assert script_rate(out, reference=self.GOLD).value == pytest.approx(2 / 3)
        assert vocalized_rate(out, reference=self.GOLD).value == pytest.approx(1 / 2)

    def test_no_hebrew_in_the_gold(self):
        assert identification(transcript("bonjour"), reference=transcript("bonjour")).value is None


class TestWerFrench:
    def test_only_french_errors_count(self):
        gold = transcript("on les avait déjà reçu à מָרָה")
        out = transcript("on les avait obtenu à Mara")  # Mara: Latin stand-in, not a French error
        r = wer_french(out, reference=gold)
        assert r.value == pytest.approx(2 / 7)
        assert r.details["top_errors"] == ["déjà reçu → obtenu"]

    def test_one_letter_differences_are_variants(self):
        gold, out = transcript("on les avait reçues ici"), transcript("on les avait reçus là")
        r = wer_french(out, reference=gold)
        assert r.value == pytest.approx(1 / 5)  # ici → là only
        assert (r.details["french_variants"], r.details["top_errors"]) == (1, ["ici → là"])
        strict = wer_french(out, reference=gold, options={"one_letter_variants": False})
        assert strict.value == pytest.approx(2 / 5) and strict.details["top_errors"] == ["reçues ici → reçus là"]

    def test_case_and_numbers(self):
        gold = transcript("La vie du deux")
        r = wer_french(transcript("la vie du 2"), reference=gold)  # lowercase by default
        assert r.value == 0 and r.details["minor"] == 2  # La / la, deux / 2
        strict = {"case_sensitive": True, "one_letter_variants": False}
        assert wer_french(transcript("la vie du 2"), reference=gold, options=strict).value == pytest.approx(1 / 4)

    def test_hebrew_passage_is_one_token(self):
        gold = transcript("c'est « שְׁמַע יִשְׂרָאֵל הַשֵּׁם אֶחָד » ici")
        assert wer_french(transcript("c'est « שְׁמַע יִשְׂרָאֵל ה' אֱלֹקֵינוּ » ici"), reference=gold).value == 0

    def test_large_edits(self):
        gold = transcript("qui se déroule sur la terre")
        r = wer_french(transcript("qui rampe dans les grands champs"), reference=gold)
        assert r.details["large_edits"] == 1
        assert r.details["large_edit_examples"] == ["[0s] se déroule sur la terre → rampe dans les grands champs"]


class TestWerRendered:
    def test_glossary_transliteration_on_both_sides(self, glossary):
        glossary(entry(1, "פֶּסַח", "Pessa'h"))
        gold = transcript("le פֶּסַח arrive")
        assert wer_rendered(transcript("le Pessah arrive"), reference=gold).value == 0
        r = wer_rendered(transcript("le פָּסַח arrive"), reference=gold)
        assert r.value == 0 and r.details["glossary_matches_gold"] == 1

    def test_latin_word_with_the_same_consonants_without_glossary(self):
        assert wer_rendered(transcript("le Pessaḥ arrive"), reference=transcript("le פֶּסַח arrive")).value == 0

    def test_errors(self):
        assert wer_rendered(transcript("le שָׁבוּעוֹת part"), reference=transcript("le פֶּסַח arrive")).value == pytest.approx(2 / 3)

    def test_quotations_stay_in_hebrew(self, glossary):
        glossary(entry(1, "כִּי אֲנִי ה׳", "ki ani HaShem", type_="quotation"))
        gold, out = transcript("car כִּי אֲנִי ה׳"), transcript("car ki ani Hachem")
        assert wer_rendered(out, reference=gold).value > 0
        assert wer_rendered(out, reference=gold, options={"quotations_in_hebrew": False}).value == 0

    def test_check_options(self):
        module = __import__("bench.metrics.wer_rendered", fromlist=["check_options"])
        assert module.check_options({"primary": "latin"})
        assert not module.check_options({"primary": "unvocalized", "glossary": False})
