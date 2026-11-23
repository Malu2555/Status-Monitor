"""Fail CI only when pyright reports more errors than the recorded baseline.

Usage: python scripts/check_pyright_budget.py pyright-current.json pyright-baseline.json
Matches ``pyright --outputjson`` output (summary.errorCount).
"""

import json
import sys


def count(path: str) -> int:
    raw = open(path, "rb").read()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        text = raw.decode("utf-16")  # Windows PowerShell `>` redirect
    else:
        text = raw.decode("utf-8-sig")
    data = json.loads(text)
    # pyright emits {"summary": {"errorCount": N}}, the baseline is flat.
    summary = data.get("summary") or data
    return int(summary.get("errorCount", 0))


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: check_pyright_budget.py <current.json> <baseline.json>")
        return 2
    current = count(sys.argv[1])
    baseline = count(sys.argv[2])
    print(f"pyright errors: current={current} baseline={baseline}")
    if current > baseline:
        print("New type errors were introduced — fix them or update the baseline deliberately.")
        return 1
    print("Type-error budget OK.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
