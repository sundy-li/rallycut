#!/usr/bin/env python3
"""Evaluate RallyCut/TTcut rally JSON against a local human truth JSON.

Example:
  python3 scripts/evaluate_rallies.py --truth /path/manual.json \
    --candidate RallyCut=/tmp/rallycut.json --candidate TTcut=/tmp/ttcut.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "vision"))
from evaluation import evaluate_files, markdown  # noqa: E402


def candidate(value: str) -> tuple[str, str]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("候选格式必须是 名称=JSON路径")
    name, path = value.split("=", 1)
    if not name or not path:
        raise argparse.ArgumentTypeError("候选格式必须是 名称=JSON路径")
    return name, path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--truth", required=True, help="人工标注的项目/回合 JSON")
    parser.add_argument(
        "--candidate",
        action="append",
        required=True,
        type=candidate,
        help="名称=候选 JSON；可重复，例如 RallyCut=... TTcut=...",
    )
    parser.add_argument("--iou", type=float, default=0.5, help="匹配 IoU 阈值，默认 0.5")
    parser.add_argument(
        "--boundary-tolerance",
        type=float,
        default=1.0,
        help="起止边界允许误差秒数，默认 1.0",
    )
    parser.add_argument(
        "--output",
        default="build/evaluation/latest",
        help="报告目录（默认 build/evaluation/latest）",
    )
    args = parser.parse_args()
    report = evaluate_files(args.truth, args.candidate, args.iou, args.boundary_tolerance)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "evaluation.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output / "evaluation.md").write_text(markdown(report), encoding="utf-8")
    for result in report["candidates"]:
        print(
            f"{result['name']}: TP={result['tp']} FP={result['fp']} FN={result['fn']} "
            f"precision={result['precision']:.1%} recall={result['recall']:.1%} "
            f"F1={result['f1']:.1%} boundary={result['boundary_accuracy']:.1%} "
            f"merges={len(result['merges'])} splits={len(result['splits'])}"
        )
    print(f"报告：{output / 'evaluation.md'}")
    print(f"原始数据：{output / 'evaluation.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
