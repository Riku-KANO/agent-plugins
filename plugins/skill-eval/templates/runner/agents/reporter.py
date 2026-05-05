"""Reporter: deterministic aggregation + Japanese markdown rendering.

Means and pairwise win counts are exact arithmetic; an LLM here adds variance
without value. The verdict rule is a fixed threshold, not a judgment call.

Output: (summary_md, full_md) where summary is the PR-comment-friendly
truncation and full contains transcript excerpts, axis breakdown, and skill
diff for the persisted report.
"""

from __future__ import annotations

import difflib
import statistics
from datetime import datetime, timezone


SCORE_AXES = ("success", "completeness", "skill_engagement", "conciseness")
AXIS_JA = {
    "success": "success (成功条件充足)",
    "completeness": "completeness (網羅性)",
    "skill_engagement": "skill_engagement (期待挙動への一致)",
    "conciseness": "conciseness (簡潔さ)",
}
WIN_THRESHOLD = 0.5  # |Δ_avg| above this triggers a non-tie verdict
SUMMARY_BYTE_BUDGET = 4500  # leave headroom under GitHub's ~65KB comment cap

VERDICT_IMPROVEMENT = "改善 ✅"
VERDICT_REGRESSION = "退行 ❌"
VERDICT_TIE = "同等 ➖"
VERDICT_ABSOLUTE = "絶対スコア ℹ️"  # mode=addition

MODE_JA = {
    "addition": "新規追加 (addition)",
    "modification": "修正 (modification)",
    "removal": "削除 (removal)",
}


def write(
    skill_path: str,
    mode: str,
    scenarios: list[dict],
    new_text: str,
    old_text: str,
    pr_num: int,
    head_sha: str,
    base_sha: str,
    *,
    evaluator_model: str,
    samples_per_arm: int,
) -> tuple[str, str]:
    aggregate = _aggregate(scenarios)
    axis_agg = _axis_aggregates(scenarios)
    coverage = _coverage(scenarios)
    failures = _failure_count(scenarios)
    verdict = _verdict(aggregate, mode)
    meta = {
        "verdict": verdict,
        "mode": mode,
        "treatment_avg": round(aggregate["treatment_avg"], 2),
        "control_avg": round(aggregate["control_avg"], 2),
        "delta": round(aggregate["delta"], 2),
        "wins": aggregate["wins"],
        "losses": aggregate["losses"],
        "ties": aggregate["ties"],
        "pair_total": aggregate["pair_total"],
        "scenarios": coverage["total"],
        "should_fire": coverage["should_fire"],
        "should_not_fire": coverage["should_not_fire"],
        "failed_runs": failures,
    }
    front = _meta_front_matter(meta)
    summary = _render_summary(skill_path, mode, verdict, aggregate, axis_agg,
                              coverage, failures, evaluator_model, samples_per_arm)
    full = _render_full(skill_path, mode, verdict, aggregate, axis_agg,
                        coverage, failures, scenarios, new_text, old_text,
                        pr_num, head_sha, base_sha, evaluator_model,
                        samples_per_arm)
    full = front + "\n" + full
    summary = front + "\n" + summary
    return _truncate_to_budget(summary), full


# --- aggregation -----------------------------------------------------------

def _aggregate(scenarios: list[dict]) -> dict:
    per_scenario = []
    total_wins = total_losses = total_ties = total_pairs = 0
    treat_avgs = []
    ctrl_avgs = []
    for entry in scenarios:
        scored = entry["scored"]["scores"]
        treat_runs = [s for s in scored.values() if s.get("arm") == "treatment"]
        ctrl_runs = [s for s in scored.values() if s.get("arm") == "control"]
        treat_means = [_run_mean(s) for s in treat_runs if _has_scores(s)]
        ctrl_means = [_run_mean(s) for s in ctrl_runs if _has_scores(s)]
        wins = losses = ties = 0
        for tm in treat_means:
            for cm in ctrl_means:
                if tm > cm: wins += 1
                elif tm < cm: losses += 1
                else: ties += 1
        pair_total = wins + losses + ties
        total_wins += wins; total_losses += losses; total_ties += ties
        total_pairs += pair_total
        per_scenario.append({
            "scenario": entry["scenario"],
            "treatment_mean": _safe_mean(treat_means),
            "control_mean": _safe_mean(ctrl_means),
            "delta": _safe_mean(treat_means) - _safe_mean(ctrl_means),
            "wins": wins, "losses": losses, "ties": ties,
            "pair_total": pair_total,
            "treatment_runs": treat_runs,
            "control_runs": ctrl_runs,
        })
        treat_avgs.append(_safe_mean(treat_means))
        ctrl_avgs.append(_safe_mean(ctrl_means))
    return {
        "per_scenario": per_scenario,
        "treatment_avg": _safe_mean(treat_avgs),
        "control_avg": _safe_mean(ctrl_avgs),
        "delta": _safe_mean(treat_avgs) - _safe_mean(ctrl_avgs),
        "wins": total_wins, "losses": total_losses, "ties": total_ties,
        "pair_total": total_pairs,
    }


def _axis_aggregates(scenarios: list[dict]) -> dict:
    """Per-axis treatment/control means and delta over all runs."""
    out = {}
    for axis in SCORE_AXES:
        treat_vals: list[float] = []
        ctrl_vals: list[float] = []
        for entry in scenarios:
            for s in entry["scored"]["scores"].values():
                v = s.get(axis)
                if not isinstance(v, (int, float)):
                    continue
                if s.get("arm") == "treatment":
                    treat_vals.append(float(v))
                elif s.get("arm") == "control":
                    ctrl_vals.append(float(v))
        t = _safe_mean(treat_vals)
        c = _safe_mean(ctrl_vals)
        out[axis] = {"treatment": t, "control": c, "delta": t - c,
                     "n_treat": len(treat_vals), "n_ctrl": len(ctrl_vals)}
    return out


def _coverage(scenarios: list[dict]) -> dict:
    """Count scenarios by expectation and archetype."""
    arche = {"direct": 0, "adjacent": 0, "subtle": 0}
    expect = {"should_fire": 0, "should_not_fire": 0}
    for entry in scenarios:
        sc = entry["scenario"]
        a = sc.get("archetype")
        e = sc.get("expectation", "should_fire")
        if a in arche:
            arche[a] += 1
        if e in expect:
            expect[e] += 1
    return {
        "total": len(scenarios),
        "archetype": arche,
        "should_fire": expect["should_fire"],
        "should_not_fire": expect["should_not_fire"],
    }


def _failure_count(scenarios: list[dict]) -> int:
    n = 0
    for entry in scenarios:
        for s in entry["scored"]["scores"].values():
            if s.get("error"):
                n += 1
    return n


def _verdict(aggregate: dict, mode: str) -> str:
    if mode == "addition":
        return VERDICT_ABSOLUTE
    delta = aggregate["delta"]
    per = aggregate["per_scenario"]
    all_treat_ge_ctrl = all(s["treatment_mean"] >= s["control_mean"] for s in per)
    if delta >= WIN_THRESHOLD and all_treat_ge_ctrl:
        return VERDICT_IMPROVEMENT
    if delta <= -WIN_THRESHOLD:
        return VERDICT_REGRESSION
    return VERDICT_TIE


def _run_mean(s: dict) -> float:
    vals = [s.get(axis) for axis in SCORE_AXES if isinstance(s.get(axis), (int, float))]
    return statistics.fmean(vals) if vals else 0.0


def _has_scores(s: dict) -> bool:
    return any(isinstance(s.get(axis), (int, float)) for axis in SCORE_AXES)


def _safe_mean(values: list[float]) -> float:
    return statistics.fmean(values) if values else 0.0


# --- rendering -------------------------------------------------------------

def _meta_front_matter(meta: dict) -> str:
    parts = [f"{k}={v}" for k, v in meta.items()]
    return "<!-- skill-eval-meta " + "; ".join(parts) + " -->"


def _expectation_ja(e: str) -> str:
    return {
        "should_fire": "発火すべき",
        "should_not_fire": "発火してはいけない",
    }.get(e, e)


def _verdict_explainer(verdict: str, mode: str, agg: dict) -> str:
    """One-sentence explanation of why this verdict was assigned."""
    if mode == "addition":
        return ("新規追加された skill のため A/B 判定は行わず、treatment (skill あり) と "
                "control (skill なし baseline) の絶対スコアを参考値として表示します。")
    delta = agg["delta"]
    per = agg["per_scenario"]
    all_ok = all(s["treatment_mean"] >= s["control_mean"] for s in per)
    if verdict == VERDICT_IMPROVEMENT:
        return (f"Δ={_signed(delta)} が +{WIN_THRESHOLD} 以上、かつ全シナリオで "
                f"treatment ≥ control を満たすため **改善** と判定しました。")
    if verdict == VERDICT_REGRESSION:
        return (f"Δ={_signed(delta)} が -{WIN_THRESHOLD} 以下のため **退行** と判定しました。")
    # tie
    reasons = []
    if abs(delta) < WIN_THRESHOLD:
        reasons.append(f"|Δ|={abs(delta):.2f} が閾値 {WIN_THRESHOLD} 未満")
    if delta >= WIN_THRESHOLD and not all_ok:
        bad = [s["scenario"].get("id", "?") for s in per
               if s["treatment_mean"] < s["control_mean"]]
        reasons.append(f"シナリオ {','.join(bad)} で treatment < control")
    return f"判定は **同等**: " + ("、".join(reasons) if reasons else "差が小さいため。")


def _render_summary(skill_path, mode, verdict, agg, axis_agg, coverage,
                    failures, evaluator_model, samples_per_arm) -> str:
    mode_label = MODE_JA.get(mode, mode)
    arche = coverage["archetype"]

    lines = [
        f"## Skill Eval: `{skill_path}` ({mode_label})",
        "",
        f"**判定**: {verdict}",
        "",
        f"- treatment 平均: **{agg['treatment_avg']:.2f}** / control 平均: **{agg['control_avg']:.2f}** / Δ: **{_signed(agg['delta'])}**",
        f"- ペア勝敗: **{agg['wins']}勝 / {agg['losses']}敗 / {agg['ties']}引分** (全 {agg['pair_total']} ペア)",
        f"- シナリオ: 全{coverage['total']}件 (発火すべき {coverage['should_fire']} / 発火してはいけない {coverage['should_not_fire']})",
        f"- archetype: direct {arche['direct']} / adjacent {arche['adjacent']} / subtle {arche['subtle']}",
        f"- 評価モデル: `{evaluator_model}` ・ N={samples_per_arm} per arm"
        + (f" ・ ⚠️ 失敗ラン {failures} 件" if failures else ""),
        "",
        f"> {_verdict_explainer(verdict, mode, agg)}",
        "",
        "### シナリオ別サマリ",
        "",
        "| ID | 種別 | 期待 | treat | ctrl | Δ | 勝/敗/分 | 発話 (40字) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for s in agg["per_scenario"]:
        sc = s["scenario"]
        lines.append(
            f"| {sc.get('id','?')} "
            f"| {sc.get('archetype','?')} "
            f"| {_expectation_ja(sc.get('expectation','should_fire'))} "
            f"| {s['treatment_mean']:.2f} "
            f"| {s['control_mean']:.2f} "
            f"| {_signed(s['delta'])} "
            f"| {s['wins']}/{s['losses']}/{s['ties']} "
            f"| {_short(sc.get('user_prompt',''), 40)} |"
        )

    lines += [
        "",
        "### 軸別の差分 (各軸 1〜5、高いほど良い)",
        "",
        "| 軸 | treat 平均 | ctrl 平均 | Δ |",
        "|---|---|---|---|",
    ]
    for axis in SCORE_AXES:
        a = axis_agg[axis]
        lines.append(
            f"| {AXIS_JA[axis]} | {a['treatment']:.2f} | {a['control']:.2f} | {_signed(a['delta'])} |"
        )

    lines += [
        "",
        f"_シナリオは `/skill-eval:create-test` で作成。`success_criteria` は ground truth として採点されます。_",
        f"_生成: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%MZ')} (UTC)_",
    ]
    return "\n".join(lines)


def _render_full(skill_path, mode, verdict, agg, axis_agg, coverage, failures,
                 scenarios, new_text, old_text, pr_num, head_sha, base_sha,
                 evaluator_model, samples_per_arm) -> str:
    parts = [_render_summary(skill_path, mode, verdict, agg, axis_agg,
                             coverage, failures, evaluator_model, samples_per_arm)]

    parts.append("\n## シナリオ別詳細")

    for s in agg["per_scenario"]:
        sc = s["scenario"]
        expectation = sc.get("expectation", "should_fire")
        parts.append(
            f"\n### {sc.get('id','?')} — archetype: `{sc.get('archetype','?')}` / "
            f"期待: `{expectation}` ({_expectation_ja(expectation)})"
        )
        parts.append(f"\n**ユーザー発話**:\n\n> {sc.get('user_prompt','')}\n")
        if sc.get("skill_relevance"):
            parts.append(f"**skill_relevance** (この skill のどの側面を検証しているか):\n\n> {sc['skill_relevance']}\n")
        crit = sc.get("success_criteria", [])
        if crit:
            parts.append("**成功条件 (success_criteria)**:")
            for c in crit:
                parts.append(f"- {c}")
            parts.append("")

        parts.append(
            f"**arm 平均**: treatment {s['treatment_mean']:.2f} / "
            f"control {s['control_mean']:.2f} / Δ {_signed(s['delta'])} ・ "
            f"ペア集計: {s['wins']}勝 / {s['losses']}敗 / {s['ties']}引分 "
            f"(全 {s['pair_total']} ペア)"
        )

        # Per-scenario per-axis breakdown
        parts.append("\n**この シナリオの 軸別差分**:")
        parts.append("\n| 軸 | treat | ctrl | Δ |")
        parts.append("|---|---|---|---|")
        for axis in SCORE_AXES:
            t_vals = [r.get(axis) for r in s["treatment_runs"] if isinstance(r.get(axis), (int, float))]
            c_vals = [r.get(axis) for r in s["control_runs"] if isinstance(r.get(axis), (int, float))]
            tm = _safe_mean(t_vals); cm = _safe_mean(c_vals)
            parts.append(f"| {AXIS_JA[axis]} | {tm:.2f} | {cm:.2f} | {_signed(tm-cm)} |")

        parts.append("\n**run スコア** (匿名 run_id × arm; 評価者は arm を知らずに採点):")
        parts.append("\n| run_id | arm | success | completeness | skill_engagement | conciseness | コメント |")
        parts.append("|---|---|---|---|---|---|---|")
        all_runs = list(s["treatment_runs"]) + list(s["control_runs"])
        for r in all_runs:
            label = r.get("error") and f"⚠️ {_short(r.get('error',''), 70)}" \
                or _short(r.get("feedback", "-"), 80)
            parts.append(
                f"| {r.get('run_id','?')} | {r.get('arm','?')} | "
                f"{r.get('success','-')} | {r.get('completeness','-')} | "
                f"{r.get('skill_engagement','-')} | {r.get('conciseness','-')} | "
                f"{label} |"
            )

        best_t = _best_run(s["treatment_runs"])
        best_c = _best_run(s["control_runs"])
        worst_t = _worst_run(s["treatment_runs"])
        worst_c = _worst_run(s["control_runs"])
        if best_t or best_c or worst_t or worst_c:
            parts.append("\n<details><summary>注目 transcript (各 arm の最良・最悪)</summary>\n")
            for label, run in [
                ("treatment 最良", best_t),
                ("control 最良", best_c),
                ("treatment 最悪", worst_t),
                ("control 最悪", worst_c),
            ]:
                if not run:
                    continue
                arm = run.get("arm", "?")
                idx = run.get("idx", "?")
                rid = run.get("run_id", "?")
                parts.append(f"\n**{label} ({rid}, {arm}_{idx})**:\n")
                parts.append("```")
                parts.append(_short(_lookup_transcript(scenarios, sc, run), 1500))
                parts.append("```")
            parts.append("\n</details>")

    parts.append("\n## 入力情報")
    parts.append(f"- PR #{pr_num}, head `{head_sha[:7]}`, base `{base_sha[:7]}`")
    parts.append(f"- mode: **{MODE_JA.get(mode, mode)}**")
    parts.append(f"- 評価モデル: `{evaluator_model}` / N={samples_per_arm} per arm")
    if failures:
        parts.append(f"- ⚠️ 失敗ラン: **{failures} 件** (詳細は各シナリオの run スコア表のコメント欄)")
    parts.append(
        "\n<details><summary>SKILL.md 差分 (unified diff)</summary>\n\n```diff\n"
        + _unified_diff(old_text, new_text)
        + "\n```\n</details>"
    )
    parts.append("\n<details><summary>NEW skill body</summary>\n\n```markdown\n"
                 + (new_text or "(empty — 削除されたため本体なし)") + "\n```\n</details>")
    parts.append("\n<details><summary>OLD skill body</summary>\n\n```markdown\n"
                 + (old_text or "(empty — 新規追加のため旧版なし)") + "\n```\n</details>")
    return "\n".join(parts)


def _unified_diff(old: str, new: str) -> str:
    if not old and not new:
        return "(diff なし)"
    diff = difflib.unified_diff(
        (old or "").splitlines(),
        (new or "").splitlines(),
        fromfile="OLD",
        tofile="NEW",
        lineterm="",
        n=3,
    )
    text = "\n".join(diff)
    return text or "(差分なし — 内容は同一)"


def _best_run(runs: list[dict]) -> dict | None:
    scored = [r for r in runs if _has_scores(r)]
    if not scored:
        return None
    return max(scored, key=_run_mean)


def _worst_run(runs: list[dict]) -> dict | None:
    scored = [r for r in runs if _has_scores(r)]
    if not scored:
        return None
    return min(scored, key=_run_mean)


def _lookup_transcript(scenarios: list[dict], scenario: dict, scored_run: dict) -> str:
    for entry in scenarios:
        if entry["scenario"].get("id") == scenario.get("id"):
            for raw in entry.get("runs", []):
                if (raw.get("arm") == scored_run.get("arm")
                        and raw.get("idx") == scored_run.get("idx")):
                    return raw.get("transcript", "") or raw.get("error", "") or ""
    return ""


def _truncate_to_budget(md: str) -> str:
    if len(md.encode("utf-8")) <= SUMMARY_BYTE_BUDGET:
        return md
    truncated = md.encode("utf-8")[:SUMMARY_BYTE_BUDGET].decode("utf-8", errors="ignore")
    return truncated + "\n\n_…バイト上限のため切り詰めました。詳細は `.claude/skills/<skill>/skill-eval/reports/` の永続レポートを参照してください。_"


def _signed(x: float) -> str:
    return f"{x:+.2f}"


def _short(text: str, n: int) -> str:
    text = (text or "").strip().replace("\n", " ")
    return text if len(text) <= n else text[: n - 1] + "…"
