"""Combine the preregistered 2x2 model-by-interface online-agent summaries."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


CELLS = (
    ("glm-5.1", "raw", "glm51_planar_dev"),
    ("glm-5.1", "skills", "glm51_skills_dev"),
    ("glm-5.2", "raw", "glm52_raw_dev"),
    ("glm-5.2", "skills", "glm52_skills_dev"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--output-csv", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rows = []
    for model, interface, directory in CELLS:
        path = args.input_root / directory / "summary.csv"
        with path.open(encoding="utf-8", newline="") as file:
            source_rows = list(csv.DictReader(file))
        if len(source_rows) != 1:
            raise ValueError(f"expected exactly one summary row in {path}")
        rows.append({"model": model, "interface": interface, **source_rows[0]})
    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.output_csv.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"summary: {args.output_csv.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
