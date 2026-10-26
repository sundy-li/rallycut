#!/usr/bin/env python3
"""Rally accuracy regression on the private rallycut-labels dataset.

  cache     fresh inference once per video, writes the L0 detection cache and
            checks that replaying it reproduces the fresh result
  run       replay every cached video with the current rules (seconds), score
            inside the labeled ranges, write a report, optionally compare /
            gate against a saved baseline
  status    list videos, labels and cache state
  import    copy a RallyCut project's human rallies (manual-* / edited) into
            the dataset as videos/<id>.json (the first `run` afterwards is the
            video's independent score)

The dataset lives outside the repository (RALLYCUT_LABELS_DIR or --labels);
nothing here uploads or embeds private media / labels.
"""
import argparse
import datetime
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VISION = ROOT / "vision"
sys.path.insert(0, str(VISION))

import detection_cache  # noqa: E402
from evaluation import score_labels  # noqa: E402

SEGMENT_EXTRA = ("duration", "start_timecode", "end_timecode", "review_required")


def mm(t):
    return f"{int(t // 60):02d}:{t % 60:04.1f}"


class Dataset:
    def __init__(self, root):
        self.root = Path(root).expanduser().resolve()
        path = self.root / "dataset.json"
        if not path.is_file():
            raise SystemExit(f"没有找到标注库 {path}；用 --labels 或 RALLYCUT_LABELS_DIR 指定")
        self.doc = json.loads(path.read_text(encoding="utf-8"))
        self.video_root = (self.root / self.doc.get("video_root", "..")).resolve()

    def videos(self, only=None):
        out = []
        for item in self.doc["videos"]:
            if only and item["id"] not in only:
                continue
            labels = json.loads((self.root / item["labels"]).read_text(encoding="utf-8"))
            out.append({**item, "doc": labels, "path": self.video_root / item["file"],
                        "role": item.get("role", "dev")})
        if only and len(out) != len(set(only)):
            missing = set(only) - {v["id"] for v in out}
            raise SystemExit(f"标注库里没有: {', '.join(sorted(missing))}")
        return out

    def cache_dir(self, video):
        return self.root / "cache" / video["id"]

    def valid_cache(self, video):
        """Newest verified cache whose L0 code matches the current sources."""
        best = None
        for meta_path in sorted(self.cache_dir(video).glob("*/meta.json")):
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if meta.get("sources") != detection_cache.source_digest():
                continue
            if not meta.get("verified"):
                continue
            if best is None or meta["created"] > best[1]["created"]:
                best = (meta_path.parent, meta)
        return best


def compare_fresh(fresh, replayed):
    """Differences between a fresh headless output and the L0 replay."""
    segments = [{k: v for k, v in s.items() if k not in SEGMENT_EXTRA} for s in fresh["segments"]]
    rallies = sorted(replayed["rallies"], key=lambda r: r["start"])
    diff = []
    if segments != rallies:
        diff.append(f"segments {len(segments)} vs replay {len(rallies)}")
    if fresh.get("tracks") != replayed["tracks"]:
        diff.append("tracks differ")
    if fresh["summary"].get("rally_events") != replayed["summary"]["rally_events"]:
        diff.append("rally_events differ")
    if fresh["summary"].get("table_segments") != replayed["summary"]["table_segments"]:
        diff.append("table_segments differ")
    return diff


def cmd_cache(args, data):
    for video in data.videos(args.video):
        found = data.valid_cache(video)
        if found and not args.force:
            print(f"{video['id']}: 已有有效 L0 缓存 {found[0].name}，跳过", flush=True)
            continue
        if not video["path"].is_file():
            print(f"{video['id']}: 找不到视频 {video['path']}", file=sys.stderr)
            continue
        base = data.cache_dir(video)
        pending = base / f".pending-{os.getpid()}"
        shutil.rmtree(pending, ignore_errors=True)
        pending.mkdir(parents=True)
        env = {**os.environ}
        if args.runtime:
            env["RALLYCUT_RUNTIME"] = args.runtime
        command = [sys.executable, str(VISION / "headless.py"), "analyze", "--input", str(video["path"]),
                   "--output", str(pending / "fresh.json"), "--include-tracks", "--device", args.device,
                   "--dump-l0", str(pending / "l0.json.gz"), "--timeout", str(args.timeout)]
        print(f"{video['id']}: 新鲜推理 {video['path'].name} …", flush=True)
        started = time.monotonic()
        with open(pending / "analyze.log", "w", encoding="utf-8") as log:
            code = subprocess.run(command, env=env, stdout=log, stderr=log).returncode
        elapsed = time.monotonic() - started
        if code != 0:
            print(f"{video['id']}: 推理失败（{code}），日志 {pending / 'analyze.log'}", file=sys.stderr)
            continue
        l0 = detection_cache.load(pending / "l0.json.gz")
        fresh = json.loads((pending / "fresh.json").read_text(encoding="utf-8"))
        diff = compare_fresh(fresh, detection_cache.replay(l0))
        meta = {"video": video["id"], "file": video["file"], "created": datetime.datetime.now().isoformat(timespec="seconds"),
                "digest": l0["digest"], "sources": l0["key"]["sources"], "key": l0["key"],
                "implementation": fresh["summary"].get("implementation"), "elapsed_seconds": round(elapsed, 1),
                "frames": len(l0["frames"]["t"]), "l0_bytes": (pending / "l0.json.gz").stat().st_size,
                "verified": not diff, "replay_diff": diff}
        (pending / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
        target = base / l0["digest"][:16]
        if target.exists():
            shutil.rmtree(target)
        pending.rename(target)
        state = "重放与新鲜推理一致" if not diff else "重放不一致: " + "; ".join(diff)
        print(f"{video['id']}: {elapsed / 60:.1f} 分钟，L0 {meta['l0_bytes'] / 1e6:.1f} MB，{state}", flush=True)


def candidates_for(found):
    l0 = detection_cache.load(found[0] / "l0.json.gz")
    return detection_cache.replay(l0)["rallies"]


def cmd_run(args, data):
    started = time.monotonic()
    report = {"created": datetime.datetime.now().isoformat(timespec="seconds"), "videos": {}}
    skipped = []
    for video in data.videos(args.video):
        found = data.valid_cache(video)
        if not found:
            skipped.append(video["id"])
            continue
        rallies = candidates_for(found)
        score = score_labels(video["doc"], rallies)
        report["videos"][video["id"]] = {"role": video["role"], "cache": found[0].name,
                                         "covered": video["doc"]["covered"], "score": score,
                                         "candidates": [[round(r["start"], 3), round(r["end"], 3)] for r in rallies]}
    report["elapsed_seconds"] = round(time.monotonic() - started, 2)
    import neural_analysis
    report["rules"] = rule_versions(neural_analysis)
    baseline = None
    if args.compare:
        path = baseline_path(data, args.compare)
        baseline = json.loads(path.read_text(encoding="utf-8"))
    text = render(report, baseline, show_holdout=args.show_holdout)
    print(text)
    if skipped:
        print(f"\n没有有效 L0 缓存（需先 eval cache）：{', '.join(skipped)}")
    out = data.root / "reports"
    out.mkdir(exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    (out / f"{stamp}.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / f"{stamp}.md").write_text(text + "\n", encoding="utf-8")
    print(f"\n报告：{out / (stamp + '.md')}")
    if args.save_baseline:
        path = baseline_path(data, args.save_baseline)
        path.parent.mkdir(exist_ok=True)
        if path.exists() and not args.force:
            raise SystemExit(f"基线已存在：{path}（加 --force 覆盖）")
        path.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"已保存基线：{path}")
    if args.gate and baseline:
        failures = gate(report, baseline, args.max_f1_drop)
        if failures:
            print("\n退化检查未通过：\n- " + "\n- ".join(failures))
            raise SystemExit(1)
        print("\n退化检查通过")


def rule_versions(neural_analysis):
    import inspect
    import re
    source = inspect.getsource(neural_analysis.analyze)
    found = dict(re.findall(r"'(implementation|activity_rule_version|play_area_version)':'([^']+)'", source))
    return found


def baseline_path(data, name):
    path = Path(name)
    return path if path.suffix == ".json" and path.exists() else data.root / "baselines" / f"{name}.json"


def gate(report, baseline, max_drop):
    failures = []
    for vid, item in report["videos"].items():
        old = baseline["videos"].get(vid)
        if not old:
            continue
        s, o = item["score"], old["score"]
        if s["f1"] < o["f1"] - max_drop:
            failures.append(f"{vid}: F1 {o['f1']:.3f} → {s['f1']:.3f}")
        if s["recall"] < o["recall"] - 1e-9:
            failures.append(f"{vid}: 召回 {o['recall']:.3f} → {s['recall']:.3f}")
    return failures


def totals(items):
    tp = sum(i["score"]["tp"] for i in items)
    fp = sum(i["score"]["fp"] for i in items)
    fn = sum(i["score"]["fn"] for i in items)
    f1 = 2 * tp / (2 * tp + fp + fn) if tp + fp + fn else 0
    return tp, fp, fn, f1


def render(report, baseline=None, show_holdout=False):
    rules = report.get("rules", {})
    lines = [f"# 回合准确率回测（{report['created']}，重放 {report['elapsed_seconds']} s）", "",
             f"规则：{rules.get('implementation', '?')} · {rules.get('activity_rule_version', '?')}", "",
             "口径：只比较标注范围；可选回合不计分；IoU≥0.5 一对一匹配；起点按标注口径容差（颠球 / 发球准备），终点严格；边界准 = 起止误差都 ≤1 s。",
             "", "| 视频 | 用途 | 真值 | 候选 | 对上 / 误报 / 漏检 | 精确率 | 召回 | F1 | 边界准 | 终点误差中位 | IoU≥0.3 | 对比基线 |",
             "|---|---|---:|---:|---|---:|---:|---:|---:|---:|---|---|"]
    for vid, item in report["videos"].items():
        s = item["score"]
        delta = ""
        if baseline and vid in baseline["videos"]:
            o = baseline["videos"][vid]["score"]
            delta = f"{s['tp'] - o['tp']:+d}/{s['fp'] - o['fp']:+d}/{s['fn'] - o['fn']:+d} F1 {s['f1'] - o['f1']:+.3f}"
        lines.append(f"| {vid} | {item['role']} | {s['truth_count']} | {s['candidate_count']} | {s['tp']} / {s['fp']} / {s['fn']} | "
                     f"{s['precision']:.2f} | {s['recall']:.2f} | {s['f1']:.3f} | {s['boundary_accuracy']:.0%} | "
                     f"{s['boundary']['end_median']:.2f} s | {s['loose']['tp']}/{s['loose']['fp']}/{s['loose']['fn']} | {delta} |")
    for role in ("dev", "holdout"):
        items = [i for i in report["videos"].values() if i["role"] == role]
        if items:
            tp, fp, fn, f1 = totals(items)
            lines.append(f"| **合计 {role}** | | | | {tp} / {fp} / {fn} | | | {f1:.3f} | | | | |")
    for vid, item in report["videos"].items():
        if item["role"] == "holdout" and not show_holdout:
            continue
        s = item["score"]
        lines += ["", f"## {vid}"]
        lines.append("- 漏检：" + ("、".join(f"{mm(m['start'])}—{mm(m['end'])}" + (f"（{m.get('tag') or m.get('note')}）" if m.get('tag') or m.get('note') else "") for m in s["missed"]) or "无"))
        lines.append("- 误报：" + ("、".join(f"{mm(e['start'])}—{mm(e['end'])}" + (f"（{e['end_reason']}）" if e.get('end_reason') else "") for e in s["extra"]) or "无"))
        if baseline and vid in baseline["videos"]:
            o = baseline["videos"][vid]["score"]
            key = lambda e: (round(e["start"], 1), round(e["end"], 1))
            new_miss = [m for m in s["missed"] if m["id"] not in {x["id"] for x in o["missed"]}]
            fixed = [m for m in o["missed"] if m["id"] not in {x["id"] for x in s["missed"]}]
            new_extra = [e for e in s["extra"] if key(e) not in {key(x) for x in o["extra"]}]
            gone = [e for e in o["extra"] if key(e) not in {key(x) for x in s["extra"]}]
            for label, rows in (("新漏检", new_miss), ("找回", fixed), ("新误报", new_extra), ("去掉误报", gone)):
                if rows:
                    lines.append(f"- {label}：" + "、".join(f"{mm(r['start'])}—{mm(r['end'])}" for r in rows))
    return "\n".join(lines)


def human_rallies(project):
    """Rallies the user added (manual-*) or corrected (edited=true)."""
    return sorted((r for r in project["rallies"] if str(r["id"]).startswith("manual") or r.get("edited")),
                  key=lambda r: r["start"])


def cmd_import(args, data):
    project_path = Path(args.project).expanduser()
    project = json.loads(project_path.read_text(encoding="utf-8"))
    video = project["video"]
    vid = args.id
    if any(v["id"] == vid for v in data.doc["videos"]) and not args.force:
        raise SystemExit(f"标注库已有 {vid}（加 --force 覆盖）")
    rallies = human_rallies(project)
    if not rallies:
        raise SystemExit("项目里没有人工添加 / 修正的回合")
    if args.covered:
        covered = [[float(x) for x in item.split("-")] for item in args.covered]
    else:
        covered = [[0.0, round(float(video["duration"]), 3)]]
    outside = [r for r in rallies if not any(a <= (r["start"] + r["end"]) / 2 < b for a, b in covered)]
    if outside:
        print(f"注意：{len(outside)} 个人工回合在标注范围外，将不参与打分")
    source = Path(video.get("path") or data.video_root / video["name"])
    if not source.is_file():
        raise SystemExit(f"找不到视频 {source}")
    (data.root / "sources").mkdir(exist_ok=True)
    (data.root / "sources" / f"{vid}-project-manual.json").write_text(json.dumps(
        {"exported_from": str(project_path), "exported_at": datetime.date.today().isoformat(), "video": video,
         "manual_rallies": rallies}, ensure_ascii=False, indent=1), encoding="utf-8")
    doc = {"video": {"name": video["name"], "size": source.stat().st_size, "sha256": video.get("fingerprint"),
                     "duration": video.get("duration"), "width": video.get("width"), "height": video.get("height"),
                     "fps": video.get("fps"), "view": args.view},
           "covered": covered, "start_convention": args.start_convention,
           "rallies": [{"id": r["id"], "start": round(r["start"], 3), "end": round(r["end"], 3),
                        "label": f"{mm(r['start'])}—{mm(r['end'])}"} for r in rallies],
           "notes": [f"{datetime.date.today()} 从项目 {project_path.name} 导入 {len(rallies)} 个人工回合；首次 run 为独立成绩"]}
    (data.root / "videos").mkdir(exist_ok=True)
    (data.root / "videos" / f"{vid}.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    try:
        relative = str(source.resolve().relative_to(data.video_root))
    except ValueError:
        relative = str(source.resolve())
    entry = {"id": vid, "labels": f"videos/{vid}.json", "file": relative, "role": args.role, "view": args.view}
    data.doc["videos"] = [v for v in data.doc["videos"] if v["id"] != vid] + [entry]
    data.doc["updated"] = datetime.date.today().isoformat()
    (data.root / "dataset.json").write_text(json.dumps(data.doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{vid}: 导入 {len(rallies)} 个回合，范围 {covered}；下一步 just eval cache --video {vid} && just eval run --video {vid}")


def cmd_status(args, data):
    for video in data.videos(args.video):
        doc = video["doc"]
        found = data.valid_cache(video)
        caches = sorted(p.parent.name for p in data.cache_dir(video).glob("*/meta.json"))
        req = sum(1 for r in doc["rallies"] if not r.get("optional"))
        print(f"{video['id']:6} {video['role']:7} 回合 {req:3}（可选 {len(doc['rallies']) - req}） 范围 {doc['covered']} "
              f"视频{'存在' if video['path'].is_file() else '缺失'} L0 {'有效 ' + found[0].name if found else '无有效'}"
              + (f"（旧缓存 {len(caches)} 份）" if caches and not found else ""))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--labels", default=os.environ.get("RALLYCUT_LABELS_DIR"), help="rallycut-labels 目录")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("import")
    p.add_argument("project", help="RallyCut 项目 JSON（~/Library/Application Support/RallyCut/projects/…）")
    p.add_argument("--id", required=True, help="标注库中的视频 id")
    p.add_argument("--covered", action="append", help="标注范围 秒-秒（可重复）；默认整段")
    p.add_argument("--start-convention", default="toss", choices=["toss", "serve_preparation"])
    p.add_argument("--view", default="unknown", help="side / fixed-oblique / spectator / broadcast …")
    p.add_argument("--role", default="dev", choices=["dev", "holdout"])
    p.add_argument("--force", action="store_true")
    for name in ("cache", "run", "status"):
        p = sub.add_parser(name)
        p.add_argument("--video", action="append", help="只处理这些视频 id（可重复）")
        if name == "cache":
            p.add_argument("--force", action="store_true", help="即使已有有效缓存也重新推理")
            p.add_argument("--device", default="mps", choices=["auto", "mps", "cpu"])
            p.add_argument("--runtime", default="torch", help="RALLYCUT_RUNTIME（默认 torch FP32，与正式分析一致）")
            p.add_argument("--timeout", type=float, default=7200)
        if name == "run":
            p.add_argument("--compare", help="对比的基线名（baselines/<名>.json）或路径")
            p.add_argument("--save-baseline", help="把本次结果存为基线")
            p.add_argument("--gate", action="store_true", help="对比基线退化时以非零退出")
            p.add_argument("--max-f1-drop", type=float, default=0.02)
            p.add_argument("--show-holdout", action="store_true", help="显示 holdout 视频的错误明细")
            p.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    if not args.labels:
        raise SystemExit("请用 --labels 或 RALLYCUT_LABELS_DIR 指定 rallycut-labels 目录")
    data = Dataset(args.labels)
    {"cache": cmd_cache, "run": cmd_run, "status": cmd_status, "import": cmd_import}[args.command](args, data)


if __name__ == "__main__":
    main()
