import os
import shutil
import json
import time
import PyPDF2
import zipfile
from config import client, collection, mongo_client
from duplicator import get_file_hash

# --- ✨ NEW: UNIVERSAL AUTO-RETRY SHIELD ✨ ---
def safe_gemini_call(contents):
    max_retries = 4
    delay = 15 # Wait 15 seconds if Google limits speed
    for attempt in range(max_retries):
        try:
            res = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=contents
            )
            return res.text.strip()
        except Exception as e:
            error_msg = str(e)
            if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
                if attempt < max_retries - 1:
                    time.sleep(delay)
                    delay += 10 # Next try waits longer (25s)
                else:
                    raise Exception("QUOTA_ERROR")
            else:
                raise e
# ---------------------------------------------

def extract_text(filepath):
    ext = filepath.lower().split('.')[-1]
    text = ""
    try:
        if ext == 'pdf':
            with open(filepath, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                if len(reader.pages) > 0: text = reader.pages[0].extract_text()[:1000]
        elif ext in ['txt', 'csv', 'md', 'py']:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                text = f.read(1000)
        elif ext == 'zip':
            with zipfile.ZipFile(filepath, 'r') as z:
                file_list = z.namelist()
                text = f"This is a ZIP archive containing these files: {', '.join(file_list[:30])}"
        # --- Using the Universal Shield for Images ---
        elif ext in ['jpg', 'jpeg', 'png', 'webp']:
            from PIL import Image
            with Image.open(filepath) as img:
                text = safe_gemini_call([
                    "Identify and describe all objects, text, or visual elements inside this image briefly in one sentence for indexing purposes.", 
                    img
                ])
                time.sleep(2) # Normal small delay after success
    except Exception as e: 
        if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
            raise Exception("QUOTA_ERROR")
    return text.strip()

def analyze_intent_and_path(query, default_dir):
    prompt = f"""
    User Query: "{query}"
    Default Directory: "{default_dir}"
    Did the user mention a specific folder path? If yes, extract it. If no, output the Default Directory.
    Return ONLY JSON: {{"target_path": "the_extracted_path"}}
    """
    try:
        raw_text = safe_gemini_call(prompt)
        text = raw_text.replace("```json", "").replace("```", "").strip()
        data = json.loads(text)
        extracted_path = data.get("target_path", default_dir)
        return extracted_path if os.path.exists(extracted_path) else default_dir
    except Exception as e:
        if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e): raise Exception("QUOTA_ERROR")
        return default_dir

def filter_by_name_heuristic(query, file_list):
    if not file_list: return []
    prompt = f"""
    User Query: "{query}"
    File Names: {file_list}
    Filter this list. Keep a file if its name suggests even a 0.1% chance of being relevant.
    Return ONLY JSON: {{"relevant_files": ["file1.ext", "file2.ext"]}}
    """
    try:
        raw_text = safe_gemini_call(prompt)
        text = raw_text.replace("```json", "").replace("```", "").strip()
        data = json.loads(text)
        return data.get("relevant_files", file_list) 
    except Exception as e:
        if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e): raise Exception("QUOTA_ERROR")
        return file_list

def perform_deep_match(query, target_dir, files_to_scan, path_map):
    file_summaries = {}
    new_files_to_summarize = {}

    for file in files_to_scan:
        file_path = path_map.get(file)
        if not file_path: continue
        
        file_hash = get_file_hash(file_path)
        record = collection.find_one({"file_hash": file_hash})
        
        is_bad_image_cache = False
        if record and file.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
            if "Empty or binary" in record.get("summary", ""):
                is_bad_image_cache = True

        if record and record.get("deep_indexed") and not is_bad_image_cache:
            file_summaries[file] = record.get("summary", "")
        else:
            content = extract_text(file_path) or "Empty or binary file."
            new_files_to_summarize[file] = {"path": file_path, "hash": file_hash, "content": content}

    # BULK PROCESSING LOGIC
    if new_files_to_summarize:
        new_files_list = list(new_files_to_summarize.items())
        batch_size = 10 
        
        for i in range(0, len(new_files_list), batch_size):
            batch = new_files_list[i:i+batch_size]
            bulk_prompt_data = {fname: data["content"][:500] for fname, data in batch}
            
            prompt = f"""
            Task: Summarize the core content of each file briefly (1 sentence each).
            Input Files: {json.dumps(bulk_prompt_data)}
            Return ONLY a valid JSON dictionary mapping filenames to their summaries.
            """
            try:
                raw_text = safe_gemini_call(prompt)
                text = raw_text.replace("```json", "").replace("```", "").strip()
                bulk_results = json.loads(text)
                
                for fname, summary in bulk_results.items():
                    if fname in new_files_to_summarize:
                        file_summaries[fname] = summary
                        f_data = new_files_to_summarize[fname]
                        record = collection.find_one({"file_hash": f_data["hash"]})
                        if record:
                            collection.update_one({"_id": record["_id"]}, {"$set": {"summary": summary, "deep_indexed": True}})
                        else:
                            collection.insert_one({
                                "file_name": fname, "original_path": f_data["path"], "new_path": f_data["path"], 
                                "suggested_category": "Others", "summary": summary, "status": "Moved", 
                                "file_hash": f_data["hash"], "deep_indexed": True
                            })
            except Exception as e:
                if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                    raise Exception("QUOTA_ERROR")
                pass
            
            time.sleep(2) 

    if not file_summaries: return None, 0, ""

    prompt = f"""
    User Intent: "{query}"
    Candidate Summaries: {json.dumps(file_summaries)}
    1. Select ONLY files that genuinely match the intent.
    2. Provide a 1-word clear folder name.
    Return ONLY JSON: {{"folder_name": "Name", "matched_files": ["f1.txt"]}}
    """
    try:
        raw_text = safe_gemini_call(prompt)
        text = raw_text.replace("```json", "").replace("```", "").strip()
        result = json.loads(text)

        matched = result.get("matched_files", [])
        folder_name = result.get("folder_name", "Organized")

        if not matched: return folder_name, 0, ""

        target_folder = os.path.join(target_dir, folder_name)
        os.makedirs(target_folder, exist_ok=True)

        moved_count = 0
        for fname in matched:
            record = collection.find_one({"file_name": fname})
            if record:
                curr_path = record.get("new_path", record.get("original_path"))
                if curr_path and os.path.exists(curr_path):
                    new_path = os.path.join(target_folder, fname)
                    shutil.move(curr_path, new_path)
                    collection.update_one({"_id": record["_id"]}, {"$set": {"new_path": new_path, "suggested_category": folder_name}})
                    moved_count += 1
        return folder_name, moved_count, target_dir
    except Exception as e: 
        if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e): raise Exception("QUOTA_ERROR")
        return None, 0, ""

def semantic_search_and_orchestrate(query, default_dir):
    try:
        target_dir = analyze_intent_and_path(query, default_dir)
        
        all_files_in_dir = []
        path_map = {}
        for root, dirs, files in os.walk(target_dir):
            dirs[:] = [d for d in dirs if d not in ["Documents", "Images", "Code", "Videos", "Datasets", "Others", "Uncategorized", "venv", ".git", "node_modules", "build"]]
            for file in files:
                all_files_in_dir.append(file)
                path_map[file] = os.path.join(root, file)
                
        if not all_files_in_dir: 
            return f"🤖 **Assistant:** I peeked into `{target_dir}` but couldn't find any loose files there. Is there another folder I should check?"

        if len(all_files_in_dir) <= 15:
            suspected_files = all_files_in_dir.copy()
        else:
            suspected_files = filter_by_name_heuristic(query, all_files_in_dir)
            
            visual_keywords = ['image', 'photo', 'picture', 'pic', 'screenshot', 'img', 'logo', 'icon']
            if any(word in query.lower() for word in visual_keywords):
                for file in all_files_in_dir:
                    if file.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
                        if file not in suspected_files:
                            suspected_files.append(file)

        ignored_files = [f for f in all_files_in_dir if f not in suspected_files]
        
        mongo_client["janitor_db"]["session_data"].update_one(
            {"session": "active"},
            {"$set": {"last_query": query, "target_dir": target_dir, "ignored_files": ignored_files, "path_map": path_map}},
            upsert=True
        )

        if not suspected_files: 
            return "🤖 **Assistant:** Just looking at the file names, I don't see anything matching your request here. Want me to do a deeper read of everything, or should we try a different folder?"

        folder_name, moved_count, _ = perform_deep_match(query, target_dir, suspected_files, path_map)
        
        if moved_count == 0:
            return "🤖 **Assistant:** I read the files that looked promising, but they didn't quite match what you asked for. You can ask me to read the rest of the files, or point me somewhere else."
            
        return f"🤖 **Assistant:** All set! I found what you needed and neatly placed **{moved_count} files** into a new folder called `{folder_name}`. ✨"
    except Exception as e:
        if str(e) == "QUOTA_ERROR":
            return "⏳ **Assistant:** I've reached my reading limit! Please give me a short break and try again in 2-3 minutes."
        return "⚠️ **Assistant:** Something went wrong while searching. Please try again."

def fallback_deep_scan():
    try:
        session = mongo_client["janitor_db"]["session_data"].find_one({"session": "active"})
        if not session or not session.get("ignored_files"):
            return "🤖 **Assistant:** I don't have any more files left to check here. Please show me a new folder."

        query = session["last_query"]
        target_dir = session["target_dir"]
        ignored_files = session["ignored_files"]
        path_map = session["path_map"]

        folder_name, moved_count, _ = perform_deep_match(query, target_dir, ignored_files, path_map)

        mongo_client["janitor_db"]["session_data"].delete_one({"session": "active"})

        if moved_count == 0:
            return "🤖 **Assistant:** I've read every single file now, but still couldn't find a match. They might be in a different folder!"
            
        return f"🤖 **Assistant:** Success! I read the remaining files and found **{moved_count} matches**. I've placed them in the `{folder_name}` folder."
    except Exception as e:
        if str(e) == "QUOTA_ERROR":
            return "⏳ **Assistant:** I'm reading too fast and hit my quota limit! Please wait 2-3 minutes before trying again."
        return "⚠️ **Assistant:** A technical error occurred during the deep scan."

def find_lost_file_globally(query):
    organized_files = list(collection.find({"status": "Moved"}))
    if not organized_files:
        return "🤖 **Assistant:** My database memory is currently empty. I haven't organized any files yet, so I don't know where anything is globally."

    file_data = [
        {"name": f['file_name'], "path": f.get('new_path', 'N/A'), "summary": f.get('summary', 'No summary available')} 
        for f in organized_files[-100:] 
    ]

    prompt = f"""
    User Query: "{query}"
    Database (JSON Array): {json.dumps(file_data)}
    Task: Identify the single best matching file for the query from the array.
    Return ONLY valid JSON format: {{"found": true, "file_name": "name", "path": "path", "reason": "why it matches"}}
    If no relevant file matches, return {{"found": false}}
    Do not add any extra text outside the JSON block.
    """
    try:
        raw_text = safe_gemini_call(prompt)
        text = raw_text.replace("```json", "").replace("```", "").strip()
        data = json.loads(text)
        
        if data.get("found"):
            return f"🤖 **Assistant:** I found it in my database memory! 🎉\n\n📄 **File:** `{data.get('file_name')}`\n📁 **Location:** `{data.get('path')}`\n💡 **Reason:** {data.get('reason')}"
        else:
            return "🤖 **Assistant:** I searched my entire database memory but couldn't find any file matching your description."
    except Exception as e:
        error_msg = str(e)
        if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
            return "⏳ **Assistant:** I've reached my reading limit! Please give me a short break and try again in 2-3 minutes."
        return f"⚠️ **Technical Error:** Something went wrong. Please try again."