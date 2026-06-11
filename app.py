import streamlit as st
import os
from config import collection, mongo_client
from scanner import quick_scan_preview, execute_approved_moves_with_progress, scan_for_duplicates, clear_pending_queue, undo_move
from semantic import semantic_search_and_orchestrate, fallback_deep_scan, find_lost_file_globally

# --- Premium UI Configuration ---
st.set_page_config(page_title="AI File Organizer", page_icon="🧠", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
    <style>
    /* HIDE STREAMLIT SYSTEM UI */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    .stAppDeployButton {display: none;}
    
    /* Styling */
    div.stButton > button:first-child {
        background: linear-gradient(90deg, #00D4FF 0%, #7C3AED 100%);
        color: white; border: none; border-radius: 8px; padding: 10px 24px; font-weight: 600; transition: all 0.3s ease;
    }
    div.stButton > button:hover { transform: translateY(-2px); box-shadow: 0 4px 15px rgba(0, 212, 255, 0.4); }
    .stTextInput>div>div>input { border-radius: 8px; background-color: #1A1F2B; border: 1px solid #2D3748; }
    .security-card { background-color: #111622; border-left: 4px solid #00D4FF; padding: 15px; border-radius: 4px; margin-bottom: 15px; }
    .reason-text { font-size: 0.85rem; color: #00D4FF; margin-bottom: 10px; display: block; }
    
    .stop-btn > button:first-child { background: transparent !important; border: 1px solid #EF4444 !important; color: #EF4444 !important; width: 100%; }
    .stop-btn > button:hover { background: #EF4444 !important; color: white !important; }
    </style>
""", unsafe_allow_html=True)

# --- Sidebar ---
with st.sidebar:
    st.markdown("#  Workspace Setup")
    folder_path = st.text_input("Target Folder Path:", placeholder="e.g., C:/Users/Downloads").strip()
    st.markdown("---")

    st.subheader(" Workspace Metrics")
    pending_count = collection.count_documents({"status": "Pending Approval"})
    moved_count = collection.count_documents({"status": "Moved"})
    col1, col2 = st.columns(2)
    col1.metric("Pending", f"{pending_count}")
    col2.metric("Organized", f"{moved_count}")
    
    st.markdown("---")
    st.subheader("🔒 Security Profile")
    st.markdown("<div class='security-card'><small style='color: #00D4FF;'><b>STATUS: SECURE</b></small><br><small style='color: #F3F4F6;'>• Local-First<br>• Zero Uploads<br>• Data Masking</small></div>", unsafe_allow_html=True)

    st.markdown("<br><br>", unsafe_allow_html=True)
    st.markdown("#### ⚙️ System Controls")
    st.caption("Wipe the AI's temporary memory and cancel pending queues. Your actual files are **100% safe**.")
    st.markdown("<div class='stop-btn'>", unsafe_allow_html=True)
    if st.button("🛑 Clear AI Memory", help="Safe to click! This just resets the AI if it gets stuck or confused."):
        clear_pending_queue()
        mongo_client["janitor_db"]["session_data"].delete_one({"session": "active"})
        st.rerun() 
    st.markdown("</div>", unsafe_allow_html=True)

st.title(" Your File Organizer")
st.write("") 

tab1, tab2, tab3, tab4 = st.tabs(["📁 Quick Organize", "🧹 Clean Duplicates", "💬 Ask the AI", "🕒 History & Undo"])

# --- TAB 1: Quick Scan & Organize ---
with tab1:
    st.subheader("Discover & Sort")
    
    if st.button(" Scan Folder Automatically"):
        if not folder_path: st.warning("Please enter a folder path in the sidebar first!")
        elif not os.path.exists(folder_path): st.error("Invalid path.")
        else:
            with st.spinner("Analyzing files..."):
                count = quick_scan_preview(folder_path)
                if count > 0: st.success(f"Found {count} files! Review them below.")
                else: st.info("No files found.")

    st.write("")
    pending = list(collection.find({"status": "Pending Approval"}))
    
    if pending:
        st.markdown("### 📋 Action Panel")
        
        if 'is_moving' not in st.session_state:
            st.session_state.is_moving = False

        col1, col2, col3 = st.columns([1, 2, 1])
        with col1:
            if st.button("🚫 Cancel Queue", disabled=st.session_state.is_moving):
                clear_pending_queue()
                st.rerun()
        with col2:
            # --- FEATURE: Only move selected files ---
            if st.button("✅ Approve & Move Selected", disabled=st.session_state.is_moving):
                unselected_ids = []
                # Check which files the user unchecked
                for p in pending:
                    chk_key = f"sel_{p['_id']}"
                    if chk_key in st.session_state and st.session_state[chk_key] is False:
                        unselected_ids.append(p['_id'])
                
                # Remove unselected files from the database queue so they are ignored
                if unselected_ids:
                    collection.delete_many({"_id": {"$in": unselected_ids}})
                    
                st.session_state.is_moving = True
                st.rerun()
        with col3:
            if st.button("🛑 Stop Agent", type="primary"):
                st.session_state.is_moving = False
                st.rerun()

        # PROGRESS BAR WITH ETA
        if st.session_state.is_moving:
            progress_bar = st.progress(0)
            status_text = st.empty()
            time_text = st.empty()
            
            final_count = 0
            for moved, total, fname, eta in execute_approved_moves_with_progress():
                if not st.session_state.is_moving: break
                progress_bar.progress(int((moved / total) * 100))
                status_text.text(f"Moving: {fname} ({moved}/{total})")
                time_text.text(f"⏳ Estimated Time Remaining: {eta} seconds")
                final_count = moved
            
            status_text.empty()
            time_text.empty()
            progress_bar.empty()
            st.session_state.is_moving = False
            st.success(f"{final_count} files organized!")
            if final_count > 0: st.rerun()

        # --- EXPANDER WITH CHECKBOXES ---
        with st.expander(f" View the {len(pending)} files (Check/Uncheck to select)", expanded=False):
            st.caption("☑️ Keep the box checked to organize the file. Uncheck the ones you want to leave as they are.")
            for p in pending:
                # Add a checkbox for each file
                st.checkbox(f"📄 **{p['file_name']}** ➡️  `{p['new_path']}`", value=True, key=f"sel_{p['_id']}")
                st.markdown(f"<span class='reason-text'>✨ AI Reasoning: {p.get('routing_reason', 'Standard Routing')}</span>", unsafe_allow_html=True)
    else:
        st.info("Workspace is clean.")

# --- TAB 2: Duplicates & Conflicts ---
with tab2:
    if st.button(" Run Duplicate Audit"):
        if not folder_path: st.warning("Need folder path!")
        else:
            scan_for_duplicates(folder_path)
            st.rerun()
            
    col1, col2 = st.columns(2, gap="large")
    with col1:
        st.markdown("#### 🗑️ Redundant Copies")
        duplicates = list(collection.find({"status": "Duplicate Pending Review"}))
        if duplicates:
            with st.expander("Review and Remove", expanded=True):
                to_delete = [dup for dup in duplicates if st.checkbox(f"Delete: {dup['file_name']}", key=str(dup['_id']))]
                if st.button("🗑️ Delete Selected Copies"):
                    for dup in to_delete:
                        if os.path.exists(dup['original_path']): os.remove(dup['original_path'])
                        collection.delete_one({"_id": dup['_id']})
                    st.rerun()
    with col2:
        st.markdown("#### ⚠️ Name Overlaps")
        conflicts = list(collection.find({"status": "Name Collision Review"}))
        if conflicts:
            with st.expander("Resolve Renaming", expanded=True):
                for conf in conflicts:
                    new_name = st.text_input(f"Rename '{conf['file_name']}':", value=f"new_{conf['file_name']}", key=f"rename_{conf['_id']}").strip()
                    if st.button(f"Save Name", key=f"btn_{conf['_id']}"):
                        if new_name:
                            new_path = os.path.join(os.path.dirname(conf['original_path']), new_name)
                            os.rename(conf['original_path'], new_path)
                            collection.update_one({"_id": conf['_id']}, {"$set": {"file_name": new_name, "original_path": new_path, "status": "Pending Approval"}})
                            st.rerun()

# --- TAB 3: Semantic Agent ---
with tab3:
    st.subheader(" Semantic Command Center")
    query = st.text_input("What are you looking for?", placeholder="e.g., Gather all my tax documents OR Where is my Flutter assignment?").strip()
    
    colA, colB = st.columns(2)
    with colA:
        if st.button(" Find files in Target Folder"):
            if not folder_path: st.warning("Provide path in sidebar.")
            elif not query: st.warning("Enter instructions.")
            else:
                with st.spinner("Evaluating..."):
                    st.success(semantic_search_and_orchestrate(query, folder_path))
    with colB:
        if st.button(" Find Lost File in Global Memory"):
            if not query: st.warning("Enter what you are looking for.")
            else:
                with st.spinner("Searching database memory..."):
                    st.success(find_lost_file_globally(query))
            
    session = mongo_client["janitor_db"]["session_data"].find_one({"session": "active"})
    if session and session.get("ignored_files"):
        if st.button(" Run Full Deep-Scan on Skipped Files"):
            with st.spinner("Deep-reading..."):
                st.success(fallback_deep_scan())
                st.rerun()

# --- TAB 4: History & Undo ---
with tab4:
    history = list(collection.find({"status": "Moved"}).sort("_id", -1).limit(20))
    if history:
        for item in history:
            colA, colB = st.columns([5, 1])
            with colA: st.markdown(f" **{item['file_name']}** moved to `{os.path.basename(os.path.dirname(item['new_path']))}`")
            with colB:
                if st.button("↩️ Undo", key=f"undo_{item['_id']}"):
                    if undo_move(item['_id']): st.rerun()
    else: st.write("No history available yet.")