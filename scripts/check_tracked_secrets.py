"""Fail if Git-tracked text contains a value shaped like an API credential."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RULES = {
    "provider_key_prefix": re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}"),
    "assigned_api_key": re.compile(
        r"(?:ANTHROPIC_API_KEY|OPENAI_API_KEY)\s*[:=]\s*[\"']?[A-Za-z0-9_-]{24,}",
        re.IGNORECASE,
    ),
}


def find_secret_rule(text: str) -> str | None:
    for name, pattern in RULES.items():
        if pattern.search(text):
            return name
    return None


def tracked_files() -> list[Path]:
    result = subprocess.run(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return [ROOT / item.decode("utf-8") for item in result.stdout.split(b"\0") if item]


def main() -> int:
    failures: list[tuple[Path, str]] = []
    for path in tracked_files():
        try:
            data = path.read_bytes()
        except OSError:
            continue
        if b"\0" in data:
            continue
        rule = find_secret_rule(data.decode("utf-8", errors="replace"))
        if rule is not None:
            failures.append((path.relative_to(ROOT), rule))
    if failures:
        for path, rule in failures:
            print(f"[FAIL] possible credential: {path} rule={rule}", file=sys.stderr)
        return 1
    print("tracked-secret scan: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
