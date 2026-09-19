"""
Hello World AI Agent built with LangChain.

Uses Groq's free API (fast Llama models, no credit card required) as the LLM
backend. Get a free API key at https://console.groq.com/keys
"""

import json
import os
from datetime import datetime

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.messages import ToolMessage
from langchain_core.tools import tool
from langchain_groq import ChatGroq

from article import fetch_article
from search import build_relevance_middleware, search_financial_express_articles
from sheets import make_sheet_logging_tool, make_stock_recommendation_tool
from stock_lookup import get_stock_price

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
    user_query: str | None = None,
):
    """
    Builds and returns a simple LangChain tool-calling agent (LangChain 1.x API).
    Pass the user's current message as `user_query` to enable relevance
    filtering on financialexpress.com search results (it scores each result
    against that specific query) — omit it (e.g. for the standalone
    `__main__` demo below) to skip that filtering.
    """
    llm = ChatGroq(
        model="openai/gpt-oss-20b",
        temperature=0.3,
        api_key=api_key or os.environ.get("GROQ_API_KEY"),
    )

    sheet_tool = make_sheet_logging_tool(
        sheet_id=google_sheet_id,
        service_account_json=google_service_account_json,
    )
    stock_recommendation_tool = make_stock_recommendation_tool(
        sheet_id=google_sheet_id,
        service_account_json=google_service_account_json,
    )

    middleware = [build_relevance_middleware(llm, user_query)] if user_query else []

    return create_agent(
        model=llm,
        tools=[
            get_current_time,
            say_hello,
            sheet_tool,
            fetch_article,
            search_financial_express_articles,
            get_stock_price,
            stock_recommendation_tool,
        ],
        middleware=middleware,
        system_prompt=(
            "You are a friendly, concise hello-world AI agent. "
            "Use tools when they help answer the question. "
            "If the user asks you to log, save, record, or add something to "
            "their sheet, use the add_sheet_entry tool — don't just say you "
            "will, actually call it.\n\n"
            "If the user pastes an article URL (e.g. a financialexpress.com "
            "link): first call fetch_article to get its text. Then read it "
            "carefully for any explicit stock recommendation(s) — a "
            "buy/sell/hold/accumulate/reduce/add call on a named stock, "
            "usually with a target price and/or a brokerage/analyst name. "
            "For each such recommendation found, call add_stock_recommendation "
            "with the stock name, the recommendation, the article URL/title, "
            "and target_price and source and rationale if the article "
            "mentions them (leave those blank rather than guessing — don't "
            "invent values). You can leave ticker and current_price blank "
            "too; that tool looks them up automatically. If the article "
            "contains no explicit stock recommendation, don't call "
            "add_stock_recommendation — just tell the user that.\n\n"
            "If the user just asks for a stock's current price or ticker "
            "symbol directly (not for logging), use get_stock_price.\n\n"
            "If the user wants to find articles about a topic, company, or "
            "sector on financialexpress.com but hasn't given you a specific "
            "link (e.g. 'find articles about healthcare stocks' or 'any "
            "news on RBI rate cuts?'), use search_financial_express_articles "
            "— turn their request into a short, effective search query (2-5 "
            "words, drop filler like 'articles about'). It's always limited "
            "to roughly the last month of articles - don't try to widen or "
            "narrow that window yourself. Call it at most once per request, "
            "unless it returns zero results, in which case you may retry "
            "once with a broader or rephrased query. After it "
            "returns, reply with a short sentence introducing the results — "
            "the results themselves are displayed separately, so don't "
            "repeat, list, or retype the titles or links. If the user then "
            "asks you to log recommendations from one of those results, "
            "treat its link the same as a pasted article URL above."
        ),
    )


def run(agent, user_input: str) -> str:
    """Sends a message to the agent and returns its final text reply."""
    result = agent.invoke({"messages": [{"role": "user", "content": user_input}]})
    return result["messages"][-1].content


def run_with_search_results(agent, user_input: str) -> tuple[str, list[dict] | None]:
    """
    Like `run`, but also returns any (already relevance-filtered)
    financialexpress.com search results found along the way, so the caller
    can render them separately from the agent's own reply text - the system
    prompt tells the agent not to retype them itself.
    """
    result = agent.invoke({"messages": [{"role": "user", "content": user_input}]})
    messages = result["messages"]

    search_results = None
    for message in reversed(messages):
        if (
            isinstance(message, ToolMessage)
            and message.name == search_financial_express_articles.name
        ):
            try:
                payload = json.loads(message.content)
            except (TypeError, ValueError):
                payload = None
            if isinstance(payload, list):
                search_results = payload
            break

    return messages[-1].content, search_results


if __name__ == "__main__":
    my_agent = build_agent()
    reply = run(my_agent, "Say hello to the world, then tell me what time it is.")
    print("\nAgent response:\n", reply)
