# Hello World AI Agent (LangChain + uv + Google Sheets)

A minimal LangChain agent with three tools (`get_current_time`, `say_hello`,
`add_sheet_entry`), wrapped in a Streamlit chat UI. Uses **Groq** as the LLM
provider because it has a genuinely free tier (no credit card required),
unlike OpenAI. Dependencies are managed with
**[uv](https://docs.astral.sh/uv/)**, Astral's fast Python package/project
manager.

Say something like *"log this: bought milk, $4"* or *"add an entry: called
mom"* and the agent will append a timestamped row to a Google Sheet you
configure — no code changes needed per entry.

Built and verified against **LangChain 1.x** (`create_agent`, the current
agent API — older tutorials using `AgentExecutor` /
`create_tool_calling_agent` are from LangChain 0.x and no longer match this
code).

## Files

- `agent.py` — the agent itself (model + tools), runnable standalone
- `sheets.py` — the Google Sheets logging tool (service-account based)
- `app.py` — Streamlit chat interface around the agent
- `.streamlit/secrets.toml` — local Streamlit secrets — **placeholders, edit with your real values**
- `pyproject.toml` / `uv.lock` — uv's dependency manifest + resolved lockfile (source of truth)
- `requirements.txt` — auto-exported from `uv.lock`, kept only because some deploy platforms still expect it (see below)
- `Dockerfile` — fully uv-native container build, for platforms that support Docker

`.streamlit/secrets.toml` ships here with placeholder values so you can see
the expected shape — fill in your real keys before running. It's already
listed in `.gitignore`, so a filled-in copy won't accidentally get
committed if you push this to GitHub.

> There's no `.env` file for now, since this is mainly run through
> Streamlit. The code still supports one if you add it back later
> (`agent.py`/`sheets.py`/`app.py` all call `load_dotenv()` on import via
> python-dotenv) — useful if you ever want to run `agent.py` standalone,
> outside Streamlit, without `secrets.toml` being readable. Until then,
> `secrets.toml` is the only local config file, and it's all `app.py` needs.

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

## 3. Set up Google Sheets logging (optional)

Skip this if you don't need the sheet-logging feature — the agent works
fine without it, it just won't have the `add_sheet_entry` tool available.

1. **Create a Google Cloud service account.**
   In [Google Cloud Console](https://console.cloud.google.com/), create (or
   pick) a project, then go to **APIs & Services → Credentials → Create
   Credentials → Service account**. Give it any name.
2. **Enable the Sheets API.**
   Go to **APIs & Services → Library**, search **Google Sheets API**, click
   **Enable**.
3. **Create a JSON key for the service account.**
   Open the service account → **Keys → Add key → Create new key → JSON**.
   This downloads a `.json` file — keep it private, never commit it to git.
4. **Share your spreadsheet with the service account.**
   Open the JSON file and copy the `client_email` value (looks like
   `something@your-project.iam.gserviceaccount.com`). In Google Sheets,
   open your target sheet → **Share** → paste that email → give it
   **Editor** access.
5. **Get the sheet's ID.**
   It's the long string in the sheet's URL:
   `https://docs.google.com/spreadsheets/d/`**`THIS_PART_IS_THE_ID`**`/edit`.
   You can also just paste the full URL into the app — it extracts the ID
   for you.

You'll put the JSON key content and the sheet ID/URL into
`.streamlit/secrets.toml` — or just paste them into the Streamlit sidebar
at runtime instead, if you'd rather not store them in a file at all.

## 4. Run it locally

uv reads `pyproject.toml`/`uv.lock` and manages an isolated `.venv`
automatically — no manual `pip install` or venv activation needed.

**Edit `.streamlit/secrets.toml` first** and replace the placeholder values
with your real Groq key (and, optionally, your Sheets config). Streamlit
reads it automatically as `st.secrets` — no exporting or extra setup needed:

```bash
uv sync                                # creates .venv, installs exact locked versions
uv run streamlit run app.py            # chat UI at http://localhost:8501
```

`secrets.toml` is Streamlit-specific, so it only configures `app.py`. If
you also want to run `agent.py` standalone (`uv run python agent.py`,
without Streamlit at all), it needs the same values as plain environment
variables instead:

```bash
export GROQ_API_KEY="your-key-here"    # Windows: set GROQ_API_KEY=your-key-here
uv run python agent.py
```

(Or add a `.env` file with the same keys — the code already calls
`load_dotenv()` on import, it's just not included by default right now.)

To add a new dependency later: `uv add <package>` (updates `pyproject.toml`
and `uv.lock` together). To remove one: `uv remove <package>`.

## 5. Deploy for free

`.streamlit/secrets.toml` is for local development only — it never gets
uploaded. Each deploy option below uses that platform's own secrets store
instead, with the same variable names.

### Option A — Streamlit Community Cloud (easiest)

Community Cloud currently only reads `requirements.txt` (it doesn't yet
support uv's native `pyproject.toml`/`uv.lock` format), so this repo keeps a
`requirements.txt` in sync as a deploy artifact. Regenerate it any time your
deps change:

```bash
uv export --no-hashes --no-dev --no-emit-project -o requirements.txt
```

Then:

1. Push this folder (including the regenerated `requirements.txt`) to a GitHub repo — **never commit the service-account JSON key**, `.gitignore` already excludes common names for it.
2. Go to <https://share.streamlit.io>, sign in with GitHub, click **"New app"**.
3. Pick the repo/branch, set the main file to `app.py`.
4. Under **Advanced settings → Secrets**, add:
   ```toml
   GROQ_API_KEY = "your-key-here"
   GOOGLE_SHEET_ID = "your-sheet-id"
   GOOGLE_SERVICE_ACCOUNT_JSON = """
   { ...paste the full contents of your downloaded JSON key here... }
   """
   ```
   With secrets set this way, the sidebar fields pre-fill automatically —
   you (or anyone using your deployed app) won't need to paste them again.
5. Click **Deploy** → free `*.streamlit.app` URL.

### Option B — Hugging Face Spaces, Streamlit SDK

Same story as above — the Streamlit SDK build step uses `requirements.txt`.

1. Go to <https://huggingface.co/new-space>, choose **Streamlit** as the SDK.
2. Upload `app.py`, `agent.py`, `sheets.py`, and `requirements.txt`.
3. In **Settings → Variables and secrets**, add secrets `GROQ_API_KEY`,
   `GOOGLE_SHEET_ID`, and `GOOGLE_SERVICE_ACCOUNT_JSON` (paste the full JSON
   key content as its value).
4. The Space builds and gives you a free `huggingface.co/spaces/...` URL.

### Option C — Hugging Face Spaces, Docker SDK (fully uv-native)

If you'd rather deploy exactly what you run locally — no `requirements.txt`
export step — use the included `Dockerfile`, which installs and runs
everything through uv itself.

1. Go to <https://huggingface.co/new-space>, choose **Docker** as the SDK.
2. Upload `Dockerfile`, `pyproject.toml`, `uv.lock`, `agent.py`, `app.py`, `sheets.py`.
3. In **Settings → Variables and secrets**, add secrets `GROQ_API_KEY`,
   `GOOGLE_SHEET_ID`, and `GOOGLE_SERVICE_ACCOUNT_JSON`.
4. The Space builds the Docker image (via uv) and serves it on the free tier.

All three options are free for an app this small — no server management.

## Going further (optional, zero-cost alternative)

If you'd rather not use any hosted API at all, swap `ChatGroq` in `agent.py`
for `ChatOllama` (`uv add langchain-ollama`) and run a local model via
[Ollama](https://ollama.com). That runs fully offline, but then you need a
host that can run a local model process (e.g. your own machine or a VM) —
the free tiers above won't run Ollama models, so this path suits local use
rather than a public free deployment.