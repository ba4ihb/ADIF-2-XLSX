# -*- coding: utf-8 -*-
"""PyInstaller runtime hook for the windowed UI build.

The bundled program cannot reliably tell whether it has a console: when Windows
starts it by double-click it has none, but when a parent process that has a
console starts it, the standard handles are inherited and ``sys.stdout`` is not
None.  Trusting that test silently sent the UI build down the command-line path,
so double-clicking appeared to do nothing, or to flash and vanish.

This hook runs inside the frozen application, before the program itself, and
declares the build's intent once so the dispatch logic does not have to guess.
Do not clear sys.stdout/sys.stderr here: the UI build still serves the command
line when it is given arguments, and those diagnostics should reach the parent
when there is somewhere to write them.

Referenced by build_exe.py only for the --windowed build.
"""

import os

os.environ["ADIF2XLSX_UI_BUILD"] = "1"
