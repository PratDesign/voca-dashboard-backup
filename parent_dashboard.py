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
    return future.result(timeout=60)


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
@st.cache_resource
def get_voca_runner() -> Runner:
    """Build the Runner inside the dedicated loop so its MCP session lives
    in the same event loop it will always be called from."""
    async def _build() -> Runner:
        from my_agent_logic.agent import root_agent
        return Runner(
            agent=root_agent,
            app_name="voca_tutor",
            session_service=InMemorySessionService(),
        )
    return run_async(_build())


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

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            if msg["role"] == "assistant" and (
                "Mastery Check" in msg["content"] or "?" in msg["content"]
            ):
                st.info(msg["content"])
            else:
                st.markdown(msg["content"])

    if word := st.chat_input("Enter a vocabulary word (or answer a quiz!)..."):
        st.session_state.messages.append({"role": "user", "content": word})
        with st.chat_message("user"):
            st.markdown(word)

        with st.chat_message("assistant"):
            with st.spinner("Consulting the Sorting Hat..."):
                answer = run_async(ask_voca(word, st.session_state.session_id))
                if "Mastery Check" in answer or "?" in answer:
                    st.info(answer)
                else:
                    st.markdown(answer)

        st.session_state.messages.append({"role": "assistant", "content": answer})

# ── TAB 2: PARENT DASHBOARD ───────────────────────────────────────────────────
with tab2:
    st.subheader("Parental Oversight & Insights")

    try:
        docs = (
            db.collection("tutor_sessions")
            .order_by("timestamp", direction=firestore.Query.DESCENDING)
            .stream()
        )
        data = [doc.to_dict() for doc in docs]
        df = pd.DataFrame(data)

        if not df.empty:

            # ── Normalise timestamps ──────────────────────────────────
            if "timestamp" in df.columns:
                df["ts"] = pd.to_datetime(df["timestamp"])
                df["date"] = df["ts"].dt.date
                df["Learned Date"] = df["ts"].dt.strftime("%b %d, %Y  %H:%M")

            # ── Streak ────────────────────────────────────────────────
            streak = compute_streak(df["date"].tolist() if "date" in df.columns else [])

            # ── Metrics row ───────────────────────────────────────────
            m1, m2, m3, m4 = st.columns(4)
            m1.metric(
                "Words Learned",
                len(df),
                delta=(
                    f"+{len(df[df['date'] >= date.today() - timedelta(days=7)])}"
                    if "date" in df.columns else None
                ),
                delta_color="normal",
                help="Total vocabulary entries recorded",
            )
            m2.metric(
                "Topics Covered",
                df["topic"].nunique() if "topic" in df.columns else "—",
                help="Distinct topics studied",
            )
            m3.metric(
                "Study Streak",
                f"{streak} days",
                help="Consecutive days with at least one word learned",
            )
            if (
                "correct" in df.columns
                and "attempted" in df.columns
                and df["attempted"].sum() > 0
            ):
                accuracy = round(df["correct"].sum() / df["attempted"].sum() * 100)
                m4.metric("Quiz Accuracy", f"{accuracy}%",
                          help="Correct answers across all quizzes")
            else:
                unique_days = df["date"].nunique() if "date" in df.columns else "—"
                m4.metric("Days Active", unique_days,
                          help="Total days with study activity")

            st.divider()

            # ── Filters ───────────────────────────────────────────────
            col_search, col_topic, col_date = st.columns([3, 2, 2])

            with col_search:
                search_term = st.text_input(
                    "Search",
                    placeholder="Search word or topic...",
                    label_visibility="collapsed",
                )
            with col_topic:
                topic_options = ["All topics"]
                if "topic" in df.columns:
                    topic_options += sorted(df["topic"].dropna().unique().tolist())
                selected_topic = st.selectbox(
                    "Filter by topic", topic_options, label_visibility="collapsed"
                )
            with col_date:
                date_filter = st.selectbox(
                    "Date range",
                    ["All time", "Last 7 days", "Last 30 days"],
                    label_visibility="collapsed",
                )

            # Apply filters to a copy — charts always show full data
            fdf = df.copy()
            if search_term:
                mask = pd.Series(False, index=fdf.index)
                for col in ["topic", "word", "parent_summary"]:
                    if col in fdf.columns:
                        mask |= fdf[col].astype(str).str.contains(
                            search_term, case=False, na=False
                        )
                fdf = fdf[mask]
            if selected_topic != "All topics" and "topic" in fdf.columns:
                fdf = fdf[fdf["topic"] == selected_topic]
            if date_filter != "All time" and "date" in fdf.columns:
                days_back = 7 if "7" in date_filter else 30
                cutoff = date.today() - timedelta(days=days_back)
                fdf = fdf[fdf["date"] >= cutoff]

            # ── Charts (always full df, not filtered) ─────────────────
            chart_col, topic_col = st.columns([3, 2])

            with chart_col:
                if "date" in df.columns:
                    activity = (
                        df.groupby("date").size().reset_index(name="Words")
                    )
                    activity["date"] = pd.to_datetime(activity["date"])
                    activity = activity.sort_values("date").tail(30)
                    fig_activity = px.bar(
                        activity, x="date", y="Words",
                        labels={"date": "", "Words": "Words learned"},
                    )
                    fig_activity.update_traces(
                        marker_color="#185FA5",
                        marker_line_width=0,
                        hovertemplate="%{x|%b %d}<br>%{y} words<extra></extra>",
                    )
                    apply_chart_theme(fig_activity, "Daily learning activity — last 30 days")
                    st.plotly_chart(fig_activity, use_container_width=True)

            with topic_col:
                if "topic" in df.columns:
                    topic_counts = (
                        df["topic"].value_counts().head(8).reset_index()
                    )
                    topic_counts.columns = ["Topic", "Count"]
                    fig_topics = px.bar(
                        topic_counts, x="Count", y="Topic",
                        orientation="h",
                        labels={"Count": "Words", "Topic": ""},
                    )
                    fig_topics.update_traces(
                        marker_color="#3B6D11",
                        marker_line_width=0,
                        hovertemplate="%{y}: %{x} words<extra></extra>",
                    )
                    apply_chart_theme(fig_topics, "Top topics")
                    fig_topics.update_layout(
                        yaxis=dict(categoryorder="total ascending", showgrid=False)
                    )
                    st.plotly_chart(fig_topics, use_container_width=True)

            st.divider()

            # ── Log header + report button ────────────────────────────
            log_title_col, report_col = st.columns([5, 1])
            with log_title_col:
                st.markdown("#### 📜 Vocabulary Log")
                st.caption(f"{len(fdf)} entr{'y' if len(fdf) == 1 else 'ies'} shown")
            with report_col:
                st.write("")  # nudge vertical alignment
                if st.button("📩 Send Report", use_container_width=True):
                    with st.spinner("Sending..."):
                        run_async(
                            ask_voca("send weekly report", st.session_state.session_id)
                        )
                    st.success("Report sent!", icon="✅")

            # ── Vocabulary log table ──────────────────────────────────
            display_col_candidates = [
                "Learned Date", "word", "topic", "parent_summary", "mastery_level"
            ]
            display_cols = [c for c in display_col_candidates if c in fdf.columns]

            if display_cols:
                rename_map = {
                    "word": "Word",
                    "topic": "Topic",
                    "parent_summary": "Summary",
                    "mastery_level": "Mastery %",
                }
                display_df = fdf[display_cols].rename(columns=rename_map).head(25)

                column_config = {
                    "Summary": st.column_config.TextColumn("Summary", width="large"),
                }
                if "Mastery %" in display_df.columns:
                    column_config["Mastery %"] = st.column_config.ProgressColumn(
                        "Mastery",
                        help="How well the student knows this word",
                        min_value=0,
                        max_value=100,
                        format="%d%%",
                    )

                st.dataframe(
                    display_df,
                    use_container_width=True,
                    hide_index=True,
                    column_config=column_config,
                )
            else:
                st.info("No matching entries for the current filters.")

        else:
            st.warning("No magical entries found in the scrolls yet.")

    except Exception as e:
        st.error(f"Sync error: {e}")
        st.exception(e)  # Remove this line in production