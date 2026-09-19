from __future__ import annotations

import json
import os
from typing import Any


class OptionalLLM:
    """Strict, optional OpenAI-compatible generator.

    The model is only allowed to propose text expressions. The deterministic validator
    and platform simulation remain the authority; no tool/code execution is delegated
    to the model.
    """
    def __init__(self):
        self.base_url = os.getenv("LLM_BASE_URL")
        self.api_key = os.getenv("LLM_API_KEY")
        self.model = os.getenv("LLM_MODEL")

    @property
    def enabled(self) -> bool:
        return bool(self.base_url and self.api_key and self.model)

    def generate(self, *, fields: list[str], operators: list[str], existing_families: list[str], n: int = 4) -> list[dict[str, str]]:
        if not self.enabled:
            return []
        from openai import OpenAI
        client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        prompt = {
            "task": "Generate novel formulaic alpha expressions for WorldQuant FASTEXPR.",
            "constraints": {
                "n": n,
                "output_only_json": True,
                "fields": fields[:250],
                "operators": operators[:120],
                "do_not_repeat_families": existing_families[:30],
                "no_external_code": True,
            },
            "schema": [{"expression": "string", "family": "string", "hypothesis": "string"}],
        }
        resp = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "Return only a JSON array. Expressions are text, never code execution."},
                {"role": "user", "content": json.dumps(prompt)},
            ],
            temperature=0.8,
            max_tokens=1200,
        )
        raw = resp.choices[0].message.content or "[]"
        data: Any = json.loads(raw)
        return data if isinstance(data, list) else []
