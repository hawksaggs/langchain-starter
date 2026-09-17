"""
Streamlit front-end for the Hello World LangChain agent.
Deployable for free on Streamlit Community Cloud or Hugging Face Spaces.
"""

import os

import streamlit as st
from dotenv import load_dotenv

from agent import build_agent, run

load_dotenv()  # populates os.environ from a local .env file, if present

st.set_page_config(page_title="Hello World AI Agent", page_icon="🤖")

if not st.user.is_logged_in:
    st.title("🤖 Hello World AI Agent")
    st.write("Please log in with Google to use this app.")
    st.button("Log in with Google", on_click=st.login, args=("google",))
    st.stop()

st.title("🤖 Hello World AI Agent")
st.caption("Built with LangChain + Groq (free tier) — can log entries to Google Sheets")

st.sidebar.write(f"Signed in as **{st.user.name}** ({st.user.email})")
st.sidebar.button("Log out", on_click=st.logout)
st.sidebar.divider()


def _secret_or_env(key: str, default: str = "") -> str:
    # st.secrets.get() raises StreamlitSecretNotFoundError instead of
    # returning the default when no secrets.toml exists anywhere at all
    # (not even an empty one) — so secrets.toml stays fully optional and we
    # fall back to .env / env vars in that case.
    try:
        value = st.secrets[key]
        if value:
            return value
    except Exception:
        pass
    return os.environ.get(key, default)


# --- Groq API key -----------------------------------------------------------
# Prefer a value set via Streamlit secrets / env var (for deployed apps);
# fall back to a sidebar input so it also works instantly when run locally.
api_key = st.sidebar.text_input(
    "Groq API key",
    value=_secret_or_env("GROQ_API_KEY"),
    type="password",
    help="Get a free key at https://console.groq.com/keys",
)

# --- Google Sheets logging (optional) ---------------------------------------
st.sidebar.divider()
st.sidebar.subheader("📝 Google Sheets logging")
st.sidebar.caption('Optional — lets you say things like *"log this: bought milk, $4"*.')

sheet_input = st.sidebar.text_input(
    "Sheet ID or URL",
    value=_secret_or_env("GOOGLE_SHEET_ID"),
    help="Paste the sheet's full URL, or just the ID from it.",
)


def _extract_sheet_id(value: str) -> str | None:
    value = value.strip()
    if not value:
        return None
    if "/d/" in value:
        return value.split("/d/")[1].split("/")[0]
    return value


sheet_id = _extract_sheet_id(sheet_input)

uploaded_key_file = st.sidebar.file_uploader(
    "Service account JSON key",
    type="json",
    help="From Google Cloud Console → your service account → Keys → Add key.",
)
if uploaded_key_file is not None:
    service_account_json = uploaded_key_file.read().decode("utf-8")
else:
    service_account_json = _secret_or_env("GOOGLE_SERVICE_ACCOUNT_JSON") or None

if sheet_id and service_account_json:
    st.sidebar.success("Sheets logging is configured.")
elif sheet_input or uploaded_key_file:
    st.sidebar.warning(
        "Add both a sheet ID/URL and a service-account key to enable logging."
    )

# --- Chat ---------------------------------------------------------------
if "history" not in st.session_state:
    st.session_state.history = []

for role, text in st.session_state.history:
    with st.chat_message(role):
        st.markdown(text)

if prompt := st.chat_input("Say something to your agent..."):
    if not api_key:
        st.error("Please enter a Groq API key in the sidebar first.")
    else:
        st.session_state.history.append(("user", prompt))
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                agent_graph = build_agent(
                    api_key=api_key,
                    google_sheet_id=sheet_id,
                    google_service_account_json=service_account_json,
                )
                response = run(agent_graph, prompt)
                st.markdown(response)

        st.session_state.history.append(("assistant", response))
