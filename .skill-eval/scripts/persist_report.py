"""Persist a per-skill report and rebuild that skill's index.md.

The orchestrator writes reports under `--reports-dir` (in CI: `skill-eval-out/
reports/`). The workflow's "Persist reports to PR branch" step copies the tree
into `.skill-eval/reports/` on the PR head and commits.

We split write-out from commit because the workflow checks out the default
branch first (trusted code only); the .skill-eval/reports/ directory on the
default branch must not be touched, so writes go to the workspace and are
copied after switching branches.

The report's HTML-comment metadata (`<!-- skill-eval-meta key=value; ... -->`)
is parsed when rebuilding `index.md`. The reporter emits this; if you change
the format there, update `_parse_meta` here.
"""

from __future__ import annotations

import re
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
    rebuild_index(target_dir)
    return out


def rebuild_index(skill_dir: Path) -> None:
    rows = []
    for md in sorted(skill_dir.glob("*.md")):
        if md.name == "index.md":
            continue
        meta = _parse_meta(md.read_text(encoding="utf-8"))
        rows.append((md.name, meta))
    lines = [
        f"# skill-eval 履歴 — `{skill_dir.name}`",
        "",
        f"このディレクトリには `{skill_dir.name}` の効果検証レポートが PR ごとに蓄積されます。",
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
