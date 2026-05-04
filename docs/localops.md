# LocalOps

LocalOps provides chat, provider settings, and workspace utilities.

## Requirements
- one or more LLM providers configured in the UI or backend storage
- `OPENAI_API_KEY` or another provider-specific credential when needed
- optional shared memory root for cross-surface context

## Typical provider values
- base URL: `http://127.0.0.1:11434`
- model: choose one available on your local provider

## Review flow
1. Open `LocalOps`
2. Add a provider
3. Start a thread
4. Verify chat, tool calls, and saved thread history
