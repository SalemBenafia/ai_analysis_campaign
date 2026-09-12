"""AI usage accounting helpers."""
from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage

from app.modules.admin.ai_usage import sum_langchain_usage


class TestSumLangchainUsage:
    def test_sums_across_ai_messages(self):
        messages = [
            HumanMessage(content="hi"),
            AIMessage(
                content="",
                usage_metadata={"input_tokens": 100, "output_tokens": 20, "total_tokens": 120},
                response_metadata={"model_name": "llama-3.3-70b-versatile"},
            ),
            AIMessage(
                content="done",
                usage_metadata={"input_tokens": 150, "output_tokens": 30, "total_tokens": 180},
                response_metadata={"model_name": "llama-3.3-70b-versatile"},
            ),
        ]
        usage = sum_langchain_usage(messages)
        assert usage == {
            "model": "llama-3.3-70b-versatile",
            "input_tokens": 250,
            "output_tokens": 50,
        }

    def test_handles_messages_without_usage(self):
        usage = sum_langchain_usage([HumanMessage(content="x"), AIMessage(content="y")])
        assert usage == {"model": None, "input_tokens": 0, "output_tokens": 0}
