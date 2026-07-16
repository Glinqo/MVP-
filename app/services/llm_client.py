import http.client
import json
import logging
import os
import time
import urllib.error
import urllib.request


DEFAULT_BASE_URL = "https://api.deepseek.com/v1"
DEFAULT_MODEL = "deepseek-chat"
MAX_RETRIES = 2
RETRY_DELAY = 1.5  # seconds between retries

logger = logging.getLogger(__name__)


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

    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    url = chat_completions_url(cfg["base_url"])

    last_error = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            request = urllib.request.Request(
                url,
                data=body,
                headers={
                    "Authorization": f"Bearer {cfg['api_key']}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
                return data["choices"][0]["message"]["content"]

        except (
            urllib.error.URLError,
            TimeoutError,
            json.JSONDecodeError,
            http.client.HTTPException,
            ConnectionError,
            OSError,
        ) as exc:
            last_error = exc
            if attempt < MAX_RETRIES:
                logger.warning(
                    "LLM call attempt %d/%d failed: %s. Retrying in %.1fs...",
                    attempt + 1, MAX_RETRIES + 1, exc, RETRY_DELAY,
                )
                time.sleep(RETRY_DELAY)
            # else: last attempt failed, fall through

        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"Unexpected LLM response shape: {exc}") from exc

    raise LLMError(
        f"LLM call failed after {MAX_RETRIES + 1} attempts. "
        f"Last error: {last_error}"
    ) from last_error


def chat_completion_stream(messages, temperature=0.2, timeout=90):
    """流式调用 LLM，逐块返回 delta 文本。

    用法:
        for chunk in chat_completion_stream(messages):
            print(chunk, end="", flush=True)
    """
    cfg = config()
    if not is_configured():
        raise LLMError("LLM is not configured")

    payload = {
        "model": cfg["model"],
        "messages": messages,
        "temperature": temperature,
        "stream": True,
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    url = chat_completions_url(cfg["base_url"])

    last_error = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            request = urllib.request.Request(
                url,
                data=body,
                headers={
                    "Authorization": f"Bearer {cfg['api_key']}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=timeout) as response:
                # 逐行读取 SSE 事件
                buffer = b""
                while True:
                    chunk = response.read(4096)
                    if not chunk:
                        break
                    buffer += chunk
                    while b"\n" in buffer:
                        line, buffer = buffer.split(b"\n", 1)
                        line_str = line.decode("utf-8").strip()
                        if not line_str or not line_str.startswith("data: "):
                            continue
                        data_str = line_str[6:]  # 去掉 "data: " 前缀
                        if data_str == "[DONE]":
                            return
                        try:
                            data = json.loads(data_str)
                            delta = data["choices"][0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                yield content
                        except (json.JSONDecodeError, KeyError, IndexError):
                            continue
                return  # 流正常结束

        except (
            urllib.error.URLError,
            TimeoutError,
            json.JSONDecodeError,
            http.client.HTTPException,
            ConnectionError,
            OSError,
        ) as exc:
            last_error = exc
            if attempt < MAX_RETRIES:
                logger.warning(
                    "LLM stream attempt %d/%d failed: %s. Retrying in %.1fs...",
                    attempt + 1, MAX_RETRIES + 1, exc, RETRY_DELAY,
                )
                time.sleep(RETRY_DELAY)
            # else: last attempt, fall through

        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"Unexpected LLM stream response shape: {exc}") from exc

    raise LLMError(
        f"LLM stream call failed after {MAX_RETRIES + 1} attempts. "
        f"Last error: {last_error}"
    ) from last_error