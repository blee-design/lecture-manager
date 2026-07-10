# file_manager.py – with tally loop

import os
import shutil
import re
import hashlib
import time
import glob
import subprocess
import sys
from datetime import datetime
from collections import Counter
from .db import get_connection, TABLE_NAME, get_record_by_any_id
from .utils import clean_field, sanitize_filename, print_colored, color_text, COLORS
from .youtube import extract_video_id
from .utils import compute_md5, ROOT_DIR, clean_field, sanitize_filename, print_colored, color_text, COLORS, TRASH_DIR

os.makedirs(TRASH_DIR, exist_ok=True)

# Pretest subjects (01-10)
PRETEST_SUBJECTS = {
    "01": "1. Geography, Population, and Environment (GK)",
    "02": "2. History and Socio‑Cultural Aspects",
    "03": "3. Economic, Banking and Public Finance",
    "04": "4. Constitution, Law and Governance",
    "05": "5. International Relations and Current Affairs",
    "06": "6. Science, Technology and ICT",
    "07": "7. Public Enterprises and Public Management",
    "08": "8. Basic Mathematical Aptitude and Analytical Ability",
    "09": "9. English Language Competence Test",
    "10": "10. Nepali Language Competence Test"
}

# Second Paper subjects
PAPER_I_SUBJECTS = {
    "01": "1. Microeconomics",
    "02": "2. Development Economics",
    "03": "3. Public Economics",
    "04": "4. Macroeconomics",
    "05": "5. Monetary Economics",
    "06": "6. International Economics"
}

PAPER_II_SUBJECTS = {
    "01": "1. General Management",
    "02": "2. Human Resource Development",
    "03": "3. Financial Economics",
    "04": "4. Managerial Economics"
}

PAPER_III_SUBJECTS = {
    "01": "1. Research Methodology",
    "02": "2. Information and Communication Technology",
    "03": "3. Banking Laws and Regulations"
}

# Map paper type to folder name and subject mapping
PAPER_CONFIG = {
    "pretest": {
        "folder": "Pretest Officer",
        "subjects": PRETEST_SUBJECTS
    },
    "paper_i": {
        "folder": "First Paper: Economics",
        "subjects": PAPER_I_SUBJECTS
    },
    "paper_ii": {
        "folder": "Second Paper: Management",
        "subjects": PAPER_II_SUBJECTS
    },
    "paper_iii": {
        "folder": "Third Paper: Research Methodologies, ICT and Banking Laws & Regulation",
        "subjects": PAPER_III_SUBJECTS
    }
}

# Keywords for detection
PAPER_KEYWORDS = {
    "pretest": [
        "gk", "pretest", "english", "nepali", "geography", "history",
        "constitution", "international", "science", "public enterprises",
        "mathematical", "orientation"
    ],
    "paper_i": [
        "microeconomics", "development economics", "public economics",
        "macroeconomics", "monetary economics", "international economics",
        "economics"
    ],
    "paper_ii": [
        "general management", "human resource", "financial economics",
        "managerial economics"
    ],
    "paper_iii": [
        "research methodology", "information technology", "ict",
        "banking laws", "regulations"
    ]
}

def collect_facebook_tally_data():
    """
    Scan the Facebook directories and return a tally summary.
    """
    facebook_dir = os.path.join(ROOT_DIR, 'facebook')
    if not os.path.exists(facebook_dir):
        return {
            'total_entries': 0,
            'files_found': [],
            'missing': [],
            'orphan': [],
            'by_type': {'video': 0, 'photo': 0}
        }

    # Get all entries from DB
    from .facebook_manager import list_facebook_entries
    db_entries = list_facebook_entries(limit=None)  # all

    # Map file_hash to entry
    entry_by_hash = {e['file_hash']: e for e in db_entries if e['file_hash']}

    # Scan files on disk
    video_exts = ('.mp4', '.mkv', '.webm', '.avi', '.mov')
    photo_exts = ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp')
    all_files = []
    video_dir = os.path.join(facebook_dir, 'videos')
    photo_dir = os.path.join(facebook_dir, 'photos')
    if os.path.exists(video_dir):
        for f in os.listdir(video_dir):
            if f.lower().endswith(video_exts):
                all_files.append(os.path.join(video_dir, f))
    if os.path.exists(photo_dir):
        for f in os.listdir(photo_dir):
            if f.lower().endswith(photo_exts):
                all_files.append(os.path.join(photo_dir, f))

    file_hash_from_path = {fp: os.path.splitext(os.path.basename(fp))[0] for fp in all_files}

    missing = []
    orphan = []
    for fp in all_files:
        h = file_hash_from_path[fp]
        if h in entry_by_hash:
            continue
        else:
            orphan.append(fp)
    for h, entry in entry_by_hash.items():
        if not any(os.path.basename(fp).startswith(h) for fp in all_files):
            missing.append(entry)

    return {
        'total_entries': len(db_entries),
        'files_found': all_files,
        'missing': missing,
        'orphan': orphan,
        'by_type': {
            'video': sum(1 for e in db_entries if e['type'] == 'video'),
            'photo': sum(1 for e in db_entries if e['type'] == 'photo')
        }
    }

def compute_md5(file_path, chunk_size=8192):
    """Compute MD5 hash of a file."""
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()

def parse_syllabus_id(syllabus_id):
    if not syllabus_id:
        return None, None, None
    # Strip trailing dash and number if present
    base = syllabus_id.split('-')[0]
    parts = [p for p in base.split('.') if p]
    if len(parts) >= 1:
        subject_num = parts[0].zfill(2)
    else:
        return None, None, None
    chapter_num = parts[1].zfill(2) if len(parts) >= 2 else "01"
    lecture_num = parts[2].zfill(2) if len(parts) >= 3 else "01"
    return subject_num, chapter_num, lecture_num

def detect_paper(subject, syllabus_id=None, chapter=None, interactive=True):
    """
    Determine which paper a record belongs to.
    Checks syllabus_id first, then subject, then chapter for disambiguation.
    """
    first_part = None
    if syllabus_id:
        parts = syllabus_id.split('.')
        if parts and parts[0].isdigit():
            first_part = parts[0].zfill(2)

    candidates = []
    for paper_key, config in PAPER_CONFIG.items():
        if first_part and first_part in config["subjects"]:
            candidates.append(paper_key)

    if len(candidates) == 1:
        return candidates[0]

    if len(candidates) > 1:
        subject_lower = subject.lower().strip()
        chapter_lower = chapter.lower().strip() if chapter else ""

        # Combine subject and chapter for keyword search
        combined = f"{subject_lower} {chapter_lower}"

        # Paper‑specific keywords
        if any(word in combined for word in ["economics", "micro", "macro", "development", "public", "monetary", "international"]):
            return "paper_i"
        if any(word in combined for word in ["management", "hr", "financial", "managerial"]):
            return "paper_ii"
        if any(word in combined for word in ["research", "methodology", "ict", "banking", "regulation", "law", "act", "aml", "compliance"]):
            return "paper_iii"

        # If pretest is among candidates, assume pretest (covers 01-10)
        if "pretest" in candidates:
            return "pretest"

        # Interactive fallback if allowed
        if interactive:
            print_colored(f"[!] Subject '{subject}' matches multiple papers: {candidates}", COLORS.YELLOW)
            print("Please choose the correct paper:")
            options = list(PAPER_CONFIG.keys())
            for i, key in enumerate(options, 1):
                print(f"  {i}. {key} ({PAPER_CONFIG[key]['folder']})")
            choice = input(color_text("Enter number (or leave blank to cancel): ", COLORS.MAGENTA)).strip()
            if choice.isdigit() and 1 <= int(choice) <= len(options):
                return options[int(choice)-1]
            return None
        else:
            return None

    # No candidate from syllabus_id → fallback to subject mapping
    subject_lower = subject.lower().strip()
    for paper_key, config in PAPER_CONFIG.items():
        for subj_num, subj_name in config["subjects"].items():
            if subject_lower == subj_name.lower():
                return paper_key

    # Keyword‑based fallback (subject only)
    matches = []
    for paper_key, keywords in PAPER_KEYWORDS.items():
        for kw in keywords:
            if kw in subject_lower:
                matches.append(paper_key)
                break
    if len(matches) == 1:
        return matches[0]
    elif len(matches) > 1:
        if interactive:
            print_colored(f"[!] Subject '{subject}' matches multiple papers: {matches}", COLORS.YELLOW)
            print("Please choose the correct paper:")
            options = list(PAPER_CONFIG.keys())
            for i, key in enumerate(options, 1):
                print(f"  {i}. {key} ({PAPER_CONFIG[key]['folder']})")
            choice = input(color_text("Enter number (or leave blank to cancel): ", COLORS.MAGENTA)).strip()
            if choice.isdigit() and 1 <= int(choice) <= len(options):
                return options[int(choice)-1]
            return None
        else:
            return None
    else:
        if interactive:
            print_colored(f"[!] Could not detect paper for subject '{subject}'.", COLORS.YELLOW)
            print("Please choose the paper manually:")
            options = list(PAPER_CONFIG.keys())
            for i, key in enumerate(options, 1):
                print(f"  {i}. {key} ({PAPER_CONFIG[key]['folder']})")
            choice = input(color_text("Enter number (or leave blank to cancel): ", COLORS.MAGENTA)).strip()
            if choice.isdigit() and 1 <= int(choice) <= len(options):
                return options[int(choice)-1]
            return None
        else:
            return None

def get_target_path(record, interactive=True):
    syllabus_id = record.get('syllabus_id')
    subject = record.get('subject', '')
    if not syllabus_id:
        return None, None

    # Use paper column if present, otherwise detect
    paper_key = record.get('paper')
    if not paper_key:
        paper_key = detect_paper(subject, syllabus_id, record.get('chapter'), interactive=interactive)

    if not paper_key:
        return None, None

    subject_num, chapter_num, _ = parse_syllabus_id(syllabus_id)
    if not subject_num:
        return None, None

    config = PAPER_CONFIG[paper_key]
    paper_folder = config["folder"]
    subject_mapping = config["subjects"]
    subject_folder_name = subject_mapping.get(subject_num)
    if not subject_folder_name:
        return None, None
    chapter_folder = f"{subject_num}.{chapter_num}"
    base_dir = os.path.join(ROOT_DIR, paper_folder, subject_folder_name, chapter_folder)

    syllabus = clean_field(syllabus_id)

    chapter_display = record.get('chapter') or record.get('video_title', '').split('||')[0].strip() or "chapter"
    subject_display = clean_field(record.get('subject', ''))
    lecturer = clean_field(record.get('lecturer', ''))
    nepali_date = clean_field(record.get('nepali_date', ''))
    time_str = clean_field(record.get('time', ''))
    parts = [syllabus, chapter_display, subject_display, lecturer, nepali_date, time_str]
    display_name = " || ".join(parts)
    filename_base = sanitize_filename(display_name)
    if len(filename_base) > 200:
        filename_base = filename_base[:200]
    return base_dir, filename_base

def prompt_for_source_file(record):
    print(f"\n--- Organizing: {color_text(record.get('syllabus_id'), COLORS.CYAN)} | {color_text(record.get('subject'), COLORS.CYAN)} | {color_text(record.get('video_id'), COLORS.CYAN)} ---")
    source = input(color_text("Enter full path to the video file (or press Enter to skip): ", COLORS.MAGENTA)).strip()
    if not source:
        return None
    source = os.path.expanduser(source)
    if os.path.isdir(source):
        print(f"[i] '{source}' is a directory. Looking for video files...")
        video_exts = ('.mp4', '.mkv', '.webm', '.avi', '.mov')
        files = [f for f in os.listdir(source) if f.lower().endswith(video_exts)]
        if not files:
            print_colored("[!] No video files found in that directory.", COLORS.RED)
            return prompt_for_source_file(record)
        print("Select a file:")
        for i, f in enumerate(files, 1):
            print(f"  {i}. {f}")
        choice = input(color_text("Enter number (or 0 to cancel): ", COLORS.MAGENTA)).strip()
        if choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(files):
                return os.path.join(source, files[idx-1])
        return None
    if os.path.isfile(source):
        return source
    else:
        print_colored(f"[!] Path not found or not a file: {source}", COLORS.RED)
        return prompt_for_source_file(record)

def organize_video(record, source_file=None, overwrite=False, interactive=True):
    target_dir, _ = get_target_path(record, interactive=interactive)  # we don't need filename_base
    if not target_dir:
        return None

    # If no source file, try to find one (existing logic)
    if not source_file and interactive:
        download_dir = "./downloads"
        if os.path.exists(download_dir):
            possible_files = []
            for f in os.listdir(download_dir):
                if record['video_id'] in f or record['syllabus_id'] in f:
                    possible_files.append(os.path.join(download_dir, f))
            if possible_files:
                source_file = possible_files[0]
                if len(possible_files) > 1:
                    print(f"Multiple files found for {record['video_id']}:")
                    for i, f in enumerate(possible_files, 1):
                        print(f"  {i}. {f}")
                    choice = input(color_text("Choose number (default 1): ", COLORS.MAGENTA)).strip()
                    if choice.isdigit() and 1 <= int(choice) <= len(possible_files):
                        source_file = possible_files[int(choice)-1]
                print_colored(f"[i] Found file: {source_file}", COLORS.BLUE)
            else:
                source_file = None
        else:
            source_file = None

    if not source_file and interactive:
        source_file = prompt_for_source_file(record)
        if not source_file:
            return None
    elif not source_file:
        print_colored(f"[!] No source file for {record['video_id']}, skipping.", COLORS.YELLOW)
        return None

    if not os.path.exists(source_file):
        if interactive:
            print_colored(f"[!] Source file not found: {source_file}", COLORS.RED)
            source_file = prompt_for_source_file(record)
            if not source_file:
                return None
        else:
            print_colored(f"[!] Source file not found: {source_file}, skipping.", COLORS.RED)
            return None

    # ---- Compute MD5 hash of the source file ----
    file_hash = compute_md5(source_file)

    # ---- Determine extension ----
    _, ext = os.path.splitext(source_file)
    if not ext:
        ext = ".mp4"

    # ---- Build new filename from hash ----
    hash_filename = f"{file_hash}{ext}"
    target_file = os.path.join(target_dir, hash_filename)

    # ---- Preserve original descriptive name for display ----
    # Reuse the existing filename_base logic (from get_target_path) for the original name
    _, filename_base = get_target_path(record, interactive=interactive)
    # Ensure we have something
    if not filename_base:
        # fallback to video_title or syllabus_id
        filename_base = record.get('video_title') or record.get('syllabus_id') or "lecture"

    # ---- Handle existing file ----
    if os.path.exists(target_file) and not overwrite:
        print_colored(f"[i] Target already exists: {target_file} (skipping)", COLORS.YELLOW)
        return 'already_exists'

    # ---- Move and rename ----
    os.makedirs(target_dir, exist_ok=True)
    try:
        shutil.move(source_file, target_file)
        print_colored(f"[✓] Moved to: {target_file}", COLORS.GREEN)
        remove_empty_directories(os.path.dirname(source_file))

        # ---- Update database ----
        conn = get_connection()
        cursor = conn.cursor()
        # Update file_hash and original_filename
        cursor.execute(f"""
            UPDATE {TABLE_NAME}
            SET file_hash = %s, original_filename = %s
            WHERE video_id = %s
        """, (file_hash, filename_base, record['video_id']))
        conn.commit()
        cursor.close()
        conn.close()

        # ---- Update hash_cache ----
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO hash_cache (file_path, file_hash, status, last_scan)
                VALUES (%s, %s, 'active', NOW())
                ON DUPLICATE KEY UPDATE file_hash = VALUES(file_hash), status = 'active', last_scan = NOW()
            """, (target_file, file_hash))
            conn.commit()
            cursor.close()
            conn.close()
        except Exception as e:
            print_colored(f"[!] Failed to update hash_cache: {e}", COLORS.YELLOW)

        return target_file
    except Exception as e:
        print_colored(f"[!] Failed to move: {e}", COLORS.RED)
        return None

def embed_youtube_metadata(file_path, record):
    """
    Add YouTube metadata (title, artist, date, thumbnail) to a video file using ffmpeg.
    """
    video_id = record['video_id']
    title = record.get('video_title') or record.get('original_filename') or f"YouTube Video {video_id}"
    lecturer = record.get('lecturer', '')
    nepali_date = record.get('nepali_date', '')

    # ---- Download thumbnail ----
    thumb_url = f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg"
    thumb_file = file_path + ".thumb.jpg"

    try:
        import requests
        resp = requests.get(thumb_url, timeout=10)
        if resp.status_code == 200:
            with open(thumb_file, 'wb') as f:
                f.write(resp.content)
            print_colored("[i] Thumbnail downloaded.", COLORS.BLUE)
        else:
            # fallback to lower quality
            thumb_url = f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"
            resp = requests.get(thumb_url, timeout=10)
            if resp.status_code == 200:
                with open(thumb_file, 'wb') as f:
                    f.write(resp.content)
                print_colored("[i] Thumbnail downloaded (lower quality).", COLORS.BLUE)
            else:
                print_colored("[!] Could not download thumbnail.", COLORS.YELLOW)
                thumb_file = None
    except Exception as e:
        print_colored(f"[!] Failed to download thumbnail: {e}", COLORS.YELLOW)
        thumb_file = None

    # ---- Build ffmpeg command to embed metadata and thumbnail ----
    # We'll use -map_metadata to set title, artist, date
    # For thumbnail, we can use -attach or -i with -disposition
    # But for simplicity, we'll use ffmpeg to copy streams and attach metadata

    if not shutil.which('ffmpeg'):
        print_colored("[!] ffmpeg not found. Install ffmpeg to embed metadata.", COLORS.YELLOW)
        if thumb_file and os.path.exists(thumb_file):
            os.remove(thumb_file)
        return

    # Prepare metadata
    # Title: use video title or original name
    # Artist: lecturer (or empty)
    # Date: nepali_date
    # Comment: video_id

    output_file = file_path + ".temp.mkv"  # we'll remux to mkv for better thumbnail support
    cmd = ['ffmpeg', '-i', file_path]

    if thumb_file and os.path.exists(thumb_file):
        cmd.extend(['-i', thumb_file, '-map', '0', '-map', '1', '-c', 'copy', '-disposition:v:1', 'attached_pic'])
    else:
        cmd.extend(['-c', 'copy'])

    # Add metadata
    cmd.extend([
        '-metadata', f'title={title}',
        '-metadata', f'artist={lecturer}',
        '-metadata', f'date={nepali_date}',
        '-metadata', f'comment=YouTube Video ID: {video_id}',
        '-metadata', f'source=YouTube',
    ])

    # If we have a thumbnail, the output format should support attached pictures (e.g., mkv)
    if thumb_file:
        output_file = os.path.splitext(file_path)[0] + ".mkv"
        cmd.append(output_file)
    else:
        # Just copy to same file with metadata (overwrite)
        cmd.append(output_file)

    try:
        subprocess.run(cmd, check=True)
        print_colored("[✓] Metadata and thumbnail embedded.", COLORS.GREEN)
        # Replace original with new file
        if output_file != file_path:
            os.remove(file_path)
            shutil.move(output_file, file_path)
        # Clean up thumb
        if thumb_file and os.path.exists(thumb_file):
            os.remove(thumb_file)
    except subprocess.CalledProcessError as e:
        print_colored(f"[!] ffmpeg failed: {e}", COLORS.RED)
        if thumb_file and os.path.exists(thumb_file):
            os.remove(thumb_file)
        # Clean up temp file
        if os.path.exists(output_file) and output_file != file_path:
            os.remove(output_file)

def move_video_interactive():
    identifier = input(color_text("Enter video ID or syllabus ID to move: ", COLORS.MAGENTA)).strip()
    if not identifier:
        return
    record = get_record_by_any_id(identifier)
    if not record:
        print_colored("[!] Record not found.", COLORS.RED)
        return
    current_path = input(color_text("Enter current full path of the video file: ", COLORS.MAGENTA)).strip()
    if not current_path or not os.path.exists(current_path):
        print_colored("[!] Invalid file path.", COLORS.RED)
        return

    # ---- Get target directory (not filename) ----
    target_dir, filename_base = get_target_path(record)
    if not target_dir:
        return

    # ---- Ask for new base name (optional) ----
    new_name = input(color_text(f"New display name (leave blank to keep '{filename_base}'): ", COLORS.MAGENTA)).strip()
    if new_name:
        original_name = sanitize_filename(new_name)
    else:
        original_name = filename_base

    # ---- Compute hash of the current file ----
    file_hash = compute_md5(current_path)
    _, ext = os.path.splitext(current_path)
    if not ext:
        ext = ".mp4"
    hash_filename = f"{file_hash}{ext}"

    # ---- Move to target_dir with hash filename ----
    os.makedirs(target_dir, exist_ok=True)
    target_file = os.path.join(target_dir, hash_filename)

    if os.path.exists(target_file):
        overwrite = input(color_text(f"Target exists: {target_file}. Overwrite? (y/n): ", COLORS.MAGENTA)).strip().lower()
        if overwrite != 'y':
            print_colored("Cancelled.", COLORS.YELLOW)
            return

    try:
        shutil.move(current_path, target_file)
        print_colored(f"[✓] Moved to: {target_file}", COLORS.GREEN)

        # ---- Update database ----
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(f"""
            UPDATE {TABLE_NAME}
            SET file_hash = %s, original_filename = %s
            WHERE video_id = %s
        """, (file_hash, original_name, record['video_id']))
        conn.commit()
        cursor.close()
        conn.close()

        # ---- Update hash_cache ----
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO hash_cache (file_path, file_hash, status, last_scan)
            VALUES (%s, %s, 'active', NOW())
            ON DUPLICATE KEY UPDATE file_hash = VALUES(file_hash), status = 'active', last_scan = NOW()
        """, (target_file, file_hash))
        conn.commit()
        cursor.close()
        conn.close()

        print_colored("[✓] Hash stored in database and cache.", COLORS.GREEN)
        remove_empty_directories(os.path.dirname(current_path))

        # ---- NEW: Ask if user wants to add YouTube metadata ----
        add_meta = input(color_text("Add YouTube metadata (title, thumbnail) to the video file? (y/n): ", COLORS.MAGENTA)).strip().lower()
        if add_meta == 'y':
            try:
                embed_youtube_metadata(target_file, record)
            except Exception as e:
                print_colored(f"[!] Failed to add metadata: {e}", COLORS.RED)

    except Exception as e:
        print_colored(f"[!] Failed to move: {e}", COLORS.RED)

def delete_video_to_trash():
    raw = input(color_text("Enter video ID, syllabus ID, mirror ID, or YouTube URL: ", COLORS.MAGENTA)).strip()
    if not raw:
        return

    # Extract video ID if URL, otherwise keep raw
    identifier = extract_video_id(raw) or raw

    # First try by video_id or mirror_id (using existing helper)
    record = get_record_by_any_id(identifier)
    if not record:
        # If not found, try by syllabus_id
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(f"SELECT * FROM {TABLE_NAME} WHERE syllabus_id = %s", (identifier,))
        record = cursor.fetchone()
        cursor.close()
        conn.close()

    if not record:
        print_colored("[!] Record not found.", COLORS.RED)
        return

    # ---------- Locate the video file using hash first ----------
    possible_files = []
    target_dir, _ = get_target_path(record, interactive=False)

    # 1) Try to find by file_hash (exact match) in the expected directory
    file_hash = record.get('file_hash')
    if file_hash and target_dir and os.path.exists(target_dir):
        for f in os.listdir(target_dir):
            if f.lower().endswith(('.mp4', '.mkv', '.webm', '.avi', '.mov')):
                # Check if filename starts with the hash (hash may have extension)
                if f.startswith(file_hash):
                    possible_files.append(os.path.join(target_dir, f))
                    break

    # 2) If not found, search the entire ROOT_DIR by hash in filename
    if not possible_files and file_hash:
        for root, _, files in os.walk(ROOT_DIR):
            for f in files:
                if f.lower().endswith(('.mp4', '.mkv', '.webm', '.avi', '.mov')):
                    if f.startswith(file_hash):
                        possible_files.append(os.path.join(root, f))
                        break
            if possible_files:
                break

    # 3) Fallback: search by old naming (video_id or syllabus_id in path)
    if not possible_files:
        print_colored("[i] File not found by hash. Falling back to old search...", COLORS.BLUE)
        if target_dir:
            for f in os.listdir(target_dir):
                if f.lower().endswith(('.mp4', '.mkv', '.webm', '.avi', '.mov')):
                    if record['video_id'] in f or (record.get('syllabus_id') and record['syllabus_id'] in f):
                        possible_files.append(os.path.join(target_dir, f))
        if not possible_files:
            for root, _, files in os.walk(ROOT_DIR):
                for f in files:
                    if f.lower().endswith(('.mp4', '.mkv', '.webm', '.avi', '.mov')):
                        if record['video_id'] in f or (record.get('syllabus_id') and record['syllabus_id'] in f):
                            possible_files.append(os.path.join(root, f))
                            break
                if possible_files:
                    break

    if not possible_files:
        print_colored("[!] Could not locate the video file for this record.", COLORS.RED)
        return

    source_file = possible_files[0]
    if len(possible_files) > 1:
        print("Multiple files found:")
        for i, f in enumerate(possible_files, 1):
            print(f"  {i}. {f}")
        choice = input(color_text("Choose number (default 1): ", COLORS.MAGENTA)).strip()
        if choice.isdigit() and 1 <= int(choice) <= len(possible_files):
            source_file = possible_files[int(choice)-1]

    confirm = input(color_text(f"Move '{source_file}' to trash? (y/n): ", COLORS.MAGENTA)).strip().lower()
    if confirm != 'y':
        print_colored("Cancelled.", COLORS.YELLOW)
        return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = os.path.basename(source_file)
    trash_name = f"{timestamp}_{base}"
    trash_path = os.path.join(TRASH_DIR, trash_name)

    try:
        shutil.move(source_file, trash_path)

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE hash_cache SET status = 'trashed' WHERE file_path = %s", (source_file,))
        cursor.execute("INSERT INTO trash_entries (original_path, record_id, trash_filename) VALUES (%s, %s, %s)",
                       (source_file, record['id'], os.path.basename(trash_path)))
        conn.commit()
        cursor.close()
        conn.close()

        print_colored(f"[✓] Moved to trash: {trash_path}", COLORS.GREEN)
        remove_empty_directories(os.path.dirname(source_file))
    except Exception as e:
        print_colored(f"[!] Failed to delete: {e}", COLORS.RED)

def restore_from_trash():
    def update_cache_status(file_path, status):
        try:
            conn = get_connection()
            cursor = conn.cursor()
            if status == 'active':
                cursor.execute("UPDATE hash_cache SET status = 'active' WHERE file_path = %s", (file_path,))
            elif status == 'deleted':
                cursor.execute("DELETE FROM hash_cache WHERE file_path = %s", (file_path,))
            conn.commit()
            cursor.close()
            conn.close()
        except Exception as e:
            print_colored(f"[!] Failed to update cache: {e}", COLORS.YELLOW)

    while True:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT id, original_path, record_id, trash_filename, deleted_at
            FROM trash_entries
            ORDER BY deleted_at DESC
        """)
        entries = cursor.fetchall()
        cursor.close()
        conn.close()

        if not entries:
            print_colored("[i] Trash is empty.", COLORS.YELLOW)
            break

        print("\n" + "═" * 50)
        print_colored("  TRASHED FILES", COLORS.CYAN, bold=True)
        print("═" * 50)
        for i, entry in enumerate(entries, 1):
            rec_info = ""
            if entry['record_id']:
                conn2 = get_connection()
                cur2 = conn2.cursor(dictionary=True)
                cur2.execute("SELECT syllabus_id, subject FROM youtube_lectures WHERE id = %s", (entry['record_id'],))
                rec = cur2.fetchone()
                cur2.close()
                conn2.close()
                if rec:
                    rec_info = f"{rec['syllabus_id']} - {rec['subject']}"
            print(f"{i}. {entry['trash_filename']} (original: {entry['original_path']}) {rec_info}")

        choice = input(color_text("Enter number to act on (or 0 to exit): ", COLORS.MAGENTA)).strip()
        if not choice.isdigit():
            continue
        idx = int(choice)
        if idx == 0:
            break
        if idx < 1 or idx > len(entries):
            print_colored("[!] Invalid number.", COLORS.RED)
            continue

        entry = entries[idx-1]
        trash_path = os.path.join(TRASH_DIR, entry['trash_filename'])

        if not os.path.exists(trash_path):
            print_colored("[!] File not found in trash directory. Removing DB entry.", COLORS.RED)
            conn2 = get_connection()
            cur2 = conn2.cursor()
            cur2.execute("DELETE FROM trash_entries WHERE id = %s", (entry['id'],))
            conn2.commit()
            cur2.close()
            conn2.close()
            continue

        action = input(color_text("Restore (r), Delete permanently (d), or Cancel (c)? [r/d/c]: ", COLORS.MAGENTA)).strip().lower()
        if action == 'c':
            print_colored("Cancelled.", COLORS.YELLOW)
            continue
        elif action == 'd':
            confirm = input(color_text(f"Permanently delete {entry['trash_filename']}? (y/n): ", COLORS.RED)).strip().lower()
            if confirm == 'y':
                try:
                    os.remove(trash_path)
                    # Delete from cache
                    update_cache_status(entry['original_path'], 'deleted')
                    conn2 = get_connection()
                    cur2 = conn2.cursor()
                    cur2.execute("DELETE FROM trash_entries WHERE id = %s", (entry['id'],))
                    conn2.commit()
                    cur2.close()
                    conn2.close()
                    print_colored(f"[✓] Deleted permanently: {entry['trash_filename']}", COLORS.GREEN)
                except Exception as e:
                    print_colored(f"[!] Deletion failed: {e}", COLORS.RED)
            else:
                print_colored("Cancelled.", COLORS.YELLOW)
            continue
        elif action == 'r':
            target = entry['original_path']
            if not os.path.exists(os.path.dirname(target)):
                print_colored("[!] Original directory no longer exists. Please specify new location.", COLORS.YELLOW)
                target = input(color_text("Enter new path (including filename): ", COLORS.MAGENTA)).strip()
                if not target:
                    continue

            if os.path.exists(target):
                overwrite = input(color_text(f"Target exists: {target}. Overwrite? (y/n): ", COLORS.MAGENTA)).strip().lower()
                if overwrite != 'y':
                    continue

            try:
                shutil.move(trash_path, target)
                # Update cache status to active
                update_cache_status(target, 'active')
                conn2 = get_connection()
                cur2 = conn2.cursor()
                cur2.execute("DELETE FROM trash_entries WHERE id = %s", (entry['id'],))
                conn2.commit()
                cur2.close()
                conn2.close()
                print_colored(f"[✓] Restored to: {target}", COLORS.GREEN)
                # Clean up trash directory if empty
                remove_empty_directories(os.path.dirname(trash_path))
            except Exception as e:
                print_colored(f"[!] Restore failed: {e}", COLORS.RED)
            continue
        else:
            print_colored("[!] Invalid choice. Please enter r, d, or c.", COLORS.RED)
            continue

def empty_trash():
    confirm = input(color_text("Permanently delete all files in trash and remove entries from DB? (y/n): ", COLORS.MAGENTA)).strip().lower()
    if confirm != 'y':
        print_colored("Cancelled.", COLORS.YELLOW)
        return
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT trash_filename, original_path FROM trash_entries")
    rows = cursor.fetchall()
    for fname, orig_path in rows:
        path = os.path.join(TRASH_DIR, fname)
        try:
            if os.path.isfile(path):
                os.remove(path)
                print(f"  [deleted] {fname}")
        except Exception as e:
            print_colored(f"  [failed] {fname}: {e}", COLORS.RED)
        # Delete from hash_cache if present
        cursor.execute("DELETE FROM hash_cache WHERE file_path = %s", (orig_path,))
    cursor.execute("DELETE FROM trash_entries")
    conn.commit()
    cursor.close()
    conn.close()
    print_colored("[✓] Trash emptied and cache cleaned.", COLORS.GREEN)

def sync_record_files(new_record, old_syllabus_id, old_video_id, old_record):
    """
    Sync (move/rename) the video file when a record's metadata changes.
    Uses hash-based naming.
    """
    print("\n" + "═" * 50)
    print_colored("  SYNCING VIDEO FILE WITH UPDATED METADATA", COLORS.CYAN, bold=True)
    print("═" * 50)

    # Locate the current file (by hash, or by old naming if hash not set)
    possible_files = []
    file_hash = old_record.get('file_hash')

    # 1) Try by hash
    if file_hash:
        old_target_dir, _ = get_target_path(old_record, interactive=False)
        if old_target_dir and os.path.exists(old_target_dir):
            for f in os.listdir(old_target_dir):
                if f.lower().endswith(('.mp4', '.mkv', '.webm', '.avi', '.mov')):
                    if f.startswith(file_hash):
                        possible_files.append(os.path.join(old_target_dir, f))
                        break
        if not possible_files:
            # Search entire ROOT_DIR by hash
            for root, _, files in os.walk(ROOT_DIR):
                for f in files:
                    if f.lower().endswith(('.mp4', '.mkv', '.webm', '.avi', '.mov')):
                        if f.startswith(file_hash):
                            possible_files.append(os.path.join(root, f))
                            break
                if possible_files:
                    break

    # 2) Fallback: search by old naming (video_id or syllabus_id)
    if not possible_files:
        print_colored("[i] File not found by hash. Falling back to old search...", COLORS.BLUE)
        old_target_dir, old_filename_base = get_target_path(old_record, interactive=False)
        if old_target_dir and os.path.exists(old_target_dir):
            for f in os.listdir(old_target_dir):
                if f.lower().endswith(('.mp4', '.mkv', '.webm', '.avi', '.mov')):
                    if old_video_id in f or (old_syllabus_id and old_syllabus_id in f):
                        possible_files.append(os.path.join(old_target_dir, f))
        if not possible_files:
            for root, _, files in os.walk(ROOT_DIR):
                for f in files:
                    if f.lower().endswith(('.mp4', '.mkv', '.webm', '.avi', '.mov')):
                        if old_video_id in f or (old_syllabus_id and old_syllabus_id in f):
                            possible_files.append(os.path.join(root, f))
                            break
                if possible_files:
                    break

    if not possible_files:
        print_colored(f"[!] Could not locate the video file for ID {old_video_id}. Sync skipped.", COLORS.RED)
        return

    source_file = possible_files[0]
    if len(possible_files) > 1:
        print("Multiple possible files found:")
        for i, f in enumerate(possible_files, 1):
            print(f"  {i}. {f}")
        choice = input(color_text("Choose number (default 1): ", COLORS.MAGENTA)).strip()
        if choice.isdigit() and 1 <= int(choice) <= len(possible_files):
            source_file = possible_files[int(choice)-1]

    # ---- Determine new target ----
    new_target_dir, filename_base = get_target_path(new_record, interactive=False)
    if not new_target_dir:
        print_colored("[!] New target path invalid. Sync failed.", COLORS.RED)
        return

    # Compute hash of the source file (if not already)
    if not file_hash:
        file_hash = compute_md5(source_file)

    # Determine extension
    _, ext = os.path.splitext(source_file)
    if not ext:
        ext = ".mp4"

    # New filename = hash + extension
    new_filename = f"{file_hash}{ext}"
    new_file = os.path.join(new_target_dir, new_filename)

    # If the file is already at the correct location and name, nothing to do
    if os.path.abspath(source_file) == os.path.abspath(new_file):
        print_colored("[i] File already at the correct location and name. No changes needed.", COLORS.YELLOW)
        return

    # Handle existing target
    if os.path.exists(new_file):
        overwrite = input(color_text(f"Target file exists: {new_file}. Overwrite? (y/n): ", COLORS.MAGENTA)).strip().lower()
        if overwrite != 'y':
            print_colored("[i] Sync aborted by user.", COLORS.YELLOW)
            return

    try:
        shutil.move(source_file, new_file)
        print_colored(f"[✓] Synced file to: {new_file}", COLORS.GREEN)

        # ---- Update database ----
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(f"""
            UPDATE {TABLE_NAME}
            SET file_hash = %s, original_filename = %s
            WHERE video_id = %s
        """, (file_hash, filename_base, new_record['video_id']))
        conn.commit()
        cursor.close()
        conn.close()

        # ---- Update hash_cache ----
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO hash_cache (file_path, file_hash, status, last_scan)
            VALUES (%s, %s, 'active', NOW())
            ON DUPLICATE KEY UPDATE file_hash = VALUES(file_hash), status = 'active', last_scan = NOW()
        """, (new_file, file_hash))
        conn.commit()
        cursor.close()
        conn.close()

        # Remove empty old directory
        remove_empty_directories(os.path.dirname(source_file))
    except Exception as e:
        print_colored(f"[!] Failed to sync file: {e}", COLORS.RED)

# ========== NEW: TALLY WITH LOOP ==========
def collect_tally_data():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(f"SELECT * FROM {TABLE_NAME}")
    records = cursor.fetchall()
    cursor.close()
    conn.close()

    record_by_vid = {r['video_id']: r for r in records}
    expected_paths = {}
    unresolved = 0
    for r in records:
        target_dir, fname = get_target_path(r, interactive=False)
        if target_dir and fname:
            expected_paths[r['video_id']] = os.path.join(target_dir, fname)
        else:
            expected_paths[r['video_id']] = None
            unresolved += 1

    # Scan for video files on disk
    video_exts = ('.mp4', '.mkv', '.webm', '.avi', '.mov')
    all_files = []
    facebook_dir = os.path.join(ROOT_DIR, 'facebook')
    for root, _, files in os.walk(ROOT_DIR):
        if root.startswith(facebook_dir):
            continue
        for f in files:
            if f.lower().endswith(video_exts):
                all_files.append(os.path.join(root, f))
    download_dir = './downloads'
    if os.path.exists(download_dir):
        for f in os.listdir(download_dir):
            if f.lower().endswith(video_exts):
                all_files.append(os.path.join(download_dir, f))

    existing_files_set = set(all_files)

    # Build file_to_vid: map file path -> video_id using file_hash (filename is the hash)
    file_to_vid = {}
    for rec in records:
        file_hash = rec.get('file_hash')
        if file_hash:
            for filepath in all_files:
                if os.path.basename(filepath).startswith(file_hash):
                    file_to_vid[filepath] = rec['video_id']
                    break
    # No syllabus_id fallback – accurate because filenames are MD5 hashes.

    # Build hash_to_path from cache (active entries)
    conn2 = get_connection()
    cur2 = conn2.cursor(dictionary=True)
    cur2.execute("SELECT file_path, file_hash FROM hash_cache WHERE status = 'active'")
    hash_to_path = {}
    for row in cur2.fetchall():
        if row['file_path'] in existing_files_set:
            hash_to_path[row['file_hash']] = row['file_path']
    cur2.close()
    conn2.close()

    missing = []
    correctly_placed = []
    mismatched = []

    for vid, rec in record_by_vid.items():
        expected = expected_paths.get(vid)
        if expected is None:
            continue  # unresolved, skip tally for this record

        matched = False

        # 1) Check if any file exists in the expected directory
        #    that matches the hash (filename starts with file_hash)
        file_hash = rec.get('file_hash')
        if file_hash and os.path.exists(os.path.dirname(expected)):
            for f in os.listdir(os.path.dirname(expected)):
                if f.lower().endswith(video_exts) and f.startswith(file_hash):
                    matched = True
                    break

        # 2) If not matched, try hash-based matching from cache
        if not matched:
            if file_hash and file_hash in hash_to_path:
                cached_path = hash_to_path[file_hash]
                if os.path.dirname(cached_path) == os.path.dirname(expected):
                    matched = True
                else:
                    # File exists but in a different location → mismatch
                    mismatched.append(rec)
                    continue

        if matched:
            correctly_placed.append(rec)
        else:
            missing.append(rec)

    orphan = [fp for fp in all_files if fp not in file_to_vid]

    return {
        'records': records,
        'all_files': all_files,
        'correctly_placed': correctly_placed,
        'missing': missing,
        'orphan': orphan,
        'mismatched': mismatched,
        'unresolved': unresolved,
        'file_to_vid': file_to_vid,
        'expected_paths': expected_paths
    }

def tally_db_with_files():
    """
    Tally database records against actual video files on disk.
    Shows a sub‑menu with options, including compression.
    """
    while True:
        data = collect_tally_data()
        records = data['records']
        all_files = data['all_files']
        correctly_placed = data['correctly_placed']
        missing = data['missing']
        orphan = data['orphan']
        mismatched = data['mismatched']
        unresolved = data['unresolved']
        file_to_vid = data['file_to_vid']
        expected_paths = data['expected_paths']

        print("\n" + "═" * 50)
        print_colored("  TALLY DATABASE WITH FILES", COLORS.CYAN, bold=True)
        print("═" * 50)
        print(f"\n📊 Summary:")
        print(f"  Total records        : {len(records)}")
        print(f"  Total files          : {len(all_files)}")
        print_colored(f"  ✅ Correctly placed  : {len(correctly_placed)} records have file in expected location", COLORS.GREEN)
        if mismatched:
            print_colored(f"  ⚠️ Mismatched        : {len(mismatched)} records have file(s) but not in expected location", COLORS.YELLOW)
        if missing:
            print_colored(f"  ❌ Missing           : {len(missing)} records have no file at all", COLORS.RED)
        if orphan:
            print_colored(f"  🗑️ Orphan            : {len(orphan)} files have no matching record", COLORS.YELLOW)
        if unresolved:
            print_colored(f"  ❓ Unresolved        : {unresolved} records could not be mapped to a target folder", COLORS.MAGENTA)

        if not (missing or orphan or mismatched) and unresolved == 0:
            print_colored("\n✅ Everything is perfectly synced!", COLORS.GREEN)

        # ---- Facebook summary ----
        fb_tally = collect_facebook_tally_data()
        if fb_tally['total_entries'] > 0 or fb_tally['orphan'] or fb_tally['missing']:
            print("\n" + "─" * 50)
            print_colored("  📘 FACEBOOK", COLORS.MAGENTA, bold=True)
            print("─" * 50)
            print(f"  Total entries : {fb_tally['total_entries']} (videos: {fb_tally['by_type']['video']}, photos: {fb_tally['by_type']['photo']})")
            print(f"  Files on disk : {len(fb_tally['files_found'])}")
            if fb_tally['missing']:
                print_colored(f"  ❌ Missing      : {len(fb_tally['missing'])} entries", COLORS.RED)
            if fb_tally['orphan']:
                print_colored(f"  🗑️ Orphan       : {len(fb_tally['orphan'])} files", COLORS.YELLOW)
            if not fb_tally['missing'] and not fb_tally['orphan']:
                print_colored("  ✅ All Facebook entries are synced!", COLORS.GREEN)

        # ---- Always show sub‑menu ----
        print("\nWhat would you like to do?")
        print("  1. Show details of missing records")
        print("  2. Show details of orphan files")
        print("  3. Show details of mismatched records")
        print("  4. Show details of unresolved records")
        print("  5. Move all orphan files to trash")
        print("  6. Mark missing records (add note 'FILE MISSING')")
        print("  7. Refresh statistics (re-scan files)")
        print("  8. " + color_text("Find content mismatches (wrong video in correct location)", COLORS.WHITE))
        print("  9. " + color_text("Download missing videos", COLORS.GREEN))
        print(" 10. " + color_text("Auto-fix all mismatched records", COLORS.GREEN))
        print(" 11. " + color_text("Compress 720p+ videos to 480p H.264 (Auto-sync DB)", COLORS.GREEN))
        print(" 12. " + color_text("Share / Restore video file (toggle)", COLORS.WHITE))
        print("  0. Return to main menu")

        choice = input(color_text("Choose an option (0-11): ", COLORS.MAGENTA)).strip()

        if choice == '1':
            if missing:
                print("\n--- MISSING RECORDS ---")
                for r in missing:
                    print(f"  {r['syllabus_id']} | {r['subject']} | {r['video_id']}")
            else:
                print("No missing records.")
            input("\nPress Enter to continue...")

        elif choice == '2':
            if orphan:
                print("\n--- ORPHAN FILES ---")
                for i, fp in enumerate(orphan):
                    if i >= 20:
                        print(f"  ... and {len(orphan)-20} more")
                        break
                    print(f"  {fp}")
            else:
                print("No orphan files.")
            input("\nPress Enter to continue...")

        elif choice == '3':
            if mismatched:
                print("\n--- MISMATCHED RECORDS ---")
                for rec in mismatched:
                    found = [fp for fp, v in file_to_vid.items() if v == rec['video_id']]
                    expected = expected_paths.get(rec['video_id'])
                    # Get the original descriptive name for display
                    original_name = rec.get('original_filename')
                    if not original_name:
                        # Fallback: construct from fields
                        parts = [
                            rec.get('syllabus_id', ''),
                            rec.get('chapter', ''),
                            rec.get('subject', ''),
                            rec.get('lecturer', ''),
                            rec.get('nepali_date', ''),
                            rec.get('time', '')
                        ]
                        original_name = " || ".join([p for p in parts if p]) or rec.get('video_title', 'No title')
                    print(f"  {rec['syllabus_id']} | {rec['subject']} | {rec['video_id']}")
                    if expected:
                        # Show only the basename of the expected path for clarity
                        print(f"    Expected: {os.path.basename(expected)}")
                    for f in found:
                        # Show the original name and the actual folder path (not the full file name)
                        actual_dir = os.path.dirname(f)
                        print(f"    Found:   {original_name}")
                        print(f"    Location: {actual_dir}")
            else:
                print("No mismatched records.")
            input("\nPress Enter to continue...")

        elif choice == '4':
            if unresolved:
                print("\n--- UNRESOLVED RECORDS ---")
                for r in records:
                    if expected_paths.get(r['video_id']) is None:
                        print(f"  {r['syllabus_id']} | {r['subject']} | {r['video_id']}")
            else:
                print("No unresolved records.")
            input("\nPress Enter to continue...")

        elif choice == '5':
            if not orphan:
                print("No orphan files.")
                input("\nPress Enter to continue...")
                continue
            confirm = input(color_text(f"Move {len(orphan)} orphan files to trash? (y/n): ", COLORS.MAGENTA)).strip().lower()
            if confirm == 'y':
                count = 0
                for fp in orphan:
                    try:
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        base = os.path.basename(fp)
                        trash_name = f"{timestamp}_{base}"
                        trash_path = os.path.join(TRASH_DIR, trash_name)
                        shutil.move(fp, trash_path)
                        count += 1
                    except Exception as e:
                        print_colored(f"[!] Failed to move {fp}: {e}", COLORS.RED)
                print_colored(f"[✓] Moved {count} orphan files to trash.", COLORS.GREEN)
            input("\nPress Enter to continue...")

        elif choice == '6':
            if not missing:
                print("No missing records.")
                input("\nPress Enter to continue...")
                continue
            conn2 = get_connection()
            cursor2 = conn2.cursor()
            for r in missing:
                notes = r.get('notes') or ''
                if 'FILE MISSING' not in notes:
                    new_notes = (notes + ' | FILE MISSING').strip()
                    cursor2.execute(f"UPDATE {TABLE_NAME} SET notes = %s WHERE id = %s", (new_notes, r['id']))
            conn2.commit()
            cursor2.close()
            conn2.close()
            print_colored(f"[✓] Marked {len(missing)} missing records with note 'FILE MISSING'.", COLORS.GREEN)
            input("\nPress Enter to continue...")

        elif choice == '7':
            print_colored("Refreshing statistics...", COLORS.BLUE)
            continue

        elif choice == '8':
            mismatches = find_content_mismatches(verbose=True)
            if not mismatches:
                print_colored("[✓] No content mismatches found. All files match their hashes.", COLORS.GREEN)
            else:
                print_colored(f"[!] Found {len(mismatches)} content mismatches:", COLORS.YELLOW)
                print("═" * 60)
                for i, item in enumerate(mismatches, 1):
                    rec = item['record']
                    print(f"\n--- Mismatch #{i} ---")
                    print(f"  ID          : {rec['id']}")
                    print(f"  Syllabus    : {rec['syllabus_id']}")
                    print(f"  Subject     : {rec['subject']}")
                    print(f"  Video ID    : {rec['video_id']}")
                    print(f"  Expected Dir: {item['expected_dir']}")
                    print(f"  Expected Filename: {item['expected_filename']}.*")
                    print(f"  Actual File : {item['file_path']}")
                    print(f"  Stored Hash : {item['stored_hash'][:8]}... (expected)")
                    print(f"  Actual Hash : {item['actual_hash'][:8]}... (found)")
                    print("─" * 60)

                action = input(color_text("\nHow to handle these mismatches? (f=fix each, a=fix all, s=skip): ", COLORS.MAGENTA)).strip().lower()
                if action == 's':
                    print_colored("Skipped.", COLORS.YELLOW)
                elif action == 'a':
                    print_colored("Fixing all mismatches...", COLORS.BLUE)
                    for item in mismatches:
                        rec = item['record']
                        trash_video_by_record(rec)
                        conn = get_connection()
                        cursor = conn.cursor()
                        cursor.execute(f"UPDATE {TABLE_NAME} SET file_hash = NULL WHERE id = %s", (rec['id'],))
                        conn.commit()
                        cursor.close()
                        conn.close()
                        print(f"  Trashed and cleared hash for {rec['syllabus_id']}")
                    print_colored(f"[✓] Fixed all {len(mismatches)} mismatches.", COLORS.GREEN)
                elif action == 'f':
                    fixed = 0
                    for item in mismatches:
                        rec = item['record']
                        print(f"\n--- Fixing {rec['syllabus_id']} ---")
                        print(f"  File: {item['file_path']}")
                        confirm = input(color_text("  Move this file to trash and clear its hash? (y/n): ", COLORS.MAGENTA)).strip().lower()
                        if confirm == 'y':
                            trash_video_by_record(rec)
                            conn = get_connection()
                            cursor = conn.cursor()
                            cursor.execute(f"UPDATE {TABLE_NAME} SET file_hash = NULL WHERE id = %s", (rec['id'],))
                            conn.commit()
                            cursor.close()
                            conn.close()
                            print_colored("  [✓] Trashed and cleared hash.", COLORS.GREEN)
                            fixed += 1
                        else:
                            print_colored("  Skipped.", COLORS.YELLOW)
                    print_colored(f"[✓] Fixed {fixed} out of {len(mismatches)} mismatches.", COLORS.GREEN)
                else:
                    print_colored("No action taken.", COLORS.YELLOW)
            input("\nPress Enter to continue...")

        elif choice == '9':
            from .crud import download_video

            if not missing:
                print_colored("[i] No missing records to download.", COLORS.YELLOW)
                input("\nPress Enter to continue...")
                continue

            print_colored(f"Found {len(missing)} missing records.", COLORS.BLUE)
            mode = input(color_text("Download all missing videos automatically? (y/n, or 'q' to quit): ", COLORS.MAGENTA)).strip().lower()

            if mode == 'q':
                print_colored("Cancelled.", COLORS.YELLOW)
                input("\nPress Enter to continue...")
                continue
            elif mode == 'y':
                # Auto mode: download all silently
                print_colored("[i] Downloading all missing videos automatically...", COLORS.GREEN)
                downloaded = 0
                for rec in missing:
                    print(f"  Downloading {rec['syllabus_id']} | {rec['subject']} ...", end=" ")
                    try:
                        download_video(rec, video_id_to_download=rec['video_id'], silent=True)
                        downloaded += 1
                        print_colored("✓", COLORS.GREEN)
                    except Exception as e:
                        print_colored(f"✗ (error: {e})", COLORS.RED)
                print_colored(f"\n[✓] Downloaded {downloaded} out of {len(missing)} missing records.", COLORS.GREEN)
                input("\nPress Enter to continue...")
                continue
            else:
                # Interactive mode: current per-file prompts
                for rec in missing:
                    print(f"\n--- Record: {rec['syllabus_id']} | {rec['subject']} | {rec['video_id']} ---")
                    action = input(color_text("Download this video? (y/n, custom ID, or 'q' to quit): ", COLORS.MAGENTA)).strip()
                    if action.lower() in ('q', 'quit', 'abort'):
                        print_colored("Aborting download process.", COLORS.YELLOW)
                        break
                    if action.lower() == 'y':
                        vid_to_dl = rec['video_id']
                    elif action and action.lower() != 'n':
                        vid_to_dl = extract_video_id(action) or action
                    else:
                        print_colored("Skipping.", COLORS.YELLOW)
                        continue
                    download_video(rec, video_id_to_download=vid_to_dl, silent=False)
                input("\nPress Enter to continue...")

        elif choice == '10':
            if not mismatched:
                print_colored("[i] No mismatched records to fix.", COLORS.YELLOW)
                input("\nPress Enter to continue...")
                continue

            print_colored(f"Found {len(mismatched)} mismatched records. Attempting to auto-fix...", COLORS.BLUE)
            from .crud import organize_video
            fixed = 0
            failed = 0

            for rec in mismatched:
                print(f"\n--- Fixing {rec['syllabus_id']} | {rec['subject']} ---")
                # 1) Re-detect paper based on current subject/syllabus/chapter
                correct_paper = detect_paper(rec['subject'], rec['syllabus_id'], rec.get('chapter'), interactive=False)
                if not correct_paper:
                    print_colored(f"[!] Could not detect paper for {rec['syllabus_id']}. Skipping.", COLORS.YELLOW)
                    failed += 1
                    continue

                # 2) If paper differs, update the database
                if rec.get('paper') != correct_paper:
                    conn = get_connection()
                    cursor = conn.cursor()
                    cursor.execute(f"UPDATE {TABLE_NAME} SET paper = %s WHERE video_id = %s",
                                   (correct_paper, rec['video_id']))
                    conn.commit()
                    cursor.close()
                    conn.close()
                    print_colored(f"  [✓] Updated paper to {correct_paper}", COLORS.GREEN)

                # 3) Move the file to the correct folder (using organize_video)
                result = organize_video(rec, overwrite=False, interactive=False)
                if result:
                    print_colored(f"  [✓] File moved successfully", COLORS.GREEN)
                    fixed += 1
                else:
                    print_colored(f"  [✗] Failed to move file", COLORS.RED)
                    failed += 1

            print_colored(f"\n[✓] Auto-fix complete: {fixed} fixed, {failed} failed.", COLORS.GREEN)
            print_colored("[i] Refreshing statistics...", COLORS.BLUE)
            continue  # This will re-run the while loop (refresh tally)

        elif choice == '11':
            from .file_compressor import compress_library_to_480p, compress_single_by_id, list_largest_files

            print_colored("\n[!] WARNING: This will re-encode videos to 480p H.264 (CRF 28).", COLORS.YELLOW)
            print_colored("[!] For the entire library, this takes ~30–40 hours.", COLORS.YELLOW)
            print_colored("[!] Make sure you have at least 5 GB free disk space.", COLORS.YELLOW)

            prompt = ("Enter a specific Video ID, Mirror ID, or file hash (MD5) to compress only that one\n"
                      "or press 'y' to list the 5 largest files, or press Enter for ALL: ")
            user_input = input(color_text(prompt, COLORS.MAGENTA)).strip()

            if user_input.lower() == 'y':
                # Show largest 5 files and get the list
                file_list = list_largest_files(5)
                # Ask for selection
                selection = input(color_text("Enter the number (1-5) or hash to compress: ", COLORS.MAGENTA)).strip()
                if not selection:
                    print_colored("Cancelled.", COLORS.YELLOW)
                elif selection.isdigit():
                    idx = int(selection)
                    if 1 <= idx <= len(file_list):
                        hash_to_compress = file_list[idx-1]['hash']
                        result = compress_single_by_id(hash_to_compress)
                        if result['status'] == 'compressed':
                            print_colored(f"[✓] {result['message']}", COLORS.GREEN)
                        elif result['status'] == 'skipped':
                            print_colored(f"[i] {result['message']}", COLORS.YELLOW)
                        else:
                            print_colored(f"[!] Failed: {result['message']}", COLORS.RED)
                    else:
                        print_colored(f"[!] Invalid number. Choose 1-{len(file_list)}", COLORS.RED)
                else:
                    # Treat as hash
                    result = compress_single_by_id(selection)
                    if result['status'] == 'compressed':
                        print_colored(f"[✓] {result['message']}", COLORS.GREEN)
                    elif result['status'] == 'skipped':
                        print_colored(f"[i] {result['message']}", COLORS.YELLOW)
                    else:
                        print_colored(f"[!] Failed: {result['message']}", COLORS.RED)

            elif user_input:
                # Compress a single file (by ID or hash)
                result = compress_single_by_id(user_input)
                if result['status'] == 'compressed':
                    print_colored(f"[✓] {result['message']}", COLORS.GREEN)
                elif result['status'] == 'skipped':
                    print_colored(f"[i] {result['message']}", COLORS.YELLOW)
                else:
                    print_colored(f"[!] Failed: {result['message']}", COLORS.RED)

            else:
                # Batch: compress all 720p+ videos
                confirm = input(color_text("Compress ALL 720p+ videos? (y/n): ", COLORS.MAGENTA)).strip().lower()
                if confirm == 'y':
                    compress_library_to_480p()
                    print_colored("[i] Compression complete. Refreshing tally...", COLORS.BLUE)
                else:
                    print_colored("Cancelled.", COLORS.YELLOW)

            continue

        elif choice == '12':
            from .file_sharing import share_toggle, list_shared_files, restore_shared_by_index

            identifier = input(color_text("Enter Video ID, Mirror ID, or file hash (or press Enter to list shared files): ", COLORS.MAGENTA)).strip()
            if not identifier:
                list_shared_files()
                restore_choice = input(color_text("Enter number to restore (or press Enter to cancel): ", COLORS.MAGENTA)).strip()
                if restore_choice.isdigit():
                    restore_shared_by_index(int(restore_choice))
            else:
                result = share_toggle(identifier)
                if result['status'] in ('shared', 'restored'):
                    print_colored(f"[✓] {result['message']}", COLORS.GREEN)
                elif result['status'] == 'cancelled':
                    print_colored(f"[i] {result['message']}", COLORS.YELLOW)
                else:
                    print_colored(f"[!] {result['message']}", COLORS.RED)
            continue
        elif choice == '0':
            print("Returning to main menu...")
            break

        else:
            print_colored("[!] Invalid choice.", COLORS.RED)
            input("\nPress Enter to continue...")

def get_tally_data():
    """Return tally data as dict for web interface."""
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(f"SELECT * FROM {TABLE_NAME}")
    records = cursor.fetchall()
    cursor.close()
    conn.close()

    record_by_vid = {r['video_id']: r for r in records}
    expected_paths = {}
    for r in records:
        target_dir, fname = get_target_path(r)
        if target_dir and fname:
            expected_paths[r['video_id']] = os.path.join(target_dir, fname)
        else:
            expected_paths[r['video_id']] = None

    video_exts = ('.mp4', '.mkv', '.webm', '.avi', '.mov')
    all_files = []
    facebook_dir = os.path.join(ROOT_DIR, 'facebook')
    for root, _, files in os.walk(ROOT_DIR):
        if root.startswith(facebook_dir):
            continue
        for f in files:
            if f.lower().endswith(video_exts):
                all_files.append(os.path.join(root, f))
    download_dir = './downloads'
    if os.path.exists(download_dir):
        for f in os.listdir(download_dir):
            if f.lower().endswith(video_exts):
                all_files.append(os.path.join(download_dir, f))

    file_to_vid = {}
    for filepath in all_files:
        basename = os.path.basename(filepath)
        vid = None
        for r in records:
            if r['video_id'] in basename:
                vid = r['video_id']
                break
            if r.get('syllabus_id') and r['syllabus_id'] in basename:
                vid = r['video_id']
                break
        if vid:
            file_to_vid[filepath] = vid

    missing = []
    orphan = []
    mismatched = []

    for vid, rec in record_by_vid.items():
        found_files = [fp for fp, v in file_to_vid.items() if v == vid]
        if not found_files:
            missing.append(rec)
        else:
            expected = expected_paths.get(vid)
            if expected:
                expected_base = os.path.splitext(expected)[0]
                matched = False
                for fp in found_files:
                    if os.path.splitext(fp)[0] == expected_base:
                        matched = True
                        break
                if not matched:
                    mismatched.append({'record': rec, 'files': found_files})
            else:
                mismatched.append({'record': rec, 'files': found_files})

    for fp in all_files:
        if fp not in file_to_vid:
            orphan.append(fp)

    return {
        'total_records': len(records),
        'matched': len(records) - len(missing),
        'missing': len(missing),
        'missing_list': missing,
        'orphan': len(orphan),
        'orphan_list': orphan,
        'mismatched': len(mismatched),
        'mismatched_list': mismatched,
    }

def trash_video_by_record(record):
    """Move video file for given record to trash without prompts."""
    target_dir, filename_base = get_target_path(record)
    if not target_dir:
        return False
    possible_files = []
    if os.path.exists(target_dir):
        for f in os.listdir(target_dir):
            if f.startswith(filename_base):
                possible_files.append(os.path.join(target_dir, f))
    if not possible_files:
        for root, _, files in os.walk(ROOT_DIR):
            for f in files:
                if record['video_id'] in f or record['syllabus_id'] in f:
                    possible_files.append(os.path.join(root, f))
                    break
    if not possible_files:
        return False
    source_file = possible_files[0]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = os.path.basename(source_file)
    trash_name = f"{timestamp}_{base}"
    trash_path = os.path.join(TRASH_DIR, trash_name)
    try:
        shutil.move(source_file, trash_path)
        return True
    except Exception:
        return False

def scan_duplicates():
    """
    Full scan: compute MD5 for every video file and store in hash_cache with status='active'.
    Also removes entries for files that no longer exist.
    """
    print("\n" + "═" * 50)
    print_colored("  SCAN FOR DUPLICATE VIDEOS", COLORS.CYAN, bold=True)
    print("═" * 50)

    # Find all video files
    video_exts = ('.mp4', '.mkv', '.webm', '.avi', '.mov')
    all_files = []
    for root, _, files in os.walk(ROOT_DIR):
        for f in files:
            if f.lower().endswith(video_exts):
                all_files.append(os.path.join(root, f))

    print(f"Found {len(all_files)} video files. Computing hashes...")

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("START TRANSACTION")
    cursor.execute("DELETE FROM hash_cache")
    print("  [cache] Cleared existing cache.")

    total = len(all_files)
    for i, fp in enumerate(all_files, 1):
        if i % 10 == 0 or i == total:
            print(f"  [{i}/{total}] {os.path.basename(fp)}", end="\r")
        h = compute_md5(fp)
        cursor.execute("""
            INSERT INTO hash_cache (file_path, file_hash, status, last_scan)
            VALUES (%s, %s, 'active', NOW())
            ON DUPLICATE KEY UPDATE file_hash = VALUES(file_hash), status = 'active', last_scan = NOW()
        """, (fp, h))
        print(f"  [computed] {os.path.basename(fp)}")
    conn.commit()
    cursor.close()
    conn.close()
    print("\n")

    # Show duplicate groups
    conn2 = get_connection()
    cur2 = conn2.cursor(dictionary=True)
    cur2.execute("""
        SELECT file_hash, GROUP_CONCAT(file_path SEPARATOR '||') as paths
        FROM hash_cache
        WHERE status = 'active'
        GROUP BY file_hash
        HAVING COUNT(*) > 1
    """)
    rows = cur2.fetchall()
    cur2.close()
    conn2.close()

    if not rows:
        print_colored("No exact duplicate files found.", COLORS.GREEN)
        return

    print_colored(f"Found {len(rows)} groups of duplicates:", COLORS.YELLOW)
    for i, row in enumerate(rows, 1):
        paths = row['paths'].split('||')
        print(f"\nGroup #{i} (hash: {row['file_hash'][:8]}...):")
        for p in paths:
            print(f"  [duplicate] {p}")

    # Also check duplicate records in DB
    conn3 = get_connection()
    cur3 = conn3.cursor(dictionary=True)
    cur3.execute(f"SELECT video_id, syllabus_id, file_hash FROM {TABLE_NAME} WHERE file_hash IS NOT NULL")
    records = cur3.fetchall()
    cur3.close()
    conn3.close()
    db_hash_map = {}
    for rec in records:
        db_hash_map.setdefault(rec['file_hash'], []).append(rec)
    print("\n--- Duplicate records in DB (same hash) ---")
    dup_records = {h: recs for h, recs in db_hash_map.items() if len(recs) > 1}
    if dup_records:
        for h, recs in dup_records.items():
            print(f"  Hash: {h[:8]}... -> {len(recs)} records:")
            for rec in recs:
                print(f"    {rec['video_id']} | {rec['syllabus_id']}")
    else:
        print("No duplicate records in DB.")

    print("\n[info] Hash cache rebuilt. Use option 23 to resolve duplicates.")

def resolve_duplicates():
    """
    Uses the hash_cache (status='active') to find duplicates.
    Lists all duplicate groups and files, then asks for confirmation.
    Keeps one file per group and moves the rest to trash, updating status to 'trashed'.
    Also cleans up stale cache entries for missing files.
    """
    print("\n" + "═" * 50)
    print_colored("  AUTO-RESOLVE DUPLICATE VIDEOS", COLORS.CYAN, bold=True)
    print("═" * 50)

    # Fetch all active files from cache
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT file_path, file_hash FROM hash_cache WHERE status = 'active'")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    if not rows:
        print_colored("[i] No active files in cache. Run option 22 first.", COLORS.YELLOW)
        return

    # --- Clean stale entries: remove or mark as 'deleted' if file doesn't exist ---
    stale_paths = []
    for row in rows:
        if not os.path.exists(row['file_path']):
            stale_paths.append(row['file_path'])

    if stale_paths:
        print_colored(f"[i] Found {len(stale_paths)} stale cache entries (files missing). Removing them.", COLORS.YELLOW)
        conn2 = get_connection()
        cur2 = conn2.cursor()
        for fp in stale_paths:
            cur2.execute("DELETE FROM hash_cache WHERE file_path = %s", (fp,))
        conn2.commit()
        cur2.close()
        conn2.close()
        # Refresh rows after cleaning
        conn3 = get_connection()
        cur3 = conn3.cursor(dictionary=True)
        cur3.execute("SELECT file_path, file_hash FROM hash_cache WHERE status = 'active'")
        rows = cur3.fetchall()
        cur3.close()
        conn3.close()
        if not rows:
            print_colored("[i] No active files remain after cleaning. Nothing to do.", COLORS.GREEN)
            return

    # Build hash -> list of file paths
    hash_map = {}
    for row in rows:
        hash_map.setdefault(row['file_hash'], []).append(row['file_path'])

    duplicate_groups = {h: paths for h, paths in hash_map.items() if len(paths) > 1}
    if not duplicate_groups:
        print_colored("No duplicate files found. Nothing to do.", COLORS.GREEN)
        return

    total_duplicates = sum(len(paths) for paths in duplicate_groups.values()) - len(duplicate_groups)
    print_colored(f"Found {len(duplicate_groups)} duplicate groups, affecting {total_duplicates} extra files.", COLORS.YELLOW)

    # List all duplicate groups
    print("\nDuplicate groups:")
    group_num = 1
    for h, paths in duplicate_groups.items():
        print(f"\nGroup #{group_num} (hash: {h[:8]}...):")
        for fp in paths:
            print(f"  [candidate] {fp}")
        group_num += 1

    confirm = input(color_text("\nMove duplicate files to trash? (y/n): ", COLORS.MAGENTA)).strip().lower()
    if confirm != 'y':
        print_colored("Aborted.", COLORS.YELLOW)
        return

    # Fetch all records for reference
    conn4 = get_connection()
    cur4 = conn4.cursor(dictionary=True)
    cur4.execute(f"SELECT * FROM {TABLE_NAME}")
    db_rows = cur4.fetchall()
    cur4.close()
    conn4.close()

    kept = []
    trashed = []
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    trashed_paths = []

    group_num = 1
    for h, paths in duplicate_groups.items():
        print(f"\nProcessing group #{group_num} (hash: {h[:8]}...)")
        file_info = []
        for fp in paths:
            # Skip if file doesn't exist (should not happen after cleaning, but just in case)
            if not os.path.exists(fp):
                print(f"  [skipping] {fp} (file missing)")
                continue

            rec = None
            basename = os.path.basename(fp)
            for r in db_rows:
                if r['video_id'] in basename or (r.get('syllabus_id') and r['syllabus_id'] in basename):
                    rec = r
                    break
            is_expected = False
            if rec and rec.get('syllabus_id') and rec['syllabus_id'] in fp:
                is_expected = True
            mtime = os.path.getmtime(fp)
            filename_len = len(os.path.basename(fp))
            file_info.append({
                'path': fp,
                'record': rec,
                'is_expected': is_expected,
                'mtime': mtime,
                'filename_len': filename_len
            })
            print(f"  [candidate] {os.path.basename(fp)} (expected: {is_expected})")

        if not file_info:
            print(f"  [skip] No valid files in this group (all missing).")
            group_num += 1
            continue

        file_info.sort(key=lambda x: (not x['is_expected'], -x['mtime'], -x['filename_len']))
        keeper = file_info[0]
        kept.append(keeper['path'])
        print(f"  [kept] {os.path.basename(keeper['path'])}")

        for info in file_info[1:]:
            trash_name = f"{timestamp}_{os.path.basename(info['path'])}"
            trash_path = os.path.join(TRASH_DIR, trash_name)
            try:
                shutil.move(info['path'], trash_path)
                # Insert into trash_entries
                conn5 = get_connection()
                cur5 = conn5.cursor()
                record_id = info['record']['id'] if info['record'] else None
                cur5.execute("""
                    INSERT INTO trash_entries (original_path, record_id, trash_filename)
                    VALUES (%s, %s, %s)
                """, (info['path'], record_id, os.path.basename(trash_path)))
                conn5.commit()
                cur5.close()
                conn5.close()
                trashed.append(info['path'])
                trashed_paths.append(info['path'])
                print(f"  [trashed] {os.path.basename(info['path'])} -> {trash_path}")
            except Exception as e:
                print_colored(f"  [failed] {os.path.basename(info['path'])}: {e}", COLORS.RED)

        group_num += 1

    # Update status of trashed files to 'trashed'
    if trashed_paths:
        conn6 = get_connection()
        cur6 = conn6.cursor()
        for fp in trashed_paths:
            cur6.execute("UPDATE hash_cache SET status = 'trashed' WHERE file_path = %s", (fp,))
        conn6.commit()
        cur6.close()
        conn6.close()
        print_colored(f"[i] Updated {len(trashed_paths)} files to 'trashed' in cache.", COLORS.BLUE)

    print("\n" + "═" * 50)
    print_colored("  SUMMARY", COLORS.CYAN, bold=True)
    print(f"  Kept  : {len(kept)} files (primary copies)")
    print(f"  Trashed: {len(trashed)} duplicate files")
    if trashed:
        print_colored(f"  You can restore them using option 18.", COLORS.BLUE)
    print("═" * 50)

def backfill_original_filenames():
    """
    Backfill the original_filename column for records that have NULL.
    Constructs the descriptive name from syllabus_id, chapter, subject, lecturer, nepali_date, time.
    """
    print("\n" + "═" * 50)
    print_colored("  BACKFILL ORIGINAL FILENAMES", COLORS.CYAN, bold=True)
    print("═" * 50)

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(f"SELECT id, video_id, syllabus_id, subject, chapter, lecturer, nepali_date, time FROM {TABLE_NAME} WHERE original_filename IS NULL")
    records = cursor.fetchall()
    cursor.close()
    conn.close()

    if not records:
        print_colored("[i] No records need backfilling.", COLORS.GREEN)
        return

    print(f"[i] Found {len(records)} records without original_filename.")
    confirm = input(color_text("Proceed to set original_filename for all? (y/n): ", COLORS.MAGENTA)).strip().lower()
    if confirm != 'y':
        print_colored("Cancelled.", COLORS.YELLOW)
        return

    updated = 0
    for rec in records:
        parts = [
            rec.get('syllabus_id', ''),
            rec.get('chapter', ''),
            rec.get('subject', ''),
            rec.get('lecturer', ''),
            rec.get('nepali_date', ''),
            rec.get('time', '')
        ]
        # Filter out empty parts
        name = " || ".join([p for p in parts if p])
        if not name:
            name = rec.get('video_title') or "Unknown"

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(f"UPDATE {TABLE_NAME} SET original_filename = %s WHERE id = %s", (name, rec['id']))
        conn.commit()
        cursor.close()
        conn.close()
        updated += 1
        print(f"  Updated {rec['video_id']} -> {name}")

    print_colored(f"[✓] Updated {updated} records.", COLORS.GREEN)

def backfill_hash_naming():
    """
    One‑time migration: rename all existing video files to their MD5 hash,
    and store their current descriptive name in original_filename.
    """
    print("\n" + "═" * 50)
    print_colored("  BACKFILL HASH NAMING", COLORS.CYAN, bold=True)
    print("═" * 50)
    print("[i] This will rename all organised video files to their MD5 hash.")
    print("[i] Original names will be stored in the database as 'original_filename'.")
    confirm = input(color_text("Proceed? (y/n): ", COLORS.MAGENTA)).strip().lower()
    if confirm != 'y':
        print_colored("Cancelled.", COLORS.YELLOW)
        return

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(f"SELECT * FROM {TABLE_NAME}")
    records = cursor.fetchall()
    cursor.close()
    conn.close()

    renamed = 0
    skipped = 0
    not_found = 0
    total = len(records)

    for idx, rec in enumerate(records, 1):
        print(f"  Processing {idx}/{total}: {rec['syllabus_id']} ...", end="\r")

        # Locate the current file
        target_dir, filename_base = get_target_path(rec, interactive=False)
        if not target_dir or not filename_base:
            skipped += 1
            continue

        # Try expected path first
        import glob
        pattern = os.path.join(target_dir, filename_base + '.*')
        matches = glob.glob(pattern)
        if not matches:
            # Search whole ROOT_DIR by video_id or syllabus_id
            found = None
            for root, _, files in os.walk(ROOT_DIR):
                for f in files:
                    if f.lower().endswith(('.mp4', '.mkv', '.webm', '.avi', '.mov')):
                        if rec['video_id'] in f or (rec['syllabus_id'] and rec['syllabus_id'] in f):
                            found = os.path.join(root, f)
                            break
                if found:
                    break
            if not found:
                not_found += 1
                continue
            file_path = found
        else:
            file_path = matches[0]

        # Check if already named as hash (32 hex chars before extension)
        base_name = os.path.basename(file_path)
        name_no_ext, ext = os.path.splitext(base_name)
        if re.fullmatch(r'[a-fA-F0-9]{32}', name_no_ext):
            # Already hash-named – just store original_filename if missing
            if not rec.get('original_filename'):
                conn2 = get_connection()
                cur2 = conn2.cursor()
                cur2.execute(f"UPDATE {TABLE_NAME} SET original_filename = %s WHERE video_id = %s",
                             (filename_base, rec['video_id']))
                conn2.commit()
                cur2.close()
                conn2.close()
                print(f"  Stored original name for {rec['syllabus_id']} (already hash‑named)")
            renamed += 1
            continue

        # Compute hash
        file_hash = compute_md5(file_path)
        new_name = f"{file_hash}{ext}"
        new_path = os.path.join(target_dir, new_name)

        # Check if new path already exists (shouldn't)
        if os.path.exists(new_path):
            print_colored(f"[!] Target exists: {new_path} – skipping", COLORS.YELLOW)
            skipped += 1
            continue

        try:
            shutil.move(file_path, new_path)
            conn2 = get_connection()
            cur2 = conn2.cursor()
            cur2.execute(f"""
                UPDATE {TABLE_NAME}
                SET file_hash = %s, original_filename = %s
                WHERE video_id = %s
            """, (file_hash, filename_base, rec['video_id']))
            conn2.commit()
            cur2.close()
            conn2.close()

            # Update hash_cache
            conn2 = get_connection()
            cur2 = conn2.cursor()
            cur2.execute("""
                INSERT INTO hash_cache (file_path, file_hash, status, last_scan)
                VALUES (%s, %s, 'active', NOW())
                ON DUPLICATE KEY UPDATE file_hash = VALUES(file_hash), status = 'active', last_scan = NOW()
            """, (new_path, file_hash))
            conn2.commit()
            cur2.close()
            conn2.close()

            print(f"  ✓ Renamed {os.path.basename(file_path)} -> {new_name}")
            renamed += 1
        except Exception as e:
            print_colored(f"[!] Failed for {rec['syllabus_id']}: {e}", COLORS.RED)
            skipped += 1

    print(f"\n[✓] Done. Renamed: {renamed}, Skipped: {skipped}, Not found: {not_found} out of {total}.")
    print("[i] Now run option 19 (Tally) – everything should be perfectly synced.")

def backfill_hashes():
    print("\n" + "═" * 50)
    print_colored("  BACKFILL FILE HASHES", COLORS.CYAN, bold=True)
    print("═" * 50)

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(f"SELECT * FROM {TABLE_NAME}")
    records = cursor.fetchall()
    cursor.close()

    if not records:
        print_colored("[i] No records in database.", COLORS.YELLOW)
        return

    # Pre-fetch hash_cache
    conn2 = get_connection()
    cur2 = conn2.cursor(dictionary=True)
    cur2.execute("SELECT file_path, file_hash FROM hash_cache WHERE status = 'active'")
    cache_map = {row['file_path']: row['file_hash'] for row in cur2.fetchall()}
    cur2.close()
    conn2.close()

    updated = 0
    skipped = 0
    total = len(records)

    # Video file extensions
    video_exts = ('.mp4', '.mkv', '.webm', '.avi', '.mov')

    for idx, rec in enumerate(records, 1):
        print(f"  Processing {idx}/{total}: {rec['syllabus_id']} ...", end="\r")

        # First try the expected target path
        target_dir, filename_base = get_target_path(rec, interactive=False)
        file_path = None

        if target_dir and filename_base:
            import glob
            pattern = os.path.join(target_dir, filename_base + '.*')
            matches = glob.glob(pattern)
            if matches:
                file_path = matches[0]

        # If not found, search the entire ROOT_DIR
        if not file_path:
            for root, _, files in os.walk(ROOT_DIR):
                for f in files:
                    if not f.lower().endswith(video_exts):
                        continue
                    full_path = os.path.join(root, f)
                    # Match by video_id OR syllabus_id in the full path
                    if rec['video_id'] in full_path or (rec.get('syllabus_id') and rec['syllabus_id'] in full_path):
                        file_path = full_path
                        break
                if file_path:
                    break

        if not file_path:
            skipped += 1
            continue

        # Compute hash (use cache if available)
        file_hash = cache_map.get(file_path)
        if file_hash is None:
            try:
                file_hash = compute_md5(file_path)
                # Insert/update cache
                conn3 = get_connection()
                cur3 = conn3.cursor()
                cur3.execute("""
                    INSERT INTO hash_cache (file_path, file_hash, status, last_scan)
                    VALUES (%s, %s, 'active', NOW())
                    ON DUPLICATE KEY UPDATE file_hash = VALUES(file_hash), status = 'active', last_scan = NOW()
                """, (file_path, file_hash))
                conn3.commit()
                cur3.close()
                conn3.close()
            except Exception as e:
                print_colored(f"[!] Failed to compute hash for {rec['syllabus_id']}: {e}", COLORS.RED)
                skipped += 1
                continue

        # Update record
        try:
            conn4 = get_connection()
            cur4 = conn4.cursor()
            cur4.execute(f"UPDATE {TABLE_NAME} SET file_hash = %s WHERE video_id = %s",
                         (file_hash, rec['video_id']))
            conn4.commit()
            cur4.close()
            conn4.close()
            updated += 1
            print(f"  ✓ Updated hash for {rec['syllabus_id']} (found: {file_path})")
        except Exception as e:
            print_colored(f"[!] Failed to update DB for {rec['syllabus_id']}: {e}", COLORS.RED)
            skipped += 1

    print(f"\n[✓] Backfill complete: {updated} records updated, {skipped} skipped out of {total} total.")

def remove_empty_directories(path, stop_root=ROOT_DIR):
    """
    Remove empty directories upwards from 'path' until reaching stop_root.
    Ignores common hidden/system files when checking emptiness.
    """
    path = os.path.abspath(path)
    stop_root = os.path.abspath(stop_root)
    IGNORE_FILES = {'.DS_Store', 'Thumbs.db', 'desktop.ini'}

    while path != stop_root and os.path.exists(path):
        try:
            contents = os.listdir(path)
            real_contents = [f for f in contents if f not in IGNORE_FILES]
            if not real_contents:
                os.rmdir(path)
                print_colored(f"[✓] Removed empty directory: {path}", COLORS.BLUE)
                path = os.path.dirname(path)
            else:
                break
        except OSError:
            break

def clean_all_empty_directories():
    """
    Walk through ROOT_DIR and remove all empty directories (ignoring .DS_Store etc.)
    """
    print("\n" + "═" * 50)
    print_colored("  CLEAN EMPTY DIRECTORIES", COLORS.CYAN, bold=True)
    print("═" * 50)
    count = 0
    IGNORE_FILES = {'.DS_Store', 'Thumbs.db', 'desktop.ini'}

    for root, dirs, files in os.walk(ROOT_DIR, topdown=False):
        real_files = [f for f in files if f not in IGNORE_FILES]
        if not real_files and not dirs:
            try:
                os.rmdir(root)
                print(f"  Removed: {root}")
                count += 1
            except OSError:
                pass
    print_colored(f"[✓] Removed {count} empty directories.", COLORS.GREEN)

def find_content_mismatches(verbose=True):
    """
    Find records where the file in the expected location has a different hash
    than the one stored in the database.
    Returns a list of dicts with details.
    If verbose=True, prints progress and detailed info.
    """
    if verbose:
        print_colored("[i] Scanning for content mismatches...", COLORS.BLUE)

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(f"SELECT * FROM {TABLE_NAME} WHERE file_hash IS NOT NULL")
    records = cursor.fetchall()
    cursor.close()
    conn.close()

    mismatches = []
    total = len(records)
    for idx, rec in enumerate(records, 1):
        if verbose and idx % 10 == 0:
            print(f"  Processing {idx}/{total} records...", end="\r")

        target_dir, filename_base = get_target_path(rec, interactive=False)
        if not target_dir or not filename_base:
            continue

        import glob
        pattern = os.path.join(target_dir, filename_base + '.*')
        matches = glob.glob(pattern)
        if not matches:
            continue

        file_path = matches[0]
        if not os.path.exists(file_path):
            continue

        actual_hash = compute_md5(file_path)
        stored_hash = rec['file_hash']

        if actual_hash != stored_hash:
            mismatches.append({
                'record': rec,
                'file_path': file_path,
                'stored_hash': stored_hash,
                'actual_hash': actual_hash,
                'expected_dir': target_dir,
                'expected_filename': filename_base
            })

    if verbose:
        print(f"\n  Completed scanning {total} records.")

    return mismatches

def get_available_players():
    """Return a list of available video players on the system."""
    # Common media players (in order of preference)
    common_players = [
        'mpv',
        'vlc',
        'xdg-open',
        'dragon',          # KDE Dragon Player
        'totem',           # GNOME Videos
        'celluloid',       # GTK mpv frontend
        'gnome-mpv',       # Old GNOME mpv frontend
        'smplayer',        # Qt mpv/mplayer frontend
        'kmplayer',        # KDE media player
        'mplayer',         # Classic mplayer
        'haruna',          # Modern KDE mpv frontend
    ]
    players = []
    for p in common_players:
        if shutil.which(p):
            players.append(p)
    return players

def _locate_youtube_file(record):
    """Locate the YouTube video file on disk."""
    target_dir, _ = get_target_path(record, interactive=False)
    file_hash = record.get('file_hash')
    if file_hash and target_dir:
        import glob
        pattern = os.path.join(target_dir, file_hash + '.*')
        matches = glob.glob(pattern)
        if matches:
            return matches[0]
    # Fallback: search whole ROOT_DIR by video_id or syllabus_id
    for root, _, files in os.walk(ROOT_DIR):
        for f in files:
            if f.lower().endswith(('.mp4', '.mkv', '.webm', '.avi', '.mov')):
                if record['video_id'] in f or (record.get('syllabus_id') and record['syllabus_id'] in f):
                    return os.path.join(root, f)
    return None

def _play_or_view_file(file_path, is_video=True):
    """Play a video or view an image using the appropriate player."""
    if not os.path.exists(file_path):
        print_colored(f"[!] File not found: {file_path}", COLORS.RED)
        return

    if is_video:
        # Existing video player selection logic
        available = get_available_players()
        if not available:
            print_colored("[!] No video player found. Please install mpv or vlc.", COLORS.RED)
            return

        print("\n" + "─" * 40)
        print_colored("  SELECT VIDEO PLAYER", COLORS.CYAN, bold=True)
        print("─" * 40)
        for i, player in enumerate(available, 1):
            print(f"  {i}. {player}")
        print("  0. Cancel")
        print("─" * 40)

        choice = input(color_text("Choose player (default 1): ", COLORS.MAGENTA)).strip()
        if choice == '0':
            print_colored("Cancelled.", COLORS.YELLOW)
            return

        if choice.isdigit() and 1 <= int(choice) <= len(available):
            player = available[int(choice)-1]
        else:
            player = available[0]

        print_colored(f"[▶] Playing with {player}: {file_path}", COLORS.GREEN)
        try:
            subprocess.run([player, file_path], check=True)
        except FileNotFoundError:
            print_colored(f"[!] Player '{player}' not found.", COLORS.RED)
        except Exception as e:
            print_colored(f"[!] Failed to play: {e}", COLORS.RED)
    else:
        # Photo: use default image viewer
        img_viewers = ['xdg-open', 'eog', 'gwenview', 'feh', 'display', 'sxiv']
        for viewer in img_viewers:
            if shutil.which(viewer):
                print_colored(f"[🖼] Viewing with {viewer}: {file_path}", COLORS.GREEN)
                try:
                    subprocess.run([viewer, file_path], check=True)
                except Exception as e:
                    print_colored(f"[!] Failed to view: {e}", COLORS.RED)
                return
        print_colored("[!] No image viewer found. Please install eog or gwenview.", COLORS.RED)

def play_video():
    from .facebook_manager import get_facebook_entry_by_id, get_facebook_file_path

    """Find and play (or view) a local media file for a given identifier."""
    raw = input(color_text("Enter media identifier (YouTube video ID, mirror ID, syllabus ID, Facebook ID, file hash, or URL): ", COLORS.MAGENTA)).strip()
    if not raw:
        return

    # First, try to extract a video ID if it's a YouTube URL
    identifier = extract_video_id(raw) or raw

    # ---- Try YouTube ----
    record = get_record_by_any_id(identifier)
    if record:
        # Use the existing YouTube logic (file location + player)
        source_file = _locate_youtube_file(record)
        if source_file:
            _play_or_view_file(source_file, is_video=True)
            return
        else:
            print_colored("[!] Could not locate the video file for this YouTube record.", COLORS.RED)
            return

    # ---- Try Facebook ----
    fb_entry = get_facebook_entry_by_id(identifier)  # searches id, facebook_id, file_hash
    if fb_entry:
        file_path = get_facebook_file_path(fb_entry)
        if file_path and os.path.exists(file_path):
            is_video = fb_entry.get('type') == 'video'
            _play_or_view_file(file_path, is_video)
        else:
            print_colored("[!] Could not locate the file for this Facebook entry.", COLORS.RED)
        return

    # ---- Not found ----
    print_colored("[!] No record found for that identifier.", COLORS.RED)
