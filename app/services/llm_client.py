import json
import os
import urllib.error
import urllib.request


DEFAULT_BASE_URL = "https://api.deepseek.com/v1"
DEFAULT_MODEL = "deepseek-chat"


class LLMError(RuntimeError):
    pass


def config():
    return {
        "api_key": os.environ.get("LLM_API_KEY", "").strip(),
        "base_url": os.environ.get("LLM_BASE_URL", DEFAULT_BASE_URL).strip().rstrip("/"),
        "model": os.environ.get("LLM_MODEL", DEFAULT_MODEL).strip(),
    }


def is_configured():
    cfg = config()
    return bool(cfg["api_key"] and cfg["base_url"] and cfg["model"])


def chat_completions_url(base_url):
    if base_url.endswith("/chat/completions"):
        return base_url
    return f"{base_url}/chat/completions"


def chat_completion(messages, temperature=0.2, timeout=60):
    cfg = config()

    if not is_configured():
        raise LLMError("LLM is not configured")

    payload = {
        "model": cfg["model"],
        "messages": messages,
        "temperature": temperature,
    }

    request = urllib.request.Request(
        chat_completions_url(cfg["base_url"]),
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {cfg['api_key']}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))

    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise LLMError(str(exc)) from exc

    try:
        return data["choices"][0]["message"]["content"]

    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError("Unexpected LLM response shape") from exc