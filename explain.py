"""Rule-based explanation layer; optional LLM rewrite when configured.

The LLM path only rewrites text that the deterministic engines already
produced. It never receives control over a decision: the recommended plan
header is always taken from the rule result, not from the model output.
"""

from __future__ import annotations

import json
import os

from suggestion import Suggestion, DISCLAIMER


def _llm_rewrite(payload: dict, system_prompt: str) -> str:
    import urllib.request

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    body = {
        "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        "temperature": 0.2,
    }
    request = urllib.request.Request(
        os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1/chat/completions"),
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        result = json.loads(response.read().decode("utf-8"))
    return result["choices"][0]["message"]["content"].strip()


def explain_suggestion(suggestion: Suggestion, use_llm: bool = False) -> str:
    """Always return deterministic text; optionally try LLM polish when enabled."""
    base = suggestion.explain_text()
    if not use_llm:
        return base
    if not os.getenv("OPENAI_API_KEY", "").strip():
        return base + "\n\n（未配置 OPENAI_API_KEY，已使用规则原文。）"
    try:
        text = _llm_rewrite(
            suggestion.to_dict(),
            "你是只读美股监控助手。只能改写用户给出的结构化建议为更顺的中文，"
            "不得发明价格、仓位或下单指令，结尾保留非投资建议声明。",
        )
        if DISCLAIMER[:12] not in text:
            text = f"{text}\n\n{DISCLAIMER}"
        return text
    except Exception as exc:
        return f"{base}\n\n（LLM 解释失败，已回退规则原文：{exc}）"


def explain_diagnosis(diagnosis, use_llm: bool = False) -> str:
    """Explain a holding_diagnosis.HoldingDiagnosis; the LLM may only rephrase."""
    base = diagnosis.explain_text()
    if not use_llm:
        return base
    if not os.getenv("OPENAI_API_KEY", "").strip():
        return base + "\n\n（未配置 OPENAI_API_KEY，已使用规则原文。）"
    plan = diagnosis.recommended_plan
    header = f"【规则引擎结论】推荐方案：{plan.name}（评分 {plan.score}，置信度 {diagnosis.confidence}）"
    try:
        text = _llm_rewrite(
            diagnosis.to_dict(),
            "你是只读美股监控助手。用户给出的是确定性规则引擎的持仓诊断结果。"
            "你只能用更易读的中文解释这些已有结论和数字，不得改变推荐方案、"
            "不得新增或修改任何价格、数量、方案，不得给出下单指令，结尾保留非投资建议声明。",
        )
    except Exception as exc:
        return f"{base}\n\n（LLM 解释失败，已回退规则原文：{exc}）"
    return f"{header}\n\n{text}\n\n—— 规则原文 ——\n{base}"
