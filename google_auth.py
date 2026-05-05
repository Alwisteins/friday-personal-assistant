import os
from datetime import datetime, timedelta, timezone

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = ["https://www.googleapis.com/auth/calendar", "https://mail.google.com/"]
BASE_DIR = os.path.dirname(__file__)
CREDENTIALS_PATH = os.path.join(BASE_DIR, "credentials.json")
TOKEN_PATH = os.path.join(BASE_DIR, "token.json")


def _load_credentials():
    if not os.path.exists(CREDENTIALS_PATH):
        raise FileNotFoundError("credentials.json belum ditemukan")

    creds = None
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_PATH, "w", encoding="utf-8") as token:
            token.write(creds.to_json())

    return creds


def ensure_google_login():
    try:
        _load_credentials()
        return {
            "status": "ok",
            "summary": "Google OAuth sudah tersimpan atau berhasil dilogin ulang",
        }
    except FileNotFoundError as error:
        return {
            "status": "unavailable",
            "summary": str(error),
        }
    except Exception as error:
        return {
            "status": "unavailable",
            "summary": f"gagal login Google: {error}",
        }


def get_calendar_service():
    creds = _load_credentials()
    return build("calendar", "v3", credentials=creds)


def get_gmail_service():
    creds = _load_credentials()
    return build("gmail", "v1", credentials=creds)


def fetch_upcoming_events(max_results=5):
    if not os.path.exists(CREDENTIALS_PATH):
        return {
            "status": "unavailable",
            "summary": "credentials.json belum ditemukan",
            "events": [],
        }

    try:
        service = get_calendar_service()
        now = datetime.now(timezone.utc)
        time_max = now + timedelta(days=1)
        result = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=now.isoformat(),
                timeMax=time_max.isoformat(),
                maxResults=max_results,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        items = result.get("items", [])
        events = []
        for item in items:
            start_raw = item.get("start", {}).get("dateTime") or item.get("start", {}).get("date")
            summary = item.get("summary") or "(Untitled event)"
            events.append(
                {
                    "start": start_raw,
                    "summary": summary,
                    "is_all_day": "date" in item.get("start", {}),
                }
            )

        if not events:
            return {
                "status": "ok",
                "summary": "tidak ada agenda dalam 24 jam ke depan",
                "events": [],
            }

        return {
            "status": "ok",
            "summary": f"{len(events)} agenda ditemukan dalam 24 jam ke depan",
            "events": events,
        }
    except HttpError as error:
        return {
            "status": "unavailable",
            "summary": f"Google Calendar API error: {error}",
            "events": [],
        }
    except Exception as error:
        return {
            "status": "unavailable",
            "summary": f"gagal mengambil agenda kalender: {error}",
            "events": [],
        }


def _extract_email_headers(payload):
    headers = {}
    for header in payload.get("headers", []):
        name = header.get("name")
        value = header.get("value")
        if name and value is not None:
            headers[name.lower()] = value
    return headers


def fetch_recent_emails(max_results=5, query="in:inbox newer_than:1d"):
    if not os.path.exists(CREDENTIALS_PATH):
        return {
            "status": "unavailable",
            "summary": "credentials.json belum ditemukan",
            "emails": [],
        }

    try:
        service = get_gmail_service()
        result = (
            service.users()
            .messages()
            .list(
                userId="me",
                maxResults=max_results,
                q=query,
            )
            .execute()
        )
        items = result.get("messages", [])
        emails = []

        for item in items:
            message = (
                service.users()
                .messages()
                .get(
                    userId="me",
                    id=item["id"],
                    format="metadata",
                    metadataHeaders=["From", "Subject", "Date"],
                )
                .execute()
            )

            payload = message.get("payload", {})
            headers = _extract_email_headers(payload)
            snippet = (message.get("snippet") or "").strip()

            emails.append(
                {
                    "id": message.get("id", item["id"]),
                    "thread_id": message.get("threadId", ""),
                    "from": headers.get("from", "(Unknown sender)"),
                    "subject": headers.get("subject", "(No subject)"),
                    "date": headers.get("date", ""),
                    "snippet": snippet,
                }
            )

        if not emails:
            return {
                "status": "ok",
                "summary": "tidak ada email baru di inbox",
                "emails": [],
            }

        return {
            "status": "ok",
            "summary": f"{len(emails)} email terbaru ditemukan",
            "emails": emails,
        }
    except HttpError as error:
        return {
            "status": "unavailable",
            "summary": f"Gmail API error: {error}",
            "emails": [],
        }
    except Exception as error:
        return {
            "status": "unavailable",
            "summary": f"gagal mengambil email: {error}",
            "emails": [],
        }
