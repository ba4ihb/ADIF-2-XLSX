#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""One place that makes a test suite's output safe on any console.

The suites print Chinese labels, and the CI Windows runners default to a cp1252
console: `print("对方呼号")` then raises UnicodeEncodeError and the suite dies
with a traceback instead of a result.  Two suites had grown their own
TextIOWrapper boilerplate and five had none, which is why CI failed on Windows
and passed locally (a Chinese Windows console is cp936, which encodes the text).

Import this and call :func:`setup_console` before the first print::

    from console_setup import setup_console
    setup_console()
"""

from __future__ import annotations

import io
import sys


def setup_console() -> None:
    """Force stdout/stderr to UTF-8, replacing what cannot be encoded.

    Best effort: when the streams are already UTF-8, are captured objects
    without a buffer, or are detached, there is simply nothing to do.
    """
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        if stream is None:
            continue
        try:
            encoding = (getattr(stream, "encoding", "") or "").lower()
            if encoding.replace("-", "") in ("utf8", "utf_8"):
                continue                      # already fine, leave it alone
            setattr(sys, name, io.TextIOWrapper(
                stream.buffer, encoding="utf-8", errors="replace",
                line_buffering=True))
        except (AttributeError, ValueError, OSError, io.UnsupportedOperation):
            # No .buffer to wrap (an already-wrapped or detached stream).  The
            # reconfigure route is the fallback.
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (AttributeError, ValueError, OSError):
                pass
