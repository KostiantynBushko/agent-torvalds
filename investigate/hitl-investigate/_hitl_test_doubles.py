#!/usr/bin/env python3
"""
Shared test doubles for the HITL diagnostics.

The important detail: the *real* production LLM is
``llama_index.llms.ollama.Ollama``, whose ``astream_chat`` is decorated with
``@llm_chat_callback()``.  ``MockFunctionCallingLLM.astream_chat`` is NOT
decorated, so a mock that only overrides ``chat``/``achat`` produces **zero
callback events** and would make the HITL diagnostics look broken for the
wrong reason.

``QuestionLLM`` below therefore mirrors Ollama's structure: an
``@llm_chat_callback()``-decorated ``astream_chat`` that yields
``ChatResponse`` objects whose ``raw`` has the Ollama shape
(``{"message": {"role": ..., "content": ...}, ...}``).
"""
from __future__ import annotations

from typing import Any, List, Sequence

from llama_index.core.base.llms.types import ChatMessage, ChatResponse
from llama_index.core.llms.callbacks import llm_chat_callback
from llama_index.core.llms.mock import MockFunctionCallingLLM
from pydantic import Field

QUESTION_TEXT = "Shall I delete the database? Do you want to continue?"


class QuestionLLM(MockFunctionCallingLLM):
    """Function-calling LLM that always answers with a question.

    Mirrors the Ollama structure so the callback path is exercised exactly
    as it is in production.
    """

    call_count: int = Field(default=0)
    last_messages: List[Any] = Field(default_factory=list)
    question_text: str = Field(default=QUESTION_TEXT)

    # -- non-streaming ------------------------------------------------
    @llm_chat_callback()
    def chat(self, messages: Sequence[ChatMessage], **kwargs: Any) -> ChatResponse:
        self.call_count += 1
        self.last_messages = list(messages)
        return ChatResponse(
            message=ChatMessage(role="assistant", content=self.question_text),
            raw={"message": {"role": "assistant", "content": self.question_text}},
        )

    @llm_chat_callback()
    async def achat(self, messages: Sequence[ChatMessage], **kwargs: Any) -> ChatResponse:
        return self.chat(messages, **kwargs)

    # -- streaming (the path the agent actually uses) ------------------
    @llm_chat_callback()
    async def astream_chat(
        self, messages: Sequence[ChatMessage], **kwargs: Any
    ):
        self.call_count += 1
        self.last_messages = list(messages)

        async def gen():
            yield ChatResponse(
                message=ChatMessage(role="assistant", content=self.question_text),
                delta=self.question_text,
                raw={
                    "message": {"role": "assistant", "content": self.question_text},
                    "done": True,
                },
            )

        return gen()


def add_two(a: int, b: int) -> int:
    """Add two integers."""
    return a + b
