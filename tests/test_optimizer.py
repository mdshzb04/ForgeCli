"""Tests for the chunker and ranker."""

from __future__ import annotations

from forgecli.optimizer.chunker import Chunker
from forgecli.optimizer.ranker import Ranker


def test_chunker_splits_with_overlap() -> None:
    chunker = Chunker(size=10, overlap=3)
    text = "abcdefghijklmnopqrstuvwxyz"
    chunks = chunker.split(text, source_id="x")
    assert chunks
    assert chunks[0].start == 0
    assert chunks[0].end == 10
    assert chunks[1].start == 7  # 10 - 3 overlap
    assert chunks[0].source_id == "x"


def test_chunker_handles_empty_text() -> None:
    assert Chunker().split("") == []


def test_ranker_prefers_overlapping_chunk() -> None:
    ranker = Ranker()
    a = type("C", (), {"text": "the quick brown fox"})()
    b = type("C", (), {"text": "completely unrelated content"})()
    chunks = [
        type("Chunk", (), {"text": c.text, "index": i, "start": 0, "end": len(c.text), "source_id": None})()
        for i, c in enumerate([a, b])
    ]
    from forgecli.optimizer.chunker import Chunk

    typed = [
        Chunk(text=c.text, index=c.index, start=c.start, end=c.end, source_id=c.source_id)
        for c in chunks
    ]
    ranked = ranker.rank("quick fox", typed)
    assert ranked[0][0].text == "the quick brown fox"
    assert ranked[0][1] > 0
