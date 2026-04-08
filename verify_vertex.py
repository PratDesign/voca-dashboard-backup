import os
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "/secrets/service_account.json"
try:
    from google.genai import Client
    # Force Vertex mode - this is what the ADK does under the hood
    client = Client(vertexai=True, project="vocaai-491503", location="us-central1")
    print("✅ VERTEX AUTH VERIFIED")
except Exception as e:
    print(f"❌ AUTH FAILED: {e}")
