"""LLM provider abstraction for paper chat."""

import asyncio
from collections.abc import Iterator
from queue import Queue
from threading import Thread

DEFAULT_OLLAMA_PARAMS = {
    "num_ctx": 32768,
    "num_predict": 2048,
    "temperature": 0.0,
    "top_k": 20,
    "top_p": 0.95,
    "presence_penalty": 1.5,
}


def get_ollama_models() -> list[str]:
    """Get installed models from Ollama."""
    try:
        import ollama
        models = ollama.list()
        return sorted(m.model for m in models.models)
    except Exception:
        return []


def stream_ollama(
    model: str, system: str, messages: list[dict],
    params: dict | None = None,
) -> Iterator[str | dict]:
    """Stream response from Ollama with configurable params.

    Yields str chunks during generation, then a dict with metrics from the final chunk.
    """
    import ollama

    opts = {**DEFAULT_OLLAMA_PARAMS, **(params or {})}
    response = ollama.chat(
        model=model,
        messages=[{"role": "system", "content": system}, *messages],
        stream=True,
        think=False,  # Qwen3.5 puts output in thinking field otherwise
        options=opts,
    )
    for chunk in response:
        text = chunk.message.content
        if text:
            yield text
        # Final chunk has done=True and metrics
        if getattr(chunk, "done", False):
            metrics = {}
            for key in ("prompt_eval_count", "prompt_eval_duration",
                        "eval_count", "eval_duration", "total_duration"):
                val = getattr(chunk, key, None)
                if val is not None:
                    metrics[key] = val
            if metrics:
                yield metrics


def stream_claude(system: str, messages: list[dict]) -> Iterator[str]:
    """Stream response from Claude via agent-sdk subprocess."""
    from claude_agent_sdk import (
        AssistantMessage,
        ClaudeAgentOptions,
        TextBlock,
        query,
    )

    # Agent-sdk takes a single prompt string, not a message array.
    # Format: system context + conversation history + latest user message.
    prompt = _format_for_agent_sdk(system, messages)

    q: Queue[str | None] = Queue()
    error_holder: list[Exception] = []

    async def run():
        try:
            options = ClaudeAgentOptions(allowed_tools=[])
            async for msg in query(prompt=prompt, options=options):
                if isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, TextBlock):
                            q.put(block.text)
        except Exception as e:
            error_holder.append(e)
        finally:
            q.put(None)  # sentinel

    thread = Thread(target=lambda: asyncio.run(run()), daemon=True)
    thread.start()

    while True:
        chunk = q.get()
        if chunk is None:
            break
        yield chunk

    if error_holder:
        raise error_holder[0]


def stream_vllm(
    model: str, system: str, messages: list[dict],
    params: dict | None = None,
) -> Iterator[str | dict]:
    """Stream response from remote vLLM server via OpenAI-compatible API.

    Yields str chunks during generation, then a dict with usage metrics.
    """
    import json as _json
    from pathlib import Path

    from openai import OpenAI

    # Read host from config
    config_path = Path(__file__).parent / "gpu_server_config.json"
    with open(config_path) as f:
        config = _json.load(f)
    host = config.get("vllm_host", "dissertation-gpu")
    port = config.get("vllm_port", 8000)

    client = OpenAI(
        base_url=f"http://{host}:{port}/v1",
        api_key="not-needed",
    )

    kwargs = {
        "model": model,
        "messages": [{"role": "system", "content": system}, *messages],
        "stream": True,
        "stream_options": {"include_usage": True},
        "extra_body": {"chat_template_kwargs": {"enable_thinking": False}},
    }
    if params:
        kwargs["max_tokens"] = params.get("num_predict", 2048)
        kwargs["temperature"] = params.get("temperature", 0.0)
        if "top_p" in params:
            kwargs["top_p"] = params["top_p"]
        if "presence_penalty" in params:
            kwargs["presence_penalty"] = params["presence_penalty"]
    else:
        kwargs["max_tokens"] = 2048
        kwargs["temperature"] = 0.0

    response = client.chat.completions.create(**kwargs)
    for chunk in response:
        if chunk.choices and chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content
        if chunk.usage:
            yield {
                "prompt_eval_count": chunk.usage.prompt_tokens,
                "eval_count": chunk.usage.completion_tokens,
            }


def get_vllm_status() -> dict:
    """Check vLLM server availability and list models."""
    import json as _json
    from pathlib import Path

    import requests

    config_path = Path(__file__).parent / "gpu_server_config.json"
    with open(config_path) as f:
        config = _json.load(f)
    host = config.get("vllm_host", "dissertation-gpu")
    port = config.get("vllm_port", 8000)
    try:
        r = requests.get(f"http://{host}:{port}/health", timeout=3)
        if not r.ok:
            return {"vllm": "loading", "models": []}
        # Fetch available models
        mr = requests.get(f"http://{host}:{port}/v1/models", timeout=3)
        models = [m["id"] for m in mr.json().get("data", [])] if mr.ok else []
        return {"vllm": "ready", "models": models}
    except Exception:
        return {"vllm": "off", "models": []}


def _format_for_agent_sdk(system: str, messages: list[dict]) -> str:
    """Format system prompt + message history into a single prompt for agent-sdk."""
    parts = [system, "\n---\n\nConversation so far:\n"]
    for msg in messages:
        role = "User" if msg["role"] == "user" else "Assistant"
        parts.append(f"\n{role}: {msg['content']}")
    parts.append("\n\nPlease respond to the latest user message.")
    return "\n".join(parts)
