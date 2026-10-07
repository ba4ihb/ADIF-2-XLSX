#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build the release ZIPs: unpack and run, no Python and no install step.

Three packages, one per front end, plus an all-in-one.  Each contains the
executable, the licence, the README and a short QUICKSTART, and every package is
verified by running the program it ships before the ZIP is written -- a release
that cannot start is worse than no release.

Usage:  python tools/make_release.py [--version v1.0.0]
Writes to release/.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import os
import subprocess
import sys
import zipfile

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(ROOT, "dist")
OUT = os.path.join(ROOT, "release")

#: variant -> (exe name in dist, onedir folder in dist, display name)
VARIANTS = {
    "web": ("adif2xlsx-web.exe", "adif2xlsx-web", "网页版 (web interface)"),
    "ui": ("adif2xlsx-ui.exe", "adif2xlsx-ui", "桌面窗口版 (desktop window)"),
    "cli": ("adif2xlsx.exe", "adif2xlsx", "命令行版 (command line)"),
}

QUICKSTART = """\
ADIF 2 XLSX —— {title}
{underline}

解压即用，不需要安装 Python，不需要联网。

{howto}

--------------------------------------------------------------
文件说明
--------------------------------------------------------------
  {exe}          主程序
{extra_files}
  README.md              完整说明（简体中文）
  README.en.md           Full documentation (English)
  LICENSE                MIT 开源协议

所有时间均为 UTC，不做时区换算。
生成的 Excel 会写明数据来源；单元格为空表示源 ADI 中没有相应数据，
不代表转换出错。

本项目由 DeepSeek Harness + DeepSeek-V4.1-Flash Max 编写。
"""

HOWTO = {
    "web": """\
怎么用
  1. 双击 启动网页版.bat
  2. 会弹出一个黑色命令行窗口，浏览器会自动打开
     —— 转换期间请不要关闭那个窗口
  3. 把 .adi / .adif 文件拖进网页，选好要输出的列，点「开始转换」
  4. Excel 会下载到浏览器的下载目录

注意
  * 这个网页需要本机服务配合才能工作（浏览器无法直接写你的磁盘，
    也不该把你的日志上传到服务器）。服务只监听 127.0.0.1，只有本机能访问。
  * 浏览器没有自动打开？手动访问窗口里显示的地址，形如
    http://127.0.0.1:8000/?token=...  那串 token 每次运行都不一样。
  * 如果 Windows 提示防火墙，允许「专用网络」即可；本程序不联网。
""",
    "ui": """\
怎么用
  1. 双击 {exe}
  2. 把 .adi / .adif 文件（或整个文件夹）拖进窗口
  3. 选好要输出的列，点「开始转换」

输出路径留空则保存到桌面，也可以自己指定。
功能和网页版完全一致 —— 同一份转换代码。
""",
    "cli": """\
怎么用（在终端里）
  {exe} log1.adi log2.adi -o 汇总.xlsx
  {exe} 日志文件夹 -o 汇总.xlsx
  {exe} 日志文件夹 -o 汇总.xlsx --columns required
  {exe} --list-fields              列出所有可输出的列
  {exe} --help                     查看全部选项

退出码
  0 = 成功   1 = 输入无法解析   2 = 参数或输出路径错误
""",
}


def sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_executable(path: str, marker: str = "ADIF") -> bool:
    """Run the program with --help; a release must actually start.

    The marker differs by variant: the command line and desktop builds print the
    ADIF banner, while the web build prints its own usage (``--port``).  The
    output is UTF-8 but the console may decode it differently, so the check looks
    for an ASCII token rather than the Chinese heading.
    """
    try:
        proc = subprocess.run([path, "--help"], capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=300)
    except Exception as exc:                       # noqa: BLE001
        print(f"     verification FAILED to launch: {exc}")
        return False
    text = (proc.stdout or "") + (proc.stderr or "")
    ok = marker in text
    print(f"     --help printed {len(text)} chars, "
          f"marker {marker!r} {'found' if ok else 'MISSING'}")
    return ok


def build_package(variant: str, version: str, onedir: bool) -> str:
    exe_name, folder, title = VARIANTS[variant]
    suffix = "-onedir" if onedir else ""
    zip_name = f"adif2xlsx-{variant}{suffix}-{version}.zip"
    zip_path = os.path.join(OUT, zip_name)
    print(f"\n=== {zip_name} ===")

    if onedir:
        source_dir = os.path.join(DIST, folder)
        if not os.path.isdir(source_dir):
            print(f"     SKIP: {source_dir} is missing")
            return ""
    else:
        source_dir = None
        source_exe = os.path.join(DIST, exe_name)
        if not os.path.isfile(source_exe):
            print(f"     SKIP: {source_exe} is missing")
            return ""

    # Verify the program starts before packaging it.
    marker = "--port" if variant == "web" else "ADIF"
    if onedir:
        if not verify_executable(os.path.join(source_dir, exe_name), marker):
            return ""
    elif not verify_executable(source_exe, marker):
        return ""

    extra_files = ""
    if variant == "web" and not onedir:
        extra_files = "  启动网页版.bat          双击这个开始\n"
    howto = HOWTO[variant].format(exe=exe_name)

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        if onedir:
            for base, _dirs, names in os.walk(source_dir):
                for name in names:
                    full = os.path.join(base, name)
                    rel = os.path.relpath(full, source_dir)
                    zf.write(full, rel)
        else:
            zf.write(source_exe, exe_name)

        # The web launcher, for both web builds.
        if variant == "web":
            launcher = os.path.join(ROOT, "启动网页版.bat")
            if os.path.isfile(launcher):
                zf.writestr(
                    "启动网页版.bat",
                    "@echo off\r\n"
                    "chcp 65001 >nul\r\n"
                    "cd /d \"%~dp0\"\r\n"
                    f"\"%~dp0{exe_name}\"\r\n"
                    "if errorlevel 1 pause\r\n")
                print("     included 启动网页版.bat")

        zf.write(os.path.join(ROOT, "LICENSE"), "LICENSE")
        # Both language versions travel with the package: the ZIP is often the
        # only copy a user has, and the two files link to each other.
        for readme in ("README.md", "README.en.md"):
            path = os.path.join(ROOT, readme)
            if os.path.isfile(path):
                zf.write(path, readme)
        zf.writestr("QUICKSTART.txt",
                    QUICKSTART.format(title=title,
                                      underline="=" * (len(title) + 20),
                                      howto=howto, exe=exe_name,
                                      extra_files=extra_files))
    size = os.path.getsize(zip_path) / (1 << 20)
    print(f"     wrote {zip_name}  ({size:.1f} MB)")
    return zip_name


def build_all_in_one(version: str) -> str:
    """One ZIP holding all six builds, for someone who wants to choose later."""
    zip_name = f"adif2xlsx-all-{version}.zip"
    zip_path = os.path.join(OUT, zip_name)
    print(f"\n=== {zip_name} ===")
    wrote_any = False
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for variant, (exe_name, folder, _title) in VARIANTS.items():
            single = os.path.join(DIST, exe_name)
            if os.path.isfile(single):
                zf.write(single, f"{variant}/{exe_name}")
                wrote_any = True
            onedir = os.path.join(DIST, folder)
            if os.path.isdir(onedir):
                for base, _dirs, names in os.walk(onedir):
                    for name in names:
                        full = os.path.join(base, name)
                        rel = os.path.relpath(full, onedir)
                        zf.write(full, f"{variant}-onedir/{rel}")
                wrote_any = True
        if not wrote_any:
            os.remove(zip_path)
            print("     SKIP: nothing to package")
            return ""
        zf.write(os.path.join(ROOT, "LICENSE"), "LICENSE")
        for readme in ("README.md", "README.en.md"):
            path = os.path.join(ROOT, readme)
            if os.path.isfile(path):
                zf.write(path, readme)
        zf.writestr("QUICKSTART.txt", """\
ADIF 2 XLSX —— 全部版本
======================

这个包里包含三种界面的两种构建：

  web/          网页版（单文件，解压即用）
  web-onedir/   网页版（文件夹版，启动更快）
  ui/           桌面窗口版（单文件）
  ui-onedir/    桌面窗口版（文件夹版，启动更快）
  cli/          命令行版（单文件）
  cli-onedir/   命令行版（文件夹版）

三种界面功能完全一致 —— 同一份转换代码。

选择建议
  * 日常使用：web-onedir/启动网页版.bat  或  ui-onedir/ 里的程序
    （文件夹版启动明显更快；单文件版首次启动要解压，可能等几十秒）
  * 批量或脚本：cli/

所有时间均为 UTC，不做时区换算。
本项目由 DeepSeek Harness + DeepSeek-V4.1-Flash Max 编写。
""")
    size = os.path.getsize(zip_path) / (1 << 20)
    print(f"     wrote {zip_name}  ({size:.1f} MB)")
    return zip_name


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the release ZIPs")
    parser.add_argument("--version", default="v1.0.0")
    args = parser.parse_args()

    if not os.path.isdir(DIST):
        print(f"no dist/ — run build_exe.py first ({DIST})")
        return 2
    os.makedirs(OUT, exist_ok=True)
    # Start from a clean release folder so a stale ZIP cannot be uploaded.
    for name in os.listdir(OUT):
        if name.endswith(".zip") or name == "SHA256SUMS.txt":
            os.remove(os.path.join(OUT, name))

    produced = []
    for variant in VARIANTS:
        produced.append(build_package(variant, args.version, onedir=False))
    for variant in VARIANTS:
        produced.append(build_package(variant, args.version, onedir=True))
    produced.append(build_all_in_one(args.version))

    made = [name for name in produced if name]
    if not made:
        print("\nnothing was packaged — are the executables built?")
        return 1

    print("\n=== SHA256SUMS.txt ===")
    lines = []
    for name in sorted(made):
        path = os.path.join(OUT, name)
        digest = sha256(path)
        lines.append(f"{digest}  {name}")
        print(f"  {digest[:16]}…  {name}")
    with open(os.path.join(OUT, "SHA256SUMS.txt"), "w", encoding="utf-8",
              newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")

    total = sum(os.path.getsize(os.path.join(OUT, n)) for n in made) / (1 << 20)
    print(f"\n{len(made)} package(s), {total:.1f} MB total, in {OUT}")
    print("verify with:  certutil -hashfile <file> SHA256")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
