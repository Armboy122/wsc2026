"""Tokenizer tests (PyThaiNLP newmm, offline)."""

from __future__ import annotations

from app.knowledge.index import tokenize


def test_thai_text_is_segmented_into_words() -> None:
    assert tokenize("ค่าไฟฟ้าค้างชำระ") == ["ค่าไฟฟ้า", "ค้างชำระ"]
    assert "2" in tokenize("ค้างชำระ 2 เดือน")


def test_lowercases_latin_text() -> None:
    assert tokenize("PEA eBill") == ["pea", "ebill"]
    assert tokenize("ค่าไฟฟ้า") == ["ค่าไฟฟ้า"]


def test_drops_whitespace_and_punctuation_tokens() -> None:
    tokens = tokenize("ค่าไฟฟ้า, (บาท) ... 100")
    assert "," not in tokens
    assert "(" not in tokens
    assert tokens == ["ค่าไฟฟ้า", "บาท", "100"]


def test_empty_input_is_empty() -> None:
    assert tokenize("") == []
    assert tokenize("   \n\t ") == []
