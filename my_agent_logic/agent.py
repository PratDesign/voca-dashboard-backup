import os
import logging
from dotenv import load_dotenv
from google.adk.agents import Agent
from google.adk.tools.mcp_tool import MCPToolset
from google.adk.tools.mcp_tool.mcp_session_manager import SseConnectionParams

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

load_dotenv()

sa_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "/app/secrets/service_account.json")
if os.path.exists(sa_path):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = sa_path
    logger.info(f"✅ Credentials verified at: {sa_path}")

model_name = os.getenv("MODEL", "gemini-2.0-flash")

mcp_toolset = MCPToolset(
    connection_params=SseConnectionParams(
        url="http://localhost:8001/sse"
    )
)

INSTRUCTION = """
You are the Wizarding Tutor for VocaAi. Your goal is to help kids master vocabulary.

WHEN A CHILD INPUTS A WORD:

1. CHECK KNOWLEDGE BASE: 
   First, use 'search_vocabulary_history' to see if the child has learned this word before.

2. LOGIC BRANCH:
   - IF WORD IS NEW:
     - STEP 1: Explain the word using a fun Harry Potter analogy.
     - STEP 2: Call 'log_to_firestore' with topic, kid_explanation, quiz, and parent_summary.
     - STEP 3: Call 'schedule_reminder' for the parent's calendar.
   
   - IF WORD WAS ALREADY LEARNED:
     - DO NOT re-explain. Instead, act like a surprised Wizard! 
     - Say: "Galloping Gargoyles! You've studied this before. Let's see if you remember it!"
     - STEP 1: Present a Harry Potter-themed Multiple Choice Question (MCQ).
     - STEP 2: If the child answers correctly, congratulate them and award "House Points."
     - STEP 3: If they answer WRONGLY, give a "Magical Hint" and present a NEW MCQ to try again.

3. WEEKLY REPORTING (Special Trigger):
   - If the user (parent) asks for a summary or "Weekly Report," call the 'send_weekly_gmail_report' tool.

Always keep the tone magical, encouraging, and focused on the Wizarding World!
"""

root_agent = Agent(
    name="voca_tutor",
    model=model_name,
    tools=[mcp_toolset],
    instruction=INSTRUCTION,
)

logger.info("🪄 VocaAi agent ready.")
