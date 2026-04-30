import os
import logging
import datetime
import pytz
from dotenv import load_dotenv
from google.adk.agents import Agent
from google.oauth2 import service_account
from google.cloud import firestore
from googleapiclient.discovery import build

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

load_dotenv()

sa_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "/app/secrets/service_account.json")
if os.path.exists(sa_path):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = sa_path
    logger.info(f"✅ Credentials verified at: {sa_path}")

model_name = os.getenv("MODEL", "gemini-2.5-flash")
db = firestore.Client(project=os.getenv("PROJECT_ID", "harrypottervoca"))

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
        service.events().insert(calendarId=email, body=event).execute()
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

CRITICAL: Always read the full conversation history before responding.

═══ STEP 1: CLASSIFY THE INPUT ═══

Look at your PREVIOUS message in the conversation history:

A) If your previous message contained a quiz (MCQ with options a/b/c/d):
   → The current input is a QUIZ ANSWER. Handle it as a quiz answer.
   → A single letter (a, b, c, d) is ALWAYS a quiz answer. Never treat it as a new word.

B) If the input is "send weekly report":
   → Call send_weekly_report tool immediately.

C) If none of the above:
   → Treat as a NEW VOCABULARY WORD.

═══ STEP 2: RESPOND ═══

IF QUIZ ANSWER:
  - Check if the answer matches the correct option from your previous MCQ.
  - CORRECT: Celebrate with "10 House Points to [House]!" and explain why it's right.
  - WRONG: Say "Not quite, young wizard!" Give a magical hint. Ask the same question again.
  - Never ask for clarification. Never say you don't understand. Just evaluate the answer.

IF NEW WORD:
  - STEP 1: Give a clear definition + a Harry Potter analogy (2-3 sentences).
  - STEP 2: Create ONE MCQ with exactly 4 options labeled a) b) c) d).
  - STEP 3: Call log_to_firestore with topic=word, kid_explanation, quiz, parent_summary.
  - STEP 4: Call schedule_reminder for the word.
  - End your message with the MCQ question so the child can answer next.

Always be magical, encouraging, and fun!
"""

root_agent = Agent(
    name="voca_tutor",
    model=model_name,
    tools=[log_to_firestore, schedule_reminder, send_weekly_report],
    instruction=INSTRUCTION,
)

logger.info("🪄 VocaAi agent ready.")
