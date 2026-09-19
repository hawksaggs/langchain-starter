"""
Looks up a stock's exchange ticker/symbol and current market price by
company name (or partial symbol), using Yahoo Finance's public search +
quote endpoints. No API key required.
"""

import re

import requests
from langchain_core.tools import tool

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}

_SEARCH_URL = "https://query2.finance.yahoo.com/v1/finance/search"
_QUOTE_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"

# Financial Express covers Indian markets, so when a company lists on more
# than one exchange, prefer its NSE ("NSI") or BSE listing over others.
_PREFERRED_EXCHANGES = ("NSI", "BSE")


def _query_variants(query: str) -> list[str]:
    # Yahoo's search is a literal-ish match, not a fuzzy one - "Larsen and
    # Toubro" and "Larsen & Toubro" return completely different result
    # sets (only one of which includes the NSE listing). Trying both
    # "and"/"&" spellings covers how article text and company legal names
    # tend to differ.
    variants = [query]
    if re.search(r"\band\b", query, flags=re.I):
        variants.append(re.sub(r"\band\b", "&", query, flags=re.I))
    if "&" in query:
        variants.append(query.replace("&", "and"))
    return variants


def _search_symbol(query: str) -> dict | None:
    first_match = None
    for variant in _query_variants(query):
        response = requests.get(
            _SEARCH_URL,
            params={"q": variant, "quotesCount": 10, "newsCount": 0},
            headers=_HEADERS,
            timeout=10,
        )
        response.raise_for_status()
        quotes = [q for q in response.json().get("quotes", []) if q.get("quoteType") == "EQUITY"]
        if not quotes:
            continue
        first_match = first_match or quotes[0]
        preferred = next((q for q in quotes if q.get("exchange") in _PREFERRED_EXCHANGES), None)
        if preferred:
            return preferred
    return first_match


def _get_quote_meta(symbol: str) -> dict | None:
    response = requests.get(_QUOTE_URL.format(symbol=symbol), headers=_HEADERS, timeout=10)
    response.raise_for_status()
    result = response.json().get("chart", {}).get("result")
    return result[0]["meta"] if result else None


def find_stock(name_or_symbol: str) -> dict | None:
    """
    Returns {"symbol", "name", "price", "currency"} for the best-matching
    stock, or None if nothing could be found/fetched.
    """
    try:
        match = _search_symbol(name_or_symbol)
        if not match:
            return None
        meta = _get_quote_meta(match["symbol"])
    except requests.exceptions.RequestException:
        return None

    if not meta or "regularMarketPrice" not in meta:
        return None

    return {
        "symbol": match["symbol"],
        "name": match.get("shortname") or match.get("longname") or name_or_symbol,
        "price": meta["regularMarketPrice"],
        "currency": meta.get("currency", ""),
    }


@tool
def get_stock_price(name_or_symbol: str) -> str:
    """
    Looks up a stock's exchange ticker/symbol and current market price given
    its company name or a partial symbol (e.g. "Hindustan Aeronautics" or
    "HAL"). Useful for answering a direct question about a stock's current
    price or symbol - stock recommendations logged via
    add_stock_recommendation already look this up automatically, so you
    don't need to call this just before that.
    """
    result = find_stock(name_or_symbol)
    if not result:
        return f"Couldn't find a current price for '{name_or_symbol}'."
    return (
        f"{result['name']}: symbol {result['symbol']}, "
        f"current price {result['price']} {result['currency']}".strip()
    )
