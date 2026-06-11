import os
import shutil
import json
import time
from config import client, collection
from duplicator import get_file_hash

IGNORED_DIRS = [
    "Documents", "Images", "Code", "Videos", "Datasets", "Others", "Uncategorized",
    "venv", "env", ".venv", "node_modules", ".git", ".dart_tool", "build", 
    "__pycache__", ".idea", ".vscode", "ios", "android", "AI_Organized_Workspace"
]

IGNORED_SYSTEM_FILES = ["WHEEL", "LICENSE", "INSTALLER", "top_level.txt", "METADATA"]

def fast_classify_filenames(file_names):
    prompt = f"""
    Categorize each file into a single-word category based ONLY on its name and extension.
    Return ONLY a valid JSON object.
    Files: {file_names}
    """
    try:
        response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
        text = response.text.strip().replace("```json", "").replace("```", "").strip()
        return json.loads(text)
    except Exception:
        return {}

def determine_optimal_path(file_path, file_name, base_dir, category):
    try:
        size_mb = os.path.getsize(file_path) / (1024 * 1024)
    except Exception:
        size_mb = 0

    ext = os.path.splitext(file_name)[1].lower()
    heavy_extensions = ['.mp4', '.mkv', '.avi', '.mov', '.iso', '.vdi', '.unitypackage', '.tar.gz', '.zip', '.rar', '.7z', '.csv', '.sql', '.db']
    
    needs_d_drive = False
    reason = "Lightweight/Active File -> Local Folder"
    
    if size_mb > 100:
        needs_d_drive = True
        reason = f"Heavy File ({size_mb:.1f} MB) -> Routed to Storage Drive"
    elif ext in heavy_extensions:
        needs_d_drive = True
        reason = f"Archive/Media ({ext}) -> Routed to Storage Drive"
        
    category = ''.join(e for e in category if e.isalnum()) or "Others"
    
    if needs_d_drive:
        if os.path.exists("D:/"):
            target_folder = os.path.join("D:/AI_Organized_Workspace", category)
        else:
            target_folder = os.path.join("C:/AI_Organized_Workspace", category)
    else:
        target_folder = os.path.join(base_dir, category)
        
    new_path = os.path.join(target_folder, file_name)
    return new_path, category, reason

def scan_for_duplicates(directory_path):
    count = 0
    hash_map = {}
    for root, dirs, files in os.walk(directory_path):
        dirs[:] = [d for d in dirs if d not in IGNORED_DIRS]
        for file in files:
            if file in IGNORED_SYSTEM_FILES: continue
            file_path = os.path.join(root, file)
            file_hash = get_file_hash(file_path)
            if not file_hash: continue

            db_exist = collection.find_one({"file_hash": file_hash, "status": {"$in": ["Moved", "Pending Approval"]}})
            if db_exist or file_hash in hash_map:
                dup_logged = collection.find_one({"original_path": file_path, "status": "Duplicate Pending Review"})
                if not dup_logged:
                    collection.insert_one({
                        "file_name": file, "original_path": file_path, "suggested_category": "Duplicate",
                        "summary": "Exact copy detected.", "status": "Duplicate Pending Review", "file_hash": file_hash
                    })
                    count += 1
            else:
                hash_map[file_hash] = file_path
    return count

def quick_scan_preview(directory_path):
    file_list = []
    path_mapping = {}
    for root, dirs, files in os.walk(directory_path):
        dirs[:] = [d for d in dirs if d not in IGNORED_DIRS]
        for file in files:
            if file in IGNORED_SYSTEM_FILES: continue
            file_path = os.path.join(root, file)
            file_list.append(file)
            path_mapping[file] = file_path

    if not file_list: return 0

    category_map = fast_classify_filenames(file_list)
    preview_count = 0

    for file in file_list:
        file_path = path_mapping[file]
        file_hash = get_file_hash(file_path)

        dup_check = collection.find_one({"file_hash": file_hash, "status": {"$in": ["Moved", "Pending Approval"]}})
        if dup_check:
            collection.insert_one({"file_name": file, "original_path": file_path, "suggested_category": "Duplicate", "summary": "Exact copy detected.", "status": "Duplicate Pending Review", "file_hash": file_hash})
            continue

        name_check = collection.find_one({"file_name": file, "status": {"$in": ["Moved", "Pending Approval"]}})
        if name_check and name_check["file_hash"] != file_hash:
            collection.insert_one({"file_name": file, "original_path": file_path, "suggested_category": "Name Conflict", "summary": "Name exists but content is different.", "status": "Name Collision Review", "file_hash": file_hash})
            continue

        raw_category = category_map.get(file, "Others")
        new_path, final_category, routing_reason = determine_optimal_path(file_path, file, directory_path, raw_category)

        collection.insert_one({
            "file_name": file, "original_path": file_path, "new_path": new_path,
            "suggested_category": final_category, "summary": "Pending user approval.",
            "status": "Pending Approval", "file_hash": file_hash, "deep_indexed": False,
            "routing_reason": routing_reason
        })
        preview_count += 1
    return preview_count

def execute_approved_moves_with_progress():
    pending_files = list(collection.find({"status": "Pending Approval"}))
    total = len(pending_files)
    moved_count = 0
    start_time = time.time()
    
    for idx, file in enumerate(pending_files):
        target_folder = os.path.dirname(file["new_path"])
        os.makedirs(target_folder, exist_ok=True)
        try:
            shutil.move(file["original_path"], file["new_path"])
            collection.update_one({"_id": file["_id"]}, {"$set": {"status": "Moved"}})
            moved_count += 1
        except Exception:
            pass
            
        elapsed_time = time.time() - start_time
        avg_time_per_file = elapsed_time / max(moved_count, 1)
        remaining_files = total - moved_count
        eta_seconds = int(avg_time_per_file * remaining_files)
        
        yield moved_count, total, file["file_name"], eta_seconds

def clear_pending_queue():
    collection.delete_many({"status": "Pending Approval"})

def undo_move(file_id):
    record = collection.find_one({"_id": file_id})
    if record and os.path.exists(record["new_path"]):
        try:
            shutil.move(record["new_path"], record["original_path"])
            collection.delete_one({"_id": file_id})
            return True
        except Exception:
            return False
    return False