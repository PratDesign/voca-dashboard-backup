import os
import datetime
import logging
import pytz
from google.oauth2 import service_account
from google.cloud import firestore
from googleapiclient.discovery import build
from mcp.server.fastmcp import FastMCP

# --- Logging setup ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

# --- Constants ---
# Updated to match your Cloud Build /app/ mount point
SERVICE_ACCOUNT_FILE = "/app/secrets/service_account.json"
GMAIL_TOKEN_FILE = "/app/secrets/token/token.json"

CALENDAR_SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.events",
]
TIMEZONE = "Asia/Kolkata"
CALENDAR_ID = "data.pratyush@gmail.com"

# --- Firestore client ---
db = firestore.Client(project="vocaai-491503")

# --- FastMCP server ---
mcp = FastMCP("VocaAi_Tools", host="0.0.0.0", port=8001)

@mcp.tool()
def log_to_firestore(topic: str, kid_explanation: str, quiz: str, parent_summary: str) -> str:
    """Logs the vocabulary session details to Firestore."""
    try:
        doc_ref = db.collection("tutor_sessions").document()
        doc_ref.set({
            "topic": topic,
            "kid_explanation": kid_explanation,
            "quiz_content": quiz,
            "parent_summary": parent_summary,
            "timestamp": datetime.datetime.now(datetime.timezone.utc),
        })
        logger.info(f"Firestore: logged session for topic='{topic}'")
        return "✅ Firestore Log Success"
    except Exception as e:
        logger.exception(f"Firestore error for topic='{topic}': {e}")
        return f"Firestore Error: {e}"

@mcp.tool()
def schedule_reminder(word: str, email: str = CALENDAR_ID) -> str:
    """Schedules a practice reminder in Google Calendar."""
    try:
        creds = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE,
            scopes=CALENDAR_SCOPES
        )
        service = build("calendar", "v3", credentials=creds)

        ist = pytz.timezone(TIMEZONE)
        now_ist = datetime.datetime.now(ist)
        remind_day = (now_ist + datetime.timedelta(days=2)).date()

        existing = service.events().list(
            calendarId=CALENDAR_ID,
            timeMin=datetime.datetime.combine(remind_day, datetime.time.min).replace(tzinfo=ist).isoformat(),
            timeMax=datetime.datetime.combine(remind_day, datetime.time.max).replace(tzinfo=ist).isoformat(),
            q="VocaAi Practice"
        ).execute()
        
        offset_mins = len(existing.get("items", [])) * 10
        start_dt = ist.localize(datetime.datetime.combine(
            remind_day,
            datetime.time(16, offset_mins % 60, 0)
        )) + datetime.timedelta(hours=offset_mins // 60)
        end_dt = start_dt + datetime.timedelta(minutes=15)

        event = {
            "summary": f"VocaAi Practice: {word}",
            "description": "Magical vocabulary review session.",
            "start": {"dateTime": start_dt.isoformat(), "timeZone": TIMEZONE},
            "end": {"dateTime": end_dt.isoformat(), "timeZone": TIMEZONE},
        }
        
        created = service.events().insert(calendarId=CALENDAR_ID, body=event).execute()
        logger.info(f"Calendar event created: {created.get('htmlLink')}")
        return f"✅ Reminder set for '{word}' on {remind_day} at {start_dt.strftime('%I:%M %p')} IST"
    except Exception as e:
        logger.exception(f"Calendar error for word='{word}': {e}")
        return f"Calendar Error: {e}"

@mcp.tool()
def send_weekly_report() -> str:
    """Triggers the Gmail push for the weekly vocabulary summary."""
    try:
        # This imports your specialized gmail push logic
        from final_gmail_push import main as push_gmail
        push_gmail()
        return "✅ Weekly Report Spell Cast! Check your Gmail inbox."
    except Exception as e:
        logger.error(f"Gmail Error: {e}")
        return f"❌ Gmail Failed: {e}"

# --- Entry point ---
if __name__ == "__main__":
    port = 8001
    logger.info(f"Starting MCP server on port {port}")
    # Using sse transport as required for the ADK Runner to connect over HTTP/localhost
    mcp.run(transport="sse")