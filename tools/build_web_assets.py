#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build the assets the browser edition needs.

The web edition runs the REAL converter -- src/adif2xlsx.py, dxcc.py,
dxcc_tables.py and postage.py -- inside the browser via Pyodide, so all three
editions keep sharing one implementation instead of the web page being a second,
drifting copy in JavaScript.

Two things have to be prepared for that:

  * the Python sources, packed into one zip the page fetches and unpacks into
    Pyodide's virtual filesystem;
  * openpyxl and its one dependency et_xmlfile, which Pyodide does not ship, so
    they are downloaded from PyPI as the pure-Python wheels they are and served
    beside the page (a browser cannot reach PyPI itself).

Usage:  python tools/build_web_assets.py [--force]
Writes web/dist/adif2xlsx-pysrc.zip and web/dist/*.whl plus a MANIFEST.json.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import sys
import urllib.error
import urllib.request
import zipfile

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
WEB = os.path.join(ROOT, "web")
DIST = os.path.join(WEB, "dist")

#: The modules the browser needs. gui.py and webapp.py are deliberately absent:
#: they are desktop/server entry points with no meaning in a browser.
MODULES = ["adif2xlsx.py", "dxcc.py", "dxcc_tables.py", "postage.py"]

#: Pyodide does not package these, and both are pure Python, so the wheels run
#: unchanged inside it.
WHEELS = [
    ("openpyxl", "3.1.5"),
    ("et_xmlfile", "2.0.0"),
]

PYODIDE_VERSION = "v0.28.0"


def download(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "adif2xlsx"})
    with urllib.request.urlopen(request, timeout=180) as response:
        return response.read()


def wheel_url(name: str, version: str) -> str:
    """The pure-Python wheel URL for a package, from the PyPI JSON API."""
    data = json.loads(download(f"https://pypi.org/pypi/{name}/{version}/json")
                      .decode())
    for item in data["urls"]:
        if item["packagetype"] == "bdist_wheel" \
                and item["filename"].endswith("py3-none-any.whl"):
            return item["url"]
    raise SystemExit(f"no pure-python wheel for {name} {version}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the browser assets")
    parser.add_argument("--force", action="store_true",
                        help="re-download and rebuild even if present")
    args = parser.parse_args()

    os.makedirs(DIST, exist_ok=True)
    manifest = {"pyodide": PYODIDE_VERSION, "generated_by":
                "tools/build_web_assets.py", "modules": [], "wheels": []}

    # --- the Python sources -------------------------------------------------
    zip_path = os.path.join(DIST, "adif2xlsx-pysrc.zip")
    missing = [m for m in MODULES if not os.path.isfile(os.path.join(SRC, m))]
    if missing:
        print(f"missing sources: {missing}")
        return 2
    print("=== packing the converter ===")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in MODULES:
            path = os.path.join(SRC, name)
            # Strip the source of any stray CRLF so line counts and diffs inside
            # the browser match what the repository holds.
            text = open(path, encoding="utf-8").read().replace("\r\n", "\n")
            archive.writestr(name, text)
            digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
            manifest["modules"].append({"name": name, "bytes": len(text),
                                        "sha256": digest})
            print(f"  {name:18} {len(text):>8} bytes  {digest[:12]}")
    size = os.path.getsize(zip_path)
    manifest["pysrc"] = {"file": os.path.basename(zip_path), "bytes": size,
                         "sha256": hashlib.sha256(
                             open(zip_path, "rb").read()).hexdigest()}
    print(f"  -> {os.path.relpath(zip_path, ROOT)}  ({size / 1024:.0f} KB)")

    # --- the wheels ---------------------------------------------------------
    print("\n=== fetching the pure-python wheels ===")
    for name, version in WHEELS:
        target = os.path.join(DIST, f"{name}-{version}-py3-none-any.whl")
        if os.path.isfile(target) and not args.force:
            print(f"  {name} {version}: cached")
        else:
            url = wheel_url(name, version)
            payload = download(url)
            with open(target, "wb") as fh:
                fh.write(payload)
            print(f"  {name} {version}: {len(payload) / 1024:.0f} KB "
                  f"from {url.rsplit('/', 1)[-1]}")
        data = open(target, "rb").read()
        manifest["wheels"].append({
            "name": name, "version": version,
            "file": os.path.basename(target), "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest()})
        print(f"     sha256 {hashlib.sha256(data).hexdigest()[:16]}")

    # --- manifest -----------------------------------------------------------
    manifest_path = os.path.join(DIST, "MANIFEST.json")
    with open(manifest_path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    print(f"\nwrote {os.path.relpath(manifest_path, ROOT)}")
    total = sum(f["bytes"] for f in [manifest["pysrc"], *manifest["wheels"]])
    print(f"total page payload (excluding Pyodide itself): "
          f"{total / 1024:.0f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
