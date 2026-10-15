"""Rule-based explanation layer; optional LLM rewrite when configured."""

from __future__ import annotations

import json
import os

from suggestion import Suggestion, DISCLAIMER


def explain_suggestion(suggestion: Suggestion, use_llm: bool = False) -> str:
    """Always return deterministic text; optionally try LLM polish when enabled."""
    base = suggestion.explain_text()
    if not use_llm:
        return base
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return base + "\n\n（未配置 OPENAI_API_KEY，已使用规则原文。）"
    try:
        import urllib.request

        payload = {
            "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是只读美股监控助手。只能改写用户给出的结构化建议为更顺的中文，"
                        "不得发明价格、仓位或下单指令，结尾保留非投资建议声明。"
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(suggestion.to_dict(), ensure_ascii=False),
                },
            ],
            "temperature": 0.2,
        }
        request = urllib.request.Request(
            os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1/chat/completions"),
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            body = json.loads(response.read().decode("utf-8"))
        text = body["choices"][0]["message"]["content"].strip()
        if DISCLAIMER[:12] not in text:
            text = f"{text}\n\n{DISCLAIMER}"
        return text
    except Exception as exc:
        return f"{base}\n\n（LLM 解释失败，已回退规则原文：{exc}）"
