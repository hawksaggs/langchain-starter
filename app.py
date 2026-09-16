"""
Streamlit front-end for the Hello World LangChain agent.
Deployable for free on Streamlit Community Cloud or Hugging Face Spaces.
"""

import os

import streamlit as st
from dotenv import load_dotenv

from agent import build_agent, run

load_dotenv()

st.set_page_config(page_title="Hello World AI Agent", page_icon="🤖")
st.title("🤖 Hello World AI Agent")
st.caption("Built with LangChain + Groq (free tier)")

if "history" not in st.session_state:
    st.session_state.history = []

for role, text in st.session_state.history:
    with st.chat_message(role):
        st.markdown(text)

if prompt := st.chat_input("Say something to your agent..."):
    st.session_state.history.append(("user", prompt))
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            agent_graph = build_agent()
            response = run(agent_graph, prompt)
            st.markdown(response)

        st.session_state.history.append(("assistant", response))
