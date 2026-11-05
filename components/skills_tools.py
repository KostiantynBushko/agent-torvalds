"""
Skills — the agent-facing half: the two tools that load a skill.

Why this module exists
----------------------
``components/skills.py`` knows what a skill is and how it is found.  This
module turns that into the two tools the model calls:

* ``list_skills`` — the catalog, fetched **on demand**;
* ``activate_skill`` — the body of one skill, cut to a token limit.

The point of the split is the *cost*.  A catalog that sits in the system
prompt is paid on every request and grows with every skill; the
measurement in ``investigate/agent-skills/`` puts a catalog of twenty
skills at 908 tokens — 16.5% of the prompt budget of the operator's model.
Here the catalog is a tool *result*: it costs the runs that ask for it, and
it lands in the conversation, where the context guard drops it once it
grows old.

When there is no skill at all, this module returns **no tools at all**, so
the feature costs nothing on a machine that does not use it.

Category: Infrastructure
Retriever Keywords: skills, skill, activate_skill, list_skills, tools
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, List, Optional, Sequence, Tuple

from llama_index.core.tools import FunctionTool
from pydantic import Field, create_model

from components.skills import (
    DEFAULT_BODY_TOKEN_LIMIT,
    DEFAULT_CATALOG_LIMIT,
    Skill,
    cap_body,
    default_skill_roots,
    discover_skills,
    find_skill,
    parse_skill_dirs,
    render_catalog,
    render_prompt_section,
)

logger = logging.getLogger(__name__)

#: The description of ``list_skills``.
LIST_SKILLS_DESCRIPTION = (
    "List the skills of this machine: the name of each and what it is for. "
    "A skill is a procedure for a task that needs one. Call this before "
    "such a task."
)

#: The description of ``activate_skill``.
ACTIVATE_SKILL_DESCRIPTION = (
    "Load the instructions of a named skill - the name must be one that "
    "list_skills returned. Follow them for the task at hand."
)

#: The schema of ``list_skills`` — it takes nothing.
LIST_SKILLS_SCHEMA = create_model("ListSkillsArgs")

#: The schema of ``activate_skill``.
#:
#: The name is a **free string**, not an enum of the names of the skills:
#: an enum grows with every skill the operator writes, and it is paid on
#: every request.  The names are fetched by ``list_skills`` instead.
ACTIVATE_SKILL_SCHEMA = create_model(
    "ActivateSkillArgs",
    name=(
        str,
        Field(description="The name of the skill to load, as list_skills gave it."),
    ),
)


def _tokenizer() -> Optional[Callable[[str], Sequence[Any]]]:
    """Return the tokenizer of the agent, or ``None`` when there is none.

    A tokenizer that cannot be loaded is not a reason to lose the feature:
    the body of a skill is then measured with the estimate of the agent —
    four characters per token.
    """
    try:
        from components.context_guard import get_tokenizer

        return get_tokenizer()
    except Exception as exc:  # noqa: BLE001 - a tokenizer is never worth a run
        logger.debug("No tokenizer for the skills: %s", exc)
        return None


def get_skill_tools(
    roots: Optional[Sequence[Path]] = None,
    skills: Optional[Sequence[Skill]] = None,
    body_token_limit: int = DEFAULT_BODY_TOKEN_LIMIT,
    catalog_limit: int = DEFAULT_CATALOG_LIMIT,
    tokenizer: Optional[Callable[[str], Sequence[Any]]] = None,
) -> List[FunctionTool]:
    """Return the tools that load the skills — or none at all.

    There is no point in giving the model a tool that has nothing to
    return, so a machine without skills gets no tools: the feature costs
    nothing when it is not used.

    Args:
        roots: The roots the skills are looked for in.  Defaults to the
            skills of the operator and the skills of the project.
        skills: The skills themselves, when they were already discovered.
        body_token_limit: How many tokens the body of a skill may take
            when it is loaded.
        catalog_limit: How many skills the catalog may name at once.
        tokenizer: The tokenizer the body is measured with.  Without one,
            four characters per token are assumed.

    Returns:
        The tools — ``[]`` when there is no skill.
    """
    if skills is None:
        if roots is None:
            roots = default_skill_roots()
        skills = discover_skills(roots)

    if not skills:
        logger.debug("No skills — the skill tools are not added.")
        return []

    logger.info(
        "Skills: %d found — the catalog is loaded on demand, not in the prompt.",
        len(skills),
    )

    if tokenizer is None:
        tokenizer = _tokenizer()

    def list_skills() -> str:
        """Return the catalog of the skills."""
        return render_catalog(skills, limit=catalog_limit)

    def activate_skill(name: str) -> str:
        """Return the instructions of the skill called *name*."""
        skill = find_skill(skills, name)
        if skill is None:
            known = ", ".join(item.name for item in skills)
            return f"There is no skill called '{name}'. The skills are: {known}."

        body = cap_body(skill.body, limit=body_token_limit, tokenizer=tokenizer)
        return f"Skill: {skill.name}\nSource: {skill.path}\n\n{body}"

    return [
        FunctionTool.from_defaults(
            fn=list_skills,
            name="list_skills",
            description=LIST_SKILLS_DESCRIPTION,
            fn_schema=LIST_SKILLS_SCHEMA,
        ),
        FunctionTool.from_defaults(
            fn=activate_skill,
            name="activate_skill",
            description=ACTIVATE_SKILL_DESCRIPTION,
            fn_schema=ACTIVATE_SKILL_SCHEMA,
        ),
    ]


def build_skills(
    enabled: bool = True,
    dirs: str = "",
    catalog_in_prompt: bool = False,
    body_token_limit: int = DEFAULT_BODY_TOKEN_LIMIT,
    project_root: Optional[Path] = None,
) -> Tuple[List[FunctionTool], str, List[Skill]]:
    """Return the tools, the text for the prompt, and the skills.

    This is the one call the orchestrators make.  Everything the feature
    needs is in the result, and everything the feature is *not* allowed to
    cost is left out: with no skills there are no tools and no text.

    Args:
        enabled: Whether the feature is on at all.
        dirs: The roots the skills are looked for in, separated by the
            separator of the platform.  Empty means the defaults: the
            skills of the operator and the skills of the project.
        catalog_in_prompt: Whether the catalog is listed in the prompt.
            Off by default — the catalog is the expensive part.
        body_token_limit: How many tokens the body of a skill may take
            when it is loaded.
        project_root: The directory of the project.  Defaults to the
            directory the agent runs in.

    Returns:
        The triple ``(tools, prompt_section, skills)``.  The prompt
        section is the empty string when there is no skill.
    """
    if not enabled:
        return [], "", []

    roots = parse_skill_dirs(dirs) or default_skill_roots(project_root)
    skills = discover_skills(roots)
    if not skills:
        return [], "", []

    tools = get_skill_tools(skills=skills, body_token_limit=body_token_limit)
    section = render_prompt_section(skills, catalog_in_prompt=catalog_in_prompt)

    return tools, section, skills
