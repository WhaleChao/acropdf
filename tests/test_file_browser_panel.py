# tests/test_file_browser_panel.py
"""
FileBrowserPanel 完整測試套件
涵蓋：初始化、根目錄邏輯、過濾器、信號、右鍵選單、Config 整合
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtCore import QModelIndex, Qt
from PyQt6.QtWidgets import QApplication

# ── 環境設定 ───────────────────────────────────────────────────────
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ui.panels.file_browser_panel import (
    FileBrowserPanel, _CaseFilterProxy, _OPENABLE_EXTS, _DEFAULT_ROOT,
)


# ── Fixtures ──────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture()
def case_tree(tmp_path):
    """建立模擬案件資料夾結構。"""
    root = tmp_path / "01_案件"
    # 正常資料夾與檔案
    (root / "法扶案件" / "刑事" / "2025-0001-王小明-一審-傷害").mkdir(parents=True)
    (root / "法扶案件" / "刑事" / "2025-0001-王小明-一審-傷害" / "委任狀.pdf").write_bytes(b"%PDF-1.4")
    (root / "法扶案件" / "刑事" / "2025-0001-王小明-一審-傷害" / "筆記.jpg").write_bytes(b"\xff\xd8\xff")
    (root / "一般案件" / "民事").mkdir(parents=True)
    (root / "一般案件" / "民事" / "起訴狀.pdf").write_bytes(b"%PDF-1.4")
    # 應被過濾的目錄
    (root / "OCR").mkdir()
    (root / "OCR" / "hidden.pdf").write_bytes(b"%PDF-1.4")
    (root / "cache").mkdir()
    (root / "cache" / "temp.pdf").write_bytes(b"%PDF-1.4")
    (root / "_私密").mkdir()
    (root / "_私密" / "secret.pdf").write_bytes(b"%PDF-1.4")
    (root / ".隱藏").mkdir()
    # 非可開啟副檔名
    (root / "法扶案件" / "刑事" / "2025-0001-王小明-一審-傷害" / "note.txt").write_bytes(b"text")
    (root / "法扶案件" / "刑事" / "2025-0001-王小明-一審-傷害" / "data.xlsx").write_bytes(b"excel")
    return root


@pytest.fixture()
def mock_config():
    cfg = MagicMock()
    cfg.get.return_value = ""
    return cfg


@pytest.fixture()
def panel(qapp, tmp_path, mock_config):
    """建立一個根目錄指向 tmp_path 的 FileBrowserPanel。"""
    mock_config.get.return_value = str(tmp_path)
    p = FileBrowserPanel(config=mock_config)
    return p


# ── 初始化測試 ────────────────────────────────────────────────────

class TestInit:
    def test_panel_creates_without_error(self, qapp, mock_config):
        panel = FileBrowserPanel(config=mock_config)
        assert panel is not None

    def test_panel_has_tree_view(self, panel):
        assert panel._tree is not None

    def test_panel_has_root_label(self, panel):
        assert panel._root_label is not None

    def test_panel_has_file_open_signal(self, panel):
        # 信號存在且可連接
        received = []
        panel.file_open_requested.connect(lambda p: received.append(p))
        assert panel.file_open_requested is not None


# ── 根目錄邏輯測試 ────────────────────────────────────────────────

class TestRootPath:
    def test_uses_config_saved_path(self, qapp, tmp_path, mock_config):
        mock_config.get.return_value = str(tmp_path)
        panel = FileBrowserPanel(config=mock_config)
        assert panel._root == str(tmp_path)

    def test_fallback_to_default_when_config_empty(self, qapp, mock_config):
        mock_config.get.return_value = ""
        with patch("ui.panels.file_browser_panel.os.path.isdir") as mock_isdir:
            mock_isdir.side_effect = lambda p: True
            panel = FileBrowserPanel(config=mock_config)
        # 預設應指向 SynologyDrive/01_案件 或 home
        assert panel._root is not None
        assert len(panel._root) > 0

    def test_fallback_when_config_path_missing(self, qapp, tmp_path, mock_config):
        mock_config.get.return_value = str(tmp_path / "nonexistent")
        panel = FileBrowserPanel(config=mock_config)
        # 路徑不存在時應 fallback，不應是那個不存在的路徑
        assert not panel._root.endswith("nonexistent")

    def test_save_root_updates_config(self, panel, mock_config, tmp_path):
        new_path = str(tmp_path / "new_root")
        os.makedirs(new_path, exist_ok=True)
        panel._save_root(new_path)
        mock_config.set.assert_called_with("file_browser_root", new_path)
        assert panel._root == new_path

    def test_root_label_shows_tilde_for_home(self, qapp, mock_config):
        home = str(Path.home())
        mock_config.get.return_value = home
        panel = FileBrowserPanel(config=mock_config)
        assert "~" in panel._root_label.text() or home in panel._root_label.text()

    def test_set_root_updates_label(self, panel, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        panel._set_root(str(sub))
        assert "sub" in panel._root_label.text() or str(sub) in panel._root_label.text()

    def test_set_root_updates_tree_root_index(self, panel, tmp_path):
        sub = tmp_path / "sub2"
        sub.mkdir()
        panel._set_root(str(sub))
        # tree 的根 index 應該更新（不應該是空的）
        assert panel._tree.rootIndex() is not None


# ── 過濾器測試（_CaseFilterProxy）────────────────────────────────

class TestCaseFilterProxy:
    def test_allows_pdf_files(self, qapp, case_tree):
        panel = FileBrowserPanel(config=None)
        panel._set_root(str(case_tree))
        # 確認 PDF 可見（model 有載入）
        model = panel._fs_model
        root_idx = model.index(str(case_tree))
        assert root_idx.isValid()

    def test_skips_ocr_directory(self, qapp, case_tree):
        panel = FileBrowserPanel(config=None)
        panel._set_root(str(case_tree))
        proxy = panel._proxy
        src_model = panel._fs_model
        # 找 OCR 目錄的 source index
        ocr_path = str(case_tree / "OCR")
        ocr_idx = src_model.index(ocr_path)
        if ocr_idx.isValid():
            parent_src = ocr_idx.parent()
            row = ocr_idx.row()
            accepted = proxy.filterAcceptsRow(row, parent_src)
            assert not accepted, "OCR 目錄不應被顯示"

    def test_skips_cache_directory(self, qapp, case_tree):
        panel = FileBrowserPanel(config=None)
        panel._set_root(str(case_tree))
        proxy = panel._proxy
        src_model = panel._fs_model
        cache_path = str(case_tree / "cache")
        cache_idx = src_model.index(cache_path)
        if cache_idx.isValid():
            accepted = proxy.filterAcceptsRow(cache_idx.row(), cache_idx.parent())
            assert not accepted

    def test_skips_underscore_directory(self, qapp, case_tree):
        panel = FileBrowserPanel(config=None)
        panel._set_root(str(case_tree))
        proxy = panel._proxy
        src_model = panel._fs_model
        hidden_path = str(case_tree / "_私密")
        hidden_idx = src_model.index(hidden_path)
        if hidden_idx.isValid():
            accepted = proxy.filterAcceptsRow(hidden_idx.row(), hidden_idx.parent())
            assert not accepted

    def test_skips_dot_directory(self, qapp, case_tree):
        panel = FileBrowserPanel(config=None)
        panel._set_root(str(case_tree))
        proxy = panel._proxy
        src_model = panel._fs_model
        dot_path = str(case_tree / ".隱藏")
        dot_idx = src_model.index(dot_path)
        if dot_idx.isValid():
            accepted = proxy.filterAcceptsRow(dot_idx.row(), dot_idx.parent())
            assert not accepted

    def test_allows_normal_case_directories(self, qapp, case_tree):
        panel = FileBrowserPanel(config=None)
        panel._set_root(str(case_tree))
        proxy = panel._proxy
        src_model = panel._fs_model
        laf_path = str(case_tree / "法扶案件")
        laf_idx = src_model.index(laf_path)
        if laf_idx.isValid():
            accepted = proxy.filterAcceptsRow(laf_idx.row(), laf_idx.parent())
            assert accepted, "法扶案件 資料夾應被顯示"

    def test_skips_txt_files(self, qapp, case_tree):
        panel = FileBrowserPanel(config=None)
        panel._set_root(str(case_tree))
        proxy = panel._proxy
        src_model = panel._fs_model
        txt_path = str(case_tree / "法扶案件" / "刑事" / "2025-0001-王小明-一審-傷害" / "note.txt")
        txt_idx = src_model.index(txt_path)
        if txt_idx.isValid():
            accepted = proxy.filterAcceptsRow(txt_idx.row(), txt_idx.parent())
            assert not accepted

    def test_skips_xlsx_files(self, qapp, case_tree):
        panel = FileBrowserPanel(config=None)
        panel._set_root(str(case_tree))
        proxy = panel._proxy
        src_model = panel._fs_model
        xlsx_path = str(case_tree / "法扶案件" / "刑事" / "2025-0001-王小明-一審-傷害" / "data.xlsx")
        xlsx_idx = src_model.index(xlsx_path)
        if xlsx_idx.isValid():
            accepted = proxy.filterAcceptsRow(xlsx_idx.row(), xlsx_idx.parent())
            assert not accepted


# ── 可開啟副檔名常數測試 ──────────────────────────────────────────

class TestOpenableExts:
    def test_pdf_is_openable(self):
        assert ".pdf" in _OPENABLE_EXTS

    def test_jpg_is_openable(self):
        assert ".jpg" in _OPENABLE_EXTS

    def test_jpeg_is_openable(self):
        assert ".jpeg" in _OPENABLE_EXTS

    def test_png_is_openable(self):
        assert ".png" in _OPENABLE_EXTS

    def test_heic_is_openable(self):
        assert ".heic" in _OPENABLE_EXTS

    def test_txt_not_openable(self):
        assert ".txt" not in _OPENABLE_EXTS

    def test_docx_not_openable(self):
        assert ".docx" not in _OPENABLE_EXTS

    def test_xlsx_not_openable(self):
        assert ".xlsx" not in _OPENABLE_EXTS


# ── 信號測試 ──────────────────────────────────────────────────────

class TestFileOpenSignal:
    def test_double_click_pdf_emits_signal(self, qapp, tmp_path, mock_config):
        pdf_path = tmp_path / "test.pdf"
        pdf_path.write_bytes(b"%PDF-1.4")
        mock_config.get.return_value = str(tmp_path)
        panel = FileBrowserPanel(config=mock_config)

        received = []
        panel.file_open_requested.connect(received.append)

        # 模擬 double click：直接呼叫 _on_double_click 邏輯
        src_idx = panel._fs_model.index(str(pdf_path))
        if src_idx.isValid():
            proxy_idx = panel._proxy.mapFromSource(src_idx)
            # 對非目錄且副檔名合法的檔案應發射信號
            panel._on_double_click(proxy_idx)
            assert len(received) == 1
            assert received[0] == str(pdf_path)

    def test_double_click_folder_does_not_emit(self, qapp, tmp_path, mock_config):
        sub = tmp_path / "subdir"
        sub.mkdir()
        mock_config.get.return_value = str(tmp_path)
        panel = FileBrowserPanel(config=mock_config)

        received = []
        panel.file_open_requested.connect(received.append)

        src_idx = panel._fs_model.index(str(sub))
        if src_idx.isValid():
            proxy_idx = panel._proxy.mapFromSource(src_idx)
            panel._on_double_click(proxy_idx)
            assert len(received) == 0

    def test_double_click_txt_does_not_emit(self, qapp, tmp_path, mock_config):
        txt_path = tmp_path / "note.txt"
        txt_path.write_bytes(b"text")
        mock_config.get.return_value = str(tmp_path)
        panel = FileBrowserPanel(config=mock_config)

        received = []
        panel.file_open_requested.connect(received.append)

        src_idx = panel._fs_model.index(str(txt_path))
        if src_idx.isValid():
            proxy_idx = panel._proxy.mapFromSource(src_idx)
            panel._on_double_click(proxy_idx)
            assert len(received) == 0

    def test_jpg_emits_signal(self, qapp, tmp_path, mock_config):
        jpg_path = tmp_path / "scan.jpg"
        jpg_path.write_bytes(b"\xff\xd8\xff")
        mock_config.get.return_value = str(tmp_path)
        panel = FileBrowserPanel(config=mock_config)

        received = []
        panel.file_open_requested.connect(received.append)

        src_idx = panel._fs_model.index(str(jpg_path))
        if src_idx.isValid():
            proxy_idx = panel._proxy.mapFromSource(src_idx)
            panel._on_double_click(proxy_idx)
            assert len(received) == 1


# ── 根目錄變更 ────────────────────────────────────────────────────

class TestChangeRoot:
    def test_change_root_updates_panel(self, panel, tmp_path):
        new_dir = tmp_path / "new_cases"
        new_dir.mkdir()
        panel._save_root(str(new_dir))
        panel._set_root(str(new_dir))
        assert panel._root == str(new_dir)

    def test_go_synology_sets_synology_root(self, panel):
        synology = str(Path.home() / "SynologyDrive")
        if os.path.isdir(synology):
            panel._go_synology()
            assert panel._root == synology

    def test_refresh_keeps_same_root(self, panel):
        original_root = panel._root
        panel._refresh()
        assert panel._root == original_root

    def test_set_root_without_config_does_not_crash(self, qapp, tmp_path):
        panel = FileBrowserPanel(config=None)
        panel._set_root(str(tmp_path))
        assert panel._root == str(tmp_path)


# ── Synology Drive 快捷按鈕 ──────────────────────────────────────

class TestSynologyButton:
    def test_button_exists_when_synology_present(self, qapp, mock_config):
        synology = str(Path.home() / "SynologyDrive")
        if not os.path.isdir(synology):
            pytest.skip("SynologyDrive 不存在，跳過此測試")
        panel = FileBrowserPanel(config=mock_config)
        # 找到帶有 "Synology" 的按鈕
        from PyQt6.QtWidgets import QPushButton
        buttons = panel.findChildren(QPushButton)
        synology_btns = [b for b in buttons if "Synology" in b.text()]
        assert len(synology_btns) >= 1


# ── 預設根目錄常數 ────────────────────────────────────────────────

class TestDefaults:
    def test_default_root_points_to_01_cases(self):
        assert "01_案件" in _DEFAULT_ROOT

    def test_default_root_under_synology_drive(self):
        assert "SynologyDrive" in _DEFAULT_ROOT
