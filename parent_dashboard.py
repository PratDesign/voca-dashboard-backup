import streamlit as st
from google.cloud import firestore
import pandas as pd
import plotly.express as px
import subprocess
import time
import os
import asyncio
import uuid
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types as genai_types
from dotenv import load_dotenv

# --- CONFIG & AUTH ---
load_dotenv()
st.set_page_config(page_title="VocaAi Hub", page_icon="🧙‍♂️", layout="wide")

PROJECT_ID = os.getenv("PROJECT_ID", "vocaai-491503")

# Path to service account (Secrets Manager mount)
sa_path = "/secrets/service_account.json"
if os.path.exists(sa_path):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = sa_path

db = firestore.Client(project=PROJECT_ID)

@st.cache_resource
def start_mcp_server():
    """Start only the MCP server as a background process."""
    abs_path = os.path.abspath(os.path.dirname(__file__))
    env = {**os.environ, "PYTHONPATH": abs_path}
    with open(os.devnull, 'w') as devnull:
        subprocess.Popen(
            ["python3", "server.py"],
            cwd=abs_path,
            stdout=devnull,
            stderr=devnull,
            env={**env, "PORT": "8001"}
        )
    time.sleep(4)
    return True

@st.cache_resource
def get_voca_runner():
    """Create the ADK runner once, reuse across all requests."""
    from my_agent_logic.agent import root_agent
    return Runner(agent=root_agent, app_name="voca_tutor", session_service=InMemorySessionService())

async def ask_voca(word: str, session_id: str) -> str:
    runner = get_voca_runner()
    
    # 1. FIX FOR "Session not found": Explicitly register the session in memory
    try:
        await runner.session_service.create_session(
            app_name="voca_tutor", 
            user_id="student", 
            session_id=session_id
        )
    except Exception:
        # If it already exists, that's fine, we just move on
        pass

    full_text = []
    msg_content = genai_types.Content(
        role="user", 
        parts=[genai_types.Part(text=word)]
    )

    # 2. FIX FOR "async_generator": Correctly iterate the event stream
    async for event in runner.run_async(
        user_id="student",
        session_id=session_id,
        new_message=msg_content,
    ):
        # 3. FIX FOR "AttributeError": Only grab text, skip tool result objects
        if event.content and event.content.parts:
            for part in event.content.parts:
                if hasattr(part, 'text') and part.text:
                    full_text.append(part.text.strip())

    return "\n\n".join(full_text) if full_text else "The spell fizzled... try again!"

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
            with st.spinner("VocaAi is casting a spell..."):
                answer = asyncio.run(ask_voca(word, st.session_state.session_id))
                st.markdown(answer)
        
        st.session_state.messages.append({"role": "assistant", "content": answer})

with tab2:
    st.header("Parent Progress Tracking")
    try:
        # Fetching data from Firestore
        docs = (
            db.collection("tutor_sessions")
            .order_by("timestamp", direction=firestore.Query.DESCENDING)
            .stream()
        )
        data = [doc.to_dict() for doc in docs]
        df = pd.DataFrame(data)

        if not df.empty:
            # Metrics Row
            m1, m2 = st.columns(2)
            m1.metric("Words Learned", len(df))
            m2.metric("Unique Words", df["topic"].nunique() if "topic" in df.columns else 0)

            # Chart Logic
            if "timestamp" in df.columns:
                # Convert timestamp to readable Date for the chart and table
                df["Learned Date"] = pd.to_datetime(df["timestamp"]).dt.strftime('%Y-%m-%d %H:%M')
                chart_df = pd.to_datetime(df["timestamp"]).dt.date
                chart_data = chart_df.value_counts().reset_index()
                chart_data.columns = ["Date", "Words"]
                st.plotly_chart(px.area(chart_data, x="Date", y="Words", title="Learning Consistency"), use_container_width=True)

            # Enhanced Table with the Date column added
            st.subheader("Vocabulary Log")
            # We explicitly add 'Learned Date' to the visible columns
            display_cols = [c for c in ["Learned Date", "topic", "parent_summary"] if c in df.columns]
            st.table(df[display_cols].head(10))
        else:
            st.info("No sessions yet — have your child practice some words!")

    except Exception as e:
        st.error(f"Sync Error: {e}")