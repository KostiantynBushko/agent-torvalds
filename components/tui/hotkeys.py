"""
The hot-keys of the Torvalds TUI.

The table of the bindings, the matcher that finds the binding of a key,
and the screen that tells the operator what every key of the TUI does.

**The table is the only list.**  The keys of the command bar and the
hot-keys of the panes live in the same table, and the ``\\keys`` screen
is rendered from it — a key list that is a copy is a copy that goes
stale.  The ``\\help`` screen keeps the commands, and nothing else.

**The bindings are configuration.**  They live in the ``[hotkeys]``
section of the file the operator already has —
``~/.config/torvalds/config.toml`` — and the operator may replace any
of them.  A value replaces the default of its action and frees the key
the action had; an empty value unbinds the action; a chord the
operating system takes, a chord that cannot be read and a chord that
two actions ask for are **refused**, with a warning, and the default
stands.

**A refusal is never a crash.**  The TUI starts, the default stands, and
the operator is told which setting of which file was refused and why.
It is the rule the rest of the configuration file already follows: *a
broken file is a warning, not a failed boot*.

Category: Infrastructure / TUI
Retriever Keywords: hotkeys, hot-keys, keyboard, shortcut, key binding,
                    tui, pane, focus, scroll, toggle, config
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Dict, List, Optional, Sequence, Tuple


# ---------------------------------------------------------------------------
# The scopes
# ---------------------------------------------------------------------------

#: The scope of a key of the command bar.  The application handles it,
#: and the registry only describes it.
SCOPE_BAR = "bar"

#: The scope of a hot-key that is live at all times — including while
#: the operator is typing, because a chord carries no text and cannot
#: eat what is being written.
SCOPE_GLOBAL = "global"

#: The scope of a hot-key that is live only while a pane has the focus.
SCOPE_PANE = "pane"


# ---------------------------------------------------------------------------
# The focus
# ---------------------------------------------------------------------------

#: The focus of the command bar.  It is the default, and nothing changes
#: for the operator who uses no hot-key at all.
FOCUS_INPUT = "input"

#: The focus of the document pane — the one on the left.
FOCUS_DOCUMENT = "document"

#: The focus of the progress pane — the one above the sidebar.
FOCUS_PROGRESS = "progress"

#: The focus of the telemetry pane — the one below the sidebar.
FOCUS_TELEMETRY = "telemetry"

#: The panes of the TUI, in the order of the focus cycle.
PANES: Tuple[str, ...] = (FOCUS_DOCUMENT, FOCUS_PROGRESS, FOCUS_TELEMETRY)

#: The marker of the pane that has the focus.
#:
#: The marker stands in front of the icon of the pane, so that the
#: operator sees which pane the keys go to.  It is one cell wide for
#: Rich, and one cell wide for the terminals that draw it that way --
#: the sign is of the "ambiguous" width, and the terminals of the
#: operator draw it as one cell.
FOCUS_MARKER = "\u25b6"

#: The gap behind the marker of the focused pane.
FOCUS_GAP = "  "

#: The pane of the layout that each focus belongs to.
#:
#: The focus of a pane and the name of the pane in the layout are two
#: names for the same thing, and the mapping is written down here — in
#: one place, so that the state, the layout and the views speak the
#: same language.
PANE_OF_FOCUS: Dict[str, str] = {
    FOCUS_DOCUMENT: "markdown_pane",
    FOCUS_PROGRESS: "progress_pane",
    FOCUS_TELEMETRY: "telemetry_pane",
}


# ---------------------------------------------------------------------------
# The actions
# ---------------------------------------------------------------------------

ACTION_TOGGLE_TELEMETRY = "toggle.telemetry"
ACTION_TOGGLE_PROGRESS = "toggle.progress"
ACTION_FOCUS_NEXT = "focus.next"
ACTION_FOCUS_PREVIOUS = "focus.previous"
ACTION_FOCUS_INPUT = "focus.input"
ACTION_SCROLL_UP = "scroll.up"
ACTION_SCROLL_DOWN = "scroll.down"
ACTION_SCROLL_PAGE_UP = "scroll.page_up"
ACTION_SCROLL_PAGE_DOWN = "scroll.page_down"
ACTION_SCROLL_HOME = "scroll.home"
ACTION_SCROLL_END = "scroll.end"


# ---------------------------------------------------------------------------
# The names of the keys
# ---------------------------------------------------------------------------

#: The names the configuration file uses for the plain keys, and the
#: names the reader gives them.
_KEY_NAMES: Dict[str, str] = {
    "ESC": "ESCAPE",
    "ESCAPE": "ESCAPE",
    "ENTER": "ENTER",
    "RETURN": "ENTER",
    "TAB": "TAB",
    "BACKSPACE": "BACKSPACE",
    "BKSP": "BACKSPACE",
    "DELETE": "DELETE",
    "DEL": "DELETE",
    "INSERT": "INSERT",
    "INS": "INSERT",
    "UP": "UP",
    "DOWN": "DOWN",
    "LEFT": "LEFT",
    "RIGHT": "RIGHT",
    "HOME": "HOME",
    "END": "END",
    "PGUP": "PGUP",
    "PAGEUP": "PGUP",
    "PGDN": "PGDN",
    "PAGEDOWN": "PGDN",
    "SPACE": "SPACE",
}

#: The function keys the reader names.
for _number in range(1, 21):
    _KEY_NAMES[f"F{_number}"] = f"F{_number}"

#: The names the configuration file uses for the modifiers, and the
#: names the reader gives them.
_MODIFIER_NAMES: Dict[str, str] = {
    "CTRL": "CTRL",
    "CONTROL": "CTRL",
    "ALT": "ALT",
    "META": "ALT",
    "SHIFT": "SHIFT",
}

#: The order the modifiers are named in.  It is fixed, so that the name
#: of a key is always the same word — and the name of a key is what a
#: binding is written against.
_MODIFIER_ORDER: Tuple[str, ...] = ("CTRL", "ALT", "SHIFT")

#: The names the ``\keys`` screen shows for the modifiers.
_MODIFIER_LABELS: Dict[str, str] = {
    "CTRL": "Ctrl",
    "ALT": "Alt",
    "SHIFT": "Shift",
}

#: The names the ``\keys`` screen shows for the plain keys.
_KEY_LABELS: Dict[str, str] = {
    "ESCAPE": "Esc",
    "ENTER": "Enter",
    "BACKSPACE": "Backspace",
    "DELETE": "Delete",
    "TAB": "Tab",
    "INSERT": "Insert",
    "UP": "Up",
    "DOWN": "Down",
    "LEFT": "Left",
    "RIGHT": "Right",
    "HOME": "Home",
    "END": "End",
    "PGUP": "PgUp",
    "PGDN": "PgDn",
    "SPACE": "Space",
}


# ---------------------------------------------------------------------------
# The chords the operating system takes
# ---------------------------------------------------------------------------

#: The chords the operating system takes, and the reason of each.
#:
#: A hot-key that the terminal or the desktop eats is not a hot-key.
#: The reader puts the terminal into *cbreak* mode, and cbreak is not
#: raw mode: ``ISIG`` and ``IXON`` are left exactly as they were.
SYSTEM_KEYS: Dict[str, str] = {
    "CTRL_C": "the kernel takes it — SIGINT",
    "CTRL_BACKSLASH": "the kernel takes it — SIGQUIT",
    "CTRL_Z": "the kernel takes it — SIGTSTP",
    "CTRL_S": "the terminal takes it — XOFF, and the screen freezes",
    "CTRL_Q": "the terminal takes it — XON",
    "CTRL_H": "the terminal takes it — it is the backspace",
    "CTRL_I": "the terminal takes it — it is the tab",
    "CTRL_J": "the terminal takes it — it is the enter",
    "CTRL_M": "the terminal takes it — it is the enter",
}


def parse_chord(text: str) -> Optional[str]:
    """The name of a chord, the way the reader names it.

    The configuration file writes the chords the way the operator reads
    them — ``Ctrl+T``, ``Shift+Tab``, ``PgDn`` — and the reader names
    them ``CTRL_T``, ``SHIFT_TAB`` and ``PGDN``.  This is the way from
    one to the other.

    Args:
        text: The chord, as the operator wrote it.

    Returns:
        The name of the chord, or None when it cannot be read.
    """
    if text is None:
        return None

    raw = str(text).strip()
    if not raw:
        return None

    pieces = [piece.strip() for piece in raw.split("+")]
    pieces = [piece for piece in pieces if piece]
    if not pieces:
        return None

    # The last piece is the key, and the ones before it are the
    # modifiers.
    key = pieces[-1].upper()
    modifiers: List[str] = []

    for piece in pieces[:-1]:
        name = _MODIFIER_NAMES.get(piece.upper())
        if name is None:
            return None
        if name not in modifiers:
            modifiers.append(name)

    if key in _KEY_NAMES:
        key = _KEY_NAMES[key]
    elif key.startswith("F") and key[1:].isdigit():
        # The function keys: F1 ... F20.
        number = int(key[1:])
        if not 1 <= number <= 20:
            return None
    else:
        # A single letter is a letter: the Ctrl chords are written
        # "Ctrl+T" and the Alt chords are written "Alt+a".
        if len(key) != 1 or not key.isalpha():
            return None

    # The order of the modifiers is fixed, so that the name of a chord
    # is always the same word.
    ordered = [name for name in _MODIFIER_ORDER if name in modifiers]
    return "_".join(ordered + [key])


def chord_label(name: str) -> str:
    """The name of a chord, the way the operator reads it.

    The other way round: ``CTRL_T`` becomes ``Ctrl+T``, and it is what
    the ``\\keys`` screen shows, and what the operator copies into the
    configuration file.

    Args:
        name: The name of the chord, the way the reader names it.

    Returns:
        The chord, the way the operator reads it.
    """
    if not name:
        return ""

    pieces = name.split("_")
    modifiers: List[str] = []
    while pieces and pieces[0] in _MODIFIER_LABELS:
        modifiers.append(_MODIFIER_LABELS[pieces.pop(0)])

    key = "_".join(pieces)
    if key in _KEY_LABELS:
        key = _KEY_LABELS[key]
    elif key.isalpha() and key.isupper() and len(key) > 1:
        key = key.capitalize()

    if not modifiers:
        return key
    return "+".join(modifiers + [key])


def refusal_reason(name: str) -> str:
    """Why a chord may not be bound — and an empty string when it may.

    Args:
        name: The name of the chord, the way the reader names it.

    Returns:
        The reason the chord is refused, and an empty string when it
        may be bound.
    """
    if not name:
        return "the chord is empty"
    if name in SYSTEM_KEYS:
        return SYSTEM_KEYS[name]
    if name.startswith("ALT_"):
        return "the Alt chords belong to the desktop"
    if name == "SPACE":
        return "a printable character always goes into the input"
    return ""


def is_system_key(name: str) -> bool:
    """Whether the operating system takes the chord.

    Args:
        name: The name of the chord, the way the reader names it.

    Returns:
        True when the chord may not be bound.
    """
    return bool(refusal_reason(name))


# ---------------------------------------------------------------------------
# The table
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class HotKey:
    """One key of the TUI.

    Attributes:
        keys: The name of the key, the way the reader names it.
        action: The id of the action the key does — empty for a key of
            the command bar, which the application handles itself.
        description: What the ``\\keys`` screen says about the key.
        scope: ``bar``, ``global`` or ``pane``.
    """

    keys: str
    action: str = ""
    description: str = ""
    scope: str = SCOPE_BAR

    @property
    def label(self) -> str:
        """The name of the key, the way the operator reads it."""
        return chord_label(self.keys)

    @property
    def setting(self) -> str:
        """The key of the setting of the configuration file.

        The setting is named after the action: ``toggle.telemetry`` is
        the setting ``hotkeys.toggle_telemetry``.  One action, one
        setting — and a test holds the two lists together.
        """
        if not self.action:
            return ""
        return "hotkeys." + self.action.replace(".", "_")

    @property
    def option(self) -> str:
        """The name of the setting inside its table."""
        if not self.action:
            return ""
        return self.action.replace(".", "_")


#: The keys of the command bar.  The application handles them, and the
#: registry only describes them — they are here so that the ``\keys``
#: screen is rendered from one list.
BAR_KEYS: Tuple[HotKey, ...] = (
    HotKey(
        keys="ENTER",
        description="Submit the prompt, or confirm the answer of the agent",
    ),
    HotKey(
        keys="BACKSPACE",
        description="Delete the character before the cursor",
    ),
    HotKey(
        keys="DELETE",
        description="Delete the character under the cursor",
    ),
    HotKey(
        keys="LEFT",
        description="Move the cursor to the left",
    ),
    HotKey(
        keys="RIGHT",
        description="Move the cursor to the right",
    ),
    HotKey(
        keys="HOME",
        description="Jump to the start of the line",
    ),
    HotKey(
        keys="END",
        description="Jump to the end of the line",
    ),
    HotKey(
        keys="UP",
        description="Move up in the input, or browse its history",
    ),
    HotKey(
        keys="DOWN",
        description="Move down in the input, or browse its history",
    ),
    HotKey(
        keys="PGUP",
        description="Scroll the document pane up",
    ),
    HotKey(
        keys="PGDN",
        description="Scroll the document pane down",
    ),
    HotKey(
        keys="CTRL_C",
        description="Cancel the input, or leave the TUI when the bar is empty",
    ),
    HotKey(
        keys="CTRL_D",
        description="Cancel the input, or leave the TUI when the bar is empty",
    ),
    HotKey(
        keys="PASTE",
        description="Paste text into the input bar (a long paste scrolls to its end)",
    ),
)


#: The hot-keys of the panes.
#:
#: Every key of this table is free of the steal list of the operating
#: system — that is the rule the table is built by, and a test checks
#: it.  ``Ctrl+T`` and ``Ctrl+P`` are two chords from the letters that
#: are left, and they are mnemonics: *T*elemetry, *P*rogress.
HOT_KEYS: Tuple[HotKey, ...] = (
    HotKey(
        keys="CTRL_T",
        action=ACTION_TOGGLE_TELEMETRY,
        description="Show or hide the *Agent Telemetry & State* pane",
        scope=SCOPE_GLOBAL,
    ),
    HotKey(
        keys="CTRL_P",
        action=ACTION_TOGGLE_PROGRESS,
        description="Show or hide the *Workflow & Tool Progress* pane",
        scope=SCOPE_GLOBAL,
    ),
    HotKey(
        keys="TAB",
        action=ACTION_FOCUS_NEXT,
        description="Give the focus to the next pane",
        scope=SCOPE_GLOBAL,
    ),
    HotKey(
        keys="SHIFT_TAB",
        action=ACTION_FOCUS_PREVIOUS,
        description="Give the focus to the previous pane",
        scope=SCOPE_GLOBAL,
    ),
    HotKey(
        keys="ESCAPE",
        action=ACTION_FOCUS_INPUT,
        description="Give the focus back to the command bar",
        scope=SCOPE_GLOBAL,
    ),
    HotKey(
        keys="UP",
        action=ACTION_SCROLL_UP,
        description="Scroll the focused pane by one line",
        scope=SCOPE_PANE,
    ),
    HotKey(
        keys="DOWN",
        action=ACTION_SCROLL_DOWN,
        description="Scroll the focused pane by one line",
        scope=SCOPE_PANE,
    ),
    HotKey(
        keys="PGUP",
        action=ACTION_SCROLL_PAGE_UP,
        description="Scroll the focused pane by one page",
        scope=SCOPE_PANE,
    ),
    HotKey(
        keys="PGDN",
        action=ACTION_SCROLL_PAGE_DOWN,
        description="Scroll the focused pane by one page",
        scope=SCOPE_PANE,
    ),
    HotKey(
        keys="HOME",
        action=ACTION_SCROLL_HOME,
        description="Go to the top of the focused pane",
        scope=SCOPE_PANE,
    ),
    HotKey(
        keys="END",
        action=ACTION_SCROLL_END,
        description="Go to the bottom of the focused pane",
        scope=SCOPE_PANE,
    ),
)


#: Every key of the TUI, in one table.
ALL_KEYS: Tuple[HotKey, ...] = BAR_KEYS + HOT_KEYS


# ---------------------------------------------------------------------------
# The bindings in force
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Resolved:
    """The keys of the TUI, as they are in force.

    Attributes:
        bindings: Every key of the TUI — the keys of the command bar
            and the hot-keys — with the chord each action is bound to.
        problems: What was refused, and why.  A refusal is a warning,
            never a crash.
    """

    bindings: Tuple[HotKey, ...] = ALL_KEYS
    problems: Tuple[str, ...] = ()

    @property
    def hot_keys(self) -> Tuple[HotKey, ...]:
        """The hot-keys — the bindings that do something."""
        return tuple(binding for binding in self.bindings if binding.action)

    def by_key(self) -> Dict[str, HotKey]:
        """The bindings, by the name of the key they are bound to."""
        return {
            binding.keys: binding
            for binding in self.bindings
            if binding.action
        }

    def action_of(self, key: str) -> str:
        """The action a key is bound to — and an empty string when it is
        bound to nothing."""
        binding = self.by_key().get(key)
        return binding.action if binding is not None else ""

    def chord_of(self, action: str) -> str:
        """The chord an action is bound to — and an empty string when it
        is bound to nothing."""
        for binding in self.bindings:
            if binding.action == action:
                return binding.keys
        return ""


def _configured_chord(config: Any, binding: HotKey) -> Optional[str]:
    """The chord the configuration file asks for, if it asks for one.

    Args:
        config: The configuration of the agent.  None means there is no
            file, and every default stands.
        binding: The binding the chord is read for.

    Returns:
        The value of the file, or None when the file says nothing about
        the action.
    """
    if config is None or not binding.setting:
        return None

    try:
        value = config.get(binding.setting, None)
    except KeyError:
        # The setting is not in the schema of the file: the default
        # stands, and nothing is read.
        return None

    if value is None:
        return None
    return str(value)


def resolve(config: Any = None) -> Resolved:
    """The keys of the TUI, as they are in force.

    The defaults are the ones of the table.  A value of the file
    replaces the default of its action, and frees the key the action
    had.  An empty value unbinds the action.  A chord that cannot be
    read, a chord the operating system takes and a chord that two
    actions ask for are **refused** — with a warning, and the default
    stands.

    Args:
        config: The configuration of the agent.  None means the
            defaults, and nothing is read from a file.

    Returns:
        The keys of the TUI, and the problems the file carried.
    """
    problems: List[str] = []
    bindings: List[HotKey] = list(BAR_KEYS)
    # The chord that is bound, and the action that holds it.
    taken: Dict[str, str] = {}

    for binding in HOT_KEYS:
        raw = _configured_chord(config, binding)
        refused: List[str] = []
        candidate: Optional[str] = None

        if raw is not None:
            text = raw.strip()
            if not text:
                # An empty value unbinds the action: the key is free,
                # and the action does nothing.
                continue

            name = parse_chord(text)
            if name is None:
                refused.append(
                    f"the chord {text!r} of the setting {binding.setting} "
                    f"cannot be read"
                )
            else:
                reason = refusal_reason(name)
                if reason:
                    refused.append(
                        f"the chord {text!r} of the setting {binding.setting} "
                        f"is refused: {reason}"
                    )
                elif name in taken:
                    refused.append(
                        f"the chord {text!r} of the setting {binding.setting} "
                        f"is refused: it is already bound to {taken[name]}"
                    )
                else:
                    candidate = name

        if candidate is None:
            # The default of the action stands.
            if binding.keys in taken:
                refused.append(
                    f"the default chord {binding.label} of "
                    f"{binding.setting} is refused: it is already bound to "
                    f"{taken[binding.keys]}"
                )
                problems.extend(refused)
                continue
            candidate = binding.keys

        taken[candidate] = binding.action
        bindings.append(replace(binding, keys=candidate))
        problems.extend(refused)

    return Resolved(tuple(bindings), tuple(problems))


# ---------------------------------------------------------------------------
# The matcher
# ---------------------------------------------------------------------------

def match(
    key: str,
    resolved: Optional[Resolved] = None,
) -> Optional[HotKey]:
    """The binding of a key.

    Args:
        key: The name of the key, the way the reader names it.
        resolved: The keys in force.  The defaults when it is omitted.

    Returns:
        The binding of the key, or None when no binding claims it.
    """
    if not key:
        return None
    table = resolved.bindings if resolved is not None else ALL_KEYS
    for binding in table:
        if binding.action and binding.keys == key:
            return binding
    return None


def is_live(binding: HotKey, focus: str) -> bool:
    """Whether the binding is live in the given focus.

    The chords are global: they are live whatever the operator is
    doing, because a chord carries no text and cannot eat what is
    being written.  The keys of a pane are live only while that pane
    has the focus.

    Args:
        binding: The binding.
        focus: The focus of the TUI.

    Returns:
        True when the binding may be applied.
    """
    if binding.scope == SCOPE_GLOBAL:
        return True
    if binding.scope == SCOPE_PANE:
        return focus != FOCUS_INPUT
    return False


# ---------------------------------------------------------------------------
# The screen
# ---------------------------------------------------------------------------

def settings_markdown(resolved: Optional[Resolved] = None) -> str:
    """The lines of the ``[hotkeys]`` section, as they stand now.

    The operator copies them into the configuration file.  The lines
    carry the chords the operator has today, so that the file says
    what the screen says.

    Args:
        resolved: The keys in force.  The defaults when it is omitted.

    Returns:
        The lines of the section, in the TOML of the file.
    """
    table = resolved.bindings if resolved is not None else ALL_KEYS

    lines = ["[hotkeys]"]
    for binding in table:
        if not binding.action:
            continue
        lines.append(f"{binding.option} = \"{binding.label}\"")
    return "\n".join(lines)


def keys_markdown(resolved: Optional[Resolved] = None) -> str:
    """The screen of the keys of the TUI.

    Every key of the TUI is named: the keys of the command bar and the
    hot-keys of the panes, in one table, from one source.

    Args:
        resolved: The keys in force.  The defaults when it is omitted.

    Returns:
        The Markdown document of the ``\\keys`` screen.
    """
    table = resolved.bindings if resolved is not None else ALL_KEYS

    lines: List[str] = [
        "# Keys of the Torvalds TUI",
        "",
        "Every key of this interface: the keys of the command bar and "
        "the hot-keys of the panes.",
        "",
        "## The command bar",
        "",
    ]

    for binding in table:
        if binding.scope != SCOPE_BAR:
            continue
        lines.append(f"- **{binding.label}** — {binding.description}")

    lines.extend(["", "## The hot-keys", ""])
    for binding in table:
        if binding.scope == SCOPE_BAR:
            continue
        lines.append(f"- **{binding.label}** — {binding.description}")

    lines.extend(
        [
            "",
            "## The panes",
            "",
            "| Pane | What it carries |",
            "| :--- | :--- |",
            "| *Markdown Document Viewer* | the answer of the agent, the "
            "documents |",
            "| *Workflow & Tool Progress* | the workflow iteration and the "
            "tools the agent runs |",
            "| *Agent Telemetry & State* | the counters, the size of the "
            "prompt, the tools the agent has |",
            "",
            "`Tab` moves the focus from pane to pane, and the cycle wraps "
            "around.  The pane that has the focus carries a brighter "
            "border and the marker `▶` in its title.",
            "",
            "A printable character always goes into the command bar, and "
            "it takes the focus back with it: the operator is never "
            "trapped in a pane.",
            "",
            "## The configuration",
            "",
            "The bindings live in the `[hotkeys]` section of the "
            "configuration file — "
            "`~/.config/torvalds/config.toml` — and the operator may "
            "replace any of them.  A value replaces the default of its "
            "action and frees the key the action had; an empty value "
            "unbinds the action.",
            "",
            "These are the lines to copy, with the chords as they are "
            "now:",
            "",
            "```toml",
            settings_markdown(resolved),
            "```",
        ]
    )

    return "\n".join(lines).rstrip() + "\n"


__all__ = [
    "ACTION_FOCUS_INPUT",
    "ACTION_FOCUS_NEXT",
    "ACTION_FOCUS_PREVIOUS",
    "ACTION_SCROLL_DOWN",
    "ACTION_SCROLL_END",
    "ACTION_SCROLL_HOME",
    "ACTION_SCROLL_PAGE_DOWN",
    "ACTION_SCROLL_PAGE_UP",
    "ACTION_SCROLL_UP",
    "ACTION_TOGGLE_PROGRESS",
    "ACTION_TOGGLE_TELEMETRY",
    "ALL_KEYS",
    "BAR_KEYS",
    "FOCUS_DOCUMENT",
    "FOCUS_GAP",
    "FOCUS_INPUT",
    "FOCUS_MARKER",
    "FOCUS_PROGRESS",
    "FOCUS_TELEMETRY",
    "HOT_KEYS",
    "HotKey",
    "PANE_OF_FOCUS",
    "PANES",
    "Resolved",
    "SCOPE_BAR",
    "SCOPE_GLOBAL",
    "SCOPE_PANE",
    "SYSTEM_KEYS",
    "chord_label",
    "is_live",
    "is_system_key",
    "keys_markdown",
    "match",
    "parse_chord",
    "refusal_reason",
    "resolve",
    "settings_markdown",
]
