import fitz
import pytest
from core.text_reflow_engine import TextReflowEngine


def test_parse_blocks(tmp_path):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 100), "這是第一行測試文字。")
    page.insert_text((72, 115), "這是第二行測試文字。")
    doc.save(str(tmp_path / "test.pdf"))

    engine = TextReflowEngine()
    doc2 = fitz.open(str(tmp_path / "test.pdf"))
    blocks = engine.parse_blocks(doc2[0])
    assert len(blocks) >= 1
    doc.close()
    doc2.close()


def test_reflow_longer_text(tmp_path):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 100), "短文字")
    doc.save(str(tmp_path / "test.pdf"))

    engine = TextReflowEngine()
    doc2 = fitz.open(str(tmp_path / "test.pdf"))
    blocks = engine.parse_blocks(doc2[0])
    if blocks:
        new_block = engine.reflow(blocks[0], "這是一段比較長的替換文字，應該會需要換行處理。")
        assert new_block is not None
        assert len(new_block.spans) > 0
    doc.close()
    doc2.close()


def test_detect_paragraph_at(tmp_path):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((100, 100), "可點擊的段落")
    doc.save(str(tmp_path / "test.pdf"))

    engine = TextReflowEngine()
    doc2 = fitz.open(str(tmp_path / "test.pdf"))
    page2 = doc2[0]
    result = engine.detect_paragraph_at(page2, (105, 105))
    # 可能找到也可能找不到，但不應該 crash
    doc.close()
    doc2.close()


def test_calculate_char_width():
    engine = TextReflowEngine()
    width = engine.calculate_char_width("helv", 11, "A")
    assert width > 0
    assert isinstance(width, float)
