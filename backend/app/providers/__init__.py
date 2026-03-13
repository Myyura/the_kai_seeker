# LLM provider adapters (BYOK)
#
# TODO: Future providers:
# - base       — abstract base class for LLM providers
# - openai     — OpenAI / OpenAI-compatible adapter
# - anthropic  — Anthropic Claude adapter
# - local      — Local model adapter (ollama, llama.cpp, etc.)
#
# Each provider adapter should:
# 1. Accept an API key, base URL, and model name
# 2. Implement a common interface for chat completion
# 3. Support streaming responses
