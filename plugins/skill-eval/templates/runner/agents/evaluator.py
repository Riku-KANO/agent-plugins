"""Evaluator agent: score 6 transcripts on a 4-axis rubric, with arms hidden.

Bias mitigation:
1. Arm labels are stripped before the prompt is built. Runs are presented as
   `run_1`..`run_N` in shuffled order.
2. The mapping `run_id -> {arm, idx}` is returned so the caller can re-attach
   labels when aggregating.
3. The evaluator model is configurable so it can differ from the implementer
   model (`--evaluator-model`).
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

from copilot_runner import Runner

PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "evaluator.md"


async def score(
    runner: Runner,
    scenario: dict,
    runs: list[dict],
    rng: random.Random | None = None,
) -> dict:
    """Returns {scores: {run_id: {success, completeness, ..., feedback,
    arm, idx, error}}, mapping: {run_id: (arm, idx)}}.

    If the evaluator session returns empty/non-JSON content (e.g. because
    Copilot's permission handler blocked an intermediate tool call and the
    model bailed out without writing a final answer), we log the failure and
    return empty per-run scores for this scenario so the orchestrator can
    continue evaluating remaining scenarios instead of crashing the entire run.
    """
    rng = rng or random.Random(0xC0FFEE)
    presented, mapping = _anonymize(runs, rng)
    prompt = _build_prompt(scenario, presented)
    raw = await runner.run(prompt)

    parse_error = None
    try:
        parsed = _parse_json(raw)
    except (json.JSONDecodeError, ValueError) as e:
        parse_error = e
        parsed = {"scores": {}}
        print(
            f"[evaluator] could not parse evaluator output for scenario "
            f"{scenario.get('id','?')}: {type(e).__name__}: {e} | "
            f"raw_len={len(raw)} raw_first200={raw[:200]!r}",
            file=sys.stderr,
            flush=True,
        )
    scores = parsed.get("scores", {})

    out_scores: dict[str, dict] = {}
    for run_id, info in mapping.items():
        s = dict(scores.get(run_id, {}))
        s["run_id"] = run_id
        s["arm"] = info["arm"]
        s["idx"] = info["idx"]
        s["error"] = info.get("error") or (
            f"evaluator parse failed: {parse_error}" if parse_error else None
        )
        out_scores[run_id] = s
    return {"scores": out_scores, "mapping": mapping}


def _anonymize(runs: list[dict], rng: random.Random) -> tuple[list[dict], dict]:
    shuffled = runs[:]
    rng.shuffle(shuffled)
    presented = []
    mapping: dict[str, dict] = {}
    for i, r in enumerate(shuffled, start=1):
        rid = f"run_{i}"
        presented.append(
            {
                "run_id": rid,
                "transcript": r.get("transcript", "")
                if not r.get("error")
                else f"(run failed: {r.get('error')})",
            }
        )
        mapping[rid] = {"arm": r["arm"], "idx": r["idx"], "error": r.get("error")}
    return presented, mapping


def _build_prompt(scenario: dict, presented: list[dict]) -> str:
    template = PROMPT_PATH.read_text(encoding="utf-8")
    return (
        template
        + "\n\n===SCENARIO_START===\n"
        + json.dumps(scenario, ensure_ascii=False, indent=2)
        + "\n===SCENARIO_END===\n\n===RUNS_START===\n"
        + json.dumps(presented, ensure_ascii=False, indent=2)
        + "\n===RUNS_END===\n"
    )


def _parse_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
        text = text.strip()
    return json.loads(text)
