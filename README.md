# Hello World AI Agent (LangChain + uv)

A minimal LangChain agent with two tools (`get_current_time`, `say_hello`),
wrapped in a Streamlit chat UI. Uses **Groq** as the LLM provider because it
has a genuinely free tier (no credit card required), unlike OpenAI.
Dependencies are managed with **[uv](https://docs.astral.sh/uv/)**, Astral's
fast Python package/project manager.

Built and verified against **LangChain 1.x** (`create_agent`, the current
agent API — older tutorials using `AgentExecutor` /
`create_tool_calling_agent` are from LangChain 0.x and no longer match this
code).

## Files

- `agent.py` — the agent itself (model + tools), runnable standalone
- `app.py` — Streamlit chat interface around the agent
- `pyproject.toml` / `uv.lock` — uv's dependency manifest + resolved lockfile (source of truth)
- `requirements.txt` — auto-exported from `uv.lock`, kept only because some deploy platforms still expect it (see below)
- `Dockerfile` — fully uv-native container build, for platforms that support Docker

## 1. Install uv (if you don't have it)

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# or via pip, anywhere
pip install uv
```

## 2. Get a free Groq API key

1. Go to <https://console.groq.com/keys>
2. Sign up (no credit card) and click "Create API Key"
3. Copy the key

## 3. Run it locally

uv reads `pyproject.toml`/`uv.lock` and manages an isolated `.venv`
automatically — no manual `pip install` or venv activation needed.

```bash
uv sync                                # creates .venv, installs exact locked versions
export GROQ_API_KEY="your-key-here"    # Windows: set GROQ_API_KEY=your-key-here
uv run python agent.py                 # quick command-line test
uv run streamlit run app.py            # chat UI at http://localhost:8501
```

To add a new dependency later: `uv add <package>` (updates `pyproject.toml`
and `uv.lock` together). To remove one: `uv remove <package>`.

## 4. Deploy for free

### Option A — Streamlit Community Cloud (easiest)

Community Cloud currently only reads `requirements.txt` (it doesn't yet
support uv's native `pyproject.toml`/`uv.lock` format), so this repo keeps a
`requirements.txt` in sync as a deploy artifact. Regenerate it any time your
deps change:

```bash
uv export --no-hashes --no-dev --no-emit-project -o requirements.txt
```

Then:

1. Push this folder (including the regenerated `requirements.txt`) to a GitHub repo.
2. Go to <https://share.streamlit.io>, sign in with GitHub, click **"New app"**.
3. Pick the repo/branch, set the main file to `app.py`.
4. Under **Advanced settings → Secrets**, add:
   ```toml
   GROQ_API_KEY = "your-key-here"
   ```
5. Click **Deploy** → free `*.streamlit.app` URL.

### Option B — Hugging Face Spaces, Streamlit SDK

Same story as above — the Streamlit SDK build step uses `requirements.txt`.

1. Go to <https://huggingface.co/new-space>, choose **Streamlit** as the SDK.
2. Upload `app.py`, `agent.py`, and `requirements.txt`.
3. In **Settings → Variables and secrets**, add secret `GROQ_API_KEY`.
4. The Space builds and gives you a free `huggingface.co/spaces/...` URL.

### Option C — Hugging Face Spaces, Docker SDK (fully uv-native)

If you'd rather deploy exactly what you run locally — no `requirements.txt`
export step — use the included `Dockerfile`, which installs and runs
everything through uv itself.

1. Go to <https://huggingface.co/new-space>, choose **Docker** as the SDK.
2. Upload `Dockerfile`, `pyproject.toml`, `uv.lock`, `agent.py`, `app.py`.
3. In **Settings → Variables and secrets**, add secret `GROQ_API_KEY`.
4. The Space builds the Docker image (via uv) and serves it on the free tier.

All three options are free for an app this small — no server management.

## Going further (optional, zero-cost alternative)

If you'd rather not use any hosted API at all, swap `ChatGroq` in `agent.py`
for `ChatOllama` (`uv add langchain-ollama`) and run a local model via
[Ollama](https://ollama.com). That runs fully offline, but then you need a
host that can run a local model process (e.g. your own machine or a VM) —
the free tiers above won't run Ollama models, so this path suits local use
rather than a public free deployment.
