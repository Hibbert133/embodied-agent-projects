"""Render ProbeMem-Online development figures from real run artifacts."""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.analyze_online_memory import analyze  # noqa: E402


DISPLAY = {
    "ALWAYS_COMPENSATION": "Always compensation",
    "ALWAYS_RETRY": "Always retry",
    "FROZEN_VARIANCE_RULE": "Frozen variance rule",
    "STATELESS_GLM": "Stateless GLM",
    "GLM_FROZEN_BOOTSTRAP_MEMORY": "GLM + frozen memory",
    "GLM_ONLINE_ACTION_MEMORY": "GLM + online memory",
    "GLM_ONLINE_MEMORY_RESONANCE": "Full resonance Agent",
    "EVALUATOR_ONLY_ORACLE": "Oracle audit",
}


def render(run_dir: Path) -> list[Path]:
    figures = run_dir / "figures"
    figures.mkdir(exist_ok=True)
    decisions = _csv(run_dir / "decisions.csv")
    audit = _json(run_dir / "api_audit.json", [])
    summary = analyze(run_dir)
    paths = [
        _rolling(decisions, figures / "rolling_recovery.png"),
        _memory_changes(summary, figures / "memory_decision_changes.png"),
        _latency(audit, figures / "api_latency_by_method.png"),
    ]
    return paths


def _rolling(rows: list[dict[str, str]], path: Path) -> Path:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        if row["method"] in DISPLAY:
            grouped[row["method"]].append(row)
    image, draw, box = _canvas("Rolling accepted recovery (%)")
    colors = ("#264653", "#2a9d8f", "#e9c46a", "#f4a261", "#e76f51", "#457b9d", "#8338ec", "#111111")
    legend: list[tuple[str, str]] = []
    for color, (method, items) in zip(colors, grouped.items()):
        items.sort(key=lambda row: int(row["episode_id"]))
        accepted = np.asarray([row["verification_status"] == "ACCEPTED" for row in items], dtype=float)
        window = min(10, len(accepted))
        if not window:
            continue
        rolling = np.convolve(accepted, np.ones(window) / window, mode="valid")
        points = [_point(index, value * 100, 1, max(60, len(accepted)), 0, 100, box)
                  for index, value in zip(range(window, len(accepted) + 1), rolling)]
        if len(points) > 1:
            draw.line(points, fill=color, width=3)
        legend.append((DISPLAY[method], color))
    _axes(draw, box, "Operational episode index", "Accepted recovery (%)")
    _legend(draw, legend, box)
    image.save(path, dpi=(180, 180))
    return path


def _memory_changes(summary: dict, path: Path) -> Path:
    changes = summary["full_vs_stateless_changes"]
    names = ["Helpful", "Harmful", "Status tie"]
    values = [changes["helpful"], changes["harmful"], changes["tie"]]
    image, draw, box = _canvas(f"Full vs stateless decisions (n={summary['operational_cases']})")
    _bars(draw, box, names, values, ["#2a9d8f", "#e76f51", "#8d99ae"], "Changed-action cases")
    image.save(path, dpi=(180, 180))
    return path


def _latency(rows: list[dict], path: Path) -> Path:
    grouped: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        grouped[str(row["method"])].append(float(row["latency_ms"]) / 1000.0)
    methods = list(grouped)
    medians = [float(np.median(grouped[name])) for name in methods]
    p90 = [float(np.quantile(grouped[name], 0.9, method="higher")) for name in methods]
    image, draw, box = _canvas("GLM API latency by method")
    labels = [DISPLAY.get(name, name).replace("GLM + ", "") for name in methods]
    _bars(draw, box, labels, medians, ["#457b9d"] * len(labels), "Median latency (s)")
    maximum = max(p90 + medians + [1.0])
    for index, value in enumerate(p90):
        x = box[0] + (index + 0.5) * (box[2] - box[0]) / len(labels)
        y = box[3] - value / maximum * (box[3] - box[1])
        draw.ellipse((x - 5, y - 5, x + 5, y + 5), fill="#e63946")
    draw.text((box[2] - 150, box[1] + 5), "red dot: p90", fill="#e63946")
    image.save(path, dpi=(180, 180))
    return path


def _canvas(title: str) -> tuple[Image.Image, ImageDraw.ImageDraw, tuple[int, int, int, int]]:
    image = Image.new("RGB", (1400, 800), "white")
    draw = ImageDraw.Draw(image)
    draw.text((80, 30), title, fill="#111111", font=ImageFont.load_default(size=26))
    return image, draw, (110, 100, 1320, 650)


def _axes(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], xlabel: str, ylabel: str) -> None:
    draw.line((box[0], box[1], box[0], box[3]), fill="#222222", width=2)
    draw.line((box[0], box[3], box[2], box[3]), fill="#222222", width=2)
    for value in range(0, 101, 20):
        y = box[3] - value / 100 * (box[3] - box[1])
        draw.line((box[0], y, box[2], y), fill="#dddddd", width=1)
        draw.text((55, y - 8), str(value), fill="#333333")
    draw.text(((box[0] + box[2]) // 2 - 80, box[3] + 70), xlabel, fill="#222222")
    draw.text((10, box[1] - 25), ylabel, fill="#222222")


def _point(x: float, y: float, xmin: float, xmax: float, ymin: float, ymax: float,
           box: tuple[int, int, int, int]) -> tuple[float, float]:
    return (box[0] + (x - xmin) / (xmax - xmin) * (box[2] - box[0]),
            box[3] - (y - ymin) / (ymax - ymin) * (box[3] - box[1]))


def _legend(draw: ImageDraw.ImageDraw, items: list[tuple[str, str]], box: tuple[int, int, int, int]) -> None:
    for index, (label, color) in enumerate(items):
        x = box[0] + (index % 4) * 300
        y = box[3] + 105 + (index // 4) * 25
        draw.line((x, y + 6, x + 24, y + 6), fill=color, width=4)
        draw.text((x + 30, y), label, fill="#222222")


def _bars(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], labels: list[str], values: list[float],
          colors: list[str], ylabel: str) -> None:
    maximum = max(values + [1.0]) * 1.1
    width = (box[2] - box[0]) / max(1, len(labels))
    draw.line((box[0], box[1], box[0], box[3]), fill="#222222", width=2)
    draw.line((box[0], box[3], box[2], box[3]), fill="#222222", width=2)
    draw.text((10, box[1] - 25), ylabel, fill="#222222")
    for index, (label, value, color) in enumerate(zip(labels, values, colors)):
        left = box[0] + index * width + width * 0.15
        right = box[0] + (index + 1) * width - width * 0.15
        top = box[3] - value / maximum * (box[3] - box[1])
        draw.rectangle((left, top, right, box[3]), fill=color)
        draw.text((left, top - 22), f"{value:.1f}", fill="#222222")
        draw.text((left, box[3] + 15), label[:22], fill="#222222")


def _csv(path: Path) -> list[dict[str, str]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _json(path: Path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() and path.stat().st_size else default


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    for path in render(args.run_dir.resolve()):
        print(f"figure: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
