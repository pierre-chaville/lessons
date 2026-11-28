"""Every metric documents its report columns (review app dashboard: tooltip and definition modal)."""

import pytest

from bench.metrics import IMPLEMENTED, get_metric_module
from bench.review_app.data import metric_doc


@pytest.mark.parametrize("name", IMPLEMENTED)
def test_value_and_details_are_documented(name):
    module = get_metric_module(name)
    value = metric_doc(module, name)
    assert value["summary"] and value["unit"] and value["doc"], name
    for key in getattr(module, "REPORT_DETAILS", {}):
        detail = metric_doc(module, key)
        assert detail["summary"] and detail["unit"], f"{name} › {key}: add it to DETAIL_DOCS with ' Unit: ...'"
