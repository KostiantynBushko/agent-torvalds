"""
The input module of the TUI — the question of the agent.

The module is the one that asks the question in the footer of the TUI.
It was broken since 2026-10-25 (commit ``dca06b9``): the module read
``self._input_type`` — the kind of answer the pending question wants —
but only the **adapter** of the TUI ever defined it.  Every question in
the multi-window TUI therefore raised an ``AttributeError`` before it
could wait for the answer:

    the question was never shown, the answer was never collected, and
    the agent continued with the default answer — as if nobody had been
    asked anything.

The operator reported it as "the agent never asks me anything", and as
"what I type is invisible": the question never reached the screen, so
there was nothing to type into.

The manual test that exercises the whole path is
``scripts/manual_hitl_privilege_test.py``.

Run with:
    pytest tests/test_tui_input_module.py -v
"""
import asyncio
import unittest

from components.tui.state_bridge import TuiInputModule, TuiState


class TestTheModuleKnowsTheKindOfAnswer(unittest.TestCase):
    """The module must know what kind of answer the question wants."""

    def test_the_module_knows_the_kind_of_answer(self):
        """The attribute the module reads must exist.

        It is read on every question, so its absence took the whole
        question path down.
        """
        module = TuiInputModule(TuiState())

        self.assertEqual(
            module._input_type,
            "text",
            "the module does not know the kind of answer it is waiting "
            "for -- every question raises an AttributeError",
        )

    def test_the_consumer_can_tell_the_module_the_kind_of_answer(self):
        """The consumer tells the module through ``set_input_type()``."""
        module = TuiInputModule(TuiState())

        module.set_input_type("menu")

        self.assertEqual(module._input_type, "menu")

    def test_an_empty_kind_of_answer_is_ignored(self):
        """An empty kind leaves the last one alone."""
        module = TuiInputModule(TuiState())
        module.set_input_type("yesno")

        module.set_input_type("")

        self.assertEqual(module._input_type, "yesno")


class TestTheQuestionReachesTheOperator(unittest.TestCase):
    """The question must be asked, and the answer must come back."""

    def test_the_prompt_does_not_raise(self):
        """The prompt must not fail before it waits for the answer."""
        state = TuiState()
        module = TuiInputModule(state)

        async def run():
            return await module.prompt_with_status(
                message="Which one?", default="", timeout=0
            )

        answer, was_timeout = asyncio.run(run())

        self.assertEqual(answer, "")
        self.assertTrue(was_timeout)

    def test_the_answer_of_the_operator_arrives(self):
        """The answer of the operator travels back to the caller."""
        state = TuiState()
        module = TuiInputModule(state)

        async def run():
            task = asyncio.ensure_future(
                module.prompt_with_status(
                    message="Which one?", default="", timeout=-1
                )
            )
            # Let the prompt reach the point where it waits.
            for _ in range(100):
                await asyncio.sleep(0.01)
                if state.hitl_future is not None:
                    break
            state.hitl_future.set_result("the second one")
            return await task

        answer, was_timeout = asyncio.run(run())

        self.assertEqual(answer, "the second one")
        self.assertFalse(was_timeout)

    def test_the_footer_is_told_the_kind_of_answer(self):
        """The footer labels the prompt by the kind of answer."""
        state = TuiState()
        module = TuiInputModule(state)
        module.set_input_type("yesno")

        async def run():
            task = asyncio.ensure_future(
                module.prompt_with_status(
                    message="Shall I?", default="", timeout=0
                )
            )
            await asyncio.sleep(0.05)
            labelled = state.hitl_input_type
            task.cancel()
            return labelled

        self.assertEqual(asyncio.run(run()), "yesno")


if __name__ == "__main__":
    unittest.main()
