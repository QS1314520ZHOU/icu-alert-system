from app.services.llm_runtime import _message_text_from_response

# Real vLLM 0.29 / Qwen3.8-Next response shape (reasoning field alongside content)
REAL = {
    "id": "chatcmpl-x", "object": "chat.completion", "model": "Qwen3.8-Next",
    "choices": [{"index": 0, "message": {"role": "assistant",
        "content": "\n\n你好！很高兴见到你 😊\n有什么我可以帮你的吗？",
        "refusal": None, "reasoning": "用户用中文打招呼“你好”。需要简短友好回应。\n"},
        "finish_reason": "stop"}],
    "usage": {"prompt_tokens": 53, "total_tokens": 92, "completion_tokens": 39,
              "completion_tokens_details": {"reasoning_tokens": 22}},
}


def test_real_vllm_response_extracts_content():
    text, has_reasoning, finish = _message_text_from_response(REAL)
    assert "你好" in text and "用户用中文" not in text
    assert has_reasoning and finish == "stop"


def test_reasoning_only_is_detected_as_empty():
    data = {"choices": [{"message": {"content": None, "reasoning": "思考很长……"}, "finish_reason": "length"}]}
    text, has_reasoning, finish = _message_text_from_response(data)
    assert text == "" and has_reasoning and finish == "length"


def test_other_formats():
    assert _message_text_from_response({"choices": [{"message": {"content": [{"type": "text", "text": "a"}, {"type": "reasoning", "text": "x"}]}}]})[0] == "a"
    assert _message_text_from_response({"choices": [{"text": "b"}]})[0] == "b"
    assert _message_text_from_response({"content": [{"type": "thinking", "thinking": "x"}, {"type": "text", "text": "c"}]})[0] == "c"
    assert _message_text_from_response({"data": {"choices": [{"message": {"content": "d"}}]}})[0] == "d"


def test_thinking_switch():
    from app.services.llm_runtime import normalize_thinking_mode, thinking_payload
    assert normalize_thinking_mode("off") == "off" and normalize_thinking_mode("ON") == "on"
    assert normalize_thinking_mode(False) == "off" and normalize_thinking_mode(None) == "auto"
    assert thinking_payload("off") == {"chat_template_kwargs": {"enable_thinking": False}}
    assert thinking_payload("on") == {"chat_template_kwargs": {"enable_thinking": True}}
    assert thinking_payload("auto") == {}
