"""
Searches financialexpress.com for articles matching a keyword or topic
(via its WordPress JSON API), and filters out false-positive keyword
matches by asking the LLM to score each result's relevance before it's
shown to the user.
"""

import json
import os
from datetime import datetime, timedelta, timezone
from html import unescape

import requests
from bs4 import BeautifulSoup
from langchain.agents.middleware import wrap_tool_call
from langchain_core.messages import ToolMessage
from langchain_core.tools import tool
from pydantic import BaseModel

SEARCH_URL = "https://www.financialexpress.com/wp-json/wp/v2/posts"
PAGE_SIZE = 100  # the API's own per-request maximum

# Every search is restricted to articles published in roughly the last
# month - old, stale recommendations aren't useful for logging.
SEARCH_WINDOW_DAYS = 30

# Safety cap on how many raw candidates pagination will collect within that
# month, regardless of how many actually exist (a very high-frequency term
# like a specific brokerage's name can have hundreds).
MAX_RAW_CANDIDATES = 150

# Relevance scoring is done in chunks of this size, each its own LLM call -
# a single call describing hundreds of candidates would be slow and risks
# tripping Groq's free-tier per-minute token limit.
RELEVANCE_BATCH_SIZE = 40

# Cap on the final, relevance-filtered results shown to the user.
MAX_RESULTS = 15
RELEVANCE_THRESHOLD = 0.5


class RelevanceItem(BaseModel):
    index: int
    relevance_score: float  # 0.0 (unrelated) to 1.0 (exact match) confidence the article is on-topic


class RelevanceCheck(BaseModel):
    items: list[RelevanceItem]


def _fetch_all_posts(query: str) -> list[dict] | dict:
    """
    Pages through the WP REST API to collect every post matching `query`
    published within SEARCH_WINDOW_DAYS, up to MAX_RAW_CANDIDATES. This is
    plain HTTP pagination (cheap), independent of the LLM relevance-scoring
    step that happens afterwards.
    """
    headers = {"User-Agent": os.environ.get("USER_AGENT", "Mozilla/5.0")}
    after = (datetime.now(timezone.utc) - timedelta(days=SEARCH_WINDOW_DAYS)).strftime(
        "%Y-%m-%dT%H:%M:%S"
    )
    posts: list[dict] = []
    page = 1
    while len(posts) < MAX_RAW_CANDIDATES:
        params = {
            "search": query,
            "per_page": PAGE_SIZE,
            "after": after,
            "orderby": "date",
            "order": "desc",
            "page": page,
        }
        try:
            response = requests.get(SEARCH_URL, headers=headers, params=params, timeout=10)
            response.raise_for_status()
            batch = response.json()
        except requests.RequestException as exc:
            if posts:
                break  # keep what we already have rather than losing it to a late page's failure
            return {"error": f"Search request failed: {exc}"}
        except ValueError as exc:
            if posts:
                break
            return {"error": f"Unexpected response from search API: {exc}"}

        if not isinstance(batch, list) or not batch:
            break
        posts.extend(batch)
        if len(batch) < PAGE_SIZE:
            break  # last page
        page += 1

    return posts[:MAX_RAW_CANDIDATES]


@tool
def search_financial_express_articles(query: str) -> list[dict] | dict:
    """Search financialexpress.com for news articles matching a keyword or topic and
    return their title, link, published date, and a short excerpt. Always searches the
    full last month (not just the most recent handful of matches). Use this when the
    user wants to find articles about a company, sector, or topic on financialexpress.com
    but hasn't given you a specific article link."""
    posts = _fetch_all_posts(query)
    if isinstance(posts, dict):
        return posts  # error

    results = []
    for post in posts:
        title_html = post.get("title", {}).get("rendered", "")
        excerpt_html = post.get("excerpt", {}).get("rendered", "")
        content_html = post.get("content", {}).get("rendered", "")
        title = unescape(BeautifulSoup(title_html, "html.parser").get_text(strip=True))
        excerpt = BeautifulSoup(excerpt_html, "html.parser").get_text(" ", strip=True)
        # Multi-stock "N stocks to watch" listicles put each stock's name in an <h2>/<h3>
        # subheading, which the title/excerpt alone don't reveal — pull those in cheaply
        # (no extra request, content is already in the response) to help relevance checks.
        headings = [
            h.get_text(strip=True)
            for h in BeautifulSoup(content_html, "html.parser").find_all(["h2", "h3"])
        ]
        results.append(
            {
                "title": title,
                "link": post.get("link", ""),
                "date": post.get("date", ""),
                "excerpt": excerpt[:300],
                "headings": headings,
            }
        )
    return results


def _describe(i, r):
    line = f"{i}. {r['title']} — {r['excerpt']}"
    if r.get("headings"):
        line += f" (sections: {'; '.join(r['headings'])})"
    return line


def _score_batch(llm, query: str, batch: list[dict]) -> list[dict]:
    """Scores one batch of candidates. On any failure, returns them unscored
    (relevance_score=None) rather than dropping them - a scoring hiccup on
    one batch shouldn't silently erase results a plain keyword match found."""
    candidates = "\n".join(_describe(i, r) for i, r in enumerate(batch))
    prompt = (
        f"User's search topic: {query!r}\n\n"
        f"Candidate articles found by a keyword search:\n{candidates}\n\n"
        "For every candidate, give a relevance_score from 0.0 to 1.0 estimating your confidence "
        "that it is genuinely about the user's topic (1.0 = clearly on-topic, 0.0 = only shares "
        "an incidental word but covers an unrelated subject). Include every index exactly once."
    )
    try:
        check = llm.with_structured_output(RelevanceCheck).invoke(prompt)
        scored = []
        for item in check.items:
            if 0 <= item.index < len(batch):
                result = dict(batch[item.index])
                result["relevance_score"] = item.relevance_score
                scored.append(result)
        return scored if scored else [dict(r, relevance_score=None) for r in batch]
    except Exception:
        return [dict(r, relevance_score=None) for r in batch]


def filter_relevant_results(llm, query: str, results):
    """financialexpress.com's search matches keywords anywhere in an article's raw body
    (including boilerplate unrelated to the topic), so it returns false positives. Ask the
    model to score how on-topic each candidate is (in batches of RELEVANCE_BATCH_SIZE, to
    keep each LLM call's token usage bounded), attach that score to the result, and keep
    only the ones that clear the relevance bar, up to MAX_RESULTS. Genuinely irrelevant
    candidates (low score) are dropped even if that leaves very few results — padding
    the list with off-topic articles just to hit a target count is worse than showing fewer."""
    if not isinstance(results, list) or not results:
        return results

    scored: list[dict] = []
    for start in range(0, len(results), RELEVANCE_BATCH_SIZE):
        scored.extend(_score_batch(llm, query, results[start : start + RELEVANCE_BATCH_SIZE]))

    # A None score means that batch's LLM call failed - keep those results
    # (best effort) rather than drop them; only apply the relevance bar to
    # results that were actually scored.
    kept = [r for r in scored if r["relevance_score"] is None or r["relevance_score"] >= RELEVANCE_THRESHOLD]
    kept.sort(key=lambda r: (r["relevance_score"] is not None, r["relevance_score"] or 0, r.get("date", "")), reverse=True)
    return kept[:MAX_RESULTS]


def build_relevance_middleware(llm, user_query: str):
    """Wraps the search tool's execution so its raw results are scored/filtered by
    filter_relevant_results before going back into the agent's conversation. Built fresh per
    query since filter_relevant_results needs the current user_query, which a wrap_tool_call
    function doesn't receive directly."""

    @wrap_tool_call
    def relevance_filter_middleware(request, handler):
        result_message = handler(request)  # actually runs the tool
        if request.tool_call["name"] != search_financial_express_articles.name:
            return result_message

        try:
            payload = json.loads(result_message.content)
        except (TypeError, ValueError):
            return result_message
        if not isinstance(payload, list):
            return result_message  # error dict from the tool — nothing to filter

        try:
            filtered = filter_relevant_results(llm, user_query, payload)
        except Exception:
            return result_message

        return ToolMessage(
            content=json.dumps(filtered),
            tool_call_id=result_message.tool_call_id,
            name=result_message.name,
        )

    return relevance_filter_middleware
