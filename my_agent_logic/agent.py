import os
import logging
import datetime
import pytz
from dotenv import load_dotenv
from google.adk.agents import Agent
from google.oauth2 import service_account
from google.cloud import firestore
from googleapiclient.discovery import build
from google.adk.tools import FunctionTool

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

load_dotenv()

sa_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "/app/secrets/service_account.json")
if os.path.exists(sa_path):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = sa_path
    logger.info(f"✅ Credentials verified at: {sa_path}")

model_name = os.getenv("MODEL", "gemini-2.0-flash")

# --- Firestore client ---
db = firestore.Client(project=os.getenv("PROJECT_ID", "harrypottervoca"))

# --- Direct tool functions (no MCP needed) ---
def log_to_firestore(topic: str, kid_explanation: str, quiz: str, parent_summary: str) -> str:
    """Logs the vocabulary session details to Firestore."""
    try:
        db.collection("tutor_sessions").document().set({
            "topic": topic,
            "kid_explanation": kid_explanation,
            "quiz_content": quiz,
            "parent_summary": parent_summary,
            "timestamp": datetime.datetime.now(datetime.timezone.utc),
        })
        return "✅ Firestore Log Success"
    except Exception as e:
        logger.exception(e)
        return f"Firestore Error: {e}"

def schedule_reminder(word: str, email: str = "data.pratyush@gmail.com") -> str:
    """Schedules a practice reminder in Google Calendar."""
    try:
        creds = service_account.Credentials.from_service_account_file(
            sa_path,
            scopes=["https://www.googleapis.com/auth/calendar",
                    "https://www.googleapis.com/auth/calendar.events"]
        )
        service = build("calendar", "v3", credentials=creds)
        ist = pytz.timezone("Asia/Kolkata")
        now_ist = datetime.datetime.now(ist)
        remind_day = (now_ist + datetime.timedelta(days=2)).date()
        existing = service.events().list(
            calendarId=email,
            timeMin=datetime.datetime.combine(remind_day, datetime.time.min).replace(tzinfo=ist).isoformat(),
            timeMax=datetime.datetime.combine(remind_day, datetime.time.max).replace(tzinfo=ist).isoformat(),
            q="VocaAi Practice"
        ).execute()
        offset_mins = len(existing.get("items", [])) * 10
        start_dt = ist.localize(datetime.datetime.combine(
            remind_day, datetime.time(16, offset_mins % 60, 0)
        )) + datetime.timedelta(hours=offset_mins // 60)
        end_dt = start_dt + datetime.timedelta(minutes=15)
        event = {
            "summary": f"VocaAi Practice: {word}",
            "description": "Magical vocabulary review session.",
            "start": {"dateTime": start_dt.isoformat(), "timeZone": "Asia/Kolkata"},
            "end": {"dateTime": end_dt.isoformat(), "timeZone": "Asia/Kolkata"},
        }
        created = service.events().insert(calendarId=email, body=event).execute()
        return f"✅ Reminder set for '{word}' on {remind_day} at {start_dt.strftime('%I:%M %p')} IST"
    except Exception as e:
        logger.exception(e)
        return f"Calendar Error: {e}"

def send_weekly_report() -> str:
    """Triggers the Gmail push for the weekly vocabulary summary."""
    try:
        from final_gmail_push import main as push_gmail
        push_gmail()
        return "✅ Weekly Report Spell Cast! Check your Gmail inbox."
    except Exception as e:
        return f"❌ Gmail Failed: {e}"

INSTRUCTION = """
You are the Wizarding Tutor for VocaAi. Your goal is to help kids master vocabulary.

WHEN A CHILD INPUTS A WORD:

1. LOGIC BRANCH:
   - IF WORD IS NEW:
     - STEP 1: Explain the word using a fun Harry Potter analogy.
     - STEP 2: Call 'log_to_firestore' with topic, kid_explanation, quiz, and parent_summary.
     - STEP 3: Call 'schedule_reminder' for the parent's calendar.
   
   - IF WORD WAS ALREADY LEARNED:
     - Say: "Galloping Gargoyles! You've studied this before. Let's see if you remember it!"
     - STEP 1: Present a Harry Potter-themed Multiple Choice Question (MCQ).
     - STEP 2: Award House Points for correct answers, give a Magical Hint for wrong ones.

2. WEEKLY REPORTING:
   - If parent asks for a summary or Weekly Report, call 'send_weekly_report'.

Always keep the tone magical, encouraging, and focused on the Wizarding World!
"""

root_agent = Agent(
    name="voca_tutor",
    model=model_name,
    tools=[log_to_firestore, schedule_reminder, send_weekly_report],
    instruction=INSTRUCTION,
)

logger.info("🪄 VocaAi agent ready.")
