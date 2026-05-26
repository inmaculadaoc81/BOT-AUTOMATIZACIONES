import asyncio
import base64
import json
import logging
from datetime import datetime, timedelta

from config import settings

logger = logging.getLogger(__name__)

_service = None


def _init_service():
    global _service
    if _service is not None:
        return _service

    if not settings.GOOGLE_SERVICE_ACCOUNT_JSON:
        logger.info("GOOGLE_SERVICE_ACCOUNT_JSON not set — calendar disabled")
        return None

    try:
        from googleapiclient.discovery import build
        from google.oauth2 import service_account

        raw = settings.GOOGLE_SERVICE_ACCOUNT_JSON.strip()
        try:
            decoded = base64.b64decode(raw).decode("utf-8")
        except Exception:
            decoded = raw

        creds_info = json.loads(decoded)
        credentials = service_account.Credentials.from_service_account_info(
            creds_info,
            scopes=["https://www.googleapis.com/auth/calendar"],
        )
        _service = build("calendar", "v3", credentials=credentials)
        logger.info("Google Calendar service initialized")
        return _service
    except Exception as e:
        logger.error(f"Google Calendar init failed: {e}", exc_info=True)
        return None


def _create_event_sync(
    summary: str,
    description: str,
    start_iso: str,
    duration_minutes: int,
    attendee_email: str | None,
) -> dict | None:
    service = _init_service()
    if not service:
        return None

    try:
        tz = settings.BUSINESS_TIMEZONE
        start_dt = datetime.fromisoformat(start_iso)
        end_dt = start_dt + timedelta(minutes=duration_minutes)

        event_body: dict = {
            "summary": summary,
            "description": description,
            "start": {"dateTime": start_dt.isoformat(), "timeZone": tz},
            "end": {"dateTime": end_dt.isoformat(), "timeZone": tz},
            "conferenceData": {
                "createRequest": {
                    "requestId": f"meet-{int(start_dt.timestamp())}",
                    "conferenceSolutionKey": {"type": "hangoutsMeet"},
                }
            },
        }

        if attendee_email:
            event_body["attendees"] = [{"email": attendee_email}]

        calendar_id = settings.GOOGLE_CALENDAR_ID or "primary"
        event = service.events().insert(
            calendarId=calendar_id,
            body=event_body,
            conferenceDataVersion=1,
            sendUpdates="all" if attendee_email else "none",
        ).execute()

        return {
            "event_id": event.get("id"),
            "html_link": event.get("htmlLink", ""),
            "meet_link": event.get("hangoutLink", ""),
        }
    except Exception as e:
        logger.error(f"Google Calendar event creation failed: {e}", exc_info=True)
        return None


async def create_meeting(
    summary: str,
    description: str,
    start_iso: str,
    duration_minutes: int | None = None,
    attendee_email: str | None = None,
) -> dict | None:
    if duration_minutes is None:
        duration_minutes = settings.MEETING_DURATION_MINUTES
    return await asyncio.to_thread(
        _create_event_sync, summary, description, start_iso, duration_minutes, attendee_email
    )
