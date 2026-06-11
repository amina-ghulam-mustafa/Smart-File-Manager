# 📂 Smart File Manager (AI Janitor)

**Built for the Google Cloud Rapid Agent Hackathon 2026**

Smart File Manager is an autonomous AI agent that brings order to digital chaos. Instead of relying on rigid folder structures or arbitrary filenames, this local-first tool uses **Google Gemini 2.5 Flash** and **MongoDB** to semantically understand, categorize, and organize your files and images based on their actual content.

## ✨ Features
* **Semantic Search & Routing:** Natural language search allows you to find files by describing their content (e.g., "Find the GitHub logo").
* **Vision-Powered Indexing:** Utilizes Gemini Vision to "look" at images, extracting objects and text for deep indexing.
* **Smart Categorization:** Automatically groups loose files into dynamically generated, context-aware folders.
* **Global Memory & Deduplication:** Powered by MongoDB, the agent remembers file hashes, summaries, and paths to prevent redundant processing.
* **Universal Shield (Auto-Retry):** Built-in exponential backoff to handle external API rate limits gracefully without crashing.
* **Self-Healing Cache:** The agent detects previous poor indexing attempts and forces fresh API scans to correct its own memory.

## 🛠️ Technology Stack (Required Tech)
* **AI Model:** Google Gemini 2.5 Flash (via Google Cloud)
* **Memory / State Management (Partner Track):** MongoDB 
* **Frontend:** Streamlit
* **Core Language:** Python 3.10+
* **Libraries:** PyPDF2, Pillow, pymongo

## 🚀 How to Run Locally

### 1. Prerequisites
Ensure you have the following installed and set up:
* Python 3.10 or higher
* A MongoDB Cluster (URI string)
* A Google Cloud Project with Generative Language API enabled (API Key)

### 2. Installation Steps
Clone the repository and navigate to the project directory:
git clone https://github.com/YOUR_GITHUB_USERNAME/Smart-File-Manager.git
cd Smart-File-Manager

Create a virtual environment:
python -m venv venv
source venv/bin/activate  # On Windows use: venv\Scripts\activate

Install the required dependencies:
pip install -r requirements.txt

### 3. Environment Variables
Create a .env file in the root directory and add your credentials:

GEMINI_API_KEY="your_google_cloud_gemini_api_key_here"

MONGO_URI="your_mongodb_connection_string_here"

### 4. Run the Application
Launch the Streamlit agent interface:
streamlit run app.py

## 📄 License
This project is licensed under the MIT License.
