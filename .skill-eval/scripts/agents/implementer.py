"""Implementer agent: run a scenario in parallel under control and treatment arms.

Each arm is ``n_per_arm`` independent Copilot sessions. Skills are loaded via
the SDK's native ``skill_directories`` parameter — for each arm we materialize
the skill body into ``<tempdir>/<skill-name>/SKILL.md`` (the SDK expects the
parent directory passed to ``skill_directories`` to contain ``<name>/SKILL.md``
subdirectories) and pass that tempdir for every run in the arm.

When an arm has no skill (e.g. control arm of an addition mode), we pass
``skill_parent_dir=None`` so the session runs with no skills loaded — that is
the genuine baseline.
"""

from __future__ import annotations

import asyncio
import shutil
import tempfile
from pathlib import Path

from copilot_runner import Runner


async def run_ab(
    runner: Runner,
    scenario: dict,
    skill_dirname: str,
    control_text: str,
    treatment_text: str,
    n_per_arm: int = 3,
) -> list[dict]:
    """Run control and treatment arms in parallel for a single scenario.

    Returns a list of run dicts: ``{arm, idx, transcript, error}``.
    """
    ctrl_parent = _materialize(skill_dirname, control_text) if control_text else None
    treat_parent = _materialize(skill_dirname, treatment_text) if treatment_text else None

    try:
        tasks = []
        for i in range(n_per_arm):
            tasks.append(_safe_run(runner, scenario, ctrl_parent, "control", i))
            tasks.append(_safe_run(runner, scenario, treat_parent, "treatment", i))
        return await asyncio.gather(*tasks)
    finally:
        if ctrl_parent:
            shutil.rmtree(ctrl_parent, ignore_errors=True)
        if treat_parent:
            shutil.rmtree(treat_parent, ignore_errors=True)


def _materialize(skill_dirname: str, skill_text: str) -> str:
    """Create ``<tempdir>/<skill_dirname>/SKILL.md`` and return ``<tempdir>``."""
    parent = tempfile.mkdtemp(prefix="sk-")
    skill_dir = Path(parent) / skill_dirname
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(skill_text, encoding="utf-8")
    return parent


async def _safe_run(
    runner: Runner,
    scenario: dict,
    skill_parent_dir: str | None,
    arm: str,
    idx: int,
) -> dict:
    try:
        text = await runner.run(
            scenario["user_prompt"],
            skill_parent_dir=Path(skill_parent_dir) if skill_parent_dir else None,
        )
        return {"arm": arm, "idx": idx, "transcript": text, "error": None}
    except Exception as e:
        return {"arm": arm, "idx": idx, "transcript": "", "error": f"{type(e).__name__}: {e}"}
