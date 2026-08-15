from dotenv import load_dotenv

from services.gmail_api import SCOPES, _get_paths


def main() -> None:
    load_dotenv()
    credentials_path, token_path = _get_paths()
    if not credentials_path.exists():
        raise SystemExit(f"credentials.json not found at: {credentials_path}")

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "Missing Gmail dependencies. Run: ./ .venv/bin/pip install -r requirements.txt (from Backend/)"
        ) from exc

    flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), SCOPES)
    creds = flow.run_local_server(port=8080)

    token_path.write_text(creds.to_json(), encoding="utf-8")
    print(f"Saved token to: {token_path}")


if __name__ == "__main__":
    main()
