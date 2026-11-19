"""Use the selected provider's cheapest judge to choose a capable CAPI model."""
from __future__ import annotations

import json
import re
import urllib.request
from typing import Any


def parse_choice(text: str, catalog: list[tuple[str, str, float, float]]) -> tuple[str, str]:
    match = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not match:
        raise ValueError("The model router returned no JSON choice.")
    try:
        result = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise ValueError("The model router returned invalid JSON.") from exc
    if not isinstance(result, dict):
        raise ValueError("The model router returned an invalid choice object.")
    available = {item[0] for item in catalog}
    model = result.get("model")
    reason = str(result.get("reason") or "").strip()
    if model not in available:
        raise ValueError("The model router selected a model outside the available catalog.")
    if not reason:
        raise ValueError("The model router did not explain its selection.")
    return model, reason[:500]


def _judge_prompt(prompt: str, catalog: list[tuple[str, str, float, float]],
                  files: list[dict[str, Any]] | None = None) -> str:
    models = "\n".join(f"- {name}: ${input_rate:.2f} input / ${output_rate:.2f} output per million tokens"
                       for name, _tier, input_rate, output_rate in catalog)
    attachments = "\n".join(
        f"- {str(item.get('name') or 'file')[:120]} ({str(item.get('mime') or 'unknown MIME')[:100]})"
        for item in (files or []) if isinstance(item, dict)
    )
    return (
        "Select the least expensive model in this catalog that is likely to complete the user's task correctly. "
        "Use a more capable model only when the task's complexity requires it. Do not solve the task. "
        "Return only JSON with keys model and reason; model must exactly match a catalog entry, and reason must be one sentence.\n\n"
        f"Catalog:\n{models}\n\nAttachments (metadata only):\n{attachments or '(none)'}\n\nUser task:\n{prompt[:12000]}"
    )


def choose(provider: str, prompt: str, files: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    if not prompt.strip():
        raise ValueError("A prompt is required for model routing.")
    import capi_chat as C
    import pair_chat

    catalog = pair_chat.slave_catalog(provider)
    if not catalog:
        raise RuntimeError(f"No models are available for provider {provider}.")
    judge_model = catalog[0][0]
    judge_prompt = _judge_prompt(prompt, catalog, files)

    if provider == "gcloud":
        import gemini_hands as H
        answer, cost = H.text_turn(judge_model, "You route model requests. Follow the user's output format exactly.",
                                   [], judge_prompt, label="capi model router")
    elif provider in ("anthropic", "oxyy"):
        P = C.PROVIDERS[provider]
        key = C._key(provider)
        if not key:
            raise RuntimeError(f"No {P['name']} API key is configured.")
        req = urllib.request.Request(
            (P["base_url"] or "https://api.anthropic.com") + "/v1/messages",
            method="POST",
            headers={
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
                "user-agent": "queen/capi-model-router",
            },
            data=json.dumps({
                "model": judge_model,
                "max_tokens": 180,
                "messages": [{"role": "user", "content": judge_prompt}],
            }).encode("utf-8"),
        )
        try:
            with urllib.request.urlopen(req, timeout=45) as response:
                body = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", errors="replace")[:200]
            except Exception:
                pass
            raise RuntimeError(f"{P['name']} model router failed: {(detail or str(exc)).replace(key, '***')}") from exc
        answer = "".join(part.get("text", "") for part in body.get("content", []) if part.get("type") == "text")
        usage = body.get("usage") or {}
        cost = round((int(usage.get("input_tokens") or 0) * catalog[0][2]
                      + int(usage.get("output_tokens") or 0) * catalog[0][3]) / 1_000_000 * P["factor"], 6)
        C._ledger(cost, "capi model router", provider=provider)
    else:
        raise ValueError(f"Unsupported provider for model routing: {provider}")

    model, reason = parse_choice(answer, catalog)
    return {
        "provider": provider,
        "model": model,
        "reason": reason,
        "judge_model": judge_model,
        "router_cost_usd": cost,
        "catalog": [item[0] for item in catalog],
    }
