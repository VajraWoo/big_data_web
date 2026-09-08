"""Sentence and review-chunk preparation for the approved NLP scope."""

from __future__ import annotations

import re
from dataclasses import dataclass


_WHITESPACE = re.compile(r"\s+")
_NON_SPACE = re.compile(r"\S+")


@dataclass(frozen=True)
class Sentence:
    index: int
    text: str
    start: int
    end: int


def split_sentences(text: str) -> list[Sentence]:
    """Split English review text without losing or rewriting any non-space text."""
    sentences: list[Sentence] = []
    cursor = 0
    for boundary in _WHITESPACE.finditer(text):
        prefix = text[cursor : boundary.start()].rstrip("\"')]} ")
        if not prefix or prefix[-1] not in ".!?":
            continue
        if boundary.end() >= len(text) or text[boundary.end()] not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789\"'([":
            continue
        raw_end = boundary.start()
        start, end = _trim_span(text, cursor, raw_end)
        if start < end:
            sentences.append(Sentence(len(sentences), text[start:end], start, end))
        cursor = boundary.end()
    start, end = _trim_span(text, cursor, len(text))
    if start < end:
        sentences.append(Sentence(len(sentences), text[start:end], start, end))
    return sentences


def chunk_sentences(sentences: list[Sentence], max_words: int) -> list[dict[str, object]]:
    """Pack whole sentences into chunks; an oversized sentence is preserved and flagged."""
    if max_words < 1:
        raise ValueError("max_words must be positive")
    chunks: list[dict[str, object]] = []
    current: list[Sentence] = []
    current_words = 0

    def flush() -> None:
        nonlocal current, current_words
        if not current:
            return
        text = " ".join(sentence.text for sentence in current)
        chunks.append(
            {
                "chunk_index": len(chunks),
                "sentence_start_index": current[0].index,
                "sentence_end_index": current[-1].index,
                "char_start": current[0].start,
                "char_end": current[-1].end,
                "text": text,
                "word_count": current_words,
                "oversize_sentence": len(current) == 1 and current_words > max_words,
            }
        )
        current = []
        current_words = 0

    for sentence in sentences:
        word_count = len(_NON_SPACE.findall(sentence.text))
        if current and current_words + word_count > max_words:
            flush()
        current.append(sentence)
        current_words += word_count
        if word_count > max_words:
            flush()
    flush()
    return chunks


def _trim_span(text: str, start: int, end: int) -> tuple[int, int]:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end
