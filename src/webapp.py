#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""adif2xlsx 的网页端。

一个本机小服务：浏览器上传 ADIF 文件，服务端用同一套 src/adif2xlsx.py 生成
Excel，然后保存到你指定的路径或直接下载。转换逻辑完全复用命令行和桌面版的
代码，不重复实现，也不会产生第二份行为。

只用 Python 标准库（http.server），不引入任何第三方依赖。

安全约定：只监听 127.0.0.1，不对外网开放；每次启动生成一个随机令牌，
所有写操作都要带令牌，避免本机其它程序误触。

运行：python src/webapp.py            （自动打开浏览器）
      python src/webapp.py --no-open  （不自动打开）
"""

from __future__ import annotations

import argparse
import io
import json
import os
import secrets
import socket
import sys
import tempfile
import threading
import urllib.parse
import webbrowser
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Dict, List, Optional, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import adif2xlsx as core  # noqa: E402
import postage  # noqa: E402


def _web_directory() -> str:
    """Where the page lives.

    From source it is ``web/`` beside ``src/``.  A frozen build unpacks the
    bundled ``web`` data folder next to the program (``sys._MEIPASS`` for a
    one-file build), so both layouts are checked rather than assumed.
    """
    candidates = []
    bundle = getattr(sys, "_MEIPASS", "")
    if bundle:
        candidates.append(os.path.join(bundle, "web"))
    candidates.append(os.path.join(os.path.dirname(HERE), "web"))
    candidates.append(os.path.join(HERE, "web"))
    for candidate in candidates:
        if os.path.isfile(os.path.join(candidate, "index.html")):
            return candidate
    return candidates[0]


WEB_DIR = _web_directory()
INDEX = os.path.join(WEB_DIR, "index.html")

#: Upload ceiling.  A 1000-QSO export is a few hundred kB, so 64 MB is generous
#: and still stops a runaway request from eating memory.
MAX_UPLOAD = 64 * 1024 * 1024

#: Random per-run token.  Sent to the page on load and required by every POST,
#: so another local program cannot drive the converter behind the user's back.
TOKEN = secrets.token_urlsafe(24)

_STATIC_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".svg": "image/svg+xml",
}


# ---------------------------------------------------------------------------
# Field catalogue, so the page and the desktop UI offer exactly the same list.
# ---------------------------------------------------------------------------
def field_catalogue() -> Dict[str, object]:
    """Everything the page needs to build the column picker."""
    required = list(core.REQUIRED_COLUMNS)
    mandatory = list(core.MANDATORY_COLUMNS)
    optional = [name for name in core.FIELD_LABELS_ZH if name not in required]
    extra = [name for name in (core.ENTITY_SOURCE_COLUMN, core.POSTAGE_DETAIL_COLUMN)
             if name not in required and name not in optional]
    return {
        "required": [
            {"name": name, "label": core.field_label(name),
             "hint": core.describe_field(name)}
            for name in required
        ],
        "optional": [
            {"name": name, "label": core.field_label(name),
             "hint": core.describe_field(name),
             "derived": name in core.DERIVED_COLUMNS,
             "always": name in mandatory}
            for name in sorted(optional + extra)
        ],
        "mandatory": mandatory,
        "presets": {
            "common": ["CALL", "QSO_DATE", "TIME_ON_UTC", "BAND", "MODE",
                       "RST_SENT", "RST_RCVD", "STATION_CALLSIGN",
                       "DXCC_ENTITY", "QSL_POSTAGE_AIR"],
            "all": None,
            "required": [],
        },
    }


def environment_info() -> Dict[str, object]:
    """Defaults the page starts with.

    ``output`` is deliberately empty: leaving it blank makes the service stream
    the workbook back as a browser download, which is what a web tool should do.
    Filling the field in switches to writing a file at that path.
    """
    return {
        "output": "",
        "suggested_output": os.path.join(core.desktop_directory(),
                                         core.DEFAULT_OUTPUT_NAME),
        "download_name": core.DEFAULT_OUTPUT_NAME,
        "weight_g": postage.REFERENCE_WEIGHT_G,
        "rates_verified": postage.RATES_VERIFIED_ON,
        "version": core.__version__,
    }


# ---------------------------------------------------------------------------
# Conversion
# ---------------------------------------------------------------------------
class Upload:
    """One file received from the browser."""

    def __init__(self, name: str, data: bytes):
        self.name = os.path.basename(name) or "upload.adi"
        self.data = data


def save_uploads(uploads: List[Upload], folder: str) -> List[str]:
    """Write uploads into a scratch folder and return their paths.

    The scratch folder is removed once the workbook exists; nothing the user
    uploaded is left behind.
    """
    paths: List[str] = []
    used: Dict[str, int] = {}
    for item in uploads:
        name = item.name
        if name in used:
            used[name] += 1
            stem, ext = os.path.splitext(name)
            name = f"{stem} ({used[name]}){ext}"
        else:
            used[name] = 1
        path = os.path.join(folder, name)
        with open(path, "wb") as fh:
            fh.write(item.data)
        paths.append(path)
    return paths


def run_conversion(paths: List[str], output: Optional[str],
                   columns: Optional[List[str]]) -> Tuple[bytes, Dict[str, object]]:
    """Convert and return ``(workbook_bytes, report)``.

    ``output`` writes the workbook straight to that path and returns no bytes
    for download; ``None`` keeps it in memory so the browser can save it.
    """
    parsed = []
    skipped: List[str] = []
    unknown_tags: Dict[str, int] = {}
    for path in paths:
        try:
            result = core.parse_adif(path)
        except (core.AdifParseError, OSError) as exc:
            skipped.append(f"{os.path.basename(path)}：{exc}")
            continue
        parsed.append((path, result.records, result.header, result.unknown_tags))
        for tag in result.unknown_tags:
            unknown_tags[tag] = unknown_tags.get(tag, 0) + 1

    if not parsed:
        raise core.AdifParseError(
            "没有可转换的记录\n" + "\n".join(skipped[:5]) if skipped
            else "没有可转换的记录")

    if output:
        result = core.convert_to_workbook(parsed, output, columns)
        payload = b""
    else:
        handle, temp_path = tempfile.mkstemp(suffix=".xlsx")
        os.close(handle)
        try:
            result = core.convert_to_workbook(parsed, temp_path, columns)
            with open(temp_path, "rb") as fh:
                payload = fh.read()
        finally:
            try:
                os.remove(temp_path)
            except OSError:
                pass

    report: Dict[str, object] = {
        "total": result.total_records,
        "columns": len(result.columns),
        "column_names": list(result.columns),
        "sources": dict(result.sources),
        "skipped": skipped,
        "unknown_tags": unknown_tags,
        "saved_to": output or "",
        "incomplete": len(result.incomplete),
        "entity_unknown": getattr(result, "entity_unknown", 0),
    }
    return payload, report


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    server_version = "adif2xlsx-web"

    def log_message(self, fmt, *args):  # noqa: A003 - quieter console
        if os.environ.get("ADIF2XLSX_WEB_VERBOSE"):
            sys.stderr.write("  %s\n" % (fmt % args))

    # -- helpers -----------------------------------------------------------
    def _send(self, code: int, body: bytes, content_type: str,
              extra: Optional[Dict[str, str]] = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, code: int, payload: Dict[str, object]) -> None:
        self._send(code, json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _error(self, code: int, message: str) -> None:
        self._json(code, {"ok": False, "error": message})

    def _authorised(self, token: str) -> bool:
        return secrets.compare_digest(token or "", TOKEN)

    # -- GET ---------------------------------------------------------------
    def do_GET(self):  # noqa: N802 - required by BaseHTTPRequestHandler
        path = urllib.parse.urlparse(self.path).path
        if path in ("/", "/index.html"):
            self._serve_index()
            return
        if path == "/api/info":
            self._json(200, {"ok": True, "token": TOKEN,
                             **field_catalogue(), **environment_info()})
            return
        # Static files from web/, path-traversal safe.
        self._serve_static(path)

    def _serve_index(self):
        try:
            with open(INDEX, "rb") as fh:
                body = fh.read()
        except OSError:
            self._error(500, f"找不到界面文件：{INDEX}")
            return
        self._send(200, body, _STATIC_TYPES[".html"])

    def _serve_static(self, path: str):
        relative = path.lstrip("/")
        target = os.path.normpath(os.path.join(WEB_DIR, relative))
        if not target.startswith(WEB_DIR) or not os.path.isfile(target):
            self._error(404, "not found")
            return
        ext = os.path.splitext(target)[1].lower()
        with open(target, "rb") as fh:
            self._send(200, fh.read(),
                       _STATIC_TYPES.get(ext, "application/octet-stream"))

    # -- POST --------------------------------------------------------------
    def do_POST(self):  # noqa: N802
        path = urllib.parse.urlparse(self.path).path
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            self._error(400, "Content-Length 无效")
            return
        if length <= 0:
            self._error(400, "请求为空")
            return
        if length > MAX_UPLOAD:
            self._error(413, f"上传内容过大（上限 {MAX_UPLOAD // 1024 // 1024} MB）")
            return
        raw = self.rfile.read(length)
        if not self._authorised(self.headers.get("X-Adif2xlsx-Token", "")):
            self._error(403, "令牌无效，请刷新页面")
            return

        if path == "/api/preview":
            self._preview(raw)
        elif path == "/api/convert":
            self._convert(raw)
        else:
            self._error(404, "not found")

    def _preview(self, raw: bytes):
        """Read the uploads and report which columns they can produce."""
        try:
            uploads = self._decode(raw)
        except ValueError as exc:
            self._error(400, str(exc))
            return
        folder = tempfile.mkdtemp(prefix="adif2xlsx_preview_")
        try:
            paths = save_uploads(uploads, folder)
            available: List[str] = []
            per_file: List[Dict[str, object]] = []
            for path in paths:
                try:
                    res = core.parse_adif(path)
                except (core.AdifParseError, OSError) as exc:
                    per_file.append({"name": os.path.basename(path),
                                     "records": 0, "error": str(exc)})
                    continue
                built = core.build_rows(
                    [(path, res.records, res.header, res.unknown_tags)])
                for column in built.available:
                    if column not in available:
                        available.append(column)
                per_file.append({"name": os.path.basename(path),
                                 "records": len(res.records), "error": ""})
            self._json(200, {"ok": True, "files": per_file,
                             "available": available})
        finally:
            _remove_tree(folder)

    def _convert(self, raw: bytes):
        try:
            uploads = self._decode(raw)
        except ValueError as exc:
            self._error(400, str(exc))
            return
        columns = None
        if self.headers.get("X-Adif2xlsx-Columns"):
            try:
                columns = json.loads(
                    urllib.parse.unquote(self.headers["X-Adif2xlsx-Columns"]))
            except (ValueError, TypeError):
                columns = None
        output = ""
        if self.headers.get("X-Adif2xlsx-Output"):
            output = urllib.parse.unquote(self.headers["X-Adif2xlsx-Output"])
        if output.lower().endswith(".xlsx") is False and output:
            output += ".xlsx"

        folder = tempfile.mkdtemp(prefix="adif2xlsx_web_")
        try:
            paths = save_uploads(uploads, folder)
            try:
                payload, report = run_conversion(paths, output or None, columns)
            except core.AdifParseError as exc:
                self._error(400, str(exc))
                return
            except OSError as exc:
                self._error(500, f"无法写入文件：{exc}")
                return
            if output:
                self._json(200, {"ok": True, **report})
            else:
                name = os.path.basename(report.get("saved_to") or "") or \
                    core.DEFAULT_OUTPUT_NAME
                self._send(
                    200, payload,
                    "application/vnd.openxmlformats-officedocument"
                    ".spreadsheetml.sheet",
                    {"Content-Disposition":
                     f'attachment; filename="{name}"',
                     "X-Adif2xlsx-Report": urllib.parse.quote(
                         json.dumps(report, ensure_ascii=False))})
        finally:
            _remove_tree(folder)

    @staticmethod
    def _decode(raw: bytes) -> List[Upload]:
        """Decode the request body: either a zip or a single ADIF file.

        A zip keeps several files in one request, which the browser can build
        for a multi-file selection; a single file is sent as-is.
        """
        if raw[:4] == b"PK\x03\x04":
            uploads: List[Upload] = []
            try:
                with zipfile.ZipFile(io.BytesIO(raw)) as zf:
                    for info in zf.infolist():
                        if info.is_dir():
                            continue
                        name = os.path.basename(info.filename)
                        if not name.lower().endswith(core.ADIF_EXTENSIONS):
                            continue
                        uploads.append(Upload(name, zf.read(info)))
            except zipfile.BadZipFile as exc:
                raise ValueError(f"压缩包无法读取：{exc}") from exc
            if not uploads:
                raise ValueError("压缩包里没有 .adi / .adif 文件")
            return uploads
        return [Upload("upload.adi", raw)]


def _remove_tree(folder: str) -> None:
    import shutil
    shutil.rmtree(folder, ignore_errors=True)


def find_port(preferred: int = 0) -> int:
    """A free port on the loopback interface."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", preferred))
        return sock.getsockname()[1]


def serve(port: int = 0, open_browser: bool = True) -> int:
    port = find_port(port)
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/"
    print("ADIF 转 Excel —— 网页端已启动")
    print(f"  地址：{url}")
    print(f"  界面：{INDEX}")
    print("  只监听本机 127.0.0.1；按 Ctrl+C 停止")
    if open_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
    finally:
        httpd.server_close()
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="adif2xlsx 网页端")
    parser.add_argument("--port", type=int, default=0,
                        help="监听端口（默认自动选择空闲端口）")
    parser.add_argument("--no-open", action="store_true",
                        help="不自动打开浏览器")
    args = parser.parse_args(argv)
    return serve(args.port, open_browser=not args.no_open)


if __name__ == "__main__":
    raise SystemExit(main())
