# Ollama Setup Guide — Run Autonomous Engineer with Zero API Cost

## Overview

[Ollama](https://ollama.ai) lets you run LLMs locally on your machine.
With `LLM_PROVIDER=ollama`, the Autonomous Engineer runs **completely free** — no API key, no cloud dependency.

**Trade-off:** Local models (Llama 3.2, Mistral) are slower and slightly less capable than Claude 3.5. Best for exploration, testing, and low-complexity tasks.

---

## Step 1: Install Ollama

**macOS / Linux:**
```bash
curl -fsSL https://ollama.com/install.sh | sh
```

**Windows:**
Download from [https://ollama.com/download](https://ollama.com/download)

Verify: `ollama --version`

---

## Step 2: Pull a Model

```bash
# Recommended: Llama 3.2 (fast, good quality, 3B params)
ollama pull llama3.2

# Alternative: Mistral 7B (more capable, needs 8GB RAM)
ollama pull mistral

# Fastest option: TinyLlama (works on any machine)
ollama pull tinyllama
```

---

## Step 3: Start Ollama Server

```bash
# Starts on http://localhost:11434 by default
ollama serve
```

---

## Step 4: Configure Autonomous Engineer

In your `.env` file (copy from `.env.example`):

```bash
LLM_PROVIDER=ollama
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=llama3.2
```

---

## Step 5: Verify Connection

```bash
python -c "
from config.llm_providers import OllamaProvider
p = OllamaProvider()
print('Available:', p.is_available())
print('Provider:', p.name)
"
```

Expected output: `Available: True | Provider: ollama`

---

## Step 6: Run a Task

```bash
# CLI
python cli.py run --task "Add type hints to core/memory.py" --provider ollama

# Docker (includes Ollama sidecar)
docker compose --profile ollama up --build
```

---

## Performance Comparison

| Task | Claude 3.5 Sonnet | Llama 3.2 (Ollama) |
|---|---|---|
| Add docstrings | ~8s | ~25s |
| Fix import error | ~12s | ~40s |
| Generate unit tests | ~20s | ~90s |
| Complex refactor | ~45s | ~3-5min |
| **Cost per task** | **~$0.03-$0.15** | **$0.00** |

---

## Hardware Requirements

| Model | RAM | GPU (optional) |
|---|---|---|
| TinyLlama (1.1B) | 2GB | Any |
| Llama 3.2 (3B) | 4GB | Recommended |
| Mistral (7B) | 8GB | Recommended |
| Llama 3.1 (8B) | 16GB | Required for speed |

---

## Troubleshooting

**"Cannot connect to Ollama"** → Make sure `ollama serve` is running
**"Model not found"** → Run `ollama pull llama3.2` first
**"Very slow responses"** → Use `tinyllama` model or enable GPU acceleration
**"Out of memory"** → Use a smaller model (tinyllama instead of mistral)

---

## SLM Routing with Ollama

The platform automatically routes low-complexity tasks to Ollama even when Claude is configured:

```bash
LLM_PROVIDER=auto             # Uses Claude for complex, Ollama for simple
OLLAMA_MODEL=llama3.2
ANTHROPIC_API_KEY=sk-ant-...  # Only used for HIGH complexity tasks
```

This cuts API costs by ~60% while maintaining quality on complex tasks.
