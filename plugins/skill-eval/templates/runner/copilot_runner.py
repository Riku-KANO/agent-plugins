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
import sys
import tempfile
from collections import Counter
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
#
# We approve filesystem reads AND the model's own internal custom-tool calls.
# Blocking custom-tool causes Claude to emit no final AssistantMessageData
# after a denied tool request — the session goes idle with empty transcripts,
# which then crashes downstream JSON parsing in the evaluator.
#
# Higher-risk kinds (shell, write, mcp, url, memory, hook) stay denied so the
# evaluator environment remains hermetic.
APPROVED_KINDS = {"read", "custom-tool"}


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
            seen_event_types: list[str] = []
            session_errors: list[str] = []

            def _summarize_event(data) -> str:
                """Stringify an event payload for diagnostic logging.

                We avoid importing every concrete event class because the SDK
                is in preview and class layouts can shift. We pull whatever
                interesting attributes are present.
                """
                interesting = ("error", "message", "code", "reason", "detail",
                               "details", "kind", "status")
                bits = {}
                for attr in interesting:
                    if hasattr(data, attr):
                        try:
                            bits[attr] = repr(getattr(data, attr))
                        except Exception:
                            bits[attr] = "<unreadable>"
                if not bits:
                    # Fall back to vars() / repr()
                    try:
                        return repr(vars(data))[:500]
                    except Exception:
                        return repr(data)[:500]
                return repr(bits)

            def on_event(event):
                data = getattr(event, "data", event)
                type_name = type(data).__name__
                seen_event_types.append(type_name)
                if isinstance(data, AssistantMessageData):
                    if data.content:
                        collected.append(data.content)
                elif type_name == "SessionErrorData":
                    # Defensive: capture any error info regardless of attribute shape.
                    session_errors.append(_summarize_event(data))
                elif isinstance(data, SessionIdleData):
                    done.set()

            session.on(on_event)
            await session.send(prompt)
            await asyncio.wait_for(done.wait(), timeout=timeout)
            result = "".join(collected).strip()

            if not result:
                # Empty response — log enough diagnostic info that we can
                # debug from CI logs alone (event mix + error payloads + any
                # message history surfaced by the SDK).
                event_counts = dict(Counter(seen_event_types))
                err_summary = " | ".join(session_errors[:3]) if session_errors else "(no SessionErrorData captured)"
                history_repr = "(get_messages unavailable)"
                try:
                    msgs = await session.get_messages()
                    history_repr = f"{len(msgs)} message(s); first200={repr(msgs)[:300]}"
                except Exception as e:
                    history_repr = f"(get_messages raised {type(e).__name__}: {e})"
                print(
                    f"[copilot_runner] empty response from session "
                    f"(model={self.model}, events={event_counts})\n"
                    f"  session_errors: {err_summary}\n"
                    f"  history: {history_repr}",
                    file=sys.stderr,
                    flush=True,
                )
            return result
