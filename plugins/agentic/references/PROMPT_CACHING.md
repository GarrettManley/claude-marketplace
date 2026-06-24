# Prompt Caching Patterns

When and how to use Anthropic's prompt cache. Defaults from this marketplace's house style.

## When prompt caching pays off

The cache pays for itself when:

- The same content (system prompt, tool definitions, RAG context, examples) is reused across **multiple turns** within the 5-minute TTL window.
- The cached content is **≥ 1024 tokens** (cache write has overhead; small prompts don't break even).
- The conversation **stays warm** — cold-start each turn means repeated writes, no reads.

Skip the cache when:

- Single-shot calls with no follow-up (no read opportunity).
- Highly variable system prompts (no shared content to cache).

## The standard 4-block pattern

For agents with tools + RAG + examples + dynamic input, structure system content as 4 cache blocks:

```python
client.messages.create(
    model="claude-sonnet-4-6",
    system=[
        # Block 1: stable persona / instructions (rarely changes)
        {
            "type": "text",
            "text": persona_prompt,
            "cache_control": {"type": "ephemeral"}
        },
        # Block 2: tool definitions (changes when adding/modifying tools)
        {
            "type": "text",
            "text": tool_definitions_text,
            "cache_control": {"type": "ephemeral"}
        },
        # Block 3: RAG context (changes per session, stable within session)
        {
            "type": "text",
            "text": rag_context,
            "cache_control": {"type": "ephemeral"}
        },
        # Block 4: few-shot examples (rarely changes)
        {
            "type": "text",
            "text": examples_text,
            "cache_control": {"type": "ephemeral"}
        },
    ],
    messages=conversation_history,  # NOT cached — varies every turn
)
```

Each `cache_control` mark cuts the cache at that point. Anthropic charges 1.25× for cache writes and 0.1× for cache reads.

## Conversation history caching

For long conversations, you can also mark the cumulative history as cacheable:

```python
messages=[
    *previous_turns,
    {"role": "user", "content": [
        {"type": "text", "text": history_summary, "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": new_user_input}
    ]}
]
```

This works best with conversation summarization keeping the cumulative size growing predictably.

## Monitoring cache hit rate

Every response includes usage stats:

```python
response.usage
# Usage(
#     input_tokens=42,         # uncached input this turn
#     output_tokens=120,
#     cache_creation_input_tokens=2400,  # tokens written to cache
#     cache_read_input_tokens=0,         # tokens served from cache
# )
```

Target hit rate by app type:

| App type | Target cache_read / total_input |
|----------|--------------------------------|
| Multi-turn chat agent | > 80% by turn 3 |
| Single-shot RAG | N/A (no reuse) |
| Batch processing same prompt | > 95% across batch |

If you're below target, the system prompt is probably changing turn-over-turn (timestamp injection? user-specific facts in system prompt?). Move that variance to `messages` instead.

## Cache TTL math

5 minutes per cache block. If your conversation has gaps > 5 min, add a "keepalive" no-op turn or accept the cache miss.

For long-running agents (hours of work), consider checkpointing: every N turns, regenerate a compressed conversation summary and cache that, dropping older turns from active history.
