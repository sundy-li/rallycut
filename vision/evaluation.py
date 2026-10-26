"""Deterministic rally/segment evaluation against a local human truth file.

The matching unit is one rally (one point), not a frame or a ball track. Truth
and candidate intervals are matched one-to-one with dynamic programming, first
maximising the number of matches and then total IoU. No private media or truth
files are embedded in this module.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
from statistics import mean, median
from typing import Any, Iterable


@dataclass(frozen=True)
class Interval:
    id: str
    start: float
    end: float

    @property
    def duration(self) -> float:
        return self.end - self.start


def _overlap(a: Interval, b: Interval) -> float:
    return max(0.0, min(a.end, b.end) - max(a.start, b.start))


def iou(a: Interval, b: Interval) -> float:
    union = max(a.end, b.end) - min(a.start, b.start)
    return _overlap(a, b) / union if union > 0 else 0.0


def _number(item: dict[str, Any], *names: str) -> float | None:
    for name in names:
        value = item.get(name)
        if isinstance(value, (int, float)) and math.isfinite(value):
            return float(value)
    return None


def load_intervals(path: str | Path) -> list[Interval]:
    """Read project, headless `segments`, or TTcut history JSON formats.

    `invalid` rallies are deliberately excluded: they are review annotations,
    not part of the real editing timeline.
    """
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(doc.get("analysis"), dict):
        doc = doc["analysis"]
    raw = doc.get("segments")
    if raw is None:
        raw = doc.get("rallies")
    if raw is None and isinstance(doc.get("sources"), list):
        sources = doc["sources"]
        active = doc.get("active_source_id")
        if active:
            raw = next((s.get("rallies", []) for s in sources if s.get("id") == active), [])
        else:
            raw = [r for source in sources for r in source.get("rallies", [])]
    if raw is None:
        raise ValueError(f"{path}: no rallies/segments found")

    intervals: list[Interval] = []
    for index, item in enumerate(raw):
        if item.get("invalid"):
            continue
        start = _number(item, "start", "start_time_seconds")
        end = _number(item, "end", "end_time_seconds")
        if start is None or end is None or start < 0 or end <= start:
            raise ValueError(f"{path}: invalid rally boundary at index {index}")
        ident = str(item.get("id", item.get("index", index + 1)))
        intervals.append(Interval(ident, start, end))
    return sorted(intervals, key=lambda item: (item.start, item.end, item.id))


def match_intervals(
    truth: list[Interval], candidates: list[Interval], threshold: float = 0.5
) -> list[tuple[int, int, float]]:
    """Maximum-cardinality, then maximum-IoU one-to-one ordered assignment."""
    if threshold <= 0 or threshold > 1:
        raise ValueError("IoU threshold must be in (0, 1]")
    n, m = len(truth), len(candidates)
    # Each cell is (match_count, total_iou, tuple_of_(truth_i, candidate_j, iou)).
    dp: list[list[tuple[int, float, tuple[tuple[int, int, float], ...]]]] = [
        [(0, 0.0, ()) for _ in range(m + 1)] for _ in range(n + 1)
    ]
    for i in range(1, n + 1):
        dp[i][0] = (0, 0.0, ())
    for j in range(1, m + 1):
        dp[0][j] = (0, 0.0, ())
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            best = dp[i - 1][j]
            skip_candidate = dp[i][j - 1]
            if (skip_candidate[0], skip_candidate[1]) > (best[0], best[1]):
                best = skip_candidate
            score = iou(truth[i - 1], candidates[j - 1])
            if score >= threshold:
                previous = dp[i - 1][j - 1]
                option = (
                    previous[0] + 1,
                    previous[1] + score,
                    previous[2] + ((i - 1, j - 1, score),),
                )
                if (option[0], option[1]) > (best[0], best[1]):
                    best = option
            dp[i][j] = best
    return list(dp[n][m][2])


def _rate(part: int, whole: int) -> float:
    return part / whole if whole else 0.0


def _percentile90(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[math.ceil(0.9 * len(ordered)) - 1]


def evaluate(
    truth: list[Interval], candidates: list[Interval], threshold: float = 0.5, boundary_tolerance: float = 1.0
) -> dict[str, Any]:
    if boundary_tolerance < 0:
        raise ValueError("boundary tolerance must be non-negative")
    matches = match_intervals(truth, candidates, threshold)
    tp = len(matches)
    fp = len(candidates) - tp
    fn = len(truth) - tp
    start_errors = [abs(truth[i].start - candidates[j].start) for i, j, _ in matches]
    end_errors = [abs(truth[i].end - candidates[j].end) for i, j, _ in matches]
    good_boundaries = sum(
        1 for i, j, _ in matches
        if abs(truth[i].start - candidates[j].start) <= boundary_tolerance
        and abs(truth[i].end - candidates[j].end) <= boundary_tolerance
    )

    merges = []
    for candidate in candidates:
        covered = [t.id for t in truth if _overlap(t, candidate) / t.duration >= 0.5]
        if len(covered) > 1:
            merges.append({"candidate": candidate.id, "truth": covered})
    splits = []
    for true in truth:
        pieces = [
            c.id for c in candidates
            if _overlap(true, c) / c.duration >= 0.5 and _overlap(true, c) > 0
        ]
        if len(pieces) > 1:
            splits.append({"truth": true.id, "candidates": pieces})

    matched_truth = {i for i, _, _ in matches}
    matched_candidates = {j for _, j, _ in matches}
    return {
        "truth_count": len(truth),
        "candidate_count": len(candidates),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": _rate(tp, tp + fp),
        "recall": _rate(tp, tp + fn),
        "f1": _rate(2 * tp, 2 * tp + fp + fn),
        "boundary_accuracy": _rate(good_boundaries, len(truth)),
        "boundary": {
            "start_mae": mean(start_errors) if start_errors else 0.0,
            "end_mae": mean(end_errors) if end_errors else 0.0,
            "start_median": median(start_errors) if start_errors else 0.0,
            "end_median": median(end_errors) if end_errors else 0.0,
            "start_p90": _percentile90(start_errors),
            "end_p90": _percentile90(end_errors),
        },
        "matches": [
            {
                "truth": truth[i].id,
                "candidate": candidates[j].id,
                "iou": score,
                "start_error": abs(truth[i].start - candidates[j].start),
                "end_error": abs(truth[i].end - candidates[j].end),
            }
            for i, j, score in matches
        ],
        "unmatched_truth": [t.id for i, t in enumerate(truth) if i not in matched_truth],
        "unmatched_candidates": [c.id for j, c in enumerate(candidates) if j not in matched_candidates],
        "merges": merges,
        "splits": splits,
    }


def evaluate_files(
    truth_path: str | Path,
    candidate_paths: Iterable[tuple[str, str | Path]],
    threshold: float = 0.5,
    boundary_tolerance: float = 1.0,
) -> dict[str, Any]:
    truth = load_intervals(truth_path)
    return {
        "truth": str(Path(truth_path).resolve()),
        "iou_threshold": threshold,
        "boundary_tolerance_seconds": boundary_tolerance,
        "candidates": [
            {
                "name": name,
                "path": str(Path(path).resolve()),
                **evaluate(truth, load_intervals(path), threshold, boundary_tolerance),
            }
            for name, path in candidate_paths
        ],
    }


def markdown(report: dict[str, Any]) -> str:
    lines = [
        "# 回合切分评估",
        "",
        f"- 真值：`{report['truth']}`",
        f"- 有效匹配：一对一最大匹配，IoU ≥ {report['iou_threshold']}",
        f"- 边界准确：匹配回合的起点和终点误差均 ≤ {report['boundary_tolerance_seconds']}s",
        "- 无效分（`invalid=true`）不计入真值或候选；数量不等于准确率。",
        "",
        "| 候选 | 真值数 | 候选数 | TP | FP | FN | Precision | Recall | F1 | 边界准确率 | 合并 | 拆分 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for result in report["candidates"]:
        lines.append(
            f"| {result['name']} | {result['truth_count']} | {result['candidate_count']} | "
            f"{result['tp']} | {result['fp']} | {result['fn']} | {result['precision']:.1%} | "
            f"{result['recall']:.1%} | {result['f1']:.1%} | {result['boundary_accuracy']:.1%} | "
            f"{len(result['merges'])} | {len(result['splits'])} |"
        )
    for result in report["candidates"]:
        boundary = result["boundary"]
        lines.extend([
            "",
            f"## {result['name']}",
            "",
            f"输出：`{result['path']}`",
            "",
            f"边界 MAE：起点 {boundary['start_mae']:.3f}s，终点 {boundary['end_mae']:.3f}s；"
            f"P90：起点 {boundary['start_p90']:.3f}s，终点 {boundary['end_p90']:.3f}s。",
            f"未匹配真值：{', '.join(result['unmatched_truth']) or '无'}",
            f"未匹配候选：{', '.join(result['unmatched_candidates']) or '无'}",
        ])
        for merge in result["merges"]:
            lines.append(f"- 合并：候选 {merge['candidate']} 覆盖真值 {', '.join(merge['truth'])}")
        for split in result["splits"]:
            lines.append(f"- 拆分：真值 {split['truth']} 被拆成候选 {', '.join(split['candidates'])}")
    lines.extend([
        "",
        "> 合并：一个候选覆盖至少两个真值回合各 ≥50%；拆分：至少两个候选各自有 ≥50% 落在同一真值内。",
        "> 本报告只衡量所给真值文件，不代表其他比赛、机位或模型配置的普遍准确率。",
        "",
    ])
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Labeled dataset scoring (rallycut-labels videos/<id>.json)
# ---------------------------------------------------------------------------
START_CONVENTIONS = ("toss", "serve_preparation")
PREP_TOLERANCE = 8.0


def score_labels(
    doc: dict[str, Any],
    candidates: list[dict[str, Any]],
    threshold: float = 0.5,
    boundary_tolerance: float = 1.0,
    prep_tolerance: float = PREP_TOLERANCE,
) -> dict[str, Any]:
    """Score candidates against one labeled video, only inside `covered`.

    - Candidates count only when their midpoint is inside a covered range.
    - `optional` truths (lets, uncertain points) never count: a candidate on
      one (>50 % of the shorter interval) is neither a hit nor a false alarm.
    - Start convention: a rally may start at the serve-preparation bounces or
      at the toss.  Truth labeled from the preparation
      (`start_convention=serve_preparation`) accepts a candidate starting up to
      `prep_tolerance` s later; a candidate that starts at detected bounces
      (`start_reason=serve_prep`) may start up to that much before a
      toss-labeled truth.  Ends are always strict.
    """
    covered = [(float(a), float(b)) for a, b in doc["covered"]]
    default = doc.get("start_convention", "toss")
    if default not in START_CONVENTIONS:
        raise ValueError(f"unknown start_convention {default!r}")

    def inside(item: dict[str, Any]) -> bool:
        mid = (float(item["start"]) + float(item["end"])) / 2
        return any(lo <= mid < hi for lo, hi in covered)

    def overlap(a: dict[str, Any], b: dict[str, Any]) -> float:
        return max(0.0, min(a["end"], b["end"]) - max(a["start"], b["start"]))

    required = [r for r in doc["rallies"] if not r.get("optional")]
    optional = [r for r in doc["rallies"] if r.get("optional")]
    cands = []
    for index, c in enumerate(sorted(candidates, key=lambda c: (c["start"], c["end"]))):
        if not inside(c):
            continue
        shorter = lambda o: .5 * min(c["end"] - c["start"], o["end"] - o["start"])
        if any(overlap(c, o) > shorter(o) for o in optional):
            continue
        cands.append({**c, "_id": str(c.get("id", f"c{index}"))})
    truth = []
    for r in sorted(required, key=lambda r: r["start"]):
        start = float(r["start"])
        best = max(cands, key=lambda c: overlap(c, r), default=None)
        if best is not None and overlap(best, r) > 0:
            convention = r.get("start_convention", default)
            if convention == "serve_preparation" and start <= best["start"] <= min(start + prep_tolerance, r["end"]):
                start = float(best["start"])
            elif best.get("start_reason") == "serve_prep" and start - prep_tolerance <= best["start"] < start:
                start = float(best["start"])
        truth.append(Interval(str(r["id"]), start, float(r["end"])))
    intervals = [Interval(c["_id"], float(c["start"]), float(c["end"])) for c in cands]
    strict = evaluate(truth, intervals, threshold, boundary_tolerance)
    loose = evaluate(truth, intervals, 0.3, boundary_tolerance)
    by_truth = {str(r["id"]): r for r in required}
    by_cand = {c["_id"]: c for c in cands}
    return {
        **{k: strict[k] for k in ("truth_count", "candidate_count", "tp", "fp", "fn", "precision", "recall", "f1",
                                  "boundary_accuracy", "boundary", "merges", "splits")},
        "optional_count": len(optional),
        "loose": {k: loose[k] for k in ("tp", "fp", "fn", "f1")},
        "matches": strict["matches"],
        "missed": [
            {"id": i, "start": by_truth[i]["start"], "end": by_truth[i]["end"],
             **{k: by_truth[i][k] for k in ("tag", "note") if k in by_truth[i]}}
            for i in strict["unmatched_truth"]
        ],
        "extra": [
            {"id": j, "start": by_cand[j]["start"], "end": by_cand[j]["end"],
             **{k: by_cand[j][k] for k in ("start_reason", "end_reason") if by_cand[j].get(k)}}
            for j in strict["unmatched_candidates"]
        ],
    }
