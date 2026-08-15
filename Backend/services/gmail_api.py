import base64
import os
from email.mime.text import MIMEText
from pathlib import Path


SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/spreadsheets",
]


def _get_paths() -> tuple[Path, Path]:
    backend_dir = Path(__file__).resolve().parents[1]
    credentials = (os.getenv("GMAIL_CREDENTIALS_PATH") or "").strip() or str(
        backend_dir / "credentials.json"
    )
    token = (os.getenv("GMAIL_TOKEN_PATH") or "").strip() or str(
        backend_dir / "token.json"
    )
    return Path(credentials), Path(token)


def _require_google_libs():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    return Credentials, Request, build


def get_gmail_service():
    Credentials, Request, build = _require_google_libs()
    credentials_path, token_path = _get_paths()

    if not token_path.exists():
        raise RuntimeError(
            "Gmail is not authenticated. Run Backend/gmail_auth.py first."
        )

    creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            token_path.write_text(creds.to_json(), encoding="utf-8")
        else:
            raise RuntimeError("Gmail token is invalid. Re-run Backend/gmail_auth.py.")

    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def send_email(to: str, subject: str, body: str) -> str:
    to_clean = (to or "").strip()
    subject_clean = (subject or "").strip()
    body_clean = (body or "").strip()
    if not to_clean:
        raise ValueError("Recipient email is required.")
    if not subject_clean:
        raise ValueError("Subject is required.")
    if not body_clean:
        raise ValueError("Email body is required.")

    service = get_gmail_service()
    message = MIMEText(body_clean)
    message["to"] = to_clean
    message["subject"] = subject_clean
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
    service.users().messages().send(userId="me", body={"raw": raw}).execute()
    return f"Email sent to {to_clean}."


def read_latest_emails(count: int = 5) -> list[dict]:
    service = get_gmail_service()
    max_results = max(1, min(int(count or 5), 10))
    results = (
        service.users().messages().list(userId="me", maxResults=max_results).execute()
    )
    messages = results.get("messages", []) or []

    out: list[dict] = []
    for item in messages:
        msg = (
            service.users()
            .messages()
            .get(userId="me", id=item["id"], format="metadata")
            .execute()
        )
        headers = (msg.get("payload") or {}).get("headers") or []
        subject = ""
        sender = ""
        for h in headers:
            name = (h.get("name") or "").lower()
            if name == "subject":
                subject = h.get("value") or ""
            elif name == "from":
                sender = h.get("value") or ""
        out.append({"from": sender.strip(), "subject": subject.strip()})
    return out


def format_latest_emails_summary(items: list[dict]) -> str:
    if not items:
        return "No emails found."
    parts = []
    for i, item in enumerate(items[:5], start=1):
        sender = (item.get("from") or "unknown sender").strip()
        subject = (item.get("subject") or "no subject").strip()
        parts.append(f"{i}. From {sender}. Subject: {subject}.")
    return " ".join(parts)
