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
from datetime import datetime

import gspread
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials
from langchain_core.tools import tool

load_dotenv()  # no-op if already loaded elsewhere or no .env file exists

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


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
