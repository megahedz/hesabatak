#!/usr/bin/env python3
"""TEMPORARY Dart sanity check (no Flutter SDK in this environment):
verifies brace/paren/bracket balance per file, ignoring string literals,
char literals and comments — catches the class of syntax errors that broke
CI before. Prints ALL OK when every file balances."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "mobile" / "lib"
errors = []
files = sorted(ROOT.rglob("*.dart"))
pairs = {")": "(", "]": "[", "}": "{"}

for f in files:
    text = f.read_text(encoding="utf-8")
    stack = []
    i, n = 0, len(text)
    in_line_comment = in_block_comment = in_str = in_char = False
    quote = ""
    while i < n:
        c = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if in_line_comment:
            if c == "\n":
                in_line_comment = False
        elif in_block_comment:
            if c == "*" and nxt == "/":
                in_block_comment = False
                i += 1
        elif in_str:
            if c == "\\":
                i += 1
            elif c == quote:
                in_str = False
        elif in_char:
            if c == "\\":
                i += 1
            elif c == "'":
                in_char = False
        else:
            if c == "/" and nxt == "/":
                in_line_comment = True
                i += 1
            elif c == "/" and nxt == "*":
                in_block_comment = True
                i += 1
            elif c in "\"":
                in_str = True
                quote = c
            elif c == "'":
                in_char = True
            elif c in "([{":
                stack.append((c, i))
            elif c in ")]}":
                if not stack or stack[-1][0] != pairs[c]:
                    errors.append(f"{f.relative_to(ROOT.parent.parent)}:{text.count(chr(10), 0, i) + 1}: unbalanced '{c}'")
                    break
                stack.pop()
        i += 1
    if stack and not errors:
        line = text.count("\n", 0, stack[-1][1]) + 1
        errors.append(f"{f.relative_to(ROOT.parent.parent)}:{line}: unclosed '{stack[-1][0]}'")

for e in errors:
    print("✗", e)
if errors:
    print(f"FAILED: {len(errors)} file(s) with unbalanced delimiters")
    sys.exit(1)
print(f"ALL OK — {len(files)} dart files balanced")
