"""
Tests for the skills — the procedures the agent loads on demand.

The bug this guards against is not a crash but a **cost**: the design that
was rejected put the catalog of the skills in the system prompt, where it
is paid on every request and grows with every skill.  On the window of
the operator's model (8192 tokens) a catalog of twenty skills took 908
tokens — 16.5% of the prompt budget — for a feature that most requests
never touch.

The tests therefore check the invariant that matters: **the fixed cost of
the feature does not grow with the number of skills**, and the catalog is
not in the prompt.

The measurement is in ``investigate/agent-skills/``.

Category: Infrastructure
"""

import json
import tempfile
import unittest
from pathlib import Path
from typing import List

from components.skills import (
    DEFAULT_BODY_TOKEN_LIMIT,
    TRUNCATION_MARKER,
    Skill,
    cap_body,
    default_skill_roots,
    discover_skills,
    find_skill,
    parse_frontmatter,
    parse_skill_dirs,
    render_catalog,
    render_prompt_section,
    root_scope,
    truncate_to_tokens,
)
from components.skills_tools import build_skills, get_skill_tools


# ---------------------------------------------------------------------------
# The helpers
# ---------------------------------------------------------------------------


def write_skill(root: Path, name: str, description: str, body: str = "the body") -> Path:
    """Write one skill into *root* and return the file it was written to."""
    folder = root / name
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "SKILL.md"
    path.write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\n{body}\n",
        encoding="utf-8",
    )
    return path


def make_skills(root: Path, count: int) -> None:
    """Write *count* skills into *root*."""
    for index in range(count):
        write_skill(
            root,
            f"skill-{index}",
            f"Does the thing that the skill does, and describes when the "
            f"agent should use it. Keyword {index}.",
        )


def real_tokenizer():
    """Return the tokenizer of the agent, or ``None`` when there is none."""
    from components.tokens import get_tokenizer

    return get_tokenizer()


def schema_tokens(tools) -> int:
    """Return the number of tokens the schemas of *tools* take up."""
    from components.context_metrics import tool_schema_text

    tokenizer = real_tokenizer()
    if tokenizer is None:
        return 0
    return len(tokenizer(tool_schema_text(tools)))


# ---------------------------------------------------------------------------
# The frontmatter
# ---------------------------------------------------------------------------


class TestTheFrontmatter(unittest.TestCase):
    """The block of ``key: value`` lines at the top of a skill file."""

    def test_the_metadata_and_the_body_are_split(self):
        metadata, body = parse_frontmatter(
            "---\nname: deploy\ndescription: Deploy it.\n---\n\n# Deploy\n\nStep one.\n"
        )
        self.assertEqual(metadata["name"], "deploy")
        self.assertEqual(metadata["description"], "Deploy it.")
        self.assertNotIn("---", body)
        self.assertIn("# Deploy", body)

    def test_a_file_without_frontmatter_is_all_body(self):
        metadata, body = parse_frontmatter("# Deploy\n\nStep one.\n")
        self.assertEqual(metadata, {})
        self.assertEqual(body, "# Deploy\n\nStep one.\n")

    def test_a_quoted_value_is_unquoted(self):
        metadata, _ = parse_frontmatter(
            '---\nname: "deploy"\ndescription: \'Deploy it.\'\n---\nbody\n'
        )
        self.assertEqual(metadata["name"], "deploy")
        self.assertEqual(metadata["description"], "Deploy it.")

    def test_a_folded_description_is_joined(self):
        metadata, _ = parse_frontmatter(
            "---\nname: deploy\ndescription: The first line\n"
            "  and the second one.\n---\nbody\n"
        )
        self.assertEqual(
            metadata["description"], "The first line and the second one."
        )


# ---------------------------------------------------------------------------
# The discovery
# ---------------------------------------------------------------------------


class TestTheDiscovery(unittest.TestCase):
    """Where the skills are looked for."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def test_a_skill_is_found(self):
        write_skill(self.root, "deploy", "Deploy it.")
        skills = discover_skills([self.root])
        self.assertEqual(len(skills), 1)
        self.assertEqual(skills[0].name, "deploy")
        self.assertEqual(skills[0].description, "Deploy it.")
        self.assertIn("the body", skills[0].body)

    def test_a_root_that_is_not_there_is_not_an_error(self):
        self.assertEqual(discover_skills([self.root / "nothing"]), [])

    def test_the_later_root_wins(self):
        user = self.root / "user"
        project = self.root / "project"
        user.mkdir()
        project.mkdir()
        write_skill(user, "deploy", "The one of the operator.")
        write_skill(project, "deploy", "The one of the project.")
        skills = discover_skills([user, project])
        self.assertEqual(len(skills), 1)
        self.assertEqual(skills[0].description, "The one of the project.")

    def test_a_skill_without_a_file_is_skipped(self):
        (self.root / "empty").mkdir()
        skills = discover_skills([self.root])
        self.assertEqual(skills, [])

    def test_the_name_of_the_directory_is_used_when_the_frontmatter_has_none(self):
        folder = self.root / "deploy"
        folder.mkdir()
        (folder / "SKILL.md").write_text("no frontmatter here\n", encoding="utf-8")
        skills = discover_skills([self.root])
        self.assertEqual(skills[0].name, "deploy")

    def test_the_default_roots_are_the_operator_and_the_project(self):
        roots = default_skill_roots(project_root=self.root)
        self.assertEqual(len(roots), 2)
        self.assertTrue(str(roots[0]).endswith("torvalds/skills"))
        self.assertEqual(roots[1], self.root / "skills")

    def test_the_dirs_setting_is_split_on_the_separator(self):
        roots = parse_skill_dirs("/one:/two")
        self.assertEqual([str(root) for root in roots], ["/one", "/two"])

    def test_an_empty_dirs_setting_means_the_defaults(self):
        self.assertEqual(parse_skill_dirs(""), [])
        self.assertEqual(parse_skill_dirs(None), [])

    def test_the_scope_of_a_root_is_its_label(self):
        # The roots of the operator are under the configuration directory
        # of the home folder; every other root belongs to a project.
        self.assertEqual(root_scope(default_skill_roots()[0]), "user")
        self.assertEqual(root_scope(default_skill_roots()[1]), "project")
        self.assertEqual(root_scope(self.root), "project")

    def test_the_lookup_ignores_the_case_and_the_space(self):
        skills = [Skill("deploy", "d", self.root, "b")]
        self.assertIsNotNone(find_skill(skills, " Deploy "))
        self.assertIsNone(find_skill(skills, "other"))


# ---------------------------------------------------------------------------
# The catalog
# ---------------------------------------------------------------------------


class TestTheCatalog(unittest.TestCase):
    """The text the model sees when it asks for the catalog."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        make_skills(self.root, 3)
        self.skills = discover_skills([self.root])

    def test_every_skill_is_one_line(self):
        catalog = render_catalog(self.skills)
        self.assertEqual(len(catalog.splitlines()), 3)
        self.assertIn("- skill-0:", catalog)

    def test_the_limit_is_respected(self):
        catalog = render_catalog(self.skills, limit=2)
        self.assertEqual(len(catalog.splitlines()), 3)  # two skills and the count
        self.assertIn("and 1 more", catalog)

    def test_an_empty_catalog_says_so(self):
        self.assertIn("no skills", render_catalog([]))


# ---------------------------------------------------------------------------
# The prompt
# ---------------------------------------------------------------------------


class TestThePromptSection(unittest.TestCase):
    """The whole of the tier 1 — the text the skills add to the prompt."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def test_nothing_is_added_when_there_is_no_skill(self):
        self.assertEqual(render_prompt_section([]), "")

    def test_the_section_names_the_tools(self):
        make_skills(self.root, 2)
        skills = discover_skills([self.root])
        section = render_prompt_section(skills)
        self.assertIn("list_skills", section)
        self.assertIn("activate_skill", section)

    def test_the_catalog_is_not_in_the_section_by_default(self):
        make_skills(self.root, 2)
        skills = discover_skills([self.root])
        section = render_prompt_section(skills)
        self.assertNotIn("skill-0", section)

    def test_the_catalog_is_in_the_section_when_it_is_asked_for(self):
        make_skills(self.root, 2)
        skills = discover_skills([self.root])
        section = render_prompt_section(skills, catalog_in_prompt=True)
        self.assertIn("skill-0", section)


# ---------------------------------------------------------------------------
# The body
# ---------------------------------------------------------------------------


class TestTheBody(unittest.TestCase):
    """The body of a skill is cut, and the cut is marked."""

    def test_a_short_body_is_untouched(self):
        body = "a short body"
        self.assertEqual(cap_body(body, limit=100), body)

    def test_a_long_body_is_cut(self):
        body = "word " * 1000
        cut = cap_body(body, limit=100)
        self.assertLess(len(cut), len(body))
        self.assertIn(TRUNCATION_MARKER, cut)

    def test_the_cut_keeps_the_tokens_under_the_limit(self):
        tokenizer = real_tokenizer()
        if tokenizer is None:
            self.skipTest("no tokenizer is available")
        body = "word " * 5000
        cut = cap_body(body, limit=100, tokenizer=tokenizer)
        # The marker is part of the result, so the *result* is what has to
        # fit - not the body alone.
        self.assertLessEqual(len(tokenizer(cut)), 100)
        self.assertIn(TRUNCATION_MARKER, cut)

    def test_a_limit_that_is_smaller_than_the_marker_still_says_something(self):
        tokenizer = real_tokenizer()
        if tokenizer is None:
            self.skipTest("no tokenizer is available")
        cut = cap_body("word " * 5000, limit=5, tokenizer=tokenizer)
        self.assertTrue(cut)
        self.assertLessEqual(len(tokenizer(cut)), 20)

    def test_a_limit_of_zero_cuts_nothing(self):
        body = "a body"
        self.assertEqual(cap_body(body, limit=0), body)

    def test_the_truncation_keeps_a_prefix(self):
        text = "abcdefghij"
        self.assertTrue(truncate_to_tokens(text, limit=1, tokenizer=lambda t: t.split()).startswith("a"))


# ---------------------------------------------------------------------------
# The tools
# ---------------------------------------------------------------------------


class TestTheTools(unittest.TestCase):
    """The two tools the model calls."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def test_a_machine_without_skills_gets_no_tools(self):
        self.assertEqual(get_skill_tools(roots=[self.root]), [])

    def test_a_machine_with_skills_gets_the_two_tools(self):
        write_skill(self.root, "deploy", "Deploy it.")
        names = [tool.metadata.name for tool in get_skill_tools(roots=[self.root])]
        self.assertEqual(names, ["list_skills", "activate_skill"])

    def test_the_catalog_is_returned_by_list_skills(self):
        write_skill(self.root, "deploy", "Deploy it.")
        tools = get_skill_tools(roots=[self.root])
        catalog = tools[0].fn()
        self.assertIn("deploy", catalog)
        self.assertIn("Deploy it.", catalog)

    def test_the_body_is_returned_by_activate_skill(self):
        write_skill(self.root, "deploy", "Deploy it.", body="run the tests first")
        tools = get_skill_tools(roots=[self.root])
        body = tools[1].fn(name="deploy")
        self.assertIn("run the tests first", body)
        self.assertIn("deploy", body)

    def test_an_unknown_name_is_reported(self):
        write_skill(self.root, "deploy", "Deploy it.")
        tools = get_skill_tools(roots=[self.root])
        answer = tools[1].fn(name="nope")
        self.assertIn("no skill called 'nope'", answer)
        self.assertIn("deploy", answer)

    def test_the_schema_of_activate_skill_is_not_an_enum(self):
        # An enum grows with every skill the operator writes, and it is
        # paid on every request.  The names come from list_skills.
        write_skill(self.root, "deploy", "Deploy it.")
        tools = get_skill_tools(roots=[self.root])
        schema = tools[1].metadata.get_parameters_dict()
        self.assertNotIn("enum", json.dumps(schema))


# ---------------------------------------------------------------------------
# The cost — the invariant the whole feature is about
# ---------------------------------------------------------------------------


class TestTheCost(unittest.TestCase):
    """The fixed cost of the feature must not grow with the skills."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def _fixed_cost(self, count: int) -> int:
        """The tokens the feature costs on every request, with *count* skills."""
        make_skills(self.root, count)
        skills = discover_skills([self.root])
        tools = get_skill_tools(skills=skills)
        section = render_prompt_section(skills)

        tokenizer = real_tokenizer()
        if tokenizer is None:
            self.skipTest("no tokenizer is available")

        return len(tokenizer(section)) + schema_tokens(tools)

    def test_the_fixed_cost_is_the_same_for_one_and_for_fifty_skills(self):
        costs: List[int] = [self._fixed_cost(count) for count in (1, 5, 20, 50)]
        self.assertEqual(
            len(set(costs)),
            1,
            f"the fixed cost grows with the number of skills: {costs}",
        )

    def test_the_fixed_cost_is_small_against_the_prompt_budget(self):
        # The budget of the operator's model: 8192 tokens of window, a
        # reserve of 20% for the answer.
        from components.context_guard import context_budget

        cost = self._fixed_cost(20)
        budget = context_budget(8192)
        self.assertLess(
            cost / budget,
            0.05,
            f"the skills cost {cost} of the {budget}-token budget",
        )

    def test_the_catalog_in_the_prompt_would_have_grown(self):
        # The design that was rejected, measured here so that the reason
        # for the design is a test and not a comment.
        make_skills(self.root, 5)
        skills = discover_skills([self.root])

        tokenizer = real_tokenizer()
        if tokenizer is None:
            self.skipTest("no tokenizer is available")

        cheap = len(tokenizer(render_prompt_section(skills)))
        catalog = len(tokenizer(render_catalog(skills)))
        self.assertLess(
            cheap,
            catalog,
            "the prompt section must be cheaper than the catalog",
        )


# ---------------------------------------------------------------------------
# The wiring
# ---------------------------------------------------------------------------


class TestBuildSkills(unittest.TestCase):
    """The one call the orchestrators make."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def test_a_disabled_feature_costs_nothing(self):
        write_skill(self.root, "deploy", "Deploy it.")
        tools, section, skills = build_skills(enabled=False, dirs=str(self.root))
        self.assertEqual(tools, [])
        self.assertEqual(section, "")
        self.assertEqual(skills, [])

    def test_an_empty_folder_costs_nothing(self):
        tools, section, skills = build_skills(dirs=str(self.root))
        self.assertEqual(tools, [])
        self.assertEqual(section, "")
        self.assertEqual(skills, [])

    def test_the_tools_the_section_and_the_skills_come_together(self):
        write_skill(self.root, "deploy", "Deploy it.")
        tools, section, skills = build_skills(dirs=str(self.root))
        self.assertEqual(len(tools), 2)
        self.assertIn("list_skills", section)
        self.assertEqual(len(skills), 1)

    def test_the_body_limit_is_passed_on(self):
        write_skill(self.root, "deploy", "Deploy it.", body="word " * 5000)
        tools, _, _ = build_skills(
            dirs=str(self.root), body_token_limit=DEFAULT_BODY_TOKEN_LIMIT
        )
        body = tools[1].fn(name="deploy")
        self.assertIn(TRUNCATION_MARKER, body)


if __name__ == "__main__":
    unittest.main()
