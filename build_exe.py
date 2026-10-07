#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build a standalone Windows executable for adif2xlsx.

Produces both shapes, because they trade start-up time against convenience:

  dist/adif2xlsx.exe          single file, ~30 MB, nothing to install.
                              Unpacks itself on every launch (~3.4 s overhead).
  dist/adif2xlsx/adif2xlsx.exe
                              a folder instead of one file, starts in ~0.6 s.
                              Better for repeated or scripted runs.

Both bundle the CPython runtime, openpyxl and the DXCC table in ``src/dxcc.py``,
so they run on a Windows machine with no Python installed.

    python build_exe.py              # build both
    python build_exe.py --onefile    # single file only
    python build_exe.py --onedir     # folder build only
    python build_exe.py --clean      # remove build/ and dist/ first

Requires PyInstaller:  pip install pyinstaller
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "src")
ENTRY = os.path.join(SRC, "adif2xlsx.py")
BUILD = os.path.join(HERE, "build")
DIST = os.path.join(HERE, "dist")

VERSION_INFO = """VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=(1, 0, 0, 0),
    prodvers=(1, 0, 0, 0),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '040904B0',
        [StringStruct('CompanyName', 'adif2xlsx'),
         StringStruct('FileDescription', 'ADIF to Excel converter'),
         StringStruct('FileVersion', '1.0.0.0'),
         StringStruct('InternalName', 'adif2xlsx'),
         StringStruct('OriginalFilename', 'adif2xlsx.exe'),
         StringStruct('ProductName', 'adif2xlsx'),
         StringStruct('ProductVersion', '1.0.0.0')])
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""


def build(mode: str, *, variant: str = "cli") -> int:
    """Run one PyInstaller build.

    ``mode`` is "onefile" or "onedir"; ``variant`` is "cli" (the command line),
    "gui" (the windowed desktop interface) or "web" (the local web service).
    """
    gui = variant == "gui"
    web = variant == "web"
    name = {"gui": "adif2xlsx-ui", "web": "adif2xlsx-web"}.get(variant, "adif2xlsx")
    entry = os.path.join(SRC, "webapp.py") if web else ENTRY

    icon_args = []
    if variant in ("gui", "web"):
        icon = os.path.join(HERE, "assets", "adif2xlsx.ico")
        if os.path.isfile(icon):
            icon_args = ["--icon", icon]

    # The windowed build needs a runtime hook: it must be able to tell that it
    # is the UI build even when a parent with a console hands it inheritable
    # standard handles, which otherwise sends it down the command-line path.
    hook_args = []
    if gui:
        hook = os.path.join(SRC, "pyi_rth_ui.py")
        if os.path.isfile(hook):
            hook_args = ["--runtime-hook", hook]

    # The web build needs the page itself, which is data rather than code.
    data_args = []
    if web:
        data_args = ["--add-data", f"{os.path.join(HERE, 'web')}{os.pathsep}web"]

    command = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--name", name,
        "--distpath", DIST,
        "--workpath", os.path.join(BUILD, f"{mode}-{variant}"),
        "--specpath", os.path.join(BUILD, f"{mode}-{variant}"),
        # src/ must be importable so dxcc.py and postage.py are bundled.
        "--paths", SRC,
        "--hidden-import", "dxcc",
        "--hidden-import", "postage",
        "--hidden-import", "gui",
        "--hidden-import", "webapp",
        "--windowed" if gui else "--console",
        "--version-file", os.path.join(BUILD, "version_info.txt"),
        *data_args,
        *hook_args,
        *icon_args,
        f"--{mode}",
        entry,
    ]
    label = f"{mode}{' (UI)' if gui else ' (web)' if web else ''}"
    print(f"\n--- building {label} ---")
    if subprocess.run(command, cwd=HERE, check=False).returncode != 0:
        print(f"{label} build FAILED")
        return 1

    target = (os.path.join(DIST, f"{name}.exe") if mode == "onefile"
              else os.path.join(DIST, name, f"{name}.exe"))
    if not os.path.isfile(target):
        print(f"build succeeded but {target} is missing")
        return 1
    if mode == "onefile":
        size = os.path.getsize(target) / (1024 * 1024)
        print(f"built {os.path.relpath(target, HERE)}  ({size:.1f} MB)")
    else:
        total = sum(os.path.getsize(os.path.join(root, f))
                    for root, _d, files in os.walk(os.path.dirname(target))
                    for f in files)
        print(f"built {os.path.relpath(target, HERE)}  "
              f"({total / (1024 * 1024):.1f} MB folder)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the adif2xlsx executables")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--onefile", action="store_true",
                       help="build only the single-file executable")
    group.add_argument("--onedir", action="store_true",
                       help="build only the folder executable")
    parser.add_argument("--cli", action="store_true",
                        help="build only the command-line variant")
    parser.add_argument("--gui", action="store_true",
                        help="build only the windowed UI variant")
    parser.add_argument("--web", action="store_true",
                        help="build only the web launcher variant")
    parser.add_argument("--clean", action="store_true",
                        help="remove build/ and dist/ before building")
    args = parser.parse_args()

    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("PyInstaller is required:  pip install pyinstaller")
        return 1

    if not os.path.isfile(ENTRY):
        print(f"entry point not found: {ENTRY}")
        return 1

    if args.clean:
        for folder in (BUILD, DIST):
            if os.path.isdir(folder):
                shutil.rmtree(folder, ignore_errors=True)
                print(f"removed {os.path.relpath(folder, HERE)}")

    os.makedirs(BUILD, exist_ok=True)
    with open(os.path.join(BUILD, "version_info.txt"), "w", encoding="utf-8") as fh:
        fh.write(VERSION_INFO)

    modes = (["onefile"] if args.onefile else
             ["onedir"] if args.onedir else ["onefile", "onedir"])
    variants = (["gui"] if args.gui else
                ["web"] if args.web else
                ["cli"] if args.cli else ["gui", "web", "cli"])
    for variant in variants:
        for mode in modes:
            code = build(mode, variant=variant)
            if code:
                return code

    print("\nBuilds are ready in dist\\.")
    print("  dist\\adif2xlsx-ui.exe           双击：桌面界面（无控制台）")
    print("  dist\\adif2xlsx-web.exe          网页端服务（浏览器打开）")
    print("  dist\\adif2xlsx.exe              命令行")
    print("  dist\\adif2xlsx-ui\\adif2xlsx-ui.exe   桌面界面，文件夹版，启动更快")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
