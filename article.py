"""
Fetches a news article (e.g. a financialexpress.com URL) and extracts its
title + body text, so the agent can read it and pull out any stock
recommendations mentioned in it.
"""

import re

import requests
from bs4 import BeautifulSoup
from langchain_core.tools import tool

_HEADERS = {
    # A browser-like UA - most news sites (financialexpress.com included)
    # block the default python-requests UA.
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}

# Keeps the article text well within the LLM's context window while still
# covering the full body of a typical news article.
_MAX_CHARS = 8000


def _extract_title(soup: BeautifulSoup) -> str:
    if soup.title and soup.title.string:
        return soup.title.string.strip()
    h1 = soup.find("h1")
    return h1.get_text(strip=True) if h1 else ""


def _find_content_container(soup: BeautifulSoup):
    """
    News sites (financialexpress.com included) often reuse <article> for
    "related stories" teaser cards, so it can't be trusted as-is. Instead,
    pick whichever <div>/<section> holds the most substantial paragraphs -
    that's reliably the real article body regardless of class/id naming,
    and among equally good candidates prefer the most specific (smallest)
    one so we don't grab the whole page.
    """
    best = None
    for tag in soup.find_all(["div", "section"]):
        paragraphs = [p for p in tag.find_all("p") if len(p.get_text(strip=True)) > 40]
        if len(paragraphs) < 3:
            continue
        size = len(tag.find_all())
        candidate = (len(paragraphs), -size, tag)
        if best is None or candidate[:2] > best[:2]:
            best = candidate
    return best[2] if best else None


def _extract_body(soup: BeautifulSoup) -> str:
    container = _find_content_container(soup) or soup
    paragraphs = [p.get_text(" ", strip=True) for p in container.find_all("p")]
    # Drop short fragments (nav links, image captions, ad labels, etc.).
    paragraphs = [p for p in paragraphs if len(p) > 30]
    return "\n\n".join(paragraphs)


@tool
def fetch_article(url: str) -> str:
    """
    Downloads a news article from a URL (e.g. financialexpress.com) and
    returns its title and body text. Always call this FIRST whenever the
    user pastes an article link, before trying to extract or log anything
    from it.
    """
    try:
        response = requests.get(url, headers=_HEADERS, timeout=15)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        return f"Couldn't fetch the article at {url}: {e}"

    soup = BeautifulSoup(response.text, "html.parser")
    title = _extract_title(soup)
    body = _extract_body(soup)

    if not body:
        return f"Fetched {url} but couldn't find any article text on the page."

    if len(body) > _MAX_CHARS:
        body = body[:_MAX_CHARS] + "\n\n[...article truncated...]"

    return f"URL: {url}\nTITLE: {title}\n\nBODY:\n{body}"
