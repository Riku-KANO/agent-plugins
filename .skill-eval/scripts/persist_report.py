"""Persist a per-skill report and rebuild that skill's index.md.

The orchestrator calls `persist()` to stage the new report file. It does NOT
rebuild index.md inline because the staging dir only has the current PR's
file — that would drop history. The workflow copies the file to the final
location on the PR head and then runs `rebuild-index` as a CLI against the
final dir (which has both the new report and prior PR history).

Report metadata format (`<!-- skill-eval-meta key=value; ... -->`) is emitted
by reporter.py and parsed here; keep the two in sync.
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


META_RE = re.compile(r"<!--\s*skill-eval-meta\s+(.*?)\s*-->", re.DOTALL)


def persist(
    skill_name: str,
    pr_num: int,
    head_sha: str,
    full_md: str,
    reports_dir: str,
) -> Path:
    short = head_sha[:7]
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    target_dir = Path(reports_dir) / skill_name
    target_dir.mkdir(parents=True, exist_ok=True)
    fname = f"{date}_PR{pr_num}_{short}.md"
    out = target_dir / fname
    out.write_text(full_md, encoding="utf-8")
    return out


def rebuild_index(skill_dir: Path, skill_name: str) -> None:
    rows = []
    for md in sorted(skill_dir.glob("*.md")):
        if md.name == "index.md":
            continue
        meta = _parse_meta(md.read_text(encoding="utf-8"))
        rows.append((md.name, meta))
    lines = [
        f"# skill-eval 履歴 — `{skill_name}`",
        "",
        f"このディレクトリには `{skill_name}` の効果検証レポートが PR ごとに蓄積されます。",
        "新しい順にソートして表示する場合はリポジトリ UI のファイル名でソートしてください。",
        "",
        "| ファイル | mode | 判定 | treat 平均 | ctrl 平均 | Δ | 勝/全ペア | シナリオ数 (発火/非発火) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for name, meta in rows:
        sf = meta.get("should_fire", "?")
        snf = meta.get("should_not_fire", "?")
        scn = meta.get("scenarios", "?")
        lines.append(
            f"| [{name}]({name}) "
            f"| {meta.get('mode','?')} "
            f"| {meta.get('verdict','?')} "
            f"| {meta.get('treatment_avg','?')} "
            f"| {meta.get('control_avg','?')} "
            f"| {meta.get('delta','?')} "
            f"| {meta.get('wins','?')}/{meta.get('pair_total','?')} "
            f"| {scn} ({sf}/{snf}) |"
        )
    (skill_dir / "index.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _parse_meta(report_md: str) -> dict:
    m = META_RE.search(report_md)
    if not m:
        return {}
    body = m.group(1)
    out: dict[str, str] = {}
    for piece in body.split(";"):
        piece = piece.strip()
        if "=" in piece:
            k, v = piece.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def _main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(
        description="Rebuild a skill's reports/index.md from existing *.md files."
    )
    sub = p.add_subparsers(dest="cmd", required=True)
    ri = sub.add_parser(
        "rebuild-index",
        help="Rebuild index.md against the directory passed (must already "
             "contain the per-PR reports).",
    )
    ri.add_argument("dir", help="path to .claude/skills/<skill>/skill-eval/reports/")
    ri.add_argument("--skill", required=True, help="skill name for the index header")
    args = p.parse_args(argv)

    if args.cmd == "rebuild-index":
        d = Path(args.dir)
        if not d.is_dir():
            print(f"not a directory: {d}", file=sys.stderr)
            return 2
        rebuild_index(d, args.skill)
        print(f"rebuilt {d / 'index.md'}")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
