import os
from datetime import datetime, timedelta, timezone

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]
BASE_DIR = os.path.dirname(__file__)
CREDENTIALS_PATH = os.path.join(BASE_DIR, "credentials.json")
TOKEN_PATH = os.path.join(BASE_DIR, "token.json")


def _load_credentials():
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


def get_calendar_service():
    creds = _load_credentials()
    return build('calendar', 'v3', credentials=creds)


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
