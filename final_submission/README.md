# VocaAi — Final Submission

## Live URL
https://voca-hub-final-583209535557.us-east1.run.app

## Architecture
- Primary agent: Google ADK + Gemini 2.5 Flash on Vertex AI
- Sub-agents: Firestore logger, Calendar scheduler, Gmail reporter, Quiz evaluator
- Quiz anti-hallucination: Firestore active_quiz collection as coordination layer
- Deployment: Google Cloud Run (containerized, dual-process)
- Credentials: Google Secret Manager

## Key files
- parent_dashboard.py — Streamlit UI + ADK runner + quiz state management
- agent_logic.py — Primary agent instruction + tool definitions
- final_gmail_push.py — Gmail OAuth2 weekly report
- server.py — MCP server (FastMCP on port 8001)
- start.sh — Dual-process startup (MCP + Streamlit)
- Dockerfile — Container definition
- cloudbuild-dashboard.yaml — Cloud Build + Cloud Run deployment pipeline
