"""
The system prompt is written down once, and both orchestrators read it.

The template of the system prompt used to live in each orchestrator, and
the two copies drifted: the rule about the user path of the machine was
added to the classic agent and not to the multi-window one, so the
multi-window agent told the model about it only on the path where the
runtime prompt injection was on — and the copy that was left behind was
the one a reader of the multi-window agent would run.

The template is in ``components/system_prompt.py`` now, and the tests
below hold it there:

* both orchestrators read the **same object** — not two equal copies;
* the rule is in the template that both of them fall back to;
* the text of the template is not written down anywhere else.

Run with:
    pytest tests/test_system_prompt_shared.py -v
"""
import ast
import importlib.util
import logging
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from components.system_prompt import (  # noqa: E402
    DYNAMIC_SYSTEM_PROMPT_TEMPLATE,
    RULE_USER_PATH,
    SYSTEM_PROMPT_TEMPLATE,
)

#: The module that holds the templates.
SHARED_MODULE = ROOT / "components" / "system_prompt.py"

#: The orchestrators that read them.
ORCHESTRATORS = ("agent-torvalds.py", "agent-torvalds-mw.py")

#: The names that are **not** a prompt template, although they look like
#: one: they carry the path of a template file, not the template itself.
NOT_A_TEMPLATE = ("PROMPT_TEMPLATE_PATH",)


def is_a_template_name(name: str) -> bool:
    """Whether the name is the name of a prompt template."""
    if name in NOT_A_TEMPLATE:
        return False
    return name.endswith("PROMPT_TEMPLATE")


def load_orchestrator(name: str, filename: str):
    """Load an orchestrator by path — its filename is not importable."""
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


#: The directories that are never walked.
SKIP_DIRS = frozenset({
    ".git", ".venv", ".pytest_cache", "__pycache__", "node_modules",
})


def python_sources():
    """Every Python file of the repository.

    The tree is walked and not read from git: a file that is not
    committed yet is a file of the source, and a rule about the source
    has to see it.

    The virtual environment and the copies of the repository are left
    alone — they are not the source of this repository.
    """
    found = []
    for path in ROOT.rglob("*.py"):
        relative = path.relative_to(ROOT)
        if any(part in SKIP_DIRS for part in relative.parts):
            continue
        if any((ROOT / part).joinpath(".git").exists() for part in relative.parts[:-1]):
            continue
        found.append(path)
    return sorted(found)


def assigned_literals(path: Path):
    """Every name of the file that is given a text of its own.

    A name that is given the shared template is not a copy of it: the
    value is a name, not a text.  Only a literal is a copy — and a
    literal that is written down over several lines is still one text,
    which is why the value is read and not the source.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return []

    assigned = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        try:
            value = ast.literal_eval(node.value)
        except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
            value = None
        if not isinstance(value, str):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                assigned.append((target.id, value))
    return assigned


class TestThePromptIsShared(unittest.TestCase):
    """One template, and both orchestrators read it."""

    def setUp(self):
        # The orchestrators configure the root logger at import time.
        root = logging.getLogger()
        self._handlers = list(root.handlers)
        self._level = root.level
        self.addCleanup(self._restore)

    def _restore(self):
        root = logging.getLogger()
        root.handlers.clear()
        root.handlers.extend(self._handlers)
        root.setLevel(self._level)

    def test_the_shared_module_holds_the_templates(self):
        """The templates live in one file."""
        self.assertTrue(SHARED_MODULE.is_file(), "the shared module is missing")
        text = SHARED_MODULE.read_text(encoding="utf-8")
        for name in ("SYSTEM_PROMPT_TEMPLATE", "DYNAMIC_SYSTEM_PROMPT_TEMPLATE"):
            self.assertIn(name, text, f"{name} is not in the shared module")

    def test_both_orchestrators_read_the_same_object(self):
        """Not two equal copies — one object, read by both."""
        classic = load_orchestrator("shared_prompt_classic", "agent-torvalds.py")
        mw = load_orchestrator("shared_prompt_mw", "agent-torvalds-mw.py")

        self.assertIs(classic.SYSTEM_PROMPT_TEMPLATE, SYSTEM_PROMPT_TEMPLATE)
        self.assertIs(mw.SYSTEM_PROMPT_TEMPLATE, SYSTEM_PROMPT_TEMPLATE)

    def test_the_rule_is_in_the_template_both_of_them_fall_back_to(self):
        """The copy that was left behind is the one that mattered.

        The multi-window agent told the model about the rule only when
        the runtime prompt injection was on.  Its fallback did not carry
        it, and the fallback is the path the operator takes with
        ``--no-prompt-injection``.
        """
        classic = load_orchestrator("shared_prompt_classic_rule", "agent-torvalds.py")
        mw = load_orchestrator("shared_prompt_mw_rule", "agent-torvalds-mw.py")

        for name, agent in (("classic", classic), ("multi-window", mw)):
            with self.subTest(agent=name):
                agent.PROMPT_INJECTION_ENABLED = False
                agent.build_project_context = lambda *args, **kwargs: "CTX"
                prompt = agent.build_system_prompt()
                self.assertIn(
                    RULE_USER_PATH,
                    prompt,
                    f"the {name} agent does not tell the model about the "
                    f"user path of the machine",
                )

    def test_the_fallbacks_of_the_two_orchestrators_are_the_same(self):
        """The two agents tell the model the same thing."""
        classic = load_orchestrator("shared_prompt_classic_same", "agent-torvalds.py")
        mw = load_orchestrator("shared_prompt_mw_same", "agent-torvalds-mw.py")

        for agent in (classic, mw):
            agent.PROMPT_INJECTION_ENABLED = False
            agent.build_project_context = lambda *args, **kwargs: "CTX"

        self.assertEqual(
            classic.build_system_prompt(),
            mw.build_system_prompt(),
            "the two orchestrators build different prompts",
        )

    def test_the_prompt_engine_reads_the_shared_template(self):
        """The runtime prompt injection carries the same rule."""
        from project_manager.prompt_engine import DEFAULT_SYSTEM_PROMPT_TEMPLATE

        self.assertIs(DEFAULT_SYSTEM_PROMPT_TEMPLATE, DYNAMIC_SYSTEM_PROMPT_TEMPLATE)
        self.assertIn(RULE_USER_PATH, DEFAULT_SYSTEM_PROMPT_TEMPLATE)

    def test_the_rule_is_written_down_once(self):
        """The rule itself is a text, and a text drifts when it is copied."""
        holders = []
        for path in python_sources():
            relative = path.relative_to(ROOT).as_posix()
            if relative.startswith("tests/") or "/tests/" in relative:
                continue
            for _, value in assigned_literals(path):
                if RULE_USER_PATH in value:
                    holders.append(relative)
                    break
        self.assertEqual(
            sorted(set(holders)),
            ["components/system_prompt.py"],
            "the rule of the user path is written down in more than one "
            "place - it drifts when it is copied: "
            f"{sorted(set(holders))}",
        )

    def test_no_other_file_defines_a_prompt_template(self):
        """A template that is defined twice is a template that drifts."""
        offenders = []
        for path in python_sources():
            if path == SHARED_MODULE:
                continue
            for name, _ in assigned_literals(path):
                if is_a_template_name(name):
                    offenders.append(
                        f"{path.relative_to(ROOT).as_posix()} ({name})"
                    )
        self.assertEqual(
            offenders,
            [],
            "these files define a prompt template of their own - the "
            "template belongs in components/system_prompt.py: "
            f"{offenders}",
        )

    def test_the_shared_module_is_imported_by_the_orchestrators(self):
        """A module nobody reads is not a shared module."""
        for filename in ORCHESTRATORS:
            with self.subTest(orchestrator=filename):
                text = (ROOT / filename).read_text(encoding="utf-8")
                self.assertIn(
                    "from components.system_prompt import",
                    text,
                    f"{filename} does not read the shared prompt",
                )


if __name__ == "__main__":
    unittest.main()
