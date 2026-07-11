# facebook_manager.py

import os
import re
import subprocess
import yt_dlp
import shutil
import glob
from datetime import datetime
from .utils import sanitize_filename, color_text, print_colored, COLORS, compute_md5
from .utils import ROOT_DIR, TRASH_DIR
from .youtube import _ensure_cookie_file
from .db import get_connection
from .file_sharing import _load_share_db, _save_share_db, SHARE_DIR



FACEBOOK_VIDEO_DIR = os.path.join(ROOT_DIR, 'facebook', 'videos')
FACEBOOK_PHOTO_DIR = os.path.join(ROOT_DIR, 'facebook', 'photos')
TABLE_NAME = 'facebook_entries'

def re_download_facebook_entry(entry):
    """
    Re-download a Facebook entry (video or photo) using its stored URL,
    and update the database entry with new file hash and original filename.
    """
    from .facebook import _download_video, _download_single_photo

    if entry['type'] == 'video':
        _download_video(entry['url'], custom_name=entry.get('original_filename'))
    else:
        _download_single_photo(entry['url'], custom_name=entry.get('original_filename'))

def get_facebook_file_path(entry):
    """
    Given a Facebook entry dict, return the full path to its file if exists.
    Searches in ROOT_DIR/facebook/videos and ROOT_DIR/facebook/photos.
    """
    file_hash = entry.get('file_hash')
    if not file_hash:
        return None
    # Check both video and photo directories
    base_dirs = [
        os.path.join(ROOT_DIR, 'facebook', 'videos'),
        os.path.join(ROOT_DIR, 'facebook', 'photos')
    ]
    for base in base_dirs:
        if os.path.exists(base):
            pattern = os.path.join(base, file_hash + '.*')
            matches = glob.glob(pattern)
            if matches:
                return matches[0]
    return None

def delete_facebook_entry_with_file(entry_id):
    """
    Delete a Facebook entry from the database and also remove the file if present.
    Returns a dict with status and message.
    """
    entry = get_facebook_entry_by_id(entry_id)
    if not entry:
        return {'status': 'failed', 'message': f'Entry with ID {entry_id} not found'}

    file_path = get_facebook_file_path(entry)
    db_deleted = delete_facebook_entry(entry_id)
    if not db_deleted:
        return {'status': 'failed', 'message': 'Database deletion failed'}

    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
            # Also remove empty directories if needed? (optional)
            return {'status': 'deleted', 'message': f'Entry and file {os.path.basename(file_path)} deleted'}
        except Exception as e:
            return {'status': 'partial', 'message': f'Entry deleted but file removal failed: {e}'}
    else:
        return {'status': 'deleted', 'message': 'Entry deleted (no file found)'}

def share_facebook_file(identifier):
    """
    Toggle sharing for a Facebook file.
    """
    entry = get_facebook_entry_by_id(identifier)
    if not entry:
        return {'status': 'failed', 'message': f'No Facebook entry found for ID: {identifier}'}

    filepath = get_facebook_file_path(entry)
    if not filepath:
        return {'status': 'failed', 'message': 'Could not locate file for this entry'}

    # Reuse the share logic from file_sharing
    from .file_sharing import share_toggle as _share_toggle
    # But share_toggle expects a record with a 'file_hash' and a way to get path.
    # We can directly implement the toggle here using the same logic as share_toggle but with our own file path.
    # To avoid duplication, we'll call a helper that moves to share and updates the share DB.
    db = _load_share_db()
    basename = os.path.basename(filepath)
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
        # Not shared -> share it
        # Build a descriptive name from the entry
        base = entry.get('original_filename') or entry.get('title') or entry.get('facebook_id', 'unknown')
        base = sanitize_filename(base)
        ext = os.path.splitext(filepath)[1] if filepath else '.mkv'
        share_name = base + ext
        share_path = os.path.join(SHARE_DIR, share_name)
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

def _extract_facebook_id(url):
    """Try to extract a stable ID from a Facebook URL."""
    # patterns for video/posts
    patterns = [
        r'/watch\?v=([^&]+)',
        r'/reel/([^/?]+)',
        r'/videos/([^/?]+)',
        r'/photo\.php\?fbid=(\d+)',
        r'/permalink\.php\?story_fbid=(\d+)',
        r'/posts/(\d+)',
        r'fb\.watch/([^/?]+)',
    ]
    for pat in patterns:
        m = re.search(pat, url)
        if m:
            return m.group(1)
    # fallback: use the last part of the URL
    return url.rstrip('/').split('/')[-1]

def _extract_facebook_id_from_url_or_id(identifier):
    """If identifier is a URL, extract the Facebook ID; otherwise return as-is."""
    if isinstance(identifier, str) and identifier.startswith('http'):
        from .facebook import _extract_facebook_id
        return _extract_facebook_id(identifier)
    return identifier

def add_facebook_lecture(url_or_id):
    """
    Handle adding a Facebook video or photo.
    Detects type, downloads, organises, and stores in DB.
    """
    from .facebook import _is_video_link, _download_video, _download_single_photo
    from .youtube import _ensure_cookie_file
    import yt_dlp

    print("\n" + "═" * 50)
    print_colored("  ADD FACEBOOK CONTENT", COLORS.CYAN, bold=True)
    print("═" * 50)

    if not url_or_id.startswith('http'):
        print_colored("[!] Please provide a full Facebook URL.", COLORS.RED)
        return

    # ---- Resolve to canonical ID using yt-dlp ----
        # ---- Resolve to canonical ID using yt-dlp ----
    facebook_id = None
    try:
        _ensure_cookie_file()
        ydl_opts = {
            'quiet': True,
            'extract_flat': False,   # get full info, not just metadata
            'ignoreerrors': True,
            'cookiefile': 'cookies.txt' if os.path.exists('cookies.txt') else None,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url_or_id, download=False)
            if info and isinstance(info, dict):
                # Try multiple possible fields
                facebook_id = info.get('id') or info.get('display_id') or info.get('webpage_url_basename')
                if not facebook_id:
                    # Some Facebook videos have ID in 'url' or 'original_url'
                    if info.get('url'):
                        import re
                        match = re.search(r'facebook\.com/watch/?\?v=(\d+)', info['url'])
                        if match:
                            facebook_id = match.group(1)
    except Exception as e:
        print_colored(f"[!] Could not resolve URL: {e}", COLORS.YELLOW)

    # ---- Fallback to old extraction method ----
    if not facebook_id:
        from .facebook import _extract_facebook_id
        facebook_id = _extract_facebook_id(url_or_id)

    if not facebook_id:
        print_colored("[!] Could not extract a valid Facebook ID from the URL.", COLORS.RED)
        return

    # ---- Check if this Facebook ID already exists ----
    existing = get_facebook_entry_by_id(facebook_id)
    if existing:
        print_colored(f"[!] Facebook ID {facebook_id} already exists.", COLORS.YELLOW)
        print_colored(f"   Title: {existing.get('title', 'Unknown')}", COLORS.BLUE)
        print_colored(f"   Type: {existing.get('type', 'Unknown')}", COLORS.BLUE)
        # Check if file exists
        file_path = get_facebook_file_path(existing)
        if file_path and os.path.exists(file_path):
            print_colored(f"   File exists: {file_path}", COLORS.GREEN)
            overwrite = input(color_text("File already exists. Re-download anyway? (y/n): ", COLORS.MAGENTA)).strip().lower()
            if overwrite != 'y':
                print_colored("Keeping existing file. No action taken.", COLORS.YELLOW)
                return
        else:
            print_colored("   File missing on disk.", COLORS.YELLOW)
            overwrite = input(color_text("Download again? (y/n): ", COLORS.MAGENTA)).strip().lower()
            if overwrite != 'y':
                print_colored("Cancelled.", COLORS.YELLOW)
                return

    custom_name = input(color_text("Enter a custom name (or press Enter to auto-detect): ", COLORS.MAGENTA)).strip()
    if not custom_name:
        custom_name = None

    # Import inside to avoid circular import
    from .facebook import _is_video_link, _download_video, _download_single_photo

    if _is_video_link(url_or_id):
        print_colored("[i] Detected as video/Reel link.", COLORS.BLUE)
        _download_video(url_or_id, custom_name)
    else:
        print_colored("[i] Detected as photo link.", COLORS.BLUE)
        _download_single_photo(url_or_id, custom_name)

def add_facebook_entry(facebook_id, entry_type, title, uploader, url, file_hash=None, original_filename=None, notes=None):
    """
    Insert or update a Facebook entry in the database.
    If facebook_id already exists, update the record with new values.
    Returns the inserted/updated ID or None on error.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(f"""
            INSERT INTO {TABLE_NAME}
            (facebook_id, type, title, uploader, url, file_hash, original_filename, notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                type = VALUES(type),
                title = VALUES(title),
                uploader = VALUES(uploader),
                url = VALUES(url),
                file_hash = VALUES(file_hash),
                original_filename = VALUES(original_filename),
                notes = VALUES(notes),
                download_date = NOW()
        """, (facebook_id, entry_type, title, uploader, url, file_hash, original_filename, notes))
        conn.commit()
        inserted_id = cursor.lastrowid
        cursor.close()
        conn.close()
        return inserted_id
    except Exception as e:
        print_colored(f"[!] Failed to insert/update Facebook entry: {e}", COLORS.RED)
        cursor.close()
        conn.close()
        return None

def get_facebook_entry_by_id(identifier):
    """
    Fetch a Facebook entry by facebook_id, id, or file_hash.
    Returns a dict or None.
    """
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    # Use CAST to avoid implicit integer conversion
    sql = f"""
        SELECT * FROM {TABLE_NAME}
        WHERE facebook_id = %s OR CAST(id AS CHAR) = %s OR file_hash = %s
    """
    cursor.execute(sql, (identifier, identifier, identifier))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return row

def list_facebook_entries(limit=None, offset=0):
    """
    Return a list of all Facebook entries, newest first.
    """
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    query = f"SELECT * FROM {TABLE_NAME} ORDER BY download_date DESC"
    if limit:
        query += f" LIMIT {limit} OFFSET {offset}"
    cursor.execute(query)
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return rows

def delete_facebook_entry(entry_id):
    """
    Delete a Facebook entry by ID (database only; file is not removed).
    Returns True if successful.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(f"DELETE FROM {TABLE_NAME} WHERE id = %s", (entry_id,))
        conn.commit()
        deleted = cursor.rowcount > 0
        cursor.close()
        conn.close()
        return deleted
    except Exception as e:
        print_colored(f"[!] Failed to delete Facebook entry: {e}", COLORS.RED)
        cursor.close()
        conn.close()
        return False

def update_facebook_file_hash(entry_id, file_hash, original_filename=None):
    """
    Update file_hash and optionally original_filename for a Facebook entry.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        if original_filename:
            cursor.execute(f"""
                UPDATE {TABLE_NAME}
                SET file_hash = %s, original_filename = %s
                WHERE id = %s
            """, (file_hash, original_filename, entry_id))
        else:
            cursor.execute(f"""
                UPDATE {TABLE_NAME}
                SET file_hash = %s
                WHERE id = %s
            """, (file_hash, entry_id))
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        print_colored(f"[!] Failed to update Facebook file hash: {e}", COLORS.RED)
        cursor.close()
        conn.close()
        return False

def get_facebook_stats():
    """
    Return counts of total entries, videos, photos, and total file size.
    """
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(f"SELECT COUNT(*) as total FROM {TABLE_NAME}")
    total = cursor.fetchone()['total']
    cursor.execute(f"SELECT COUNT(*) as videos FROM {TABLE_NAME} WHERE type = 'video'")
    videos = cursor.fetchone()['videos']
    cursor.execute(f"SELECT COUNT(*) as photos FROM {TABLE_NAME} WHERE type = 'photo'")
    photos = cursor.fetchone()['photos']
    # Sum file sizes (if files exist)
    cursor.execute(f"""
        SELECT SUM(LENGTH(file_hash)) as size_est FROM {TABLE_NAME} WHERE file_hash IS NOT NULL
    """)
    # Not a real size; we'll compute from actual files later.
    cursor.close()
    conn.close()
    return {'total': total, 'videos': videos, 'photos': photos}

# ========== EXPORT / IMPORT ==========

def export_facebook_csv():
    """Export all Facebook entries to a CSV file."""
    import csv
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM facebook_entries ORDER BY download_date DESC")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    if not rows:
        print_colored("[i] No Facebook entries to export.", COLORS.YELLOW)
        return
    filename = input(color_text("Enter CSV filename (default: facebook_export.csv): ", COLORS.MAGENTA)).strip()
    if not filename:
        filename = "facebook_export.csv"
    if not filename.endswith('.csv'):
        filename += '.csv'
    fieldnames = list(rows[0].keys())
    try:
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        print_colored(f"[✓] Exported {len(rows)} records to {filename}", COLORS.GREEN)
    except Exception as e:
        print_colored(f"[!] Export failed: {e}", COLORS.RED)

def export_facebook_json():
    """Export all Facebook entries to a JSON file."""
    import json
    from datetime import datetime
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM facebook_entries ORDER BY download_date DESC")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    if not rows:
        print_colored("[i] No Facebook entries to export.", COLORS.YELLOW)
        return
    filename = input(color_text("Enter JSON filename (default: facebook_export.json): ", COLORS.MAGENTA)).strip()
    if not filename:
        filename = "facebook_export.json"
    if not filename.endswith('.json'):
        filename += '.json'
    # Convert datetime objects to strings
    for row in rows:
        for key, value in row.items():
            if isinstance(value, datetime):
                row[key] = value.isoformat()
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(rows, f, indent=2, ensure_ascii=False)
        print_colored(f"[✓] Exported {len(rows)} records to {filename}", COLORS.GREEN)
    except Exception as e:
        print_colored(f"[!] Export failed: {e}", COLORS.RED)

def import_facebook_csv():
    """Import Facebook entries from a CSV file."""
    import csv
    filename = input(color_text("Enter CSV filename: ", COLORS.MAGENTA)).strip()
    if not filename:
        print_colored("[!] No filename given.", COLORS.RED)
        return
    if not os.path.exists(filename):
        print_colored(f"[!] File {filename} not found.", COLORS.RED)
        return
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
    except Exception as e:
        print_colored(f"[!] Failed to read CSV: {e}", COLORS.RED)
        return
    if not rows:
        print_colored("[i] No data found.", COLORS.YELLOW)
        return

    print(f"Found {len(rows)} records. How to handle duplicates?")
    print("  1. Skip duplicates (keep existing)")
    print("  2. Update existing records")
    print("  3. Abort on any duplicate")
    choice = input(color_text("Choose (1-3): ", COLORS.MAGENTA)).strip()
    if choice not in ('1', '2', '3'):
        print_colored("[!] Invalid choice. Aborting.", COLORS.RED)
        return

    conn = get_connection()
    cursor = conn.cursor()
    added = 0
    updated = 0
    skipped = 0

    for row in rows:
        facebook_id = row.get('facebook_id', '').strip()
        if not facebook_id:
            print_colored("[!] Missing facebook_id, skipping.", COLORS.YELLOW)
            skipped += 1
            continue

        # Check if exists
        cursor.execute("SELECT id FROM facebook_entries WHERE facebook_id = %s", (facebook_id,))
        exists = cursor.fetchone()

        if exists:
            if choice == '1':
                skipped += 1
                continue
            elif choice == '2':
                # Update
                cursor.execute("""
                    UPDATE facebook_entries
                    SET type = %s, title = %s, uploader = %s, url = %s,
                        file_hash = %s, original_filename = %s, notes = %s
                    WHERE facebook_id = %s
                """, (
                    row.get('type', 'video'),
                    row.get('title', ''),
                    row.get('uploader', ''),
                    row.get('url', ''),
                    row.get('file_hash') or None,
                    row.get('original_filename') or None,
                    row.get('notes') or None,
                    facebook_id
                ))
                updated += 1
                continue
            else:  # choice == 3
                print_colored(f"[!] Duplicate facebook_id {facebook_id}, aborting.", COLORS.RED)
                conn.rollback()
                cursor.close()
                conn.close()
                return
        else:
            # Insert
            cursor.execute("""
                INSERT INTO facebook_entries
                (facebook_id, type, title, uploader, url, file_hash, original_filename, notes)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                facebook_id,
                row.get('type', 'video'),
                row.get('title', ''),
                row.get('uploader', ''),
                row.get('url', ''),
                row.get('file_hash') or None,
                row.get('original_filename') or None,
                row.get('notes') or None
            ))
            added += 1

    conn.commit()
    cursor.close()
    conn.close()
    print_colored(f"[✓] Import complete: {added} added, {updated} updated, {skipped} skipped.", COLORS.GREEN)

def import_facebook_json():
    """Import Facebook entries from a JSON file."""
    import json
    filename = input(color_text("Enter JSON filename: ", COLORS.MAGENTA)).strip()
    if not filename:
        print_colored("[!] No filename given.", COLORS.RED)
        return
    if not os.path.exists(filename):
        print_colored(f"[!] File {filename} not found.", COLORS.RED)
        return
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            rows = json.load(f)
    except Exception as e:
        print_colored(f"[!] Failed to read JSON: {e}", COLORS.RED)
        return
    if not isinstance(rows, list):
        print_colored("[!] JSON must be a list of objects.", COLORS.RED)
        return
    if not rows:
        print_colored("[i] No data found.", COLORS.YELLOW)
        return

    print(f"Found {len(rows)} records. How to handle duplicates?")
    print("  1. Skip duplicates (keep existing)")
    print("  2. Update existing records")
    print("  3. Abort on any duplicate")
    choice = input(color_text("Choose (1-3): ", COLORS.MAGENTA)).strip()
    if choice not in ('1', '2', '3'):
        print_colored("[!] Invalid choice. Aborting.", COLORS.RED)
        return

    conn = get_connection()
    cursor = conn.cursor()
    added = 0
    updated = 0
    skipped = 0

    for row in rows:
        if not isinstance(row, dict):
            print_colored("[!] Item is not a dict, skipping.", COLORS.YELLOW)
            skipped += 1
            continue
        facebook_id = row.get('facebook_id', '').strip()
        if not facebook_id:
            print_colored("[!] Missing facebook_id, skipping.", COLORS.YELLOW)
            skipped += 1
            continue

        cursor.execute("SELECT id FROM facebook_entries WHERE facebook_id = %s", (facebook_id,))
        exists = cursor.fetchone()

        if exists:
            if choice == '1':
                skipped += 1
                continue
            elif choice == '2':
                cursor.execute("""
                    UPDATE facebook_entries
                    SET type = %s, title = %s, uploader = %s, url = %s,
                        file_hash = %s, original_filename = %s, notes = %s
                    WHERE facebook_id = %s
                """, (
                    row.get('type', 'video'),
                    row.get('title', ''),
                    row.get('uploader', ''),
                    row.get('url', ''),
                    row.get('file_hash') or None,
                    row.get('original_filename') or None,
                    row.get('notes') or None,
                    facebook_id
                ))
                updated += 1
                continue
            else:  # choice == 3
                print_colored(f"[!] Duplicate facebook_id {facebook_id}, aborting.", COLORS.RED)
                conn.rollback()
                cursor.close()
                conn.close()
                return
        else:
            cursor.execute("""
                INSERT INTO facebook_entries
                (facebook_id, type, title, uploader, url, file_hash, original_filename, notes)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                facebook_id,
                row.get('type', 'video'),
                row.get('title', ''),
                row.get('uploader', ''),
                row.get('url', ''),
                row.get('file_hash') or None,
                row.get('original_filename') or None,
                row.get('notes') or None
            ))
            added += 1

    conn.commit()
    cursor.close()
    conn.close()
    print_colored(f"[✓] Import complete: {added} added, {updated} updated, {skipped} skipped.", COLORS.GREEN)

def facebook_menu():
    """Interactive menu for managing Facebook entries."""
    while True:
        print("\n" + "═" * 50)
        print_colored("  FACEBOOK MANAGER", COLORS.CYAN, bold=True)
        print("═" * 50)
        print("  1. List all entries")
        print("  2. View entry details")
        print("  3. Delete an entry (and file)")
        print("  4. Share/Restore a Facebook file")
        print("  5. Refresh file hashes (recompute MD5)")
        print("  6. Export Facebook entries to CSV")
        print("  7. Export Facebook entries to JSON")
        print("  8. Import Facebook entries from CSV")
        print("  9. Import Facebook entries from JSON")
        print("  0. Return to main menu")
        print("═" * 50)

        choice = input(color_text("Choose an option (0-9): ", COLORS.MAGENTA)).strip()

        if choice == '1':
            entries = list_facebook_entries()
            if not entries:
                print_colored("[i] No Facebook entries found.", COLORS.YELLOW)
            else:
                print(f"\n--- FACEBOOK ENTRIES ({len(entries)}) ---")
                for e in entries:
                    print(f"  ID:{e['id']:4} | FB ID: {e['facebook_id']:>16} | {e['type']:5} | {e['uploader']:20} | {e['title'][:40]}")
                print()
            input("Press Enter to continue...")

        elif choice == '2':
            identifier = input(color_text("Enter Facebook ID, entry ID, or file hash: ", COLORS.MAGENTA)).strip()
            if not identifier:
                continue
            entry = get_facebook_entry_by_id(identifier)
            if not entry:
                print_colored("[!] Entry not found.", COLORS.RED)
            else:
                file_path = get_facebook_file_path(entry)
                print("\n" + "═" * 50)
                print_colored("  FACEBOOK ENTRY DETAILS", COLORS.CYAN, bold=True)
                print("═" * 50)
                print(f"  ID           : {entry['id']}")
                print(f"  Facebook ID  : {entry['facebook_id']}")
                print(f"  Type         : {entry['type']}")
                print(f"  Title        : {entry['title']}")
                print(f"  Uploader     : {entry['uploader']}")
                print(f"  URL          : {entry['url']}")
                print(f"  File Hash    : {entry['file_hash'] or '(none)'}")
                print(f"  Original Name: {entry['original_filename'] or '(none)'}")
                print(f"  Download Date: {entry['download_date']}")
                print(f"  Notes        : {entry['notes'] or '(none)'}")
                if file_path:
                    print_colored(f"  File Location: {file_path}", COLORS.BLUE)
                else:
                    print_colored("  File Location: (not found on disk)", COLORS.RED)
                print("═" * 50)
            input("\nPress Enter to continue...")

        elif choice == '3':
            identifier = input(color_text("Enter Facebook ID, entry ID, or file hash: ", COLORS.MAGENTA)).strip()
            if not identifier:
                continue
            entry = get_facebook_entry_by_id(identifier)
            if not entry:
                print_colored("[!] Entry not found.", COLORS.RED)
                continue
            file_path = get_facebook_file_path(entry)
            print(f"Entry: {entry['title']} ({entry['type']})")
            if file_path:
                print(f"File: {file_path}")
            confirm = input(color_text("Delete this entry and file? (y/n): ", COLORS.MAGENTA)).strip().lower()
            if confirm == 'y':
                result = delete_facebook_entry_with_file(entry['id'])
                if result['status'] == 'deleted' or result['status'] == 'partial':
                    print_colored(f"[✓] {result['message']}", COLORS.GREEN)
                else:
                    print_colored(f"[!] {result['message']}", COLORS.RED)
            else:
                print_colored("Cancelled.", COLORS.YELLOW)
            input("\nPress Enter to continue...")

        elif choice == '4':
            identifier = input(color_text("Enter Facebook ID, entry ID, or file hash: ", COLORS.MAGENTA)).strip()
            if not identifier:
                continue
            result = share_facebook_file(identifier)
            if result['status'] in ('shared', 'restored'):
                print_colored(f"[✓] {result['message']}", COLORS.GREEN)
            elif result['status'] == 'cancelled':
                print_colored(f"[i] {result['message']}", COLORS.YELLOW)
            else:
                print_colored(f"[!] {result['message']}", COLORS.RED)
            input("\nPress Enter to continue...")

        elif choice == '5':
            # Refresh file hashes: for each entry without a file hash, recompute
            print_colored("[i] Refreshing Facebook file hashes...", COLORS.BLUE)
            conn = get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute(f"SELECT * FROM {TABLE_NAME} WHERE file_hash IS NULL OR file_hash = ''")
            entries = cursor.fetchall()
            cursor.close()
            conn.close()
            if not entries:
                print_colored("[i] All entries have file hashes.", COLORS.GREEN)
                input("Press Enter to continue...")
                continue
            updated = 0
            for e in entries:
                fp = get_facebook_file_path(e)
                if fp and os.path.exists(fp):
                    new_hash = compute_md5(fp)
                    if update_facebook_file_hash(e['id'], new_hash, e.get('original_filename')):
                        updated += 1
                        print(f"  Updated ID {e['id']} -> {new_hash}")
                    else:
                        print_colored(f"  Failed to update ID {e['id']}", COLORS.RED)
                else:
                    print_colored(f"  File not found for ID {e['id']}, skipping.", COLORS.YELLOW)
            print_colored(f"[✓] Updated {updated} entries.", COLORS.GREEN)
            input("\nPress Enter to continue...")

        elif choice == '6':
            export_facebook_csv()
            input("\nPress Enter to continue...")
        elif choice == '7':
            export_facebook_json()
            input("\nPress Enter to continue...")
        elif choice == '8':
            import_facebook_csv()
            input("\nPress Enter to continue...")
        elif choice == '9':
            import_facebook_json()
            input("\nPress Enter to continue...")

        elif choice == '0':
            break
        else:
            print_colored("[!] Invalid choice.", COLORS.RED)
            input("\nPress Enter to continue...")
