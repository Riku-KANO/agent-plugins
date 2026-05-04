"""Load user-authored scenarios from .claude/skills/<skill>/skill-eval/scenarios.json.

This plugin does not auto-generate scenarios at runtime (in contrast to the
skill-eval-sample reference which uses a Planner agent). Scenarios are created
ahead of time via the `/skill-eval:create-test` interview flow and committed
to the repo, co-located with the skill they exercise.

If the file is missing for a changed skill, the orchestrator surfaces a
"create scenarios first" message in the PR comment and skips that skill —
this avoids silent passes.
"""

from __future__ import annotations

import json
from pathlib import Path

SKILLS_ROOT = Path(".claude/skills")
SCENARIOS_FILE = "skill-eval/scenarios.json"


def scenarios_path(skill_name: str) -> Path:
    return SKILLS_ROOT / skill_name / SCENARIOS_FILE


def load(skill_name: str) -> list[dict] | None:
    """Return the scenarios list, or None if no scenarios file exists.

    Fills in `expectation: "should_fire"` when missing so older scenario
    files (pre-`expectation` schema) keep working under the assumption that
    every scenario was a positive trigger case.
    """
    f = scenarios_path(skill_name)
    if not f.exists():
        return None
    data = json.loads(f.read_text(encoding="utf-8"))
    scenarios = data.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        return None
    for sc in scenarios:
        sc.setdefault("expectation", "should_fire")
    return scenarios
