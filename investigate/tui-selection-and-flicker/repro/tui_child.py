"""
Run the real multi-window TUI in a pty and capture the raw byte stream.

The child process starts the *production* TUI (``components.tui.TuiApp``)
with a stub agent, so the captured bytes are exactly what a user sees.
Three things can be injected while the TUI runs:

``--noisy``
    The agent logs while it works - what the real agent does on every
    iteration of its loop.

``--legacy-console``
    The console is built the way it was before the change: with no size
    and with the environment as it is.  This is how the defect is
    reproduced.

``--mode request``
    The agent is put to work: the document pane fills with a long
    answer and the progress pane shows running tools.

The size Rich believes the terminal has, and the log file the TUI
writes into, are written to the file named by
``TORVALDS_PROBE_SIZE_FILE`` - they are the first things that go
wrong, and the probe needs them.

Usage:
    python tui_child.py [--seconds N] [--mode idle|request] [--noisy]
                         [--legacy-console]
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from rich.console import Console  # noqa: E402

from components.tui.log_routing import resolve_tui_log_config  # noqa: E402
from components.tui.state_bridge import TuiState  # noqa: E402
from components.tui.tui_app import TuiApp  # noqa: E402

LONG_ANSWER = """## Result of the review

The branch `deferred-auto-enrolment` carries six commits on top of
`master` and two of them are still local.  The work splits cleanly into
two independent concerns:

1. The deferred auto-enrolment feature itself, which is ready to be
   pushed and reviewed.
2. The face-database management commands, which belong to a different
   feature and must stay out of this branch.

The submodule pins commit `3528dd1`, and that commit has to exist on the
submodule remote or CI cannot build the pull request at all.  The check
is cheap, and it is the one thing that can still break the build after
everything else is in place.

### Recommendation

Push the six commits, open the pull request against `master`, and keep
the face-database work on its own branch until the review is done.
"""


class StubAgent:
    """A stand-in for the agent - the TUI only passes it through."""

    llm = None


async def fake_prompt_handler(cmd, agent, enable_stats=True, event_consumer=None):
    """Simulate a request: the panes change while the answer is produced."""
    state = fake_prompt_handler.state
    state.set_busy(True, cmd)
    state.update_tool_start("execute_shell_command", {"command": "git status"})
    await asyncio.sleep(0.4)
    state.update_tool_end("execute_shell_command", "On branch master", False)
    state.update_tool_start("git_diff", {"file_path": "README.md"})
    await asyncio.sleep(0.4)
    state.update_tool_end("git_diff", "diff --git", False)
    state.set_markdown_content(LONG_ANSWER)
    state.set_busy(False)
    return LONG_ANSWER, None


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=float, default=4.0)
    parser.add_argument("--mode", choices=["idle", "request"], default="idle")
    parser.add_argument("--noisy", action="store_true")
    parser.add_argument("--legacy-console", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stderr)],
        force=True,
    )
    logger = logging.getLogger("probe")

    # The legacy console: the way the TUI was built before the change.
    # The production TUI builds its own console, and that console asks
    # the terminal for its size.
    console = Console() if args.legacy_console else None

    state = TuiState()
    state.model_name = "llama3:8b"
    state.memory_msg_count = 12

    fake_prompt_handler.state = state

    app = TuiApp(
        agent=StubAgent(),
        prompt_handler_fn=fake_prompt_handler,
        state=state,
        console=console,
        target_fps=15,
    )

    # What the console of the TUI believes, and where the log goes.
    # Both are written to a file, not to the terminal, so the capture is
    # not disturbed.
    size_file = os.environ.get("TORVALDS_PROBE_SIZE_FILE")
    if size_file:
        try:
            log_file = str(resolve_tui_log_config().log_file)
        except Exception as exc:  # noqa: BLE001 - the report is not a run
            log_file = f"(unresolved: {exc})"
        with open(size_file, "w", encoding="utf-8") as handle:
            handle.write(f"console={app.console.width}x{app.console.height}\n")
            handle.write(f"log_file={log_file}\n")

    async def driver() -> None:
        if args.mode == "request":
            await asyncio.sleep(0.6)
            asyncio.create_task(app._execute_agent_query("please review the branch"))
        if args.noisy:
            # The agent logs while it works - what the real agent does on
            # every iteration of its loop.
            await asyncio.sleep(1.0)
            for i in range(6):
                logger.info("event %s received", i)
                await asyncio.sleep(0.25)

    asyncio.create_task(driver())
    try:
        await asyncio.wait_for(app.run(), timeout=args.seconds)
    except asyncio.TimeoutError:
        pass
    finally:
        state.exit_requested = True


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    sys.exit(0)
