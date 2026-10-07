"""Language statistics for the README badges.

Counts the lines of each language actually in the repository -- the project
sources, the tests, the tooling and the web front end -- skipping build output,
vendored data and generated files, so the percentages describe what a reader will
find in the tree.
"""

import io
import os
import sys
from collections import Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

#: extension -> language
LANGUAGES = {
    ".py": "Python",
    ".html": "HTML",
    ".bat": "Batchfile",
    ".md": "Markdown",
    ".toml": "TOML",
    ".yml": "YAML",
    ".yaml": "YAML",
    ".css": "CSS",
    ".js": "JavaScript",
    ".txt": "Text",
    ".go": "Go",
    ".json": "JSON",
    ".spec": "Python",
}
#: Directories that are not part of the readable source.
SKIP_DIRS = {".git", "dist", "build", "__pycache__", ".ruff_cache",
             "node_modules", ".github"}
#: Generated files: counting them would double-count the sources.
SKIP_FILES = {"src/dxcc_tables.py", "tools/data/arrl_dxcc_2018.txt",
              "tools/data/arrl_dxcc_2026.txt",
              # The GitHub Pages landing page is documentation, not part of the
              # application; counting it would overstate the HTML share.
              "docs/index.html"}


def main():
    counts = Counter()
    files = Counter()
    for base, dirs, names in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in names:
            path = os.path.join(base, name)
            rel = os.path.relpath(path, ROOT).replace("\\", "/")
            if rel in SKIP_FILES:
                continue
            ext = os.path.splitext(name)[1].lower()
            language = LANGUAGES.get(ext)
            if not language:
                continue
            try:
                text = open(path, encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            lines = sum(1 for line in text.splitlines() if line.strip())
            if not lines:
                continue
            if language in ("Markdown", "Text", "JSON", "YAML", "TOML"):
                # Prose and config are reported but kept out of the code mix.
                counts[f"_{language}"] += lines
                files[f"_{language}"] += 1
                continue
            counts[language] += lines
            files[language] += 1

    prose = {k[1:]: v for k, v in counts.items() if k.startswith("_")}
    code = {k: v for k, v in counts.items() if not k.startswith("_")}
    total = sum(code.values())

    print("=== code languages (share of code lines) ===")
    for language, lines in sorted(code.items(), key=lambda kv: -kv[1]):
        pct = 100.0 * lines / total if total else 0
        print(f"  {language:14} {lines:7} lines  {pct:5.1f}%  "
              f"({files[language]} files)")
    print(f"  {'TOTAL':14} {total:7} lines")

    print()
    print("=== prose and configuration (not part of the code mix) ===")
    for language, lines in sorted(prose.items(), key=lambda kv: -kv[1]):
        print(f"  {language:14} {lines:7} lines  ({files['_' + language]} files)")

    print()
    print("=== shields.io badge values ===")
    for language, lines in sorted(code.items(), key=lambda kv: -kv[1]):
        pct = 100.0 * lines / total if total else 0
        print(f"  {language} {pct:.1f}%")

    return code, total


if __name__ == "__main__":
    main()
