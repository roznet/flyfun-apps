#!/usr/bin/env python3

import json
from types import SimpleNamespace

import pytest

from web.server.chatbot_core import RunConversationResult, run_conversation


class FakeLLM:
    def __init__(self, responses):
        self._responses = iter(responses)
        self.calls = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return next(self._responses)


def make_response(content=None, *, tool_calls=None):
    message = SimpleNamespace(content=content, tool_calls=tool_calls)
    choice = SimpleNamespace(message=message)
    return SimpleNamespace(choices=[choice])


def make_tool_call(name, arguments):
    function = SimpleNamespace(name=name, arguments=json.dumps(arguments))
    return SimpleNamespace(id="tool_call_1", type="function", function=function)


def simple_thinking_extractor(text: str):
    return "thinking", text.strip()


def simple_formatter(name, args, result):
    return f"{name}:{args}:{result}"


def test_run_conversation_without_tools():
    messages = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "Hi"},
    ]
    llm = FakeLLM([make_response("Brief analysis: Hello pilot")])

    result = run_conversation(
        messages=messages,
        llm_call=llm,
        tool_executor=lambda name, args: {},
        tools=[],
        llm_model="test-model",
        max_completion_tokens=None,
        extract_thinking_and_answer=simple_thinking_extractor,
        format_tool_response=simple_formatter,
    )

    assert isinstance(result, RunConversationResult)
    assert result.final_message == "Brief analysis: Hello pilot"
    assert result.thinking == "thinking"
    assert result.tool_calls == []
    assert messages[-1]["role"] == "assistant"
    assert messages[-1]["content"] == "Brief analysis: Hello pilot"
    assert len(llm.calls) == 1


def test_run_conversation_with_tool_and_fallback():
    messages = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "Need airport data"},
    ]

    tool_call = make_tool_call("get_airport_details", {"icao_code": "LFPG"})

    llm = FakeLLM([
        make_response("", tool_calls=[tool_call]),
        make_response("{}"),
    ])

    recorded_calls = []

    def tool_executor(name, args):
        recorded_calls.append((name, args))
        return {"result": "ok", "visualization": {"points": []}}

    result = run_conversation(
        messages=messages,
        llm_call=llm,
        tool_executor=tool_executor,
        tools=[{"name": "get_airport_details"}],
        llm_model="test-model",
        max_completion_tokens=512,
        extract_thinking_and_answer=simple_thinking_extractor,
        format_tool_response=simple_formatter,
    )

    assert recorded_calls == [("get_airport_details", {"icao_code": "LFPG"})]
    assert result.tool_calls[0]["arguments"]["icao_code"] == "LFPG"
    assert result.visualizations == [{"points": []}]
    assert result.final_message.startswith("get_airport_details")
    assert result.thinking == ""
    # With tool calls, assistant response is not appended to history
    assert messages[-1]["role"] == "tool"
    assert len(llm.calls) == 2

