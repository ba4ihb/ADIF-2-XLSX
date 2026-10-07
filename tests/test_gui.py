#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the desktop UI and for the "double-click and it vanishes" class of
failure.

The important guarantees here:

  * a windowed (--noconsole) build has ``sys.stdout`` and ``sys.stderr`` set to
    None, so any unguarded write kills the process silently.  The tool must
    tolerate that;
  * started with no arguments a windowed build must open the UI and stay open,
    not exit;
  * starting the UI must never spawn more than one process (an earlier version
    recursed until the machine filled with copies);
  * an unexpected exception must be written to a log file, never swallowed.

Run:  python tests/test_gui.py            (source and UI checks)
      python tests/test_gui.py --with-exe (also drives dist\\adif2xlsx-ui.exe)
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "src")
SCRIPT = os.path.join(SRC, "adif2xlsx.py")
GUI = os.path.join(SRC, "gui.py")
UI_EXE = os.path.join(ROOT, "dist", "adif2xlsx-ui.exe")
CLI_EXE = os.path.join(ROOT, "dist", "adif2xlsx.exe")

sys.path.insert(0, SRC)

FAILURES = []
CHECKS = 0
OUT = tempfile.mkdtemp(prefix="adif2xlsx_gui_")


def check(condition, label, detail=""):
    global CHECKS
    CHECKS += 1
    if condition:
        print(f"  PASS  {label}")
    else:
        print(f"  FAIL  {label}" + (f"  [{detail}]" if detail else ""))
        FAILURES.append(label)


def run(args, timeout=90, env=None, script=SCRIPT):
    merged = dict(os.environ)
    if env:
        merged.update(env)
    # PYTHONIOENCODING: status text contains emoji, which a GBK console code
    # page cannot encode.  Without this the child dies printing its own result.
    merged.setdefault("PYTHONIOENCODING", "utf-8")
    return subprocess.run([sys.executable, script, *args], cwd=ROOT,
                          capture_output=True, text=True, errors="replace",
                          encoding="utf-8", timeout=timeout, check=False,
                          env=merged)


# ---------------------------------------------------------------------------
def test_no_console_tolerance():
    """Every diagnostic path must survive stdout/stderr being None."""
    print("\n=== a windowed build has no console streams ===")
    driver = os.path.join(OUT, "noconsole_driver.py")
    with open(driver, "w", encoding="utf-8") as fh:
        fh.write(
            "import sys, runpy\n"
            "sys.stdout = None\n"
            "sys.stderr = None\n"
            "sys.argv = ['adif2xlsx', 'no-such-file.adi']\n"
            "sys.path.insert(0, r'%s')\n"
            "try:\n"
            "    runpy.run_path(r'%s', run_name='__main__')\n"
            "except SystemExit as exc:\n"
            "    raise SystemExit(exc.code or 0)\n" % (SRC, SCRIPT))
    proc = subprocess.run([sys.executable, driver], cwd=ROOT, capture_output=True,
                          text=True, errors="replace", timeout=90, check=False)
    check("AttributeError" not in proc.stderr,
          "a missing console never raises AttributeError", proc.stderr[-160:])
    check(proc.returncode in (1, 2),
          "a missing input still reports through the exit code",
          f"rc={proc.returncode}")

    # Same, for a failure deep inside the parser rather than the CLI.
    driver2 = os.path.join(OUT, "noconsole_driver2.py")
    junk = os.path.join(OUT, "junk.adi")
    with open(junk, "wb") as fh:
        fh.write(b"<<<>>>" + bytes(range(256)) + b"<EOR>")
    with open(driver2, "w", encoding="utf-8") as fh:
        fh.write(
            "import sys, runpy\n"
            "sys.stdout = None\n"
            "sys.stderr = None\n"
            "sys.argv = ['adif2xlsx', r'%s', '-o', r'%s']\n"
            "sys.path.insert(0, r'%s')\n"
            "try:\n"
            "    runpy.run_path(r'%s', run_name='__main__')\n"
            "except SystemExit as exc:\n"
            "    raise SystemExit(exc.code or 0)\n"
            % (junk, os.path.join(OUT, "junk.xlsx"), SRC, SCRIPT))
    proc = subprocess.run([sys.executable, driver2], cwd=ROOT, capture_output=True,
                          text=True, errors="replace", timeout=90, check=False)
    check("Traceback" not in proc.stderr,
          "a damaged input raises no traceback without a console",
          proc.stderr[-160:])


def test_crash_logging():
    """An unexpected exception must land in the log, not disappear."""
    print("\n=== crash logging ===")
    import adif2xlsx as core

    path = core.log_path()
    check(os.path.isabs(path) and path.endswith(".log"),
          "the log path is absolute", path)

    import importlib
    importlib.reload(core)
    before = os.path.getsize(path) if os.path.exists(path) else 0

    def boom():
        raise ValueError("deliberate failure for the test")

    code = core.main_guard(boom)
    after = os.path.getsize(path) if os.path.exists(path) else 0
    check(code == 1, "main_guard reports failure as exit code 1", str(code))
    check(after > before, "main_guard appended the crash to the log")
    with open(path, encoding="utf-8") as fh:
        tail = fh.read()[-2000:]
    check("deliberate failure for the test" in tail,
          "the log names the actual exception")

    check(core.main_guard(lambda: 0) == 0, "main_guard passes a success through")

    def exit_with(code_):
        raise SystemExit(code_)

    try:
        core.main_guard(lambda: exit_with(7))
        check(False, "main_guard lets SystemExit through untouched")
    except SystemExit as exc:
        check(exc.code == 7, "main_guard lets SystemExit through untouched")


def test_dispatch():
    """The no-argument rule: GUI without a console, usage with one."""
    print("\n=== startup dispatch ===")
    proc = run([])
    check(proc.returncode == 2 and "usage" in proc.stdout.lower(),
          "no arguments with a console prints usage", f"rc={proc.returncode}")

    proc = run(["--help"])
    check("--gui" in proc.stdout, "--help documents --gui")

    # With a console, --gui is honoured by loading the UI module.
    probe = os.path.join(OUT, "dispatch_probe.py")
    with open(probe, "w", encoding="utf-8") as fh:
        fh.write(
            "import sys\n"
            "sys.path.insert(0, r'%s')\n"
            "import adif2xlsx as core\n"
            "calls = []\n"
            "core.launch_gui = lambda extra=None: (calls.append(list(extra or [])),\n"
            "                                     0)[1]\n"
            "print('empty  ->', core.entry([]), calls)\n"
            "print('gui    ->', core.entry(['--gui']), calls)\n"
            "print('selft  ->', core.entry(['--self-test']), calls)\n"
            "print('gui+st ->', core.entry(['--gui', '--self-test']), calls)\n"
            "print('file   ->', core.entry([r'%s']))\n" % (SRC, SCRIPT))
    proc = subprocess.run([sys.executable, probe], cwd=ROOT, capture_output=True,
                          text=True, errors="replace", timeout=90, check=False,
                          env=dict(os.environ, ADIF2XLSX_UI_CHILD=""))
    out = proc.stdout
    # entry([]) has a console here, so it prints help rather than the GUI.
    check("empty  -> 2 []" in out,
          "no arguments with a console does not open the UI", out[-400:])
    check("gui    -> 0 [[]]" in out,
          "--gui alone opens the UI with no extra flags", out[-400:])
    check("selft  -> 0 [[], ['--self-test']]" in out,
          "--self-test reaches the UI module", out[-400:])
    check("gui+st -> 0 [[], ['--self-test'], ['--self-test']]" in out,
          "--gui --self-test reaches the UI module with the flag intact",
          out[-400:])


def test_no_spawn_loop():
    """Starting the UI must never fork copies of itself."""
    print("\n=== the UI must not spawn copies ===")
    import adif2xlsx as core

    marker = core.SPAWN_MARKER
    check(isinstance(marker, str) and marker,
          "a spawn marker constant exists", repr(marker))

    # Simulate a build where gui.py cannot be found: launch_gui must refuse to
    # spawn again rather than recurse.
    probe = os.path.join(OUT, "spawn_probe.py")
    with open(probe, "w", encoding="utf-8") as fh:
        fh.write(
            "import sys, os\n"
            "sys.path.insert(0, r'%s')\n"
            "import adif2xlsx as core\n"
            "core._load_gui_module = lambda: None\n"
            "os.environ[core.SPAWN_MARKER] = '1'\n"
            "code = core.launch_gui(['--self-test'])\n"
            "print('exit', code)\n" % SRC)
    proc = subprocess.run([sys.executable, probe], cwd=ROOT, capture_output=True,
                          text=True, errors="replace", timeout=60, check=False)
    check("exit 3" in proc.stdout,
          "with no UI module and the marker set it stops instead of forking",
          proc.stdout[-200:] + proc.stderr[-200:])


def test_no_blocking_dialog():
    """An error must never open a modal dialog that nobody can dismiss.

    An earlier version showed one even from a console build, which hung test
    runs and scheduled tasks forever.
    """
    print("\n=== errors must not block on a dialog ===")
    probe = os.path.join(OUT, "dialog_probe.py")
    with open(probe, "w", encoding="utf-8") as fh:
        fh.write(
            "import sys, os, time\n"
            "sys.path.insert(0, r'%s')\n"
            "import adif2xlsx as core\n"
            "calls = []\n"
            "core.messagebox = None  # not imported unless a dialog is wanted\n"
            "import tkinter\n"
            "tkinter.Tk = lambda *a, **k: (_ for _ in ()).throw(\n"
            "    RuntimeError('a dialog was opened'))\n"
            "start = time.time()\n"
            "core._show_error_dialog('t', 'body')      # console present -> no dialog\n"
            "print('with_console_elapsed', round(time.time() - start, 3))\n"
            "sys.stdout = None\n"
            "sys.stderr = None\n"
            "os.environ['ADIF2XLSX_NO_DIALOG'] = '1'\n"
            "core._show_error_dialog('t', 'body')      # suppressed by the flag\n"
            "print('ok')\n" % SRC)
    proc = subprocess.run([sys.executable, probe], cwd=ROOT, capture_output=True,
                          text=True, errors="replace", timeout=30, check=False)
    check("with_console_elapsed" in proc.stdout,
          "a console build returns immediately instead of opening a dialog",
          proc.stdout[-200:] + proc.stderr[-200:])
    check("RuntimeError: a dialog was opened" not in proc.stdout + proc.stderr,
          "no dialog was constructed when a console exists",
          proc.stdout[-200:])

    # And the real command-line path must finish quickly on a bad input.
    bad = os.path.join(OUT, "blocking.adi")
    with open(bad, "wb") as fh:
        fh.write(bytes(range(32)) + b"\xff\xfe garbage")
    start = time.time()
    proc = run([bad, "-o", os.path.join(OUT, "blocking.xlsx")], timeout=60)
    elapsed = time.time() - start
    check(elapsed < 30, "a bad input fails fast rather than hanging",
          f"{elapsed:.1f}s")
    check(proc.returncode == 1, "a bad input exits 1", f"rc={proc.returncode}")


def test_gui_self_test_source():
    """The window must build and lay out from source."""
    print("\n=== UI self-test (from source) ===")
    marker = os.path.join(OUT, "marker_source.txt")
    if os.path.exists(marker):
        os.remove(marker)
    proc = run(["--self-test"], env={"ADIF2XLSX_GUI_MARKER": marker}, timeout=120)
    check(proc.returncode == 0, "the UI self-test exits 0", f"rc={proc.returncode}")
    text = open(marker, encoding="utf-8").read() if os.path.exists(marker) else ""
    check("gui self-test ok" in text, "the window reports a usable size", text.strip())


def test_gui_widgets():
    """The window's controls must be present and wired up."""
    print("\n=== UI controls ===")
    probe = os.path.join(OUT, "widget_probe.py")
    with open(probe, "w", encoding="utf-8") as fh:
        fh.write(
            "import sys, tkinter as tk\n"
            "sys.path.insert(0, r'%s')\n"
            "import gui\n"
            "root = tk.Tk()\n"
            "app = gui.AdifApp(root)\n"
            "root.update_idletasks()\n"
            "print('list', app.listbox.size())\n"
            "print('default_out_absolute', __import__('os').path.isabs(app.output_var.get()))\n"
            "print('has_button', app.button is not None)\n"
            "print('recursive_default', app.recursive_var.get())\n"
            "app._add([r'%s'])\n"
            "print('after_add', app.listbox.size())\n"
            "app.listbox.selection_set(0)\n"
            "app.remove_selected()\n"
            "print('after_remove', app.listbox.size())\n"
            "root.destroy()\n" % (SRC, SCRIPT))
    proc = subprocess.run([sys.executable, probe], cwd=ROOT, capture_output=True,
                          text=True, errors="replace", encoding="utf-8",
                          timeout=120, check=False,
                          env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    out = proc.stdout
    for expected, label in (
            ("list 0", "the file list starts empty"),
            ("default_out_absolute True", "the output box starts on the Desktop"),
            ("has_button True", "the convert button exists"),
            ("recursive_default False", "sub-folders are off by default"),
            ("after_add 1", "adding a file shows it"),
            ("after_remove 0", "removing the selection clears it")):
        check(expected in out, label, out[-200:] or proc.stderr[-200:])


def test_field_picker_scrolling():
    """A long field list must scroll, and must never show blank space.

    Two defects lived here: a global wheel binding scrolled the list from
    anywhere in the dialog, and binding <Configure> twice overwrote the handler
    that sets the scroll region, leaving the list unscrollable.
    """
    print("\n=== field picker scrolling ===")
    probe = os.path.join(OUT, "scroll_probe.py")
    with open(probe, "w", encoding="utf-8") as fh:
        fh.write(
            "import io, os, sys, tkinter as tk\n"
            "sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8',\n"
            "                              errors='replace')\n"
            "sys.path.insert(0, r'%s')\n"
            "import adif2xlsx as core\n"
            "import gui\n"
            "available = list(core.REQUIRED_COLUMNS) + [\n"
            "    f'APP_TEST_{i:02d}' for i in range(40)] + ['COMMENT', 'NAME']\n"
            "root = tk.Tk()\n"
            "gui.AdifApp(root)\n"
            "picker = gui.FieldPicker(root, available, None,\n"
            "                         list(core.REQUIRED_COLUMNS), lambda c: None)\n"
            "picker.update()\n"
            "root.update_idletasks()\n"
            "canvas = None\n"
            "for child in picker.winfo_children():\n"
            "    for sub in child.winfo_children():\n"
            "        if isinstance(sub, tk.Canvas) and sub.winfo_height() > 100:\n"
            "            canvas = sub\n"
            "if canvas is None:\n"
            "    print('NO_CANVAS')\n"
            "    sys.stdout.flush(); os._exit(1)\n"
            "region = canvas.cget('scrollregion')\n"
            "print('scrollregion', repr(region))\n"
            "bbox = canvas.bbox('all')\n"
            "content = bbox[3] - bbox[1]\n"
            "viewport = canvas.winfo_height()\n"
            "print('content', content, 'viewport', viewport)\n"
            "canvas.yview_moveto(1.0); picker.update()\n"
            "top, bottom = canvas.yview()\n"
            "print('at_end', round(top, 3), round(bottom, 3))\n"
            "for _ in range(40):\n"
            "    canvas.yview_scroll(-3, 'units')\n"
            "picker.update()\n"
            "top2, bottom2 = canvas.yview()\n"
            "print('at_start', round(top2, 3), round(bottom2, 3))\n"
            "print('ratio', round(viewport / content, 3),\n"
            "      'fraction', round(bottom2 - top2, 3))\n"
            "sys.stdout.flush(); os._exit(0)\n" % SRC)
    proc = subprocess.run([sys.executable, probe], cwd=ROOT, capture_output=True,
                          text=True, errors="replace", encoding="utf-8",
                          timeout=120, check=False,
                          env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    out = proc.stdout
    # A scroll region of "0 0 <w> <height>" with a height larger than the
    # viewport is what makes the list scrollable at all.
    region_height = None
    for line in out.splitlines():
        if line.startswith("scrollregion"):
            parts = line.split("'")[1].split()
            if len(parts) == 4:
                region_height = int(parts[3])
    check(region_height is not None and region_height > 400,
          "the canvas has a real scroll region larger than the viewport",
          out[:200])
    check("at_end" in out and " 1.0" in out.split("at_end")[1].split(chr(10))[0],
          "scrolling reaches the end", out[-200:])
    check("at_start 0.0" in out,
          "scrolling returns to the start", out[-200:])
    # The visible fraction must match the viewport/content ratio, which is what
    # stops the last screen from showing empty space.
    ratio = fraction = None
    for line in out.splitlines():
        if line.startswith("ratio"):
            parts = line.split()
            ratio, fraction = float(parts[1]), float(parts[3])
    check(ratio is not None and abs(ratio - fraction) < 0.01,
          "the view fraction matches the viewport, so no blank area shows",
          f"ratio={ratio} fraction={fraction}")


def test_gui_conversion():
    """The UI's worker must actually produce a workbook."""
    print("\n=== UI conversion path ===")
    probe = os.path.join(OUT, "convert_probe.py")
    sample = os.path.join(ROOT, "tests", "fixtures", "samples", "sample_log.adi")
    output = os.path.join(OUT, "ui_out.xlsx")
    if os.path.exists(output):
        os.remove(output)
    with open(probe, "w", encoding="utf-8") as fh:
        fh.write(
            "import sys, io, os, time, tkinter as tk\n"
            # Report through a UTF-8 stream: the status line contains emoji and
            # a GBK console code page cannot encode it.
            "sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8',\n"
            "                              errors='replace')\n"
            "sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8',\n"
            "                              errors='replace')\n"
            "sys.path.insert(0, r'%s')\n"
            "import gui\n"
            "# Replace the modal dialogs so a failure cannot block the run.\n"
            "import tkinter.messagebox as mb\n"
            "seen = []\n"
            "mb.showinfo = lambda *a, **k: seen.append(('info', str(a)[:200]))\n"
            "mb.showerror = lambda *a, **k: seen.append(('error', str(a)[:200]))\n"
            "gui.messagebox = mb\n"
            "root = tk.Tk()\n"
            "try:\n"
            "    app = gui.AdifApp(root)\n"
            "    app.paths = [r'%s']\n"
            "    app.output_var.set(r'%s')\n"
            "    app.open_var.set(False)\n"
            "    app.start()\n"
            "    deadline = time.time() + 90\n"
            "    while app.busy and time.time() < deadline:\n"
            "        root.update()\n"
            "        app._drain()\n"
            "        time.sleep(0.05)\n"
            "    print('busy', app.busy)\n"
            "    print('status', app.status.cget('text'))\n"
            "    print('dialogs', seen)\n"
            "finally:\n"
            "    # An open Tk root blocks interpreter shutdown, so a crash above\n"
            "    # would hang the parent instead of failing the test.\n"
            "    try:\n"
            "        root.destroy()\n"
            "    except tk.TclError:\n"
            "        pass\n"
            "    sys.stdout.flush()\n"
            "    sys.stderr.flush()\n"
            "    os._exit(0)\n" % (SRC, sample, output))
    proc = subprocess.run([sys.executable, probe], cwd=ROOT, capture_output=True,
                          text=True, errors="replace", encoding="utf-8",
                          timeout=180, check=False,
                          env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    check(os.path.exists(output), "the UI wrote a workbook",
          proc.stdout[-200:] + proc.stderr[-200:])
    if os.path.exists(output):
        from openpyxl import load_workbook
        book = load_workbook(output)
        check("QSOs" in book.sheetnames and "Summary" in book.sheetnames,
              "the workbook has the expected sheets", str(book.sheetnames))
        rows = book["QSOs"].max_row - 1
        check(rows > 0, f"the workbook has records ({rows})")
    check("busy False" in proc.stdout, "the UI returns to an idle state after work",
          proc.stdout[-200:])


def test_exe():
    """The packaged UI executable: no console, no arguments, stays open."""
    print("\n=== packaged UI executable ===")
    if not os.path.isfile(UI_EXE):
        print(f"  SKIP  {os.path.relpath(UI_EXE, ROOT)} not built")
        return
    if os.name != "nt":
        print("  SKIP  windowed-launch checks are Windows-specific")
        return

    import ctypes

    marker = os.path.join(OUT, "marker_exe.txt")
    if os.path.exists(marker):
        os.remove(marker)

    def launch(args, wait):
        env = dict(os.environ, ADIF2XLSX_GUI_MARKER=marker)
        return subprocess.Popen([UI_EXE, *args], cwd=ROOT, env=env,
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)


    def _child_pids(root_pid):
        """Every live process whose ancestry includes root_pid.

        Counting by image name is unreliable: a PyInstaller --onefile build runs
        a bootloader parent plus a child, and the child's reported details vary.
        Walking the parent links is exact.
        """
        TH32CS_SNAPPROCESS = 0x00000002

        class PROCESSENTRY32(ctypes.Structure):
            _fields_ = [("dwSize", ctypes.c_ulong),
                        ("cntUsage", ctypes.c_ulong),
                        ("th32ProcessID", ctypes.c_ulong),
                        ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
                        ("th32ModuleID", ctypes.c_ulong),
                        ("cntThreads", ctypes.c_ulong),
                        ("th32ParentProcessID", ctypes.c_ulong),
                        ("pcPriClassBase", ctypes.c_long),
                        ("dwFlags", ctypes.c_ulong),
                        ("szExeFile", ctypes.c_char * 260)]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        parents = {}
        entry = PROCESSENTRY32()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32)
        if kernel32.Process32First(snapshot, ctypes.byref(entry)):
            while True:
                parents[int(entry.th32ProcessID)] = int(entry.th32ParentProcessID)
                if not kernel32.Process32Next(snapshot, ctypes.byref(entry)):
                    break
        kernel32.CloseHandle(snapshot)

        live = set(parents)
        family = set()
        for pid in live:
            seen = set()
            cursor = pid
            while cursor and cursor not in seen:
                seen.add(cursor)
                if cursor == root_pid:
                    family.add(pid)
                    break
                cursor = parents.get(cursor, 0)
        return family

    def _visible_windows(pids):
        """Visible top-level windows owned by any of ``pids``.

        This is the check that matches the user's complaint: a build that dies
        on startup leaves no window behind.  Counting processes is unreliable
        here, because a --onefile build re-launches itself and the bootloader's
        process lifecycle varies between runs.
        """
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        found = []
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p,
                                        ctypes.c_void_p)

        def callback(hwnd, _param):
            if not user32.IsWindowVisible(hwnd):
                return True
            owner = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
            if owner.value in pids:
                length = user32.GetWindowTextLengthW(hwnd)
                buffer = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buffer, length + 1)
                found.append((owner.value, buffer.value))
            return True

        user32.EnumWindows(WNDENUMPROC(callback), None)
        return found

    def instances_for(popen):
        """The live processes making up this launch, parent included."""
        family = _child_pids(popen.pid)
        if popen.poll() is None:
            family.add(popen.pid)
        return family

    # 1. self-test through the packaged build
    proc = launch(["--self-test"], wait=True)
    proc.wait(timeout=120)
    check(proc.returncode == 0, "the packaged UI self-test exits 0",
          f"rc={proc.returncode}")
    text = open(marker, encoding="utf-8").read() if os.path.exists(marker) else ""
    check("gui self-test ok" in text, "the packaged window reports a usable size",
          text.strip())

    # 2. genuine double-click: no arguments, must open a real window and keep it
    proc = launch([], wait=False)
    # A packaged first window takes several seconds to appear: the bootloader
    # unpacks, then Tcl/Tk initialises.  Poll rather than guess.
    deadline = time.time() + 60
    windows = []
    while time.time() < deadline:
        time.sleep(3)
        if proc.poll() is not None:
            break
        windows = [(pid, title) for pid, title in _visible_windows(instances_for(proc))
                   if title.startswith("ADIF")]
        if windows:
            break
    alive = proc.poll() is None
    early = instances_for(proc)
    check(alive, "a windowed build with no arguments stays open (no 闪退)",
          f"exited with {proc.poll()}")
    check(bool(windows), "the UI window is actually on screen",
          f"windows={windows}")
    # It must still be there a few seconds later, owned by a bounded number of
    # processes.  An earlier version forked a fresh copy until the machine was
    # full; another opened no window at all.
    time.sleep(8)
    late = instances_for(proc)
    still = [(pid, title) for pid, title in _visible_windows(late)
             if title.startswith("ADIF")]
    check(proc.poll() is None and bool(still),
          "the window is still open after several seconds",
          f"alive={proc.poll() is None} windows={still}")
    check(1 <= len(late) <= 3,
          "opening the UI spawns a bounded number of processes, not a storm",
          f"after 6s={sorted(early)} after 14s={sorted(late)}")
    if alive:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
    time.sleep(1)
    if alive:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()

    # 3. a genuine failure must not vanish either
    bad = os.path.join(OUT, "bad_exe.adi")
    with open(bad, "wb") as fh:
        fh.write(b"\x00\x01\x02 not adif at all \xff\xfe")
    proc = subprocess.run([UI_EXE, bad, "--quiet"], cwd=ROOT,
                          capture_output=True, text=True, errors="replace",
                          timeout=120, check=False)
    check(proc.returncode != 0, "an unreadable input fails with a non-zero code",
          f"rc={proc.returncode}")
    check("Traceback" not in proc.stderr, "the failure is reported, not dumped",
          proc.stderr[-160:])


def test_cli_exe_still_console():
    """The command-line build keeps working for scripting."""
    print("\n=== packaged command-line executable ===")
    if not os.path.isfile(CLI_EXE) or os.name != "nt":
        print("  SKIP  dist\\adif2xlsx.exe not built, or not Windows")
        return
    sample = os.path.join(ROOT, "tests", "fixtures", "samples", "sample_log.adi")
    output = os.path.join(OUT, "cli_out.xlsx")
    if os.path.exists(output):
        os.remove(output)
    proc = subprocess.run([CLI_EXE, sample, "-o", output, "--quiet"], cwd=ROOT,
                          capture_output=True, text=True, errors="replace",
                          timeout=180, check=False)
    check(proc.returncode == 0, "the console build converts without a UI",
          f"rc={proc.returncode} {proc.stderr[-120:]}")
    check(os.path.exists(output), "the console build wrote the workbook")



def has_display() -> bool:
    """Can a Tk window actually be opened here?

    False on a headless Linux runner, where the desktop UI cannot be tested at
    all.  Probing beats guessing from the platform: a Windows session without a
    desktop (a service, say) also cannot open one.
    """
    if os.environ.get("ADIF2XLSX_NO_GUI_TESTS"):
        return False
    try:
        import tkinter
    except ImportError:
        return False
    try:
        root = tkinter.Tk()
    except Exception:                               # noqa: BLE001 - any Tk/display error
        return False
    root.destroy()
    return True


def main() -> int:
    if not has_display():
        print("  SKIP  no display available, so the desktop UI cannot "
              "be tested here (the window never opens)")
        return 0
    parser = argparse.ArgumentParser(description="Test the UI and the no-console paths")
    parser.add_argument("--with-exe", action="store_true",
                        help="also drive the packaged executables")
    args = parser.parse_args()

    test_no_console_tolerance()
    test_crash_logging()
    test_dispatch()
    test_no_spawn_loop()
    test_no_blocking_dialog()
    test_gui_self_test_source()
    test_gui_widgets()
    test_field_picker_scrolling()
    test_gui_conversion()
    if args.with_exe:
        test_exe()
        test_cli_exe_still_console()

    print(f"\n{'=' * 62}")
    print(f"checks: {CHECKS}   failures: {len(FAILURES)}")
    for item in FAILURES:
        print(f"  - {item}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    raise SystemExit(main())
