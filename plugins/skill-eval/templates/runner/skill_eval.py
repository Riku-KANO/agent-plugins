"""Orchestrator: drive the Implementer → Evaluator → Reporter chain.

Run this from the workflow as:

  python .skill-eval/scripts/skill_eval.py \
      --pr <num> --repo <owner/name> \
      --head-sha <sha> --base-sha <sha> \
      --pr-files pr-files.json \
      --reports-dir skill-eval-out/reports \
      --pr-comment-out skill-eval-out/pr-comment.md

The orchestrator runs in the default-branch checkout (trusted code only). The
PR head is consumed only as data via gh API in `pr_data`.

Scenarios are user-authored ahead of time via `/skill-eval:create-test` and
loaded from `.claude/skills/<skill>/skill-eval/scenarios.json`. Skills without
scenarios are surfaced in the PR comment and skipped (no silent passes).

Final report destination on the PR branch (written by the workflow after the
orchestrator finishes):
  .claude/skills/<skill>/skill-eval/reports/<file>.md
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from agents import evaluator, implementer, reporter  # noqa: E402
import load_scenarios  # noqa: E402
import persist_report  # noqa: E402
import pr_data  # noqa: E402
from copilot_runner import make_runner  # noqa: E402


MODE_BY_STATUS = {
    "added": "addition",
    "modified": "modification",
    "renamed": "modification",
    "removed": "removal",
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Skill A/B evaluation orchestrator.")
    p.add_argument("--pr", type=int, required=True)
    p.add_argument("--repo", required=True, help="<owner>/<name>")
    p.add_argument("--head-sha", required=True)
    p.add_argument("--base-sha", required=True)
    p.add_argument("--pr-files", required=True,
                   help="JSON file produced by `gh api --paginate --slurp`")
    p.add_argument("--reports-dir", required=True,
                   help="staging dir under which `<skill>/<file>.md` is written. "
                        "The workflow copies each subtree to "
                        ".claude/skills/<skill>/skill-eval/reports/ after "
                        "switching to the PR head.")
    p.add_argument("--pr-comment-out", required=True,
                   help="markdown file that will be posted as the PR comment")
    p.add_argument("--samples-per-arm", type=int, default=3)
    p.add_argument("--max-skills", type=int, default=5,
                   help="cap on skills evaluated per run; excess are listed "
                        "but not evaluated")
    p.add_argument("--model", default=None,
                   help="shorthand: set implementer/evaluator models to the "
                        "same value. Per-role overrides take precedence.")
    p.add_argument("--implementer-model", default=None)
    p.add_argument("--evaluator-model", default=None)
    p.add_argument("--smoke", action="store_true",
                   help="minimal config for plumbing verification: "
                        "--samples-per-arm 1.")
    args = p.parse_args()

    default_model = args.model or "claude-sonnet-4.5"
    args.implementer_model = args.implementer_model or default_model
    args.evaluator_model = args.evaluator_model or default_model

    if args.smoke:
        args.samples_per_arm = 1
    return args


def split_arms(s: pr_data.SkillChange, mode: str) -> tuple[str, str]:
    """Return (control_text, treatment_text)."""
    if mode == "addition":
        return ("", s["new_text"])
    if mode == "removal":
        return (s["old_text"], "")
    return (s["old_text"], s["new_text"])  # modification/rename


async def evaluate_one_skill(s: pr_data.SkillChange, scenarios: list[dict],
                             args: argparse.Namespace) -> tuple[str, str, str]:
    """Returns (skill_name, summary_md, full_md)."""
    skill_name = pr_data.skill_dirname(s["path"] or s["prev_path"])
    mode = MODE_BY_STATUS.get(s["status"], "modification")
    ctrl_text, treat_text = split_arms(s, mode)

    per_scenario_results: list[dict] = []
    async with make_runner(model=args.implementer_model) as impl_runner:
        for sc in scenarios:
            runs = await implementer.run_ab(
                impl_runner,
                scenario=sc,
                skill_dirname=skill_name,
                control_text=ctrl_text,
                treatment_text=treat_text,
                n_per_arm=args.samples_per_arm,
            )
            per_scenario_results.append({"scenario": sc, "runs": runs})

    async with make_runner(model=args.evaluator_model) as eval_runner:
        for entry in per_scenario_results:
            scored = await evaluator.score(
                eval_runner, scenario=entry["scenario"], runs=entry["runs"]
            )
            entry["scored"] = scored

    summary, full = reporter.write(
        skill_path=s["path"] or s["prev_path"],
        mode=mode,
        scenarios=per_scenario_results,
        new_text=s["new_text"],
        old_text=s["old_text"],
        pr_num=args.pr,
        head_sha=args.head_sha,
        base_sha=args.base_sha,
        evaluator_model=args.evaluator_model,
        samples_per_arm=args.samples_per_arm,
    )
    return skill_name, summary, full


async def main_async(args: argparse.Namespace) -> int:
    print(
        f"[skill-eval] PR #{args.pr} repo={args.repo} "
        f"head={args.head_sha[:7]} base={args.base_sha[:7]} "
        f"smoke={args.smoke} models=impl/{args.implementer_model} "
        f"eval/{args.evaluator_model}",
        flush=True,
    )
    skills = pr_data.changed_skills(
        args.pr_files,
        head_sha=args.head_sha,
        base_sha=args.base_sha,
        repo=args.repo,
    )
    print(f"[skill-eval] changed_skills returned {len(skills)} entry/entries:",
          flush=True)
    for s in skills:
        print(f"[skill-eval]   - {s['path']} status={s['status']} "
              f"new_len={len(s['new_text'])} old_len={len(s['old_text'])}",
              flush=True)

    if not skills:
        print("[skill-eval] no skill changes — writing skip comment and exiting.",
              flush=True)
        Path(args.pr_comment_out).write_text(
            "ℹ️ `.claude/skills/**/SKILL.md` に変更がないため skill-eval は"
            "スキップしました。",
            encoding="utf-8",
        )
        return 0

    skipped = []
    if len(skills) > args.max_skills:
        skipped = [s["path"] for s in skills[args.max_skills:]]
        skills = skills[: args.max_skills]
        print(f"[skill-eval] capped to first {args.max_skills} skills, "
              f"deferring {len(skipped)}.", flush=True)

    summaries: list[str] = []
    for s in skills:
        skill_name = pr_data.skill_dirname(s["path"] or s["prev_path"])
        scenarios = load_scenarios.load(skill_name)

        if scenarios is None:
            print(f"[skill-eval] no scenarios for {skill_name} — skipping.",
                  flush=True)
            summaries.append(
                f"## Skill Eval: `{s['path']}` ({s['status']})\n"
                f"⚠️ シナリオ未作成 (`{load_scenarios.scenarios_path(skill_name)}` が無い)。"
                f"`/skill-eval:create-test {skill_name}` でシナリオを作成してから "
                f"再度 `/skill-eval` をコメントしてください。"
            )
            continue

        print(f"[skill-eval] evaluating {s['path']} (status={s['status']}, "
              f"scenarios={len(scenarios)}) ...", flush=True)
        try:
            sk_name, summary, full = await evaluate_one_skill(s, scenarios, args)
            persist_report.persist(
                skill_name=sk_name,
                pr_num=args.pr,
                head_sha=args.head_sha,
                full_md=full,
                reports_dir=args.reports_dir,
            )
            summaries.append(summary)
            print(f"[skill-eval] done {s['path']}.", flush=True)
        except Exception as e:
            tb = traceback.format_exc(limit=4)
            print(f"[skill-eval] CRASHED on {s['path']}: {type(e).__name__}: {e}",
                  flush=True)
            print(tb, flush=True)
            summaries.append(
                f"## Skill Eval: `{s['path']}` ({s['status']})\n"
                f"❌ 評価中にクラッシュしました: `{type(e).__name__}: {e}`\n\n"
                f"<details><summary>トレースバック</summary>\n\n```\n{tb}\n```\n</details>"
            )

    if skipped:
        summaries.append(
            "### 未評価のスキル (`--max-skills` 上限超過のため次回に持ち越し)\n"
            + "\n".join(f"- `{p}`" for p in skipped)
        )

    Path(args.pr_comment_out).write_text(
        "\n\n---\n\n".join(summaries), encoding="utf-8"
    )
    print(f"[skill-eval] wrote PR comment to {args.pr_comment_out} "
          f"({len(summaries)} section(s))", flush=True)
    return 0


def main() -> int:
    args = parse_args()
    try:
        return asyncio.run(main_async(args))
    except Exception as e:
        try:
            Path(args.pr_comment_out).write_text(
                f"❌ skill-eval オーケストレーターが起動に失敗しました: "
                f"`{type(e).__name__}: {e}`\n",
                encoding="utf-8",
            )
        except Exception:
            pass
        traceback.print_exc()
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
