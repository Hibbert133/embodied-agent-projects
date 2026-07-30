"""Validate research-first documentation links and required architecture surfaces."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCUMENTS = (
    ROOT / "README.md",
    ROOT / "RESEARCH_PLAN.md",
    ROOT / "docs/research_question.md",
    ROOT / "docs/architecture.md",
    ROOT / "docs/terminology.md",
    ROOT / "docs/reproduction.md",
    ROOT / "docs/design_review_active_evidence_agent.md",
)
PACKAGES = (
    "rollout",
    "trajectory",
    "diagnosis",
    "uncertainty",
    "probe",
    "reasoning",
    "planner",
    "verification",
    "memory",
    "evaluation",
    "visualization",
)
LINK = re.compile(r"\[[^]]+\]\(([^)]+)\)")


def main() -> int:
    missing = [str(path.relative_to(ROOT)) for path in DOCUMENTS if not path.is_file()]
    missing.extend(
        f"src/{name}/__init__.py"
        for name in PACKAGES
        if not (ROOT / "src" / name / "__init__.py").is_file()
    )
    broken: list[str] = []
    for document in DOCUMENTS:
        if not document.is_file():
            continue
        text = document.read_text(encoding="utf-8")
        for target in LINK.findall(text):
            if "://" in target or target.startswith("#"):
                continue
            path = (document.parent / target.split("#", 1)[0]).resolve()
            if not path.exists():
                broken.append(f"{document.relative_to(ROOT)} -> {target}")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    required = (
        "How can an embodied agent actively acquire diagnostic evidence",
        "Embodied Research Agent",
        "evidence-acquisition decision",
        "verification rollout",
    )
    absent = [phrase for phrase in required if phrase not in readme]
    if missing or broken or absent:
        for item in missing:
            print(f"[FAIL] missing research surface: {item}")
        for item in broken:
            print(f"[FAIL] broken local link: {item}")
        for item in absent:
            print(f"[FAIL] README missing research phrase: {item}")
        return 1
    print("research documentation check: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
