"""
Google Sheets integration for the agent: a LangChain tool that appends a row
to a configured Google Sheet using a service account. Service accounts work
headlessly (no browser login flow), which is what makes this deployable.

Setup (see README.md for the full walkthrough):
1. Create a Google Cloud service account, enable the Sheets API, download
   its JSON key.
2. Share the target spreadsheet with the service account's email
   (found in the JSON key as "client_email"), as an Editor.
3. Provide the sheet ID and the JSON key content to `make_sheet_logging_tool`
   (or via the GOOGLE_SHEET_ID / GOOGLE_SERVICE_ACCOUNT_JSON env vars).
"""

import json
import os
import re
from datetime import datetime

import gspread
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials
from langchain_core.tools import tool

from stock_lookup import find_stock

load_dotenv()  # no-op if already loaded elsewhere or no .env file exists

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

STOCK_RECOMMENDATION_HEADERS = [
    "Timestamp",
    "Article URL",
    "Article Title",
    "Stock/Company",
    "Ticker/Symbol",
    "Recommendation",
    "Target Price",
    "Current Price",
    "upside_percent",
    "Source/Brokerage",
    "Rationale",
]

_NUMBER_RE = re.compile(r"[-+]?\d*\.?\d+")


def _parse_float(value: str) -> float | None:
    """Pulls a plain float out of a price string like '₹5,481' or 'Rs 950'."""
    if not value:
        return None
    match = _NUMBER_RE.search(value.replace(",", ""))
    if not match:
        return None
    try:
        return float(match.group())
    except ValueError:
        return None


def _resolve_credentials_source(explicit: str | dict | None):
    """Explicit value wins; otherwise fall back to env vars for local/CLI use."""
    if explicit:
        return explicit

    env_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if env_json:
        return env_json

    env_file = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE")
    if env_file and os.path.exists(env_file):
        with open(env_file, encoding="utf-8") as f:
            return f.read()

    return None


def _authorize(credentials_source: str | dict):
    info = (
        json.loads(credentials_source)
        if isinstance(credentials_source, str)
        else credentials_source
    )
    creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    return gspread.authorize(creds)


def _get_or_create_worksheet(spreadsheet, name: str, headers: list[str]):
    """
    Returns (worksheet, actual_header_row), creating the worksheet (with
    `headers`) if it doesn't exist yet. If the worksheet already exists,
    any header from `headers` that isn't already present is appended as a
    new trailing column - this keeps sheets created before a new column was
    added (e.g. upside_percent) working correctly instead of silently
    shifting existing columns out of alignment. Rows should always be built
    by matching values to the returned header order, never to `headers`'
    order, since the two can now differ.
    """
    try:
        worksheet = spreadsheet.worksheet(name)
    except gspread.exceptions.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(name, rows=1000, cols=len(headers))
        worksheet.append_row(headers)
        return worksheet, list(headers)

    existing_headers = worksheet.row_values(1)
    if not existing_headers:
        worksheet.append_row(headers)
        return worksheet, list(headers)

    missing = [h for h in headers if h not in existing_headers]
    if missing:
        start_col = len(existing_headers) + 1
        worksheet.update(
            f"{gspread.utils.rowcol_to_a1(1, start_col)}:"
            f"{gspread.utils.rowcol_to_a1(1, start_col + len(missing) - 1)}",
            [missing],
        )
        existing_headers = existing_headers + missing
    return worksheet, existing_headers


def make_stock_recommendation_tool(
    sheet_id: str | None = None,
    service_account_json: str | dict | None = None,
    worksheet_name: str = "Stock Recommendations",
):
    """
    Returns a LangChain tool that logs one stock recommendation (extracted
    from a news article) as a structured row in a dedicated worksheet tab,
    with proper column headers created automatically the first time.
    """

    @tool
    def add_stock_recommendation(
        stock_name: str,
        recommendation: str,
        article_url: str = "",
        article_title: str = "",
        ticker: str = "",
        target_price: str = "",
        current_price: str = "",
        source: str = "",
        rationale: str = "",
    ) -> str:
        """
        Logs one stock recommendation to a "Stock Recommendations" tab in
        the user's Google Sheet, with proper column headers. Call this once
        per stock the article gives an explicit call on (buy/sell/hold/
        accumulate/reduce/add) - do NOT call it if the article doesn't
        contain an actual stock recommendation. If ticker and/or
        current_price are left blank, they're looked up automatically -
        don't call another tool for that first. An upside_percent column is
        computed automatically from target_price and current_price - don't
        pass it yourself.

        Args:
            stock_name: Company or stock name, e.g. "Tata Motors".
            recommendation: The call, e.g. "Buy", "Sell", "Hold", "Accumulate", "Reduce".
            article_url: The article's URL.
            article_title: The article's headline.
            ticker: Stock ticker/symbol, if already known - otherwise leave blank to auto-look-up.
            target_price: Analyst's target price as a plain number, if mentioned - no currency symbol or comma (e.g. "950", not "₹950" or "9,50,000").
            current_price: The stock's current market price as a plain number - leave blank to auto-look-up.
            source: The brokerage or analyst who gave the call, if named.
            rationale: A one or two sentence summary of why.
        """
        resolved_sheet_id = sheet_id or os.environ.get("GOOGLE_SHEET_ID")
        resolved_creds = _resolve_credentials_source(service_account_json)

        if not resolved_sheet_id:
            return (
                "I can't log that yet — no Google Sheet is configured. "
                "Set a sheet ID/URL first."
            )
        if not resolved_creds:
            return (
                "I can't log that yet — no Google service account "
                "credentials are configured."
            )

        if not ticker or not current_price:
            looked_up = find_stock(ticker or stock_name)
            if looked_up:
                ticker = ticker or looked_up["symbol"]
                if not current_price:
                    current_price = looked_up["price"]

        target_price_value = _parse_float(str(target_price))
        current_price_value = _parse_float(str(current_price))

        upside_percent = ""
        if target_price_value is not None and current_price_value:
            upside_percent = round(
                (target_price_value - current_price_value) / current_price_value * 100, 2
            )

        try:
            client = _authorize(resolved_creds)
            spreadsheet = client.open_by_key(resolved_sheet_id)
            worksheet, actual_headers = _get_or_create_worksheet(
                spreadsheet, worksheet_name, STOCK_RECOMMENDATION_HEADERS
            )

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            values_by_header = {
                "Timestamp": timestamp,
                "Article URL": article_url,
                "Article Title": article_title,
                "Stock/Company": stock_name,
                "Ticker/Symbol": ticker,
                "Recommendation": recommendation,
                "Target Price": target_price_value if target_price_value is not None else "",
                "Current Price": current_price_value if current_price_value is not None else "",
                "upside_percent": upside_percent,
                "Source/Brokerage": source,
                "Rationale": rationale,
            }
            # Build the row in whatever order the sheet's actual header row is
            # in - never assume it matches STOCK_RECOMMENDATION_HEADERS'
            # order, since existing sheets may have their columns arranged
            # differently (e.g. a column added later ends up at the end).
            row = [values_by_header.get(header, "") for header in actual_headers]
            worksheet.append_row(row)
            return f"Logged to '{worksheet_name}': {stock_name} — {recommendation}"
        except json.JSONDecodeError:
            return "I can't log that — the service account credentials aren't valid JSON."
        except gspread.exceptions.SpreadsheetNotFound:
            return (
                "I can't log that — the sheet wasn't found. Check the sheet "
                "ID and make sure it's shared with the service account's "
                "email (as an Editor)."
            )
        except gspread.exceptions.APIError as e:
            return f"Google Sheets API rejected the request: {e}"
        except Exception as e:
            return f"Failed to add the row to the sheet: {e}"

    return add_stock_recommendation


def make_sheet_logging_tool(
    sheet_id: str | None = None,
    service_account_json: str | dict | None = None,
    worksheet_name: str | None = None,
):
    """
    Returns a LangChain tool bound to one Google Sheet + credentials. Building
    a fresh tool per request (rather than reading global state at call time)
    keeps this safe if the app ever serves more than one user/session.
    """

    @tool
    def add_sheet_entry(values: list[str]) -> str:
        """
        Append a new row to the user's Google Sheet log. Use this ONLY when
        the user explicitly asks to log, save, record, or add an entry to
        their sheet. Pass each cell's text as a separate item, in the order
        it should appear, e.g. ["Groceries", "Milk and eggs", "$12.50"]. A
        timestamp is added automatically as the first column - don't include
        your own.
        """
        resolved_sheet_id = sheet_id or os.environ.get("GOOGLE_SHEET_ID")
        resolved_creds = _resolve_credentials_source(service_account_json)

        if not resolved_sheet_id:
            return (
                "I can't log that yet — no Google Sheet is configured. "
                "Set a sheet ID/URL first."
            )
        if not resolved_creds:
            return (
                "I can't log that yet — no Google service account "
                "credentials are configured."
            )

        try:
            client = _authorize(resolved_creds)
            spreadsheet = client.open_by_key(resolved_sheet_id)
            worksheet = (
                spreadsheet.worksheet(worksheet_name)
                if worksheet_name
                else spreadsheet.sheet1
            )
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            row = [timestamp, *values]
            worksheet.append_row(row)
            return f"Added to the sheet: {row}"
        except json.JSONDecodeError:
            return "I can't log that — the service account credentials aren't valid JSON."
        except gspread.exceptions.SpreadsheetNotFound:
            return (
                "I can't log that — the sheet wasn't found. Check the sheet "
                "ID and make sure it's shared with the service account's "
                "email (as an Editor)."
            )
        except gspread.exceptions.APIError as e:
            return f"Google Sheets API rejected the request: {e}"
        except Exception as e:
            return f"Failed to add the row to the sheet: {e}"

    return add_sheet_entry
