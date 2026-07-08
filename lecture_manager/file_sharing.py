# File file_sharing.py

# file_sharing.py
import os
import json
import shutil
import re
from .db import get_record_by_any_id
from .utils import print_colored, COLORS, ROOT_DIR, color_text
from .file_compressor import get_file_path_for_record

SHARE_DIR = os.path.join(ROOT_DIR, 'share')
SHARE_DB_FILE = os.path.expanduser("~/.lecture_share.json")

def _load_share_db():
    if os.path.exists(SHARE_DB_FILE):
        with open(SHARE_DB_FILE, 'r') as f:
            return json.load(f)
    return {}

def _save_share_db(db):
    with open(SHARE_DB_FILE, 'w') as f:
        json.dump(db, f, indent=2)

def list_shared_files():
    db = _load_share_db()
    if not db:
        print_colored("[i] No shared files.", COLORS.YELLOW)
        return
    print("\n" + "═" * 60)
    print_colored("  SHARED FILES", COLORS.CYAN, bold=True)
    print("═" * 60)
    for i, (share_name, orig_path) in enumerate(db.items(), 1):
        share_path = os.path.join(SHARE_DIR, share_name)
        size = os.path.getsize(share_path) if os.path.exists(share_path) else 0
        size_mb = size / (1024*1024)
        print(f"  {i}. {share_name}  ({size_mb:.1f} MB)  -> {orig_path}")
    print("═" * 60)

def restore_shared_by_index(idx):
    db = _load_share_db()
    if not db:
        print_colored("[i] No shared files.", COLORS.YELLOW)
        return
    items = list(db.items())
    if idx < 1 or idx > len(items):
        print_colored("[!] Invalid number.", COLORS.RED)
        return
    share_name, orig_path = items[idx-1]
    share_path = os.path.join(SHARE_DIR, share_name)
    if not os.path.exists(share_path):
        print_colored(f"[!] File missing: {share_path}", COLORS.RED)
        del db[share_name]
        _save_share_db(db)
        return
    os.makedirs(os.path.dirname(orig_path), exist_ok=True)
    if os.path.exists(orig_path):
        overwrite = input(color_text(f"Target exists: {orig_path}. Overwrite? (y/n): ", COLORS.MAGENTA)).strip().lower()
        if overwrite != 'y':
            print_colored("Cancelled.", COLORS.YELLOW)
            return
    shutil.move(share_path, orig_path)
    del db[share_name]
    _save_share_db(db)
    print_colored(f"[✓] Restored to: {orig_path}", COLORS.GREEN)

def share_toggle(identifier):
    record = get_record_by_any_id(identifier)
    if not record:
        return {'status': 'failed', 'message': f'No record found for ID: {identifier}'}

    # ---- Locate the file ----
    filepath = get_file_path_for_record(record)
    if not filepath:
        from .file_manager import get_target_path
        target_dir, _ = get_target_path(record, interactive=False)
        if target_dir:
            file_hash = record.get('file_hash')
            if file_hash:
                import glob
                pattern = os.path.join(target_dir, file_hash + '.*')
                matches = glob.glob(pattern)
                if matches:
                    filepath = matches[0]
        if not filepath:
            return {'status': 'failed', 'message': f'Could not locate file for record {identifier}'}

    db = _load_share_db()

    # Check if already shared
    share_name = None
    for share_key, orig_path in db.items():
        if orig_path == filepath:
            share_name = share_key
            break

    if share_name:
        # Already shared -> ask to restore
        print_colored(f"File is currently shared as: {share_name}", COLORS.BLUE)
        print(f"  Share path: {os.path.join(SHARE_DIR, share_name)}")
        print(f"  Original path: {filepath}")
        confirm = input(color_text("Restore it back? (y/n): ", COLORS.MAGENTA)).strip().lower()
        if confirm == 'y':
            share_path = os.path.join(SHARE_DIR, share_name)
            if not os.path.exists(share_path):
                print_colored(f"[!] File missing in share, removing DB entry.", COLORS.RED)
                del db[share_name]
                _save_share_db(db)
                return {'status': 'failed', 'message': 'File not found in share'}
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            if os.path.exists(filepath):
                overwrite = input(color_text(f"Target exists: {filepath}. Overwrite? (y/n): ", COLORS.MAGENTA)).strip().lower()
                if overwrite != 'y':
                    return {'status': 'cancelled', 'message': 'Restore cancelled'}
            shutil.move(share_path, filepath)
            del db[share_name]
            _save_share_db(db)
            return {'status': 'restored', 'message': f'Restored to {filepath}'}
        else:
            return {'status': 'cancelled', 'message': 'Restore cancelled'}

    else:
        # -------- NOT SHARED: BUILD DESCRIPTIVE NAME FROM FIELDS --------
        parts = []
        syllabus = record.get('syllabus_id', '').strip()
        if syllabus:
            parts.append(syllabus)

        chapter = record.get('chapter', '').strip()
        if not chapter:
            video_title = record.get('video_title', '')
            if '||' in video_title:
                chapter = video_title.split('||')[0].strip()
        if chapter:
            parts.append(chapter)

        subject = record.get('subject', '').strip()
        if subject:
            parts.append(subject)

        lecturer = record.get('lecturer', '').strip()
        if lecturer:
            parts.append(lecturer)

        nepali_date = record.get('nepali_date', '').strip()
        if nepali_date:
            parts.append(nepali_date)

        time_str = record.get('time', '').strip()
        if time_str:
            parts.append(time_str)

        if len(parts) < 2:
            parts.append(record.get('video_id', 'unknown'))

        base = " || ".join(parts)

        # Remove dangerous characters, but keep '||' (preserve the separator)
        import re
        base = re.sub(r'[\\/*?"<>:]', '', base)   # Remove \, /, *, ?, ", <, >, :
        base = re.sub(r'[\x00-\x1f\x7f]', '', base) # Remove control chars
        base = base.strip()

        if not base:
            base = record.get('video_id', 'unknown')

        ext = os.path.splitext(filepath)[1] if filepath else '.mkv'
        share_name = base + ext
        share_path = os.path.join(SHARE_DIR, share_name)

        # Avoid name collision
        counter = 1
        while os.path.exists(share_path):
            share_name = f"{base}_{counter}{ext}"
            share_path = os.path.join(SHARE_DIR, share_name)
            counter += 1

        os.makedirs(SHARE_DIR, exist_ok=True)
        try:
            shutil.move(filepath, share_path)
        except Exception as e:
            return {'status': 'failed', 'message': f'Move failed: {e}'}

        db[share_name] = filepath
        _save_share_db(db)
        print_colored(f"[✓] File moved to share: {share_path}", COLORS.GREEN)
        print("You can now share this file (e.g., copy or share the share directory).")
        restore_now = input(color_text("Restore file back to its original location? (y/n): ", COLORS.MAGENTA)).strip().lower()
        if restore_now == 'y':
            if os.path.exists(filepath):
                overwrite = input(color_text(f"Target exists: {filepath}. Overwrite? (y/n): ", COLORS.MAGENTA)).strip().lower()
                if overwrite != 'y':
                    return {'status': 'shared', 'message': f'File kept in share: {share_path}'}
            shutil.move(share_path, filepath)
            del db[share_name]
            _save_share_db(db)
            return {'status': 'restored', 'message': f'Restored to {filepath}'}
        else:
            return {'status': 'shared', 'message': f'File kept in share: {share_path}'}
