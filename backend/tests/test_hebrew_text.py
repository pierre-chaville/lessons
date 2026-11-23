"""Tests for Hebrew glossary search keys."""

import unicodedata

from hebrew_text import contains_hebrew_letter, hebrew_consonants, normalize_hebrew

TESHUVA = "תְּשׁוּבָה"


def test_normalize_keeps_niqqud_and_is_nfc() -> None:
    assert normalize_hebrew(TESHUVA) == unicodedata.normalize("NFC", TESHUVA)
    assert normalize_hebrew(f"  {TESHUVA}  ") == normalize_hebrew(TESHUVA)


def test_normalize_is_independent_of_mark_order() -> None:
    # Dagesh then shin dot vs shin dot then dagesh: same canonical form.
    assert normalize_hebrew("שּׁ") == normalize_hebrew("שּׁ")


def test_normalize_removes_cantillation_and_meteg() -> None:
    with_teamim = "בְּרֵאשִׁ֖ית"  # tipcha (U+0596)
    with_meteg = "הָֽאָרֶץ"  # meteg (U+05BD)
    assert normalize_hebrew(with_teamim) == normalize_hebrew("בְּרֵאשִׁית")
    assert normalize_hebrew(with_meteg) == normalize_hebrew("הָאָרֶץ")


def test_normalize_standardizes_quotes() -> None:
    assert normalize_hebrew('רמב"ם') == "רמב״ם"
    assert normalize_hebrew("רמב”ם") == "רמב״ם"
    assert normalize_hebrew("ר' עקיבא") == "ר׳ עקיבא"


def test_normalize_collapses_whitespace_keeps_maqaf() -> None:
    assert normalize_hebrew("יוֹם   כִּפּוּר") == normalize_hebrew("יוֹם כִּפּוּר")
    assert "־" in normalize_hebrew("בֵּית־הַמִּקְדָּשׁ")


def test_consonants_remove_all_niqqud() -> None:
    assert hebrew_consonants(TESHUVA) == "תשובה"
    assert hebrew_consonants("בְּרֵאשִׁ֖ית") == "בראשית"
    assert hebrew_consonants('רַמְבַּ"ם') == "רמב״ם"


def test_contains_hebrew_letter() -> None:
    assert contains_hebrew_letter(TESHUVA)
    assert not contains_hebrew_letter("techouva")
    assert not contains_hebrew_letter("ְִ")  # points only
