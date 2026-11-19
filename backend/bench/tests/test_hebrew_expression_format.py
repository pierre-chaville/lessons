from bench.metrics import get_metric, get_metric_module
from bench.metrics.hebrew_expression_format import is_french, translit_key

metric = get_metric("hebrew_expression_format")

TEXT = """Le Rav cite וְאָהַבְתָּ לְרֵעֲךָ כָּמוֹךָ (*Ve'ahavta lere'akha kamokha*, "tu aimeras ton prochain comme toi-même").
Plus loin, *ve'ahavta lere'akha kamokha* revient, et il parle de בֵּית הַמִּקְדָּשׁ (*Beith ha-Miqdash*).
Le *Beith ha-Miqdash* sera reconstruit. On évoque aussi *Kiboud Av va-Em* et le Rav Grosstein.
Le verset dit « לֹא טוֹב הֱיוֹת הָאָדָם לְבַדּוֹ » (*Lo tov heyoth ha-Adam levado*), « Il n'est pas bien que l'homme soit seul ».
Puis ha-Qadosh baroukh Hou parle, et Rabbi Yehoshoua ben Levi enseigne. Enfin שְׁמַע יִשְׂרָאֵל sans rien.
"""


def by_expression(details):
    return {i["expression"]: i for i in details["items"]}


def test_detects_full_forms_and_problems():
    result = metric(TEXT, input_text="", options={})
    items = by_expression(result.details)
    assert items["Ve'ahavta lere'akha kamokha"]["compliant"]
    assert items["Ve'ahavta lere'akha kamokha"]["occurrences"] == 2
    assert items["Ve'ahavta lere'akha kamokha"]["first_occurrence"]
    assert items["Beith ha-Miqdash"]["problem"] == "no translation"
    assert items["Kiboud Av va-Em"]["problem"] == "no Hebrew"
    assert items["Lo tov heyoth ha-Adam levado"]["compliant"]  # translation just after the parenthesis
    assert items["ha-Qadosh baroukh Hou"]["problem"] == "no Hebrew"  # non-italic run
    assert items["שְׁמַע יִשְׂרָאֵל"]["problem"] == "no transliteration"
    assert not any("Grosstein" in e or "Levi" in e for e in items)  # names
    assert result.details["expressions"] == 6
    assert result.value == 2 / 6
    assert result.details["translation_after"] == 1
    span = items["Beith ha-Miqdash"]["spans"][0]
    assert TEXT[span["start"]:span["end"]].startswith("בֵּית")


def test_a_following_hebrew_quote_is_not_a_translation():
    text = ("La parole de הַקָּדוֹשׁ בָּרוּךְ הוּא (*ha-Qadosh baroukh Hou*) : « לֹא טוֹב הֱיוֹת הָאָדָם לְבַדּוֹ » "
            "(*Lo tov heyoth ha-Adam levado*), « Il n'est pas bien que l'homme soit seul ».")
    items = by_expression(metric(text, input_text="", options={}).details)
    assert items["ha-Qadosh baroukh Hou"]["problem"] == "no translation"
    assert items["Lo tov heyoth ha-Adam levado"]["compliant"]


def test_strict_requires_translation_inside_parentheses():
    result = metric(TEXT, input_text="", options={"strict": True})
    assert by_expression(result.details)["Lo tov heyoth ha-Adam levado"]["problem"] == "no translation"


def test_part_of_a_full_verse_and_hebrew_repetition_comply():
    text = ("« זָכָר וּנְקֵבָה בָּרָא אֹתָם » (*zakhar ou-Neqevah bara otam*, « mâle et femelle Il les créa »). "
            "Ensuite *zakhar ou-Neqevah* revient, et זָכָר וּנְקֵבָה aussi.")
    result = metric(text, input_text="", options={})
    assert result.value == 1.0
    assert result.details["expressions"] == 2


def test_require_first_and_ignore():
    text = "D'abord *Matan Torah* seul, puis מַתַּן תּוֹרָה (*Matan Torah*, « le don de la Torah »)."
    assert metric(text, input_text="", options={}).value == 1.0
    first = metric(text, input_text="", options={"require_first": True})
    assert first.value == 0.0 and first.details["first_occurrence_rate"] == 0.0
    assert metric(text, input_text="", options={"ignore": ["matan torah"]}).value is None


def test_hyphen_in_transliteration_is_not_a_translation_separator():
    text = "Il cite הַקָּדוֹשׁ בָּרוּךְ הוּא (*ha-Qadosh Baroukh Hou*) souvent."
    items = by_expression(metric(text, input_text="", options={}).details)
    assert items["ha-Qadosh Baroukh Hou"]["problem"] == "no translation"


def test_french_and_keys():
    assert is_french("peut-être") and is_french("l'homme") and is_french("aujourd'hui")
    assert not is_french("ha-Miqdash") and not is_french("baroukh")
    assert translit_key("ha-Qadosh Baroukh Hou") == translit_key("HaQadosh baroukh hou")
    assert metric("Un texte entièrement français.", input_text="", options={}).value is None
    check = get_metric_module("hebrew_expression_format").check_options
    assert check({"min_words": 1}) and check({"ignore": "x"}) and check({"strict": "yes"})
    assert not check({"min_words": 3, "ignore": ["Avraham Avinou"], "require_first": True})
