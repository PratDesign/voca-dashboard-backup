import os
import logging
from dotenv import load_dotenv
from google.adk.agents import Agent
from google.adk.tools.mcp_tool import MCPToolset
from google.adk.tools.mcp_tool.mcp_session_manager import SseConnectionParams

# --- Logging setup ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

# --- Load environment variables ---
load_dotenv()

# --- Ensure Credentials for Cloud Run ---
# This ensures ADK can find your service account for Vertex AI calls
sa_path = "/app/service_account.json"
if os.path.exists(sa_path):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = sa_path
    logger.info(f"Credentials set to: {sa_path}")
else:
    logger.warning("service_account.json not found in /app. Relying on default credentials.")

model_name = os.getenv("MODEL")
if not model_name:
    # Fallback to a default if the env var is missing to prevent total crash
    model_name = "gemini-2.0-flash" 
    logger.warning(f"MODEL env var missing. Falling back to {model_name}")

logger.info(f"Loading VocaAi agent with model: {model_name}")

# --- MCP Toolset ---
# Connects to your server.py background process running on localhost:8001
mcp_toolset = MCPToolset(
    connection_params=SseConnectionParams(url="http://127.0.0.1:8001/sse")
)

# --- Agent instruction ---
INSTRUCTION = """
You are VocaAi, a friendly and magical vocabulary tutor for kids.

When a child gives you a word, follow these steps every single time:

STEP 1 — Explain the word
Explain the meaning in simple, fun language using a Harry Potter analogy.
Keep it short, warm, and exciting for a child aged 6-12.

STEP 2 — Log the session (ALWAYS do this)
Call the 'log_to_firestore' tool with these exact arguments:
- topic: the vocabulary word (e.g. "curious")
- kid_explanation: the Harry Potter explanation you just gave
- quiz: a simple fill-in-the-blank sentence using the word
- parent_summary: one sentence for the parent explaining the word and its usage

STEP 3 — Schedule a reminder (ALWAYS do this after logging)
Call the 'schedule_reminder' tool with these exact arguments:
- word: the vocabulary word
- email: "vocaaitest@gmail.com"

After both tools succeed, tell the child their word has been saved and
a practice reminder has been sent to their parent. Keep it fun!
"""

# --- Root agent ---
root_agent = Agent(
    name="voca_tutor",
    model=model_name,
    tools=[mcp_toolset],
    instruction=INSTRUCTION,
)

logger.info("VocaAi root_agent ready.")