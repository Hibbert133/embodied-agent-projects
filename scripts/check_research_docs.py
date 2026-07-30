"""Validate research-first documentation links and required architecture surfaces."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCUMENTS = (
    ROOT / "README.md",
    ROOT / "RESEARCH_PLAN.md",
    ROOT / "docs/problem_definition.md",
    ROOT / "docs/agent_architecture.md",
    ROOT / "docs/experiment_plan.md",
    ROOT / "docs/research_question.md",
    ROOT / "docs/architecture.md",
    ROOT / "docs/terminology.md",
    ROOT / "docs/reproduction.md",
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
    texts = {path: path.read_text(encoding="utf-8") for path in DOCUMENTS}
    readme = texts[ROOT / "README.md"]
    required_by_document = {
        ROOT / "README.md": (
            "Active Evidence Acquisition for Self-Improving Embodied Agents",
            "Causal information boundary",
            "Current empirical evidence",
            "面向自改进具身智能体的主动证据获取",
        ),
        ROOT / "docs/problem_definition.md": (
            "Research question",
            "Failure taxonomy",
            "Why passive diagnosis is insufficient",
        ),
        ROOT / "docs/agent_architecture.md": (
            "Rollout",
            "Failure Detection",
            "Evidence Manager",
            "Probe Selection",
            "Diagnosis",
            "Correction",
            "Verification",
            "Memory",
        ),
        ROOT / "docs/experiment_plan.md": (
            "Baseline agents",
            "Failure types",
            "Probe types",
            "Metrics",
            "Expected experiments",
        ),
    }
    absent = [
        f"{path.relative_to(ROOT)}: {phrase}"
        for path, phrases in required_by_document.items()
        for phrase in phrases
        if phrase not in texts[path]
    ]
    mojibake_markers = ("â€", "ï¼", "ä¸", "ç ", "å…")
    mojibake = [
        str(path.relative_to(ROOT))
        for path, text in texts.items()
        if any(marker in text for marker in mojibake_markers)
    ]
    if missing or broken or absent or mojibake:
        for item in missing:
            print(f"[FAIL] missing research surface: {item}")
        for item in broken:
            print(f"[FAIL] broken local link: {item}")
        for item in absent:
            print(f"[FAIL] research document missing phrase: {item}")
        for item in mojibake:
            print(f"[FAIL] mojibake marker in research document: {item}")
        return 1
    print("research documentation check: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
