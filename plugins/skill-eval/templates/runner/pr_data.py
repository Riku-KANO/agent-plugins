"""Read PR file changes and fetch SKILL.md contents at the right SHAs.

The workflow runs `gh api .../pulls/<n>/files --paginate --slurp` which produces
an array-of-arrays (one inner array per page). We flatten it here.

OLD content is fetched at the PR base SHA (`baseRefOid`), not at the base
branch ref, so the comparison is stable even if the base branch advances
between PR creation and `/skill-eval` invocation.
"""

from __future__ import annotations

import base64
import json
import subprocess
from typing import TypedDict


SKILL_PREFIX = ".claude/skills/"
SKILL_SUFFIX = "/SKILL.md"


class SkillChange(TypedDict):
    path: str
    status: str           # added | modified | removed | renamed
    prev_path: str | None
    new_text: str
    old_text: str


def changed_skills(
    pr_files_path: str,
    head_sha: str,
    base_sha: str,
    repo: str,
) -> list[SkillChange]:
    with open(pr_files_path, encoding="utf-8") as f:
        raw = json.load(f)

    if raw and isinstance(raw[0], list):
        files = [entry for page in raw for entry in page]
    else:
        files = raw

    out: list[SkillChange] = []
    for entry in files:
        path = entry["filename"]
        prev = entry.get("previous_filename")
        if not (_is_skill_path(path) or _is_skill_path(prev)):
            continue

        status = entry["status"]
        new_text = ""
        old_text = ""

        if status != "removed":
            new_text = _fetch_file(repo, path, head_sha)

        if status != "added":
            old_path = prev or path
            old_text = _fetch_file(repo, old_path, base_sha)

        out.append(
            SkillChange(
                path=path,
                status=status,
                prev_path=prev,
                new_text=new_text,
                old_text=old_text,
            )
        )
    return out


def skill_dirname(path: str) -> str:
    """Extract `<name>` from `.claude/skills/<name>/SKILL.md`."""
    rest = path[len(SKILL_PREFIX):]
    return rest[: -len(SKILL_SUFFIX)]


def _is_skill_path(path: str | None) -> bool:
    return bool(path) and path.startswith(SKILL_PREFIX) and path.endswith(SKILL_SUFFIX)


def _fetch_file(repo: str, path: str, ref: str) -> str:
    """Fetch a file blob via `gh api repos/<owner>/<name>/contents/<path>?ref=<sha>`.

    Returns "" when the file does not exist at that ref.
    """
    from urllib.parse import quote
    encoded_path = "/".join(quote(seg, safe="") for seg in path.split("/"))
    res = subprocess.run(
        [
            "gh",
            "api",
            f"repos/{repo}/contents/{encoded_path}?ref={ref}",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if res.returncode != 0:
        if "Not Found" in res.stderr or "404" in res.stderr:
            return ""
        raise RuntimeError(
            f"gh api failed for {path}@{ref[:7]}: rc={res.returncode} {res.stderr.strip()}"
        )
    blob = json.loads(res.stdout)
    encoded = blob.get("content", "")
    return base64.b64decode(encoded).decode("utf-8")
