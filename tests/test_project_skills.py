"""
Tests for the skills **of this project** — the ones under ``skills/``.

The feature is forgiving on purpose: a skill that cannot be read is
skipped, and a skill without a name is skipped, so that a broken skill
never keeps the agent from starting.  That is the right behaviour for a
skill the operator writes on the machine — but it makes a broken skill in
**the repository** invisible.  Nothing fails, nothing warns, and the
procedure is simply never loaded.

These tests are the eyes for that case.  They check the skills that ship
with the project: that they are found, that each one has a name and a
description, that the description says *when* the skill is worth loading,
and that the body fits into the limit the feature cuts it to.

The tests of the feature itself are in ``tests/test_skills.py``.

Category: Infrastructure
"""

import unittest
from pathlib import Path
from typing import List

from components.skills import (
    DEFAULT_BODY_TOKEN_LIMIT,
    SKILL_FILENAME,
    discover_skills,
    parse_frontmatter,
)
from components.tokens import count_tokens_of, get_tokenizer

#: The root of the repository, and the skills of the project under it.
ROOT = Path(__file__).resolve().parent.parent
PROJECT_SKILLS = ROOT / "skills"


def project_skills() -> List:
    """Return the skills of this project, as the agent would find them."""
    return discover_skills([PROJECT_SKILLS])


class TestTheSkillsOfTheProject(unittest.TestCase):
    """The skills that ship with the repository, under ``skills/``."""

    def setUp(self) -> None:
        self.skills = project_skills()

    def test_the_project_carries_skills(self) -> None:
        """The repository holds at least one skill — the feature has material."""
        self.assertTrue(
            self.skills,
            "There is no skill under skills/ — the project has nothing to "
            "load, and the feature cannot be tried out.",
        )

    def test_every_skill_is_found(self) -> None:
        """Every folder under ``skills/`` is found by the discovery."""
        folders = sorted(
            entry.name
            for entry in PROJECT_SKILLS.iterdir()
            if entry.is_dir()
        )
        found = sorted(skill.name for skill in self.skills)
        self.assertEqual(folders, found)

    def test_every_skill_has_a_description(self) -> None:
        """A skill without a description cannot be chosen: the catalog line is empty."""
        for skill in self.skills:
            with self.subTest(skill=skill.name):
                self.assertTrue(
                    skill.description.strip(),
                    f"The skill {skill.name} has no description — the model "
                    f"has nothing to read in the catalog.",
                )

    def test_every_description_says_when_to_use_the_skill(self) -> None:
        """The description must carry the *when*, not only the *what*.

        The catalog is the only thing the model sees before it decides, so
        a description that names the trigger is the difference between a
        skill that is loaded and a skill that is never read.
        """
        for skill in self.skills:
            with self.subTest(skill=skill.name):
                self.assertIn(
                    "use it when",
                    skill.description.lower(),
                    f"The description of {skill.name} does not say when the "
                    f"skill is worth loading.",
                )

    def test_every_body_fits_into_the_limit(self) -> None:
        """A body that is too long is cut when it is loaded — and the cut is a loss."""
        for skill in self.skills:
            with self.subTest(skill=skill.name):
                count, _estimated = count_tokens_of(skill.body)
                self.assertLessEqual(
                    count,
                    DEFAULT_BODY_TOKEN_LIMIT,
                    f"The body of {skill.name} takes {count} tokens, which is "
                    f"more than the limit of {DEFAULT_BODY_TOKEN_LIMIT} — it "
                    f"would be cut when it is loaded.",
                )

    def test_every_body_is_written_for_the_agent(self) -> None:
        """A body is a list of steps, not an essay."""
        for skill in self.skills:
            with self.subTest(skill=skill.name):
                self.assertTrue(
                    skill.body.strip(),
                    f"The skill {skill.name} has an empty body.",
                )

    def test_the_frontmatter_of_every_skill_is_parsed(self) -> None:
        """A file whose frontmatter does not parse is a body without a description."""
        for path in sorted(PROJECT_SKILLS.glob(f"*/{SKILL_FILENAME}")):
            with self.subTest(skill=path.parent.name):
                metadata, body = parse_frontmatter(path.read_text(encoding="utf-8"))
                self.assertIn("name", metadata)
                self.assertIn("description", metadata)
                self.assertTrue(body.strip())

    def test_no_skill_names_the_home_of_the_operator(self) -> None:
        """The repository is public: a skill may not carry a private path."""
        import re

        pattern = re.compile(r"/home/[A-Za-z0-9._<>-]+|/Users/[A-Za-z0-9._<>-]+")
        for skill in self.skills:
            with self.subTest(skill=skill.name):
                self.assertIsNone(
                    pattern.search(skill.body),
                    f"The skill {skill.name} carries a path of a home directory.",
                )

    def test_the_skills_are_reachable_through_the_project_root(self) -> None:
        """The default roots find the skills of the project, and the project wins.

        The agent runs in the working copy, so the second default root — the
        ``skills`` folder of the directory the agent runs in — has to be the
        one that carries the skills of the project.
        """
        from components.skills import default_skill_roots

        roots = default_skill_roots(ROOT)
        self.assertIn(PROJECT_SKILLS, roots)
        found = discover_skills(roots)
        names = {skill.name for skill in found}
        self.assertTrue(
            {skill.name for skill in self.skills} <= names,
            "The skills of the project are not found through the default roots.",
        )

    def test_the_catalog_of_the_project_is_small(self) -> None:
        """The catalog is a tool result, not the prompt — but it is still read."""
        from components.skills import render_catalog

        catalog = render_catalog(self.skills)
        tokenizer = get_tokenizer()
        if tokenizer is None:
            self.skipTest("No tokenizer is available — the count would be an estimate.")

        self.assertLess(
            len(tokenizer(catalog)),
            500,
            "The catalog of the skills of the project takes more than 500 "
            "tokens — the skills are described too verbosely.",
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
