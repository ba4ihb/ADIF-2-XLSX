#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate the browser edition of the web page.

The browser edition must not be a second implementation of the converter: the
project's whole architecture is that one Python module serves every front end.
So this page runs the REAL ``src/adif2xlsx.py`` inside the browser, via Pyodide
(CPython compiled to WebAssembly), and only the UI layer is JavaScript.

The page is generated from ``web/index.html`` -- the local-service edition -- so
the two cannot drift apart in wording, layout or behaviour.  The differences are
exactly three and each is marked in the generated file:

  1. the bootstrap runs Pyodide instead of talking to a local service;
  2. "保存到" becomes a download file name, because a page cannot write to an
     arbitrary path on your disk (and should not be able to);
  3. nothing is uploaded anywhere.

Usage:  python tools/build_browser_page.py
Writes web/browser.html and docs/web.html.
"""

from __future__ import annotations

import io
import os
import re
import subprocess
import sys
import zipfile

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE = os.path.join(ROOT, "web", "index.html")
TARGET_WEB = os.path.join(ROOT, "web", "browser.html")
TARGET_DOCS = os.path.join(ROOT, "docs", "web.html")

#: Pinned so a Pyodide release cannot change behaviour underneath a built page.
#: The asset builder records the same version in web/dist/MANIFEST.json.
PYODIDE_VERSION = "v0.28.0"

BANNER = """<!--
  ADIF 2 XLSX -- browser edition (generated; do not edit by hand).

  Generated from web/index.html by tools/build_browser_page.py.

  This page runs the real converter -- src/adif2xlsx.py, dxcc.py, dxcc_tables.py
  and postage.py -- inside the browser via Pyodide (CPython in WebAssembly), so
  there is exactly one implementation of the conversion logic in this project.
  It talks to no server: your log never leaves the machine.

  Differences from the local-service edition, and nothing else:
    1. bootstrap: Pyodide + a virtual filesystem instead of /api/* calls;
    2. the save field is a download file NAME (a page cannot write to an
       arbitrary path, by design);
    3. no upload, no token, no local service.
-->
"""

#: Injected just before </head>: the runtime loader.
HEAD_INJECT = """
  /* browser-edition styling: the runtime notice bar */
  #boot {
    background: var(--lavender); border-radius: 12px; padding: 12px 14px;
    font-size: 12.5px; margin-bottom: 16px;
  }
  #boot b { color: var(--pink-dark); }
  #boot .bar {
    height: 6px; background: #fff; border-radius: 999px; overflow: hidden;
    margin-top: 8px;
  }
  #boot .bar i {
    display: block; height: 100%; width: 0%;
    background: linear-gradient(90deg, var(--pink), #A98BFF);
    transition: width .3s;
  }
  #boot.ok { background: var(--mint); color: var(--mint-text); }
  #boot.bad { background: #FFE9EC; color: #B03050; }
  .only-browser { display: none; }
"""

#: The Python bootstrap, injected into the page as a string.  It is deliberately
#: thin: it calls the same module functions the desktop app calls.
PY_BOOTSTRAP = '''
import base64, io, json, os, sys, traceback

sys.path.insert(0, "/app")


def _sel(payload):
    """Turn the page's column selection into the argument core expects.

    ``null`` means "every column that holds data", ``[]`` means "the mandatory
    set only", a list means those columns.  Same contract as --columns.
    """
    columns = payload.get("columns")
    if columns is None:
        return None
    return list(columns)


def convert(payload):
    """Convert uploaded files and return a JSON-able report.

    ``payload`` is ``{"files": [{"name":..., "data": <b64>}], "columns": ...}``.
    Returns ``{"ok": True, "xlsx": <b64>, "report": {...}}`` or ``{"ok": False,
    "error": ...}``.  Nothing touches the network: this runs in the page.
    """
    try:
        import adif2xlsx as core
    except Exception as exc:                      # noqa: BLE001
        return {"ok": False, "error": f"加载转换模块失败：{exc}"}

    if not hasattr(core, "parse_adif_bytes"):
        # A stale copy of the module is loaded.  Say so precisely: this is the
        # one failure mode that looks like a conversion bug but is a build
        # problem, and the file path identifies it immediately.
        return {"ok": False, "error":
                f"载入的 adif2xlsx 是旧版本（file={getattr(core, '__file__', '?')}，"
                f"version={getattr(core, '__version__', '?')}）—— 请重新构建 "
                f"web/dist/adif2xlsx-pysrc.zip"}

    parsed, skipped, unknown_tags = [], [], {}
    for item in payload.get("files") or []:
        name = item.get("name") or "upload.adi"
        try:
            raw = base64.b64decode(item.get("data") or "")
        except Exception as exc:                  # noqa: BLE001
            skipped.append(f"{name}：无法解码（{exc}）")
            continue
        try:
            result = core.parse_adif_bytes(raw, label=name)
        except Exception as exc:                  # noqa: BLE001
            skipped.append(f"{name}：{exc}")
            continue
        parsed.append((name, result.records, result.header, result.unknown_tags))
        for tag in result.unknown_tags:
            unknown_tags[tag] = unknown_tags.get(tag, 0) + 1

    if not parsed:
        return {"ok": False, "saved_to": "",
                "error": "没有可转换的记录\\n" + "\\n".join(skipped[:5])}

    try:
        payload_bytes, result = core.workbook_bytes(parsed, _sel(payload))
    except Exception as exc:                      # noqa: BLE001
        return {"ok": False, "error": str(exc),
                "trace": traceback.format_exc()[-1200:]}

    report = {
        "total": result.total_records,
        "columns": len(result.columns),
        "column_names": list(result.columns),
        "sources": dict(result.sources),
        "skipped": skipped,
        "unknown_tags": unknown_tags,
        "saved_to": "",
        "incomplete": len(result.incomplete),
        "entity_unknown": getattr(result, "entity_unknown", 0),
    }
    return {"ok": True, "xlsx": base64.b64encode(payload_bytes).decode("ascii"),
            "report": report}


def preview(payload):
    """Report each file's record count and the fields the data can produce.

    The same two things the local service returns, computed by the same module.
    """
    try:
        import adif2xlsx as core
    except Exception as exc:                      # noqa: BLE001
        return {"ok": False, "error": f"加载转换模块失败：{exc}"}
    files, available = [], []
    for item in payload.get("files") or []:
        name = item.get("name") or "upload.adi"
        entry = {"name": name, "records": 0, "error": ""}
        try:
            raw = base64.b64decode(item.get("data") or "")
            parsed = core.parse_adif_bytes(raw, label=name)
            entry["records"] = len(parsed.records)
            merged = [(name, parsed.records, parsed.header, parsed.unknown_tags)]
            result = core.build_rows(merged, None)
            available = list(result.available) or available
        except Exception as exc:                  # noqa: BLE001
            entry["error"] = str(exc)
        files.append(entry)
    return {"ok": True, "files": files, "available": available}


def catalogue():
    """The column catalogue, taken from the core so labels cannot disagree."""
    import adif2xlsx as core
    required = list(core.REQUIRED_COLUMNS)
    optional = [n for n in core.FIELD_LABELS_ZH if n not in required]
    optional += [n for n in (core.ENTITY_SOURCE_COLUMN,
                             core.POSTAGE_DETAIL_COLUMN)
                 if n not in required and n not in optional]
    mandatory = list(core.MANDATORY_COLUMNS)
    return {
        "required": [{"name": n, "label": core.field_label(n),
                      "hint": core.describe_field(n)} for n in required],
        "optional": [{"name": n, "label": core.field_label(n),
                      "hint": core.describe_field(n),
                      "derived": n in core.DERIVED_COLUMNS,
                      "always": n in mandatory}
                     for n in sorted(optional)],
        "mandatory": mandatory,
        "presets": {
            "common": ["CALL", "QSO_DATE", "TIME_ON_UTC", "BAND", "MODE",
                       "RST_SENT", "RST_RCVD", "STATION_CALLSIGN",
                       "DXCC_ENTITY", "QSL_POSTAGE_AIR"],
            "all": None,
            "required": [],
        },
        "download_name": core.DEFAULT_OUTPUT_NAME,
        "version": core.__version__,
        "weight_g": __import__("postage").REFERENCE_WEIGHT_G,
        "rates_verified": __import__("postage").RATES_VERIFIED_ON,
    }
'''

#: The JavaScript that loads Pyodide, unpacks the sources and wires the calls.
JS_LOADER = """
/* ---------- 浏览器版引导：把真正的 Python 转换器跑在本页里 ---------- */
/* The page calls these three functions instead of /api/*. Everything else on
   this page is byte-for-byte the local-service edition. */
const PYODIDE_VERSION = "__PYODIDE_VERSION__";
const PYODIDE_CDN =
  `https://cdn.jsdelivr.net/pyodide/${PYODIDE_VERSION}/full/`;

function boot(message, ratio, state) {
  /* A stall here is otherwise invisible from outside, so every stage is
     announced to an embedding harness when there is one. */
  if (window.parent && window.parent !== window) {
    try {
      window.parent.postMessage(
        { from: "adif2xlsx", log: "boot: " + message.replace(/<[^>]+>/g, "") },
        "*");
    } catch (_) { /* nothing to do */ }
  }
  const bar = document.querySelector("#boot .bar i");
  document.getElementById("bootText").innerHTML = message;
  if (bar) bar.style.width = Math.round((ratio || 0) * 100) + "%";
  const box = document.getElementById("boot");
  box.classList.remove("ok", "bad");
  if (state) box.classList.add(state);
}

function b64ToBytes(b64) {
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

function bytesToB64(bytes) {
  let out = "";
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    out += String.fromCharCode.apply(null, bytes.subarray(i, i + chunk));
  }
  return btoa(out);
}

/* Unzip with the platform's own decompressor -- no third-party code. */
async function inflateRaw(bytes) {
  const stream = new Blob([bytes]).stream()
    .pipeThrough(new DecompressionStream("deflate-raw"));
  return new Uint8Array(await new Response(stream).arrayBuffer());
}

async function unpackSources(pyodide, zipBytes) {
  const view = new DataView(zipBytes.buffer, zipBytes.byteOffset,
                            zipBytes.byteLength);
  let at = 0;
  const files = [];
  while (at + 30 <= zipBytes.length && view.getUint32(at, true) === 0x04034b50) {
    const method = view.getUint16(at + 8, true);
    const size = view.getUint32(at + 18, true);
    const nameLen = view.getUint16(at + 26, true);
    const extraLen = view.getUint16(at + 28, true);
    const name = new TextDecoder().decode(
      zipBytes.subarray(at + 30, at + 30 + nameLen));
    const start = at + 30 + nameLen + extraLen;
    const raw = zipBytes.subarray(start, start + size);
    const content = method === 8 ? await inflateRaw(raw) : raw;
    files.push(["/app/" + name, content]);
    at = start + size;
  }
  for (const [path, content] of files) pyodide.FS.writeFile(path, content);
  return files.map(f => f[0]);
}

let PY = null;                      // the running Python namespace
let BOOT_ERROR = "";

/* The page may be opened straight from disk (file://), where a cross-origin
   <script> will not load.  Those two URLs answer without CORS headers, so the
   fetch() route works where the tag does not. */
async function loadScript(url) {
  if (location.protocol !== "file:") {
    const tag = document.createElement("script");
    tag.src = url;
    const viaTag = new Promise((ok, bad) => {
      tag.onload = ok;
      tag.onerror = () => bad(new Error("script tag failed"));
    });
    document.head.appendChild(tag);
    try { await viaTag; return; } catch (_) { /* fall through to fetch */ }
  }
  const source = await (await fetch(url, { mode: "cors" })).text();
  const inline = document.createElement("script");
  inline.textContent = source;
  document.head.appendChild(inline);
  if (typeof loadPyodide !== "function") {
    throw new Error("Pyodide 加载失败");
  }
}

async function bootPython() {
  boot("正在准备浏览器版运行时…（<b>首次约 10 MB</b>，之后走缓存）", 0.05);
  await loadScript(PYODIDE_CDN + "pyodide.js");

  boot("正在启动 Python 运行时…", 0.25);
  const pyodide = await loadPyodide({ indexURL: PYODIDE_CDN });

  boot("正在下载 openpyxl（首次约 260 KB）…", 0.5);
  const wheels = [
    "dist/openpyxl-3.1.5-py3-none-any.whl",
    "dist/et_xmlfile-2.0.0-py3-none-any.whl",
  ];
  await pyodide.loadPackage(
    wheels.map(w => new URL(w, location.href).href));

  boot("正在载入转换器（同一份 Python 代码）…", 0.75);
  const zip = new Uint8Array(await (await fetch(
    new URL("dist/adif2xlsx-pysrc.zip", location.href))).arrayBuffer());
  pyodide.FS.mkdirTree("/app");
  pyodide.FS.chdir("/app");
  const names = await unpackSources(pyodide, zip);

  pyodide.runPython(`__import__("sys").path.insert(0, "/app")`);
  pyodide.runPython(__PY_BOOTSTRAP__);
  /* The bridge always exchanges JSON *text*.  Pyodide auto-converts a returned
     dict into a JsProxy -- and JSON.parse() on that is a confusing crash -- so
     the Python side is asked for a string and the page parses it itself.
     The argument is passed as base64 inside a Python literal, which avoids
     quoting problems with the quotes and newlines in ADIF payloads, and a
     no-argument call stays a no-argument call. */
  const bridge = (name) => (arg) => {
    let call;
    if (arg === undefined || arg === null) {
      call = `${name}()`;
    } else {
      /* A string argument is already JSON; anything else is serialised here.
         Double-encoding a string is how "str object has no attribute get"
         happens: the payload arrives as a string instead of a dict. */
      const json = typeof arg === "string" ? arg : JSON.stringify(arg);
      const b64 = btoa(unescape(encodeURIComponent(json)));
      call = `${name}(_j.loads(__import__("base64").b64decode("${b64}")` +
             `.decode("utf-8")))`;
    }
    return pyodide.runPython(
      `import json as _j; _j.dumps(${call}, ensure_ascii=False)`);
  };
  window.__pyCatalogue = bridge("catalogue");
  window.__pyConvert = bridge("convert");
  window.__pyPreview = bridge("preview");
  PY = window.__pyConvert;

  const catalogue = JSON.parse(window.__pyCatalogue());
  ENV = catalogue;
  CATALOGUE = {
    required: catalogue.required, optional: catalogue.optional,
    mandatory: catalogue.mandatory, presets: catalogue.presets,
  };
  document.getElementById("downloadName").value = catalogue.download_name;
  document.getElementById("infoLine").textContent =
    `自动附上 DXCC 实体与 QSL 平信邮资（${catalogue.weight_g} 克，` +
    `资费核对于 ${catalogue.rates_verified}）；` +
    `某列全空通常是导出软件没有提供该字段，Summary 表会逐列说明`;
  renderFields();
  boot("✅ 浏览器版已就绪 —— <b>全部在本页完成，日志不会离开这台电脑</b>",
       1, "ok");
  document.querySelectorAll(".only-browser").forEach(
    el => { el.style.display = el.dataset.display || "block"; });
  window.__ready = true;
  console.log("adif2xlsx browser edition ready; python modules:", __MODULE_NAMES__);
}

/* The three calls the page makes, mirroring the local service API.  Each one
   hands JSON text to Python and gets JSON text back, so nothing depends on how
   Pyodide chooses to convert a value. */
async function pyConvert(payload) {
  const out = JSON.parse(PY(JSON.stringify(payload)));
  if (out.ok) out.bytes = b64ToBytes(out.xlsx);
  return out;
}

async function pyPreview(payload) {
  return JSON.parse(window.__pyPreview(JSON.stringify(payload)));
}

function filePayload() {
  return Promise.all(files.map(async item => ({
    name: item.name,
    data: bytesToB64(new Uint8Array(await item.file.arrayBuffer())),
  })));
}

/* ---------- 测试钩子 ----------
   Only active when the page is embedded (a harness drives it).  It reports the
   real outcome of a real conversion so the test asserts the RESULT rather than
   looking for a visual cue that a screenshot may or may not catch. */
if (window.parent && window.parent !== window) {
  window.addEventListener("message", async (event) => {
    if (!event.data || event.data.cmd !== "run-test") return;
    const say = (m) => window.parent.postMessage(
      { from: "adif2xlsx", log: m }, "*");
    try {
      say(`ready=${!!window.__ready} ` +
          `required=${CATALOGUE.required.length} ` +
          `optional=${CATALOGUE.optional.length}`);
      if (!window.__ready) { window.parent.postMessage(
        { from: "adif2xlsx", done: false, why: "runtime not ready" }, "*"); return; }

      // The payload is built from the ADI TEXT the harness sends, not from a
      // File put into the page's <input>.  A File constructed in another realm
      // reads back short through arrayBuffer() (335 bytes of a 3.5 KB log), so
      // building the payload here is both simpler and honest about what is
      // being tested: the conversion of those bytes.
      const files = [{ name: event.data.name || "sample.adi",
                       data: bytesToB64(new TextEncoder().encode(event.data.adi)) }];
      say(`payload: ${files.length} file, ${files[0].data.length} b64 chars, ` +
          `${event.data.adi.length} chars of ADIF`);

      // Capture the download instead of writing it to disk.
      let blob = null;
      const realCreate = URL.createObjectURL.bind(URL);
      URL.createObjectURL = (b) => { blob = b; return realCreate(b); };
      const realClick = HTMLAnchorElement.prototype.click;
      let savedAs = "";
      HTMLAnchorElement.prototype.click = function () {
        savedAs = this.download;
      };

      const started = performance.now();
      // Drive the conversion through the same bridge the UI uses, and report
      // each step: the UI's own convert() swallows errors into a toast, which is
      // invisible to a harness.
      const data = await pyConvert({ files, columns: selectedColumns() });
      say("pyConvert returned ok=" + data.ok +
          (data.ok ? ` total=${data.report.total} cols=${data.report.columns} ` +
                     `xlsx=${data.bytes.length}B`
                   : ` error=${data.error}`));
      if (!data.ok) {
        window.parent.postMessage({ from: "adif2xlsx", done: false,
                                    why: String(data.error).slice(0, 300) }, "*");
        return;
      }
      // Write it the way the UI does, capturing the blob instead of saving it.
      savedAs = ($("downloadName").value.trim() || "adif_export.xlsx");
      blob = new Blob([data.bytes], {
        type: "application/vnd.openxmlformats-officedocument" +
              ".spreadsheetml.sheet" });
      window.__lastReport = data.report;
      HTMLAnchorElement.prototype.click = realClick;

      const report = window.__lastReport || {};
      let magic = "";
      if (blob) {
        const head = new Uint8Array(await blob.slice(0, 4).arrayBuffer());
        magic = Array.from(head)
          .map(b => b.toString(16).padStart(2, "0")).join(" ");
      }
      say(`converted in ${((performance.now() - started) / 1000).toFixed(1)}s: ` +
          `total=${report.total} columns=${report.columns}`);
      window.parent.postMessage({
        from: "adif2xlsx", done: true,
        total: report.total, columns: report.columns,
        column_names: report.column_names || [],
        saved_as: savedAs, bytes: blob ? blob.size : 0, magic: magic,
        required: CATALOGUE.required.map(r => r.name),
      }, "*");
    } catch (err) {
      window.parent.postMessage(
        { from: "adif2xlsx", done: false, why: String(err && err.message || err) },
        "*");
    }
  });
  window.parent.postMessage({ from: "adif2xlsx", greeting: true }, "*");
}

bootPython().catch(err => {
  BOOT_ERROR = String(err && err.message || err);
  boot(`❌ 浏览器版无法启动：${BOOT_ERROR}<br>` +
       `请改用<a href="https://github.com/ba4ihb/ADIF-2-XLSX/releases/latest">` +
       `桌面版或命令行版</a>（功能相同）。`, 0, "bad");
});
"""


def main() -> int:
    if not os.path.isfile(SOURCE):
        print(f"missing {SOURCE}")
        return 2

    # Always refresh the packed sources first.  A stale zip is the one failure
    # mode that looks like a converter bug ("module has no attribute ...") but is
    # a build problem, so it is made impossible rather than documented.
    print("=== refreshing web/dist (packed sources and wheels) ===")
    builder = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "build_web_assets.py")
    result = subprocess.run([sys.executable, builder], capture_output=True,
                            text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        print(result.stdout[-800:])
        print(result.stderr[-800:])
        return result.returncode
    for line in result.stdout.splitlines():
        if line.startswith("  adif2xlsx.py") or line.startswith("  -> "):
            print(f"  {line.strip()}")

    # The packed sources must be the ones on disk right now.
    zip_path = os.path.join(ROOT, "web", "dist", "adif2xlsx-pysrc.zip")
    with zipfile.ZipFile(zip_path) as archive:
        packed = archive.read("adif2xlsx.py").decode("utf-8")
    current = open(os.path.join(ROOT, "src", "adif2xlsx.py"),
                   encoding="utf-8").read().replace("\r\n", "\n")
    if packed != current:
        print("*** the packed sources do not match src/ — refusing to build")
        return 1
    print(f"  packed adif2xlsx.py matches src/ ({len(packed)} bytes)")

    html = open(SOURCE, encoding="utf-8").read()

    # --- head: title, banner, notice bar -----------------------------------
    html = html.replace(
        "<title>ADIF 转 Excel ✨</title>",
        "<title>ADIF 转 Excel ✨（浏览器版，打开即用）</title>", 1)
    html = html.replace("</style>", HEAD_INJECT + "</style>", 1)

    # --- the notice bar and the honest wording about what this edition is ---
    html = html.replace(
        """  <header>
    <h1>ADIF <span class="arrow">→</span> Excel ✨</h1>
    <p>把业余无线电日志整理成一张干净的表格 · 所有时间为 UTC，不做时区换算</p>
  </header>
""",
        """  <header>
    <h1>ADIF <span class="arrow">→</span> Excel ✨</h1>
    <p>把业余无线电日志整理成一张干净的表格 · 所有时间为 UTC，不做时区换算</p>
  </header>

  <div id="boot">
    <span id="bootText">正在准备浏览器版运行时…</span>
    <div class="bar"><i></i></div>
  </div>
""", 1)

    # --- "保存到" becomes a download name ---------------------------------
    html = html.replace(
        """  <!-- 3. 保存到 -->
  <section class="card lavender">
    <h2>💾 保存到 <span class="count" id="saveMode">留空 = 浏览器下载</span></h2>
    <input type="text" id="output" spellcheck="false"
           placeholder="留空则下载到浏览器的下载目录；填路径则直接写到该位置">
    <div class="row" style="margin-top:8px">
      <button class="btn" id="clearOutput">清空（改为下载）</button>
      <button class="btn ghost" id="useDesktop">填默认位置</button>
    </div>
    <div class="info" id="infoLine"></div>
  </section>""",
        """  <!-- 3. 下载文件名（浏览器版：不能写你磁盘上的任意路径） -->
  <section class="card lavender">
    <h2>💾 下载文件名 <span class="count">保存到浏览器的下载目录</span></h2>
    <input type="text" id="downloadName" spellcheck="false" value="adif_export.xlsx">
    <div class="info" id="infoLine"></div>
  </section>""", 1)

    # The two checkboxes described server-side behaviour.
    html = html.replace(
        """      <label class="check"><input type="checkbox" id="openAfter" checked>
        完成后提示保存位置</label>
      <label class="check"><input type="checkbox" id="subfolders" checked>
        文件夹包含子目录</label>""",
        """      <label class="check"><input type="checkbox" id="openAfter" checked>
        完成后提示保存位置</label>
      <label class="check"><input type="checkbox" id="subfolders" checked>
        文件夹包含子目录</label>
      <span class="count" style="margin-left:auto">🔒 不过网络，不上传</span>""", 1)

    # --- the script: keep the UI, replace the transport --------------------
    start = html.index("<script>")
    end = html.index("</script>", start) + len("</script>")
    script = html[start:end]

    # 1. The network calls become in-page calls.
    script = script.replace(
        """/* ---------- 初始化 ---------- */
async function init() {
  try {
    const res = await fetch("/api/info");
    const info = await res.json();
    if (!info.ok) throw new Error(info.error || "服务未就绪");
    TOKEN = info.token;
    CATALOGUE = {
      required: info.required, optional: info.optional,
      mandatory: info.mandatory, presets: info.presets,
    };
    ENV = info;
    $("output").value = info.output || "";
    updateSaveMode();
    $("infoLine").textContent =
      `自动附上 DXCC 实体与 QSL 平信邮资（${info.weight_g} 克，` +
      `资费核对于 ${info.rates_verified}）；` +
      `某列全空通常是导出软件没有提供该字段，Summary 表会逐列说明`;
    renderFields();
  } catch (err) {
    toast("无法连接本地服务：" + err.message, 6000);
  }
}
""",
        """/* ---------- 初始化 ---------- */
/* No service to connect to: bootPython() fills CATALOGUE and ENV from the
   Python catalogue, then calls renderFields(). */
""", 1)

    # 2. Multi-file packing is no longer needed (no request body limit).
    script = script.replace(
        """/* ---------- 上传 ---------- */
async function buildBody() {
  if (files.length === 1) {
    return await files[0].file.arrayBuffer();
  }
  // 多个文件打成一个 zip，一次请求送达。
  const zip = new ZipWriter();
  for (const item of files) {
    zip.add(item.name, new Uint8Array(await item.file.arrayBuffer()));
  }
  return zip.finish();
}

""",
        """/* ---------- 读取与转换：直接调用本页里的 Python ---------- */

""", 1)

    script = script.replace(
        """async function readFields() {
  if (!files.length) return;
  busy(true);
  try {
    const body = await buildBody();
    const res = await fetch("/api/preview", {
      method: "POST", body,
      headers: { "X-Adif2xlsx-Token": TOKEN },
    });
    const data = await res.json();
    if (!data.ok) { toast(data.error || "读取失败", 5000); return; }""",
        """async function readFields() {
  if (!files.length) return;
  if (!window.__ready) { toast("运行时还在准备，请稍候", 4000); return; }
  busy(true);
  try {
    const data = await pyPreview({ files: await filePayload() });
    if (!data.ok) { toast(data.error || "读取失败", 5000); return; }""", 1)

    script = script.replace(
        """async function convert() {
  if (!files.length) return;
  busy(true);
  $("result").classList.remove("show");
  $("warnBox").style.display = "none";
  try {
    const body = await buildBody();
    const headers = { "X-Adif2xlsx-Token": TOKEN };
    const cols = selectedColumns();
    if (cols !== null) {
      headers["X-Adif2xlsx-Columns"] = encodeURIComponent(JSON.stringify(cols));
    }
    const output = $("output").value.trim();
    if (output) headers["X-Adif2xlsx-Output"] = encodeURIComponent(output);

    const res = await fetch("/api/convert", { method: "POST", body, headers });
    if (output) {
      const data = await res.json();
      if (!data.ok) { toast(data.error || "转换失败", 6000); return; }
      showResult(data);
    } else {
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        toast(data.error || "转换失败", 6000);
        return;
      }
      const blob = await res.blob();
      const report = JSON.parse(decodeURIComponent(
        res.headers.get("X-Adif2xlsx-Report") || "%7B%7D"));
      downloadBlob(blob, "adif_export.xlsx");
      showResult(report);
    }
  } catch (err) {
    toast("转换失败：" + err.message, 6000);
  } finally {
    busy(false);
  }
}""",
        """async function convert() {
  if (!files.length) return;
  if (!window.__ready) { toast("运行时还在准备，请稍候", 4000); return; }
  busy(true);
  $("result").classList.remove("show");
  $("warnBox").style.display = "none";
  try {
    const data = await pyConvert({
      files: await filePayload(),
      columns: selectedColumns(),
    });
    if (!data.ok) {
      toast(data.error || "转换失败", 6000);
      if (data.trace) console.error(data.trace);
      return;
    }
    const name = ($("downloadName").value.trim() || "adif_export.xlsx");
    downloadBlob(new Blob([data.bytes], {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }), name);
    showResult(data.report);
    window.__lastReport = data.report;   // test hook: lets a harness verify
  } catch (err) {
    toast("转换失败：" + err.message, 6000);
  } finally {
    busy(false);
  }
}""", 1)

    # 3. The save-mode toggle and the zip writer go away with the transport.
    script = script.replace(
        """// "留空 = 下载" is the point of a web tool, so the field starts empty and says
// which mode is active.
function updateSaveMode() {
  const filled = $("output").value.trim().length > 0;
  $("saveMode").textContent = filled ? "写入该路径" : "留空 = 浏览器下载";
}
$("output").addEventListener("input", updateSaveMode);
$("clearOutput").onclick = () => {
  $("output").value = "";
  updateSaveMode();
  toast("已改为直接下载");
};
$("useDesktop").onclick = () => {
  $("output").value = ENV.suggested_output || "";
  updateSaveMode();
  toast("将写入 " + $("output").value, 4000);
};
""",
        """/* The download name needs no mode switch: the browser always downloads. */
$("downloadName").addEventListener("change", () => {
  let name = $("downloadName").value.trim() || "adif_export.xlsx";
  if (!/\\.xlsx$/i.test(name)) name += ".xlsx";
  $("downloadName").value = name;
});
""", 1)

    # Drop the zip writer: it existed to pack several files into one request.
    script = re.sub(
        r"/\* ---------- 极简 zip 写入器.*?function crc32\(bytes\) \{.*?\n\}\n",
        "/* The zip writer of the local edition is not needed here: this page\n"
        "   hands the Python code the files directly. */\n",
        script, flags=re.S)

    # 4. Boot the runtime instead of init().
    script = script.replace("\ninit();\n", "\n/* bootPython() is defined below and starts the runtime. */\n", 1)

    # `let TOKEN` is unused now.
    script = script.replace('let TOKEN = "";\n', "", 1)

    # Append the loader.
    loader = JS_LOADER.replace("__PYODIDE_VERSION__", PYODIDE_VERSION)
    loader = loader.replace("__PY_BOOTSTRAP__",
                            "`" + PY_BOOTSTRAP.replace("\\", "\\\\")
                            .replace("`", "\\`")
                            .replace("${", "\\${") + "`")
    loader = loader.replace("__MODULE_NAMES__",
                            '["adif2xlsx.py","dxcc.py","dxcc_tables.py",'
                            '"postage.py"]')
    script = script[: -len("</script>")] + loader + "\n</script>"
    html = html[:start] + script + html[end:]

    html = BANNER + html
    open(TARGET_WEB, "w", encoding="utf-8", newline="\n").write(html)
    open(TARGET_DOCS, "w", encoding="utf-8", newline="\n").write(html)

    # Sanity: the generated page must still contain every UI affordance, and
    # must not contain a single call to a local service.  Comments are allowed to
    # mention /api/ (the banner explains what changed), so the check looks for
    # the calls themselves.
    for needle, label in (
            ('id="drop"', "drag and drop"),
            ('id="picker"', "file picker"),
            ('id="folderPicker"', "folder picker"),
            ('data-preset="common"', "preset: common"),
            ('data-preset="all"', "preset: all"),
            ('data-preset="required"', "preset: required"),
            ('id="fields"', "column list"),
            ('id="start"', "start button"),
            ('id="result"', "result card"),
            ('id="boot"', "runtime notice"),
            ("pyodide", "Pyodide bootstrap"),
            ("pyConvert", "conversion goes through Python in the page"),
    ):
        present = needle in html
        print(f"  {'ok' if present else '*** MISSING ***':16} {label}")

    forbidden = {
        'fetch("/api/info"': "no /api/info call",
        'fetch("/api/preview"': "no /api/preview call",
        'fetch("/api/convert"': "no /api/convert call",
        "X-Adif2xlsx-Token": "no service token",
        'headers: { "X-Adif2xlsx': "no service headers",
    }
    for needle, label in forbidden.items():
        found = needle in html
        print(f"  {'*** PRESENT ***' if found else 'ok':16} {label}")
    # A page that fetches anything must only fetch its own assets.
    fetches = re.findall(r"fetch\(([^)]{0,80})", html)
    print(f"  fetch() calls: {fetches}")

    print(f"\nwrote {os.path.relpath(TARGET_WEB, ROOT)} "
          f"({os.path.getsize(TARGET_WEB)} bytes)")
    print(f"wrote {os.path.relpath(TARGET_DOCS, ROOT)} "
          f"({os.path.getsize(TARGET_DOCS)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
