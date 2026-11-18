import pytest
from bench.metrics.text import fold

class TestFold:

    def test_fold_hebrew(self):
        assert fold("Sinaï") == "sinai"
        assert fold("'Omer") == "omer"
        assert fold("ha-Lou'hoth") == "haluhot"
        assert fold("Assereth") == "aseret"
        assert fold("Moshéh") == "moche"
        assert fold("Marah") == "mara"
        assert fold("Parashah") == "paracha"
        assert fold("ma'hloqeth") == "mahloket"
        assert fold("galouth") == "galut"
        assert fold("Neqevah") == "nekeva"
        assert fold("Neqevah") == "nekeva"
        assert fold("Rabbeinou") == "rabenu"


    def test_fold_french(self):
        assert fold("veau") == "veau"
        assert fold("accepté") == "acepte"
