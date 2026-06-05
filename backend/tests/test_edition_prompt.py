from types import SimpleNamespace

import pytest

from services.edition import edit_segment_group


class _CapturingLLM:
    def __init__(self):
        self.prompt = None

    async def ainvoke(self, prompt: str):
        self.prompt = prompt
        return SimpleNamespace(content="Edited lesson text.")


@pytest.mark.anyio
async def test_edit_segment_group_sends_plain_text_without_timestamps():
    llm = _CapturingLLM()

    result = await edit_segment_group(
        [
            {"start": 142.7, "end": 144.0, "text": "au troisième jour"},
            {"start": 144.0, "end": 146.2, "text": "nous continuons"},
        ],
        llm,
        "Rewrite clearly.",
    )

    assert result == "Edited lesson text."
    assert llm.prompt is not None
    assert "au troisième jour" in llm.prompt
    assert "nous continuons" in llm.prompt
    assert "[142.7s - 144.0s]" not in llm.prompt
    assert "[144.0s - 146.2s]" not in llm.prompt
    assert "Return only the edited text." in llm.prompt
    assert "Do not include JSON, metadata, timestamps" in llm.prompt
