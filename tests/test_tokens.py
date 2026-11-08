"""
The tokenizer of the agent, and the counting of tokens.

These tests cover the one place where the tokenizer is reached and the
one rule that estimates the tokens when there is no tokenizer.  The
modules that use them — the context guard, the context metrics, the
skills and the chat history — are covered by their own tests.

Category: Infrastructure
"""

from unittest.mock import patch

import pytest

from components.tokens import (
    CHARS_PER_TOKEN,
    count_tokens_of,
    estimate_tokens,
    get_tokenizer,
    load_tokenizer,
)


# ---------------------------------------------------------------------------
# The estimate
# ---------------------------------------------------------------------------


def test_the_estimate_is_four_characters_per_token():
    """The estimate is the rule the agent has always used."""
    assert CHARS_PER_TOKEN == 4
    assert estimate_tokens("") == 0
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("abcde") == 2
    assert estimate_tokens("a" * 400) == 100


def test_the_estimate_is_the_same_rule_for_every_length():
    """The estimate rounds up, so a text is never worth less than n/4."""
    for length in (0, 1, 7, 16, 100, 401):
        assert estimate_tokens("x" * length) == (length + 3) // 4


# ---------------------------------------------------------------------------
# The count
# ---------------------------------------------------------------------------


def test_an_empty_text_holds_no_tokens():
    """An empty text is not an error and not an estimate."""
    assert count_tokens_of("") == (0, False)


def test_the_tokenizer_counts_the_text():
    """The tokenizer of the agent counts the tokens of a text."""
    tokens, estimated = count_tokens_of("the prompt that goes to the model")

    assert estimated is False
    assert tokens > 0


def test_a_given_tokenizer_is_used():
    """The tokenizer of the caller is the one that counts."""
    tokens, estimated = count_tokens_of("four", tokenizer=lambda text: text.split())

    assert tokens == 1
    assert estimated is False


def test_a_broken_tokenizer_degrades_into_the_estimate():
    """A tokenizer that raises does not take the count down."""

    def broken(_text):
        raise RuntimeError("no tokenizer here")

    tokens, estimated = count_tokens_of("some text", broken)

    assert estimated is True
    assert tokens == estimate_tokens("some text")


def test_a_missing_tokenizer_degrades_into_the_estimate():
    """Without a tokenizer the tokens are estimated, and it is said."""
    with patch(
        "components.tokens.load_tokenizer",
        side_effect=ImportError("no tokenizer here"),
    ):
        tokens, estimated = count_tokens_of("some text")

    assert estimated is True
    assert tokens == estimate_tokens("some text")


# ---------------------------------------------------------------------------
# The tokenizer
# ---------------------------------------------------------------------------


def test_the_tokenizer_of_the_agent_is_loaded():
    """The tokenizer is the one of the chat memory."""
    tokenizer = get_tokenizer()

    if tokenizer is None:
        pytest.skip("no tokenizer is available on this machine")

    assert len(tokenizer("the prompt")) > 0


def test_a_tokenizer_that_cannot_be_loaded_is_none_and_not_an_error():
    """The safe loader degrades instead of raising."""
    with patch(
        "components.tokens.load_tokenizer",
        side_effect=ImportError("no tokenizer here"),
    ):
        assert get_tokenizer() is None


def test_the_raw_loader_reports_the_failure():
    """The raw loader lets the failure through — the caller needs to know."""
    with patch(
        "llama_index.core.utils.get_tokenizer",
        side_effect=ImportError("no tokenizer here"),
    ):
        with pytest.raises(ImportError):
            load_tokenizer()
