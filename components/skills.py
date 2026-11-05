"""
Skills — procedures the agent loads on demand, from disk.

Why this module exists
----------------------
An agent skill is a procedure that is too long to keep in the system prompt
and too rare to be worth a tool: *how this project is deployed*, *the
checklist before a release*, *the way this database is migrated*.  The
**Agent Skills** format keeps such a procedure in a file and lets the model
load it when the task calls for it.

The format
-----------
A skill is a directory that holds one file, ``SKILL.md``::

    <skills-root>/<name>/SKILL.md

The file opens with a frontmatter block — the small subset of YAML the
format needs — and the body is the procedure itself::

    ---
    name: deploy
    description: Deploy this project to the remote host over SSH.
    ---

    # Deploy

    1. Check that the tests pass.
    2. Build the image.

The **name** is the name of the directory, unless the frontmatter names
one.  The **description** is one line, and it is what tells the model
whether the skill is worth loading at all.

Where the skills live
---------------------
Two roots, in this order:

1. ``~/.config/torvalds/skills`` — the skills of the operator, next to the
   configuration file;
2. ``<project>/skills`` — the skills of the project the agent works in.

A skill of the project **overrides** a skill of the operator with the same
name: the project is the more specific context, and a procedure that is
part of the project is the one that describes the project.

The cost — and why the catalog is *not* in the prompt
------------------------------------------------------
The obvious way to build this is *progressive disclosure*: the prompt
carries a catalog of the names and the descriptions, and the model asks
for the body of the one it needs.  The measurement in
``investigate/agent-skills/`` shows what that costs on the window of the
operator's model (8192 tokens)::

    catalog of 20 skills        908 tokens   (45 tokens per skill)
    activation tool schema      175 tokens
    the fixed cost             1083 tokens   16.5% of the prompt budget

That catalog is **paid on every request**, whether the run touches a skill
or not, and it grows with the number of skills.  On the window of the
operator's model it takes a third of the room the conversation had left.

This module therefore keeps the catalog off the prompt:

* the **prompt** carries one line, and only when there is at least one
  skill — the cost does not depend on how many there are;
* the **catalog** is fetched by a tool call, and lands in the
  conversation, where the context guard can drop it once it grows old;
* the **body** is loaded by a tool call and is cut to a token limit, so
  that one long skill cannot fill the window on its own.

The fixed cost of the feature is therefore the cost of the two tool
schemas — a constant, whether there are two skills or two hundred.

Category: Infrastructure
Retriever Keywords: skills, skill, procedures, progressive disclosure,
                    activate_skill, list_skills, catalog, prompt cost
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from components.tokens import CHARS_PER_TOKEN, estimate_tokens

logger = logging.getLogger(__name__)

#: The file that holds a skill.
SKILL_FILENAME = "SKILL.md"

#: The directory the skills of the operator live in, next to the
#: configuration file.
USER_SKILLS_DIRNAME = "skills"

#: The directory the skills of a project live in.
PROJECT_SKILLS_DIRNAME = "skills"

#: How many tokens the body of a skill may take when it is loaded.
DEFAULT_BODY_TOKEN_LIMIT = 2000

#: How many skills the catalog may name at once.
DEFAULT_CATALOG_LIMIT = 50

#: The marker put in front of a body that was cut.
TRUNCATION_MARKER = (
    "[the skill was cut here — it is longer than the limit; "
    "the full text is in the file named above]"
)

#: The marker used when the limit is too small for the long one.
SHORT_TRUNCATION_MARKER = "[the skill was cut]"

#: The frontmatter block: ``---`` … ``---`` at the very top of the file.
_FRONTMATTER_RE = re.compile(
    r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)",
    re.DOTALL,
)


# ---------------------------------------------------------------------------
# The skill
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Skill:
    """One procedure the agent can load.

    Attributes:
        name: The name the model uses to ask for the skill.
        description: One line, telling the model what the skill is for.
        path: The file the skill was read from.
        body: The procedure itself, without the frontmatter.
        scope: Where the skill came from — ``"user"`` or ``"project"``.
    """

    name: str
    description: str
    path: Path
    body: str
    scope: str = "user"

    @property
    def summary(self) -> str:
        """The one line the catalog shows."""
        return self.description or "(no description)"


# ---------------------------------------------------------------------------
# The frontmatter
# ---------------------------------------------------------------------------


def parse_frontmatter(text: str) -> Tuple[Dict[str, str], str]:
    """Split the frontmatter of a skill file from its body.

    The frontmatter is the small subset of YAML the skill format needs: a
    block of ``key: value`` lines between two ``---`` markers.  A key that
    continues on the next line — a folded description — is joined with a
    space, because that is the only continuation YAML has that a hand
    written skill needs.

    Args:
        text: The whole file.

    Returns:
        The pair ``(metadata, body)``.  A file without frontmatter has
        empty metadata, and its body is the whole file.
    """
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}, text

    metadata: Dict[str, str] = {}
    key: Optional[str] = None

    for line in match.group(1).splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        if line[:1] in (" ", "\t") and key is not None:
            # A continuation of the key above it.
            metadata[key] = f"{metadata[key]} {stripped}".strip()
            continue

        if ":" not in line:
            continue

        name, _, value = line.partition(":")
        key = name.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        metadata[key] = value

    return metadata, text[match.end():]


# ---------------------------------------------------------------------------
# The roots
# ---------------------------------------------------------------------------


def default_skill_roots(project_root: Optional[Path] = None) -> List[Path]:
    """Return the roots the skills are looked for in.

    The skills of the operator come first, the skills of the project
    second — and the project wins, because a procedure that belongs to the
    project is the one that describes it.

    Args:
        project_root: The directory of the project.  Defaults to the
            directory the agent runs in.

    Returns:
        The roots, in the order they are read.
    """
    home = Path(os.path.expanduser("~"))
    roots = [home / ".config" / "torvalds" / USER_SKILLS_DIRNAME]

    base = Path(project_root) if project_root is not None else Path.cwd()
    roots.append(base / PROJECT_SKILLS_DIRNAME)

    return roots


def root_scope(root: Path) -> str:
    """Return the scope of a root: ``"user"`` or ``"project"``.

    The roots of the operator are the ones under the configuration
    directory of the home folder; every other root belongs to a project.
    The scope is a label — it says where a skill came from, and the skill
    of the project is the one that wins.
    """
    home = Path(os.path.expanduser("~"))
    try:
        Path(root).relative_to(home / ".config" / "torvalds")
    except ValueError:
        return "project"
    return "user"


def parse_skill_dirs(value: Optional[str]) -> List[Path]:
    """Return the roots named by a ``skills.dirs`` setting.

    The setting is a list of directories separated by the separator of the
    platform (``;`` on Windows, ``:`` everywhere else).  An empty value
    means "the defaults".

    Args:
        value: The value of the setting.

    Returns:
        The roots, in the order they are read.  The last one wins.
    """
    if not value or not value.strip():
        return []

    separator = ";" if os.name == "nt" else ":"
    roots: List[Path] = []
    for part in value.split(separator):
        part = part.strip()
        if not part:
            continue
        roots.append(Path(os.path.expanduser(part)))
    return roots


# ---------------------------------------------------------------------------
# The discovery
# ---------------------------------------------------------------------------


def _read_skill_file(path: Path, scope: str) -> Optional[Skill]:
    """Read one skill file, or return ``None`` when it cannot be read.

    A skill that cannot be read is skipped, not fatal: a broken skill must
    never keep the agent from starting.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("Could not read the skill %s: %s", path, exc)
        return None

    metadata, body = parse_frontmatter(text)
    name = (metadata.get("name") or path.parent.name).strip()
    description = (metadata.get("description") or "").strip()

    if not name:
        logger.warning("The skill %s has no name — it is skipped.", path)
        return None

    return Skill(
        name=name,
        description=description,
        path=path,
        body=body.strip(),
        scope=scope,
    )


def discover_skills(roots: Sequence[Path]) -> List[Skill]:
    """Return every skill found under *roots*.

    A root is a directory of skill directories: each of them holds a
    ``SKILL.md``.  A root that does not exist is not an error — the
    operator may have no skills at all.

    Args:
        roots: The roots, in the order they are read.  A skill of a later
            root replaces a skill of an earlier one with the same name.

    Returns:
        The skills, sorted by name.
    """
    found: Dict[str, Skill] = {}

    for root in roots:
        root = Path(root)
        if not root.is_dir():
            continue

        for entry in sorted(root.iterdir()):
            if not entry.is_dir():
                continue

            path = entry / SKILL_FILENAME
            if not path.is_file():
                continue

            skill = _read_skill_file(path, scope=root_scope(root))
            if skill is None:
                continue

            found[skill.name] = skill

    return [found[name] for name in sorted(found)]


def find_skill(skills: Sequence[Skill], name: str) -> Optional[Skill]:
    """Return the skill called *name*, or ``None``.

    The lookup ignores the case and the surrounding space, because the
    name comes from a model that may write it either way.
    """
    wanted = (name or "").strip().lower()
    if not wanted:
        return None

    for skill in skills:
        if skill.name.lower() == wanted:
            return skill

    return None


# ---------------------------------------------------------------------------
# The catalog
# ---------------------------------------------------------------------------


def render_catalog(skills: Sequence[Skill], limit: int = DEFAULT_CATALOG_LIMIT) -> str:
    """Return the catalog of the skills, one line per skill.

    The format is deliberately flat: a bullet, the name, a colon and the
    description.  The XML shape of the specification costs about ten
    tokens per skill in tags alone, and the tags buy nothing — the model
    reads the names, not the markup.

    Args:
        skills: The skills.
        limit: How many skills the catalog may name.  The rest are
            counted, not listed.

    Returns:
        The catalog, or a line that says that there is none.
    """
    if not skills:
        return "There are no skills on this machine."

    listed = list(skills)[: max(0, limit)]
    lines = [
        f"- {skill.name}: {skill.summary}" for skill in listed
    ]

    remaining = len(skills) - len(listed)
    if remaining > 0:
        lines.append(
            f"- ... and {remaining} more — call list_skills to see them all"
        )

    return "\n".join(lines)


def render_prompt_section(
    skills: Sequence[Skill],
    catalog_in_prompt: bool = False,
    limit: int = DEFAULT_CATALOG_LIMIT,
) -> str:
    """Return the text the skills add to the system prompt.

    This is the whole of the *tier 1* of the progressive disclosure — and
    it is deliberately tiny.  Without the catalog, the prompt carries one
    line that tells the model the feature exists and how to use it; the
    catalog itself is fetched on demand.

    The line is what makes the feature reachable for a model that would
    otherwise never call ``list_skills``.  It costs the same whether
    there are two skills or two hundred.

    Args:
        skills: The skills.
        catalog_in_prompt: Whether the catalog is listed in the prompt.
            Off by default: the catalog is the expensive part.
        limit: How many skills the catalog may name.

    Returns:
        The text, or an empty string when there is no skill at all.
    """
    if not skills:
        return ""

    lines = [
        "### Skills",
        "",
        "Procedures for tasks that need one are available on this machine.",
        "Call `list_skills` to see what there is, and `activate_skill` to "
        "load the instructions of the one you need, before you start the "
        "task it covers.",
    ]

    if catalog_in_prompt:
        lines += ["", render_catalog(skills, limit=limit)]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# The body
# ---------------------------------------------------------------------------


def truncate_to_tokens(
    text: str,
    limit: int,
    tokenizer: Optional[Callable[[str], Sequence[Any]]] = None,
) -> str:
    """Return the longest prefix of *text* that fits into *limit* tokens.

    The cut is made on a character boundary, and the prefix is found with a
    binary search, so the text is tokenized a handful of times and not
    once per character.

    Args:
        text: The text to cut.
        limit: How many tokens the result may take.  A limit of zero or
            less returns the text unchanged.
        tokenizer: The tokenizer to count with.  Without one, four
            characters per token are assumed.

    Returns:
        The prefix that fits.
    """
    if limit <= 0 or not text:
        return text

    if tokenizer is None:
        # Four characters per token is the estimate the agent uses when no
        # tokenizer can be loaded.
        return text[: limit * CHARS_PER_TOKEN]

    if len(tokenizer(text)) <= limit:
        return text

    low, high = 0, len(text)
    while low < high:
        middle = (low + high + 1) // 2
        if len(tokenizer(text[:middle])) <= limit:
            low = middle
        else:
            high = middle - 1

    return text[:low]


def cap_body(
    body: str,
    limit: int = DEFAULT_BODY_TOKEN_LIMIT,
    tokenizer: Optional[Callable[[str], Sequence[Any]]] = None,
) -> str:
    """Return the body of a skill, cut to *limit* tokens.

    A skill that does not fit is cut, and the cut is marked, so that the
    model knows it is reading a part of the procedure and not all of it.

    The limit is the size of the **result**, the marker included.  The
    count of the result is not the sum of the counts of its parts: the
    seam between the body and the marker may merge two tokens into one,
    and a body that fits exactly would push the result over the limit.
    The result is therefore measured, and the body is cut until it fits.
    """
    if limit <= 0 or not body:
        return body

    if tokenizer is None:
        # Four characters per token is the estimate the agent uses when
        # no tokenizer can be loaded.
        marker = f"\n\n{TRUNCATION_MARKER}"
        budget = max(limit - estimate_tokens(marker), 1)
        kept = body[: budget * CHARS_PER_TOKEN]
        if len(kept) == len(body):
            return body
        return f"{kept}{marker}"

    if len(tokenizer(body)) <= limit:
        return body

    for marker in (f"\n\n{TRUNCATION_MARKER}", f"\n\n{SHORT_TRUNCATION_MARKER}"):
        kept = _longest_prefix_that_fits(body, marker, limit, tokenizer)
        if kept:
            return f"{kept}{marker}"

    # Even the short marker does not fit: the limit is smaller than the
    # marker.  The body is dropped, and the marker says so.
    return SHORT_TRUNCATION_MARKER


def _longest_prefix_that_fits(
    body: str,
    marker: str,
    limit: int,
    tokenizer: Callable[[str], Sequence[Any]],
) -> str:
    """Return the longest prefix of *body* that fits into *limit* tokens.

    The prefix is measured **with the marker attached**, because that is
    what the model reads.
    """
    low, high = 0, len(body)
    best = ""

    while low <= high:
        middle = (low + high) // 2
        candidate = f"{body[:middle]}{marker}"
        if len(tokenizer(candidate)) <= limit:
            best = body[:middle]
            low = middle + 1
        else:
            high = middle - 1

    return best
