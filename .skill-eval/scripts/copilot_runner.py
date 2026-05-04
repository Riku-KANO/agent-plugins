"""Thin wrapper around github-copilot-sdk v0.3.0.

The SDK is in public preview. All SDK-specific shape (imports, event data
classes, permission-handler return type) is intentionally isolated in this
module so that breaking changes only require updating one file.

Skill loading: we use the SDK's native ``skill_directories`` parameter on
``create_session``. The parent directory passed in is expected to contain
``<skill-name>/SKILL.md`` immediate subdirectories.

This is the production code path Claude uses when it loads skills, so the A/B
eval measures real behavior rather than a prompt-embedding simulation.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from copilot import CopilotClient, SubprocessConfig
from copilot.session import PermissionRequestResult
from copilot.generated.session_events import (
    AssistantMessageData,
    SessionIdleData,
)

DEFAULT_MODEL = "claude-sonnet-4.5"
DEFAULT_TIMEOUT = 180.0

# Permission kinds (per v0.3.0 PermissionRequest.kind enum):
# "shell" | "write" | "read" | "mcp" | "custom-tool" | "url" | "memory" | "hook"
# We approve only filesystem reads; everything else is denied so the evaluator
# environment stays hermetic.
APPROVED_KINDS = {"read"}


def restrictive_permission_handler(request, invocation):
    kind = request.kind.value if hasattr(request.kind, "value") else str(request.kind)
    if kind in APPROVED_KINDS:
        return PermissionRequestResult(kind="approved")
    return PermissionRequestResult(kind="denied-by-rules")


@asynccontextmanager
async def make_runner(model: str = DEFAULT_MODEL) -> AsyncIterator["Runner"]:
    """Create a Runner backed by an isolated Copilot CLI subprocess.

    The CLI's working directory is a fresh tempdir so prompt-injection in a
    skill body cannot trick the model into reading repository files.
    """
    cwd = tempfile.mkdtemp(prefix="cp-cwd-")
    try:
        config = SubprocessConfig(
            github_token=os.environ["COPILOT_GITHUB_TOKEN"],
            use_logged_in_user=False,
            cwd=cwd,
        )
        async with CopilotClient(config) as client:
            yield Runner(client=client, model=model)
    finally:
        shutil.rmtree(cwd, ignore_errors=True)


class Runner:
    def __init__(self, client: CopilotClient, model: str):
        self.client = client
        self.model = model

    async def run(
        self,
        prompt: str,
        *,
        skill_parent_dir: Path | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> str:
        kwargs: dict = {
            "on_permission_request": restrictive_permission_handler,
            "model": self.model,
        }
        if skill_parent_dir is not None:
            kwargs["skill_directories"] = [str(skill_parent_dir)]

        async with await self.client.create_session(**kwargs) as session:
            done = asyncio.Event()
            collected: list[str] = []

            def on_event(event):
                data = getattr(event, "data", event)
                if isinstance(data, AssistantMessageData):
                    text = getattr(data, "content", None) or getattr(data, "text", "")
                    if text:
                        collected.append(text)
                elif isinstance(data, SessionIdleData):
                    done.set()

            session.on(on_event)
            await session.send(prompt)
            await asyncio.wait_for(done.wait(), timeout=timeout)
            return "".join(collected).strip()
