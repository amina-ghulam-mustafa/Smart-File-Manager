import os
from pymongo import MongoClient
from google import genai
from dotenv import load_dotenv

# Environment load
load_dotenv()
MONGO_URI = os.getenv("MONGODB_URI")
PROJECT_ID = os.getenv("GCP_PROJECT_ID")
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "gcp-key.json"

# MongoDB connection set up
mongo_client = MongoClient(MONGO_URI)
collection = mongo_client["janitor_db"]["file_logs"]

# Gemini Agent set up
client = genai.Client(vertexai=True, project=PROJECT_ID, location="us-central1")