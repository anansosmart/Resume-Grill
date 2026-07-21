from __future__ import annotations

import json
from typing import Any

import requests


DEFAULT_MODEL = "qwen2.5:7b-instruct"
BACKUP_MODELS = ["qwen2.5-coder:7b", "llama3.1:8b", "llama3.2:3b"]


def ollama_available(base_url: str = "http://127.0.0.1:11434") -> bool:
    try:
        response = requests.get(f"{base_url}/api/tags", timeout=2)
        return response.ok
    except requests.RequestException:
        return False


def list_ollama_models(base_url: str = "http://127.0.0.1:11434") -> list[str]:
    try:
        response = requests.get(f"{base_url}/api/tags", timeout=3)
        response.raise_for_status()
        return [m["name"] for m in response.json().get("models", [])]
    except Exception:
        return []


def ask_ollama(prompt: str, model: str = DEFAULT_MODEL, base_url: str = "http://127.0.0.1:11434") -> str:
    response = requests.post(
        f"{base_url}/api/generate",
        json={"model": model, "prompt": prompt, "stream": False, "options": {"temperature": 0.25}},
        timeout=180,
    )
    response.raise_for_status()
    return response.json().get("response", "").strip()


def evaluate_answer(claim: str, question: str, answer: str, model: str) -> dict[str, Any]:
    prompt = f"""
你是一名严格但公正的中文技术面试官。请审计候选人的回答，不得因为表达不流畅就判定造假。

简历声明：{claim}
面试问题：{question}
候选人回答：{answer}

请只输出 JSON：
{{
  "score": 0到100的整数,
  "verdict": "可信/需补充/高风险",
  "strengths": ["最多3条"],
  "gaps": ["最多4条"],
  "follow_up": "一个最关键的继续追问"
}}
评分重点：是否给出本人贡献、baseline、数据和环境、代码位置、实验复现、失败案例。不要断言造假，只能指出证据不足或矛盾。
""".strip()
    raw = ask_ollama(prompt, model=model)
    start, end = raw.find("{"), raw.rfind("}")
    if start >= 0 and end > start:
        return json.loads(raw[start:end + 1])
    raise ValueError("本地模型未返回有效 JSON。")
