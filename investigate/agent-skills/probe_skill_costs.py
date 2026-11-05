#!/usr/bin/env python3
"""Probe: what do Agent Skills cost in prompt tokens?

Read-only.  It measures and prints; it changes nothing in the repository
and in the agent.

The numbers in ``INVESTIGATION_REPORT.md`` come from this script, so they
can be reproduced instead of believed.

Three questions are answered:

1. How much does the **catalog** (tier 1 of progressive disclosure) cost?
2. How much does the **activation tool schema** cost?
3. How does that sit against the **budget the context guard** leaves for
   the conversation?

And — because the fix is the point of the probe — a fourth:

4. What does the feature cost **as it is implemented**, where the catalog
   is not in the prompt?

Run it with::

    .venv/bin/python investigate/agent-skills/probe_skill_costs.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from components.context_guard import context_budget  # noqa: E402
from components.skills import (  # noqa: E402
    discover_skills,
    render_catalog,
    render_prompt_section,
)
from components.skills_tools import get_skill_tools  # noqa: E402
from components.tokens import load_tokenizer  # noqa: E402

#: A context window of the size the operator's local model uses.
CONTEXT_WINDOW = 8192

#: The number of tools the operator had loaded in the run reported in
#: ``investigate/agent-loop-context-guard/`` — the number the 3211-token
#: figure in that report refers to.
TOOL_SCHEMA_TOKENS = 3211


def _catalog(skills: list[tuple[str, str]]) -> str:
    """The catalog, in the XML shape the specification shows."""
    lines = ["<available_skills>"]
    for name, description in skills:
        lines.append("  <skill>")
        lines.append(f"    <name>{name}</name>")
        lines.append(f"    <description>{description}</description>")
        lines.append("  </skill>")
    lines.append("</available_skills>")
    return "\n".join(lines)


def _schema(names: list[str]) -> dict:
    """The schema of the activation tool, with the names as an enum."""
    return {
        "type": "function",
        "function": {
            "name": "activate_skill",
            "description": "Load the full instructions of a named skill.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "The name of the skill to activate.",
                        "enum": names,
                    }
                },
                "required": ["name"],
            },
        },
    }


def _tokens(text: str, tokenizer) -> int:
    return len(tokenizer(text))


def _sample_skills(count: int) -> list[tuple[str, str]]:
    """Skills with the shape the specification asks for."""
    return [
        (
            f"skill-{index}",
            "Does the thing that the skill does, and describes when the "
            f"agent should use it. Keyword {index}.",
        )
        for index in range(count)
    ]


def _write_skills(root: Path, count: int) -> None:
    """Write *count* skills into *root*, as the agent would find them."""
    for index, (name, description) in enumerate(_sample_skills(count)):
        folder = root / name
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: {description}\n---\n\n"
            f"The body of {name}.\n",
            encoding="utf-8",
        )


def _implemented_cost(count: int, tokenizer) -> tuple[int, int, int]:
    """Return the cost of the feature **as it is implemented**.

    The three numbers are the text the prompt carries, the schemas of the
    two tools, and the sum of the two.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_skills(root, count)

        skills = discover_skills([root])
        tools = get_skill_tools(skills=skills)

        section = _tokens(render_prompt_section(skills), tokenizer)
        schemas = _tokens(
            json.dumps(
                [tool.metadata.to_openai_tool(skip_length_check=True) for tool in tools]
            ),
            tokenizer,
        )

    return section, schemas, section + schemas


def main() -> int:
    tokenizer = load_tokenizer()

    # ------------------------------------------------------------------
    # 1. The cost of the catalog.
    # ------------------------------------------------------------------
    print("=" * 72)
    print("1. The catalog (tier 1) — the cost of the skill list")
    print("=" * 72)
    print()
    print(f"{'skills':>8}  {'tokens':>7}  {'per skill':>11}")
    print("-" * 72)
    for count in (1, 5, 10, 20, 50):
        cost = _tokens(_catalog(_sample_skills(count)), tokenizer)
        print(f"{count:>8}  {cost:>7}  {cost // count:>11}")
    print()

    # ------------------------------------------------------------------
    # 2. The cost of the activation tool schema.
    # ------------------------------------------------------------------
    print("=" * 72)
    print("2. The activation tool schema — what the model sees every request")
    print("=" * 72)
    print()
    print(f"{'names in the enum':>18}  {'tokens':>7}")
    print("-" * 72)
    for count in (1, 5, 10, 20, 50):
        blob = json.dumps([_schema([f"skill-{index}" for index in range(count)])])
        cost = _tokens(blob, tokenizer)
        print(f"{count:>18}  {cost:>7}")
    print()

    # ------------------------------------------------------------------
    # 3. The budget the context guard leaves.
    # ------------------------------------------------------------------
    print("=" * 72)
    print("3. The budget — what the skills cost against the guard")
    print("=" * 72)
    print()
    budget = context_budget(CONTEXT_WINDOW)
    conversation = budget - TOOL_SCHEMA_TOKENS
    print(f"context window                : {CONTEXT_WINDOW}")
    print(f"budget (context_budget)       : {budget}")
    print(f"tool schemas of the 27 tools  : {TOOL_SCHEMA_TOKENS}")
    print(f"left for the conversation     : {conversation}")
    print()

    catalog_20 = _tokens(_catalog(_sample_skills(20)), tokenizer)
    schema_20 = _tokens(
        json.dumps([_schema([f"skill-{index}" for index in range(20)])]), tokenizer
    )
    fixed = catalog_20 + schema_20
    print(f"catalog of 20 skills          : {catalog_20}")
    print(f"activation tool schema        : {schema_20}")
    print(f"the fixed cost of the feature : {fixed}")
    print(f"share of the budget           : {fixed / budget:.1%}")
    print(f"left for the conversation     : {conversation - fixed}")
    print()
    print(
        "The skill *bodies* are not in this number: they are loaded when a "
        "skill is activated, and they cost their own tokens at that moment."
    )
    print()

    # ------------------------------------------------------------------
    # 4. The cost of the feature as it is implemented.
    # ------------------------------------------------------------------
    print("=" * 72)
    print("4. The fix — the catalog is fetched on demand, not in the prompt")
    print("=" * 72)
    print()
    print(f"{'skills':>8}  {'prompt':>7}  {'schemas':>8}  {'fixed':>7}")
    print("-" * 72)
    implemented = []
    for count in (1, 5, 10, 20, 50):
        section, schemas, total = _implemented_cost(count, tokenizer)
        implemented.append((section, schemas, total))
        print(f"{count:>8}  {section:>7}  {schemas:>8}  {total:>7}")
    print()
    print("The fixed cost is the same for every number of skills: it is the")
    print("cost of two tool schemas and of one line in the prompt.")
    print()

    section, schemas, total = implemented[3]  # the row of twenty skills
    print(f"the fixed cost, 20 skills      : {total}")
    print(f"the fixed cost before the fix  : {fixed}")
    print(f"what the fix saves             : {fixed - total}")
    print(f"share of the budget            : {total / budget:.1%}")
    print(f"left for the conversation      : {conversation - total}")
    print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
