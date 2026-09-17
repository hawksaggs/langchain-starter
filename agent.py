"""
Hello World AI Agent built with LangChain.

Uses Groq's free API (fast Llama models, no credit card required) as the LLM
backend. Get a free API key at https://console.groq.com/keys
"""

import os
from datetime import datetime

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_groq import ChatGroq

from sheets import make_sheet_logging_tool

load_dotenv()  # populates os.environ from a local .env file, if present


@tool
def get_current_time() -> str:
    """Returns the current date and time. Useful when the user asks what time it is."""
    return datetime.now().strftime("%A, %B %d, %Y at %I:%M %p")


@tool
def say_hello(name: str) -> str:
    """Returns a friendly greeting for the given name."""
    return f"Hello, {name}! Nice to meet you."


def build_agent(
    api_key: str | None = None,
    google_sheet_id: str | None = None,
    google_service_account_json: str | dict | None = None,
):
    """Builds and returns a simple LangChain tool-calling agent (LangChain 1.x API)."""
    llm = ChatGroq(
        model="openai/gpt-oss-20b",
        temperature=0.3,
        api_key=api_key or os.environ.get("GROQ_API_KEY"),
    )

    sheet_tool = make_sheet_logging_tool(
        sheet_id=google_sheet_id,
        service_account_json=google_service_account_json,
    )

    return create_agent(
        model=llm,
        tools=[get_current_time, say_hello, sheet_tool],
        system_prompt=(
            "You are a friendly, concise hello-world AI agent. "
            "Use tools when they help answer the question. "
            "If the user asks you to log, save, record, or add something to "
            "their sheet, use the add_sheet_entry tool — don't just say you "
            "will, actually call it."
        ),
    )


def run(agent, user_input: str) -> str:
    """Sends a message to the agent and returns its final text reply."""
    result = agent.invoke({"messages": [{"role": "user", "content": user_input}]})
    return result["messages"][-1].content


if __name__ == "__main__":
    my_agent = build_agent()
    reply = run(my_agent, "Say hello to the world, then tell me what time it is.")
    print("\nAgent response:\n", reply)
