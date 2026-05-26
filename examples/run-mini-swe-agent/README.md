# run-mini-swe-agent

Minimal end-to-end example that runs mini-swe-agent in an Agentix
sandbox through the Python API (`DefaultAgent.run(...)`), without
using abridge.

## Build

```bash
cd examples/run-mini-swe-agent
uv sync
uv run agentix build . --name run-mini-swe-agent:0.1.0 --output dist/run-mini-swe-agent.bundle.tar
BUNDLE=$(uv run agentix deploy docker dist/run-mini-swe-agent.bundle.tar | awk -F' -> ' '/^bundle -> /{print $2}')
```

## Run

Set OpenAI-compatible credentials for mini-swe-agent/litellm:

```bash
OPENAI_API_KEY=sk-... \
OPENAI_BASE_URL=https://api.openai.com/v1 \
uv run python main.py --bundle "$BUNDLE"
```

Optional model override:

```bash
OPENAI_API_KEY=sk-... \
MINI_SWE_MODEL=openai/gpt-4.1-mini \
uv run python main.py --bundle "$BUNDLE"
```
