import streamlit as st
from google.cloud import firestore
import pandas as pd
import plotly.express as px
import subprocess
import time
import os
import asyncio
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types as genai_types
from dotenv import load_dotenv

# --- CONFIG & AUTH ---
# Load .env file if it exists (for local testing and Cloud Run safety)
load_dotenv()

PROJECT_ID = os.getenv("PROJECT_ID", "vocaai-491503")

# Set the path to the service account key
# This matches the mount path in your Cloud Run deployment
sa_path = "/secrets/service_account.json"
if os.path.exists(sa_path):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = sa_path

# Initialize Firestore
db = firestore.Client(project=PROJECT_ID)

st.set_page_config(page_title="VocaAi Hub", page_icon="🧙‍♂️", layout="wide")

@st.cache_resource
def start_mcp_server():
    """Start only the MCP server as a background process."""
    abs_path = os.path.abspath(os.path.dirname(__file__))
    # Ensure current dir and agent logic are in the PYTHONPATH for the subprocess
    env = {**os.environ, "PYTHONPATH": abs_path}
    
    with open(os.devnull, 'w') as devnull:
        subprocess.Popen(
            ["python3", "server.py"],
            cwd=abs_path,
            stdout=devnull,
            stderr=devnull,
            env={**env, "PORT": "8001"}
        )
    time.sleep(4)  # wait for MCP server to be ready
    return True

@st.cache_resource
def get_runner():
    """Create the ADK runner once, reuse across all requests."""
    # Ensure the subfolder logic is importable
    from my_agent_logic.agent import root_agent
    session_service = InMemorySessionService()
    runner = Runner(
        agent=root_agent,
        app_name="voca_tutor",
        session_service=session_service,
    )
    return runner, session_service

def run_agent(word: str, session_id: str) -> str:
    """Run the agent synchronously and return the text response."""
    runner, session_service = get_runner()

    async def _run():
        await session_service.create_session(
            app_name="voca_tutor",
            user_id="student",
            session_id=session_id,
        )
        content = genai_types.Content(
            role="user",
            parts=[genai_types.Part(text=word)]
        )
        full_response = ""
        async for event in runner.run_async(
            user_id="student",
            session_id=session_id,
            new_message=content,
        ):
            if event.is_final_response() and event.content and event.content.parts:
                full_response = "".join(p.text for p in event.content.parts if hasattr(p, "text"))
        return full_response

    return asyncio.run(_run())

# --- Boot ---
start_mcp_server()

# --- UI ---
tab1, tab2 = st.tabs(["✨ Student Portal", "📈 Parent Dashboard"])

with tab1:
    st.header("Wizarding Vocabulary Training")
    st.caption("Type a word and VocaAi will explain it with a Harry Potter twist!")

    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "session_id" not in st.session_state:
        import uuid
        st.session_state.session_id = str(uuid.uuid4())

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    word = st.chat_input("Enter a vocabulary word...")
    if word:
        st.session_state.messages.append({"role": "user", "content": word})
        with st.chat_message("user"):
            st.markdown(word)

        with st.chat_message("assistant"):
            with st.spinner("VocaAi is thinking..."):
                response = run_agent(word, st.session_state.session_id)
            st.markdown(response)
        st.session_state.messages.append({"role": "assistant", "content": response})

with tab2:
    st.header("Parent Progress Tracking")
    try:
        docs = (
            db.collection("tutor_sessions")
            .order_by("timestamp", direction=firestore.Query.DESCENDING)
            .stream()
        )
        data = [doc.to_dict() for doc in docs]
        df = pd.DataFrame(data)
        if not df.empty:
            m1, m2 = st.columns(2)
            m1.metric("Words Learned", len(df))
            m2.metric("Unique Words", df["topic"].nunique() if "topic" in df.columns else 0)

            # Check if timestamp exists before processing
            if "timestamp" in df.columns:
                df["Date"] = pd.to_datetime(df["timestamp"]).dt.date
                chart_data = df.groupby("Date").size().reset_index(name="Words")
                st.plotly_chart(px.area(chart_data, x="Date", y="Words"), use_container_width=True)
            
            # Show table with available columns
            display_cols = [c for c in ["topic", "parent_summary"] if c in df.columns]
            st.table(df[display_cols].head(10))
        else:
            st.info("No sessions yet — have your child practice some words!")
    except Exception as e:
        st.error(f"Sync Error: {e}")