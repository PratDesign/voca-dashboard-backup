import streamlit as st
from google.cloud import firestore
import pandas as pd
import plotly.express as px
import subprocess
import time
import os
import asyncio
import uuid
import threading
import socket
from datetime import date, timedelta
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types as genai_types
from dotenv import load_dotenv

# ── CONFIG & THEME ─────────────────────────────────────────────────────────────
load_dotenv()
st.set_page_config(page_title="VocaAi Wizarding Hub", page_icon="🧙‍♂️", layout="wide")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700&family=Source+Sans+Pro:wght@400;600&display=swap');

    .stApp {
        background-color: #0e1117;
        background-image: radial-gradient(circle at 2px 2px, #1d2129 1px, transparent 0);
        background-size: 40px 40px;
    }
    h1, h2, h3 {
        font-family: 'Playfair Display', serif !important;
        color: #FFD700 !important;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 24px;
        background-color: transparent;
    }
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        background-color: #1a1c23;
        border-radius: 8px 8px 0px 0px;
        color: #ffffff;
        padding: 0 20px;
    }
    .stTabs [aria-selected="true"] {
        background-color: #740001 !important;
        border-bottom: 3px solid #FFD700 !important;
    }
    [data-testid="stMetricValue"] { color: #FFD700 !important; }
    [data-testid="stMetricLabel"] { color: #aaaaaa !important; }
    [data-testid="stMetricDelta"] { font-size: 12px !important; }
    .stChatMessage {
        background-color: #1a1c23 !important;
        border: 1px solid #3e4149;
        border-radius: 15px;
    }
    div[data-testid="stDataFrame"] {
        border: 1px solid #3e4149 !important;
        border-radius: 8px;
    }
    .stSelectbox > div, .stTextInput > div > div {
        background-color: #1a1c23 !important;
        border-color: #3e4149 !important;
        color: #ffffff !important;
    }
    </style>
""", unsafe_allow_html=True)

# ── FIRESTORE ──────────────────────────────────────────────────────────────────
PROJECT_ID = os.getenv("PROJECT_ID", "vocaai-491503")
db = firestore.Client(project=PROJECT_ID)

# ── DEDICATED ASYNC EVENT LOOP ─────────────────────────────────────────────────
# A single persistent loop in a background thread. Avoids asyncio.run()
# conflicts with Streamlit's own loop and keeps the MCP session alive.
_loop: asyncio.AbstractEventLoop = asyncio.new_event_loop()

def _start_loop(loop: asyncio.AbstractEventLoop) -> None:
    asyncio.set_event_loop(loop)
    loop.run_forever()

_loop_thread = threading.Thread(target=_start_loop, args=(_loop,), daemon=True)
_loop_thread.start()


def run_async(coro) -> object:
    """Submit a coroutine to the persistent background loop and block until done."""
    future = asyncio.run_coroutine_threadsafe(coro, _loop)
    return future.result(timeout=300)


# ── MCP SERVER ─────────────────────────────────────────────────────────────────
def start_mcp_server() -> None:
    """Start MCP server using absolute paths to avoid Cloud Run directory confusion."""
    # In your Docker container, this will resolve to /app
    abs_path = os.path.abspath(os.path.dirname(__file__))
    server_path = os.path.join(abs_path, "server.py")
    
    env = {**os.environ, "PYTHONPATH": abs_path, "PORT": "8001"}
    
    # We remove devnull here so if it fails, the error appears in Cloud Run Logs
    subprocess.Popen(
        ["python3", server_path],
        cwd=abs_path,
        env=env
    )
    
    # Increase to 30 seconds (range 60) because Cloud Run startup can be slow
    for _ in range(60):  
        try:
            with socket.create_connection(("localhost", 8001), timeout=0.5):
                return
        except (ConnectionRefusedError, OSError):
            time.sleep(0.5)
            
    raise RuntimeError(f"MCP server failed to start at {server_path} within 30 seconds")
# Run exactly once per browser session
if "mcp_started" not in st.session_state:
    pass  # MCP already running via start.sh
    st.session_state.mcp_started = True


# ── ADK RUNNER ────────────────────────────────────────────────────────────────
_runner_instance = None

def get_voca_runner() -> Runner:
    """Module-level singleton — no Streamlit context needed."""
    global _runner_instance
    if _runner_instance is None:
        from my_agent_logic.agent import root_agent
        _runner_instance = Runner(
            agent=root_agent,
            app_name="voca_tutor",
            session_service=InMemorySessionService(),
        )
    return _runner_instance


async def ask_voca(word: str, session_id: str) -> str:
    runner = get_voca_runner()
    try:
        await runner.session_service.create_session(
            app_name="voca_tutor",
            user_id="student",
            session_id=session_id,
        )
    except Exception:
        pass  # Session may already exist

    full_text: list = []
    msg_content = genai_types.Content(
        role="user", parts=[genai_types.Part(text=word)]
    )

    async for event in runner.run_async(
        user_id="student",
        session_id=session_id,
        new_message=msg_content,
    ):
        if event.content and event.content.parts:
            for part in event.content.parts:
                if hasattr(part, "text") and part.text:
                    full_text.append(part.text.strip())

    return "\n\n".join(full_text) if full_text else "The spell fizzled... try again!"


# ── HELPERS ───────────────────────────────────────────────────────────────────
def compute_streak(study_dates: list) -> int:
    """Return the number of consecutive days (including today) with activity."""
    if not study_dates:
        return 0
    sorted_days = sorted(set(study_dates), reverse=True)
    streak = 0
    check = date.today()
    for d in sorted_days:
        if d == check or d == check - timedelta(days=1):
            streak += 1
            check = d
        else:
            break
    return streak


def apply_chart_theme(fig, title: str):
    """Apply consistent dark-theme styling to a Plotly figure."""
    fig.update_layout(
        title=dict(text=title, font=dict(size=13, color="#aaaaaa")),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#888888"),
        margin=dict(l=0, r=0, t=36, b=0),
        xaxis=dict(showgrid=False, zeroline=False),
        yaxis=dict(gridcolor="rgba(255,255,255,0.06)", zeroline=False),
    )
    return fig


# ── SESSION STATE DEFAULTS ────────────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = []
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

# ── PAGE TITLE ────────────────────────────────────────────────────────────────
st.title("🧙‍♂️ VocaAi: The Wizarding Academy")

tab1, tab2 = st.tabs(["✨ Student Portal", "📈 Parent Dashboard"])

# ── TAB 1: STUDENT PORTAL ─────────────────────────────────────────────────────
with tab1:
    st.subheader("Vocabulary Training Room")

    # Chat container — all messages render here, above the input
    chat_container = st.container()
    with chat_container:
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

    if word := st.chat_input("Enter a vocabulary word (or answer a quiz!)..."):
        st.session_state.messages.append({"role": "user", "content": word})

        # If a quiz is active, inject context so agent cannot hallucinate
        if st.session_state.get("quiz_active") and word.strip().lower() in ["a","b","c","d"]:
            injected = (
                f"The student answered '{word.strip().lower()}'. "
                f"The word being tested is '{st.session_state.quiz_word}'. "
                f"The correct answer is '{st.session_state.quiz_answer}'. "
                f"Evaluate if the student is correct or wrong based only on this word."
            )
            prompt = injected
        else:
            prompt = word
            st.session_state.quiz_active = False

        with chat_container:
            with st.chat_message("user"):
                st.markdown(word)
            with st.chat_message("assistant"):
                with st.spinner("🔮 Consulting the Sorting Hat..."):
                    answer = run_async(ask_voca(prompt, st.session_state.session_id))
                st.markdown(answer)

        # Track quiz state simply
        if any(emoji in answer for emoji in ["🅐", "🅑", "🅒", "🅓"]):
            st.session_state.quiz_active = True
        else:
            st.session_state.quiz_active = False

        st.session_state.messages.append({"role": "assistant", "content": answer})
