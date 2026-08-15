import json
import os
from pathlib import Path
from typing import Any

SHEETS_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def _get_paths() -> tuple[Path, Path]:
    backend_dir = Path(__file__).resolve().parents[1]
    credentials = (os.getenv("GMAIL_CREDENTIALS_PATH") or "").strip() or str(
        backend_dir / "credentials.json"
    )
    token = (os.getenv("GMAIL_TOKEN_PATH") or "").strip() or str(
        backend_dir / "token.json"
    )
    return Path(credentials), Path(token)


def _load_config() -> dict:
    backend_dir = Path(__file__).resolve().parents[1]
    config_path = backend_dir / "linkedin_content.json"
    if not config_path.exists():
        return {}
    raw = config_path.read_text(encoding="utf-8")
    parsed = json.loads(raw)
    return parsed if isinstance(parsed, dict) else {}


def _require_google_libs():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    return Credentials, Request, build


def get_sheets_service():
    Credentials, Request, build = _require_google_libs()
    credentials_path, token_path = _get_paths()

    if not token_path.exists():
        raise RuntimeError(
            "Google is not authenticated. Run Backend/gmail_auth.py first."
        )

    creds = Credentials.from_authorized_user_file(str(token_path), SHEETS_SCOPES)
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            token_path.write_text(creds.to_json(), encoding="utf-8")
        else:
            raise RuntimeError(
                "Google token is invalid or missing Sheets scope. Re-run Backend/gmail_auth.py."
            )

    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def get_sheet_metadata() -> dict:
    config = _load_config()
    sheet_id = (config.get("sheet") or {}).get("id", "").strip()
    if not sheet_id:
        raise RuntimeError(
            "LinkedIn sheet ID not configured. Set it in Backend/linkedin_content.json under sheet.id"
        )
    service = get_sheets_service()
    sheet = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
    return sheet


def append_row(row: list[Any]) -> str:
    config = _load_config()
    sheet_cfg = config.get("sheet") or {}
    sheet_id = (sheet_cfg.get("id") or "").strip()
    tab_name = (sheet_cfg.get("tab_name") or "").strip() or "Content"
    columns = sheet_cfg.get("columns") or []

    if not sheet_id:
        raise RuntimeError(
            "LinkedIn sheet ID not configured. Set it in Backend/linkedin_content.json under sheet.id"
        )

    if len(row) > len(columns):
        raise ValueError(
            f"Row has {len(row)} values but sheet has {len(columns)} columns"
        )

    padded = row + [""] * (len(columns) - len(row))
    range_name = f"{tab_name}!A:{chr(64 + len(columns))}"

    service = get_sheets_service()
    result = (
        service.spreadsheets()
        .values()
        .append(
            spreadsheetId=sheet_id,
            range=range_name,
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body={"values": [padded]},
        )
        .execute()
    )
    updated = result.get("updates", {}).get("updatedRows", 0)
    return f"Added {updated} row(s) to sheet '{tab_name}'."


def create_sheet() -> str:
    config = _load_config()
    sheet_cfg = config.get("sheet") or {}
    sheet_id = (sheet_cfg.get("id") or "").strip()
    tab_name = (sheet_cfg.get("tab_name") or "").strip() or "Content"
    columns = sheet_cfg.get("columns") or []

    service = get_sheets_service()

    if not sheet_id:
        spreadsheet = (
            service.spreadsheets()
            .create(body={"properties": {"title": sheet_cfg.get("name", "LinkedIn Content")}})
            .execute()
        )
        sheet_id = spreadsheet["spreadsheetId"]

        config["sheet"]["id"] = sheet_id
        backend_dir = Path(__file__).resolve().parents[1]
        config_path = backend_dir / "linkedin_content.json"
        config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")

    header_range = f"{tab_name}!A1:{chr(64 + len(columns))}1"
    service.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range=header_range,
        valueInputOption="USER_ENTERED",
        body={"values": [columns]},
    ).execute()

    return f"LinkedIn content sheet created/ready. Sheet ID: {sheet_id}"
