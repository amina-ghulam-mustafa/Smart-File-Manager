import os
import streamlit as st
from pymongo import MongoClient
from google import genai
from dotenv import load_dotenv

load_dotenv()

# Streamlit secrets ya local .env se variables lena
MONGO_URI = st.secrets.get("MONGODB_URI", os.getenv("MONGODB_URI"))
PROJECT_ID = st.secrets.get("GCP_PROJECT_ID", os.getenv("GCP_PROJECT_ID"))

# Streamlit ke andar securely gcp-key.json file create karna
if "GCP_KEY_JSON" in st.secrets:
    with open("gcp-key.json", "w") as f:
        f.write(st.secrets["GCP_KEY_JSON"])

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "gcp-key.json"

# MongoDB connection set up
mongo_client = MongoClient(MONGO_URI)
collection = mongo_client["janitor_db"]["file_logs"]

# Gemini Agent set up
client = genai.Client(vertexai=True, project=PROJECT_ID, location="us-central1")
