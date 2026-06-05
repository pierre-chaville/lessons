from types import SimpleNamespace

import pytest

from services.edition import (
    MAX_EDITED_PARAGRAPH_CHARS,
    edit_segment_group,
    _split_oversized_markdown_paragraphs,
)


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
    assert "- au troisième jour" in llm.prompt
    assert "- nous continuons" in llm.prompt
    assert "Return only the edited text." in llm.prompt
    assert "Do not include JSON, metadata, timestamps" in llm.prompt


def test_split_oversized_markdown_paragraphs_on_sentence_boundaries():
    long_paragraph = " ".join(
        f"Phrase {index} avec du contenu pour dépasser la limite."
        for index in range(80)
    )

    result = _split_oversized_markdown_paragraphs(long_paragraph)
    paragraphs = result.split("\n\n")

    assert len(paragraphs) > 1
    assert all(len(paragraph) <= MAX_EDITED_PARAGRAPH_CHARS for paragraph in paragraphs)
    assert all(paragraph.endswith(".") for paragraph in paragraphs)
