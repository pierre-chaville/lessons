from types import SimpleNamespace

import pytest

from services.correction import correct_segment_group


class _CapturingLLM:
    def __init__(self, output: str):
        self.output = output
        self.prompt = None

    async def ainvoke(self, prompt: str):
        self.prompt = prompt
        return SimpleNamespace(content=self.output)


@pytest.mark.anyio
async def test_correct_segment_group_uses_compact_output_format():
    llm = _CapturingLLM("2|Bonjour, ceci est corrigé.")

    result = await correct_segment_group(
        [
            (10, {"start": 0.0, "end": 1.0, "text": "Texte inchangé."}),
            (11, {"start": 1.0, "end": 2.0, "text": "Bonjur ceci est corigé."}),
        ],
        llm,
        "Correct only real transcript errors.",
    )

    assert result == [
        (10, "Texte inchangé."),
        (11, "Bonjour, ceci est corrigé."),
    ]
    assert llm.prompt is not None
    assert "one changed segment per line as <id>|<corrected text>" in llm.prompt
    assert "If no segment needs correction, return exactly NONE" in llm.prompt
    assert "Do not return JSON" in llm.prompt


@pytest.mark.anyio
async def test_correct_segment_group_keeps_originals_when_response_is_none():
    llm = _CapturingLLM("NONE")

    result = await correct_segment_group(
        [
            (20, {"start": 0.0, "end": 1.0, "text": "Déjà correct."}),
            (21, {"start": 1.0, "end": 2.0, "text": "Encore correct."}),
        ],
        llm,
        "Correct only real transcript errors.",
    )

    assert result == [
        (20, "Déjà correct."),
        (21, "Encore correct."),
    ]
