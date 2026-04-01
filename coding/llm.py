"""LLM provider abstraction for paper chat."""

import asyncio
from collections.abc import Iterator
from queue import Queue
from threading import Thread

DEFAULT_OLLAMA_PARAMS = {
    "num_ctx": 32768,
    "num_predict": 2048,
    "temperature": 0.6,
    "top_k": 20,
    "top_p": 0.95,
    "presence_penalty": 1.5,
}


def get_ollama_models() -> list[str]:
    """Get installed Qwen3.5 models from Ollama."""
    try:
        import ollama
        models = ollama.list()
        return sorted(
            m.model for m in models.models
            if "qwen3" in m.model.lower()
        )
    except Exception:
        return []


def stream_ollama(
    model: str, system: str, messages: list[dict],
    params: dict | None = None,
) -> Iterator[str]:
    """Stream response from Ollama with configurable params."""
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


def _format_for_agent_sdk(system: str, messages: list[dict]) -> str:
    """Format system prompt + message history into a single prompt for agent-sdk."""
    parts = [system, "\n---\n\nConversation so far:\n"]
    for msg in messages:
        role = "User" if msg["role"] == "user" else "Assistant"
        parts.append(f"\n{role}: {msg['content']}")
    parts.append("\n\nPlease respond to the latest user message.")
    return "\n".join(parts)
