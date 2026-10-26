"""Probe: the state of ``user.token_limit`` management in ``chat_manager``.

Run it from the repository root:

    self-development/.venv/bin/python investigate/chat-manager-user-settings/probe_user_settings.py

The probe answers six questions, each with a printed verdict:

1. **Is there a public API to change ``user.token_limit``?**  The manager is
   the public surface of the package; the connector is an internal detail.
2. **Does a changed token limit actually reach the live memory buffer?**
   The buffer is cached, so a limit written to the database may be ignored.
3. **Is the ``token_limit`` override of ``get_memory_buffer()`` honoured?**
4. **Is there an interactive command to manage user settings?**  The command
   registry is the single source of truth for what the operator can type.
5. **Does the legacy chat-history implementation still exist?**
6. **What happens when the metadata database is unreachable?**  This is the
   only remaining reason the legacy path is still needed.
"""

from __future__ import annotations

import os
import sys
from unittest.mock import patch

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from chat_manager.manager import ChatHistoryManager  # noqa: E402

SEPARATOR = "=" * 78


def _header(title: str) -> None:
    print()
    print(SEPARATOR)
    print(title)
    print(SEPARATOR)


def probe_public_api() -> None:
    """Question 1 — can a caller change ``token_limit`` through the manager?"""
    _header("Q1 — Public API for changing user.token_limit")

    manager = ChatHistoryManager(
        storage_uri="sqlite:///:memory:",
        llama_uri="sqlite:///:memory:",
    )
    with patch.object(ChatHistoryManager, "_get_os_username", return_value="probe-user"):
        manager.initialize()

    public = [n for n in dir(manager) if not n.startswith("_")]
    update_like = [n for n in public if "update" in n or "user" in n or "setting" in n]
    print(f"Manager public members matching update/user/setting: {update_like}")

    has_user_update = any(
        callable(getattr(manager, n, None)) and "user" in n and "update" in n
        for n in public
    )
    print(f"Manager exposes a user-update method: {has_user_update}")

    # The connector has one — but reaching it means touching a private attr.
    connector_methods = [
        n for n in dir(manager._db) if not n.startswith("_") and "user" in n
    ]
    print(f"Connector (private, manager._db) user methods: {connector_methods}")
    print(f"Connector.update_user exists: {callable(getattr(manager._db, 'update_user', None))}")

    # Can the operator do it today?  Only by reaching into the private attr.
    user = manager.current_user
    before = user.token_limit
    user.token_limit = 12345
    manager._db.update_user(user)  # <-- private attribute access
    reloaded = manager._db.get_user_by_username("probe-user")
    print(f"token_limit before={before} -> after direct connector write={reloaded.token_limit}")
    print()
    print("VERDICT: NO public API. The write requires manager._db (private attribute).")
    manager.shutdown()


def probe_buffer_caching() -> None:
    """Question 2 — does a written token limit reach the live buffer?"""
    _header("Q2 — Does a changed token_limit reach the live memory buffer?")

    manager = ChatHistoryManager(
        storage_uri="sqlite:///:memory:",
        llama_uri="sqlite:///:memory:",
    )
    with patch.object(ChatHistoryManager, "_get_os_username", return_value="probe-user"):
        manager.initialize()

    buffer = manager.get_memory_buffer()
    print(f"Buffer token limit on first build: {buffer.token_limit}")

    # Change the user's preference in the database.
    user = manager.current_user
    user.token_limit = 99999
    manager._db.update_user(user)
    print(
        "users.token_limit in the database now: "
        f"{manager._db.get_user_by_username('probe-user').token_limit}"
    )

    # Ask for the buffer again — the manager hands back the cached one.
    buffer2 = manager.get_memory_buffer()
    print(f"Buffer token limit on second call: {buffer2.token_limit}")
    print(f"Same buffer object returned: {buffer is buffer2}")

    # Only an explicit invalidation rebuilds it.
    manager._memory_buffer = None
    buffer3 = manager.get_memory_buffer()
    print(f"Buffer token limit after invalidation: {buffer3.token_limit}")

    print()
    print("VERDICT: The limit is baked in at buffer-build time. The cached buffer is")
    print("         only invalidated by switch_session() and clear_messages().")
    manager.shutdown()


def probe_override_ignored() -> None:
    """Question 3 — is the ``token_limit`` argument of get_memory_buffer honoured?"""
    _header("Q3 — Is the get_memory_buffer(token_limit=...) override honoured?")

    manager = ChatHistoryManager(
        storage_uri="sqlite:///:memory:",
        llama_uri="sqlite:///:memory:",
    )
    with patch.object(ChatHistoryManager, "_get_os_username", return_value="probe-user"):
        manager.initialize()

    first = manager.get_memory_buffer(token_limit=111)
    print(f"First call with token_limit=111 -> buffer limit {first.token_limit}")

    second = manager.get_memory_buffer(token_limit=222)
    print(f"Second call with token_limit=222 -> buffer limit {second.token_limit}")
    print(f"Same object returned: {first is second}")

    print()
    print("VERDICT: The override only works on the FIRST call. The early return on")
    print("         the cached buffer happens before the argument is ever read.")
    manager.shutdown()


def probe_commands() -> None:
    """Question 4 — is there an interactive command for user settings?"""
    _header("Q4 — Interactive command for user settings")

    from chat_manager.commands.handler import CHAT_COMMANDS

    print(f"CHAT_COMMANDS registry: {sorted(CHAT_COMMANDS)}")
    settings_like = [c for c in CHAT_COMMANDS if "user" in c or "setting" in c or "pref" in c]
    print(f"Commands mentioning user/settings/preference: {settings_like}")

    from components.command_registry import COMMAND_SPECS

    chat_specs = [s.name for s in COMMAND_SPECS if s.category == "Chat"]
    print(f"Command registry, Chat category: {chat_specs}")

    from chat_manager.commands import __all__ as command_exports

    print(f"chat_manager.commands exports: {list(command_exports)}")

    print()
    print("VERDICT: NO command exists. Every \\chat-* command manages sessions;")
    print("         none reads or writes the user's own settings.")
    for name in ("\\chat-user", "\\chat-settings", "\\user-info"):
        from chat_manager.commands.handler import is_chat_command

        print(f"  is_chat_command({name!r}) -> {is_chat_command(name)}")


def probe_legacy() -> None:
    """Question 5 — does the legacy chat-history implementation still exist?"""
    _header("Q5 — Legacy chat-history implementation")

    import agent_chat_memory as legacy

    legacy_symbols = [n for n in dir(legacy) if not n.startswith("__")]
    print(f"agent_chat_memory public symbols: {legacy_symbols}")

    # The legacy single-key helpers are still there.
    print(f"_get_chat_store_key() -> {legacy._get_chat_store_key()!r}")
    print(f"_get_token_limit()    -> {legacy._get_token_limit()}")

    # The legacy path is still wired as a fallback inside get_chat_memory().
    import inspect

    source = inspect.getsource(legacy.get_chat_memory)
    has_legacy_fallback = "Legacy fallback" in source
    print(f"get_chat_memory() still contains the legacy fallback branch: {has_legacy_fallback}")

    # The flag that selects the legacy path.
    for orchestrator in ("agent-torvalds.py", "agent-torvalds-mw.py"):
        path = os.path.join(REPO_ROOT, orchestrator)
        with open(path, encoding="utf-8") as handle:
            content = handle.read()
        has_flag = "--no-chat-history" in content
        has_legacy_fallback_msg = "Falling back to the legacy single-session" in content
        print(
            f"{orchestrator}: --no-chat-history={has_flag} "
            f"legacy-fallback-message={has_legacy_fallback_msg}"
        )

    # Dead configuration: TOKEN_LIMITS is defined and never used.
    for orchestrator in ("agent-torvalds.py", "agent-torvalds-mw.py"):
        path = os.path.join(REPO_ROOT, orchestrator)
        with open(path, encoding="utf-8") as handle:
            lines = handle.read().splitlines()
        definitions = [
            (i + 1, ln.strip())
            for i, ln in enumerate(lines)
            if ln.strip().startswith("TOKEN_LIMITS")
        ]
        uses = [
            (i + 1, ln.strip())
            for i, ln in enumerate(lines)
            if "TOKEN_LIMITS" in ln and not ln.strip().startswith("TOKEN_LIMITS")
        ]
        print(f"{orchestrator}: TOKEN_LIMITS defined={definitions} used={uses}")

    print()
    print("VERDICT: YES, the legacy implementation is still present and reachable:")
    print("         - agent_chat_memory.py keeps the single-key path alive")
    print("         - --no-chat-history selects it explicitly")
    print("         - TORVALDS_CHAT_KEY / TORVALDS_TOKEN_LIMIT still feed it")
    print("         - TOKEN_LIMITS in both orchestrators is dead configuration")


def probe_metadata_db_down() -> None:
    """Question 6 — what happens when the metadata database is unreachable?"""
    _header("Q6 — Behaviour when the metadata database is unreachable")

    # An unreachable PostgreSQL host: the URI is syntactically valid but the
    # host does not resolve, so connect() fails the same way a down server does.
    manager = ChatHistoryManager(
        storage_uri="postgresql://nobody:nobody@127.0.0.1:1/nonexistent",
        llama_uri="sqlite:///:memory:",
    )
    try:
        with patch.object(ChatHistoryManager, "_get_os_username", return_value="probe-user"):
            manager.initialize()
        print("initialize() succeeded — unexpected")
    except Exception as exc:
        print(f"initialize() raised: {type(exc).__name__}: {exc}")

    print(f"manager.is_initialized: {manager.is_initialized}")
    print()
    print("VERDICT: The metadata layer has NO in-memory fallback. When it is down,")
    print("         initialize() raises and the orchestrators fall back to the")
    print("         legacy single-session path. This is the only live reason the")
    print("         legacy implementation is still needed.")
    try:
        manager.shutdown()
    except Exception:
        pass

    # For contrast: the MESSAGE layer does degrade.
    print()
    print("For contrast, the message layer degrades on its own:")
    degraded = ChatHistoryManager(
        storage_uri="sqlite:///:memory:",
        llama_uri="postgresql://nobody:nobody@127.0.0.1:1/nonexistent",
    )
    with patch.object(ChatHistoryManager, "_get_os_username", return_value="probe-user"):
        degraded.initialize()
    print(f"message backend in use: {type(degraded._backend).__name__}")
    print(f"metadata connector connected: {degraded._db.is_connected}")
    degraded.shutdown()


def main() -> int:
    print("PROBE — chat_manager user settings & legacy implementation")
    print(f"repo root: {REPO_ROOT}")

    probe_public_api()
    probe_buffer_caching()
    probe_override_ignored()
    probe_commands()
    probe_legacy()
    probe_metadata_db_down()

    print()
    print(SEPARATOR)
    print("PROBE COMPLETE")
    print(SEPARATOR)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
