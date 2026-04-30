import os
import base64
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from google.cloud import firestore

TOKEN_PATH = os.getenv("TOKEN_PATH", "/app/secrets/token/token.json")
RECIPIENT = "data.pratyush@gmail.com"
SCOPES = ["https://www.googleapis.com/auth/gmail.send"]

def build_html_report():
    try:
        db = firestore.Client(project=os.getenv("PROJECT_ID", "harrypottervoca"))
        docs = db.collection("tutor_sessions").order_by(
            "timestamp", direction=firestore.Query.DESCENDING
        ).limit(10).stream()
        rows = ""
        for doc in docs:
            d = doc.to_dict()
            rows += f"<tr><td>{d.get('topic','—')}</td><td>{d.get('kid_explanation','—')[:80]}...</td></tr>"
        return f"""
        <html><body>
        <h2>🧙 VocaAi Weekly Report</h2>
        <table border='1' cellpadding='6' cellspacing='0'>
        <tr><th>Word</th><th>Explanation</th></tr>
        {rows}
        </table>
        </body></html>
        """
    except Exception as e:
        return f"<html><body><p>Could not load session data: {e}</p></body></html>"

def main():
    try:
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
        if not creds.valid and creds.refresh_token:
            creds.refresh(Request())
        service = build("gmail", "v1", credentials=creds)
        html_body = build_html_report()
        message = MIMEMultipart("alternative")
        message["to"] = RECIPIENT
        message["from"] = RECIPIENT
        message["subject"] = "🧙 VocaAi Weekly Vocabulary Report"
        message.attach(MIMEText(html_body, "html"))
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        service.users().messages().send(userId="me", body={"raw": raw}).execute()
        print("✅ Weekly report sent!")
    except Exception as e:
        print(f"❌ Gmail Failed: {e}")
        raise

if __name__ == "__main__":
    main()
