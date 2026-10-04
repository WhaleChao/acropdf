"""Make the destination and transfer of document text explicit before AI calls."""
from urllib.parse import urlsplit
import ipaddress


def endpoint_is_local(endpoint):
    parsed = urlsplit(endpoint)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("請使用不含帳號密碼的 HTTP(S) API 網址。")
    host = parsed.hostname.lower()
    if host == "localhost":
        return True
    try:
        local = ipaddress.ip_address(host).is_loopback
    except ValueError:
        local = False
    if not local and parsed.scheme != "https":
        raise ValueError("遠端 AI 端點須使用 HTTPS，以保護傳送的文件內容。")
    return local


def confirm_document_transfer(parent, endpoint, pages):
    from PyQt6.QtWidgets import QMessageBox
    try:
        local = endpoint_is_local(endpoint)
    except ValueError as exc:
        QMessageBox.warning(parent, "API 端點不適用", str(exc))
        return False
    if local:
        return True
    reply = QMessageBox.question(
        parent, "傳送文件文字至遠端 AI",
        f"將把 {pages} 頁的可擷取文字傳送至：\n{endpoint}\n\n"
        "文字將由該服務處理。請確認此服務適合接收這份文件。",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    return reply == QMessageBox.StandardButton.Yes
