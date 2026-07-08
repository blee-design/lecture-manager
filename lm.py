# File config.py

import os
import json
from .utils import color_text, print_colored, COLORS

CONFIG_FILE = os.path.expanduser("~/.lecture_manager_config.json")
db_config = None

def load_or_create_config():
    global db_config
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                db_config = json.load(f)
            print_colored("[✓] Loaded database configuration.", COLORS.GREEN)
            return
        except Exception as e:
            print_colored(f"[!] Error reading config: {e}. Will create new one.", COLORS.YELLOW)

    print("\n" + "═" * 50)
    print_colored("  DATABASE CONFIGURATION", COLORS.CYAN, bold=True)
    print("═" * 50)
    print("Please enter your MariaDB/MySQL connection details.")
    host = input(color_text("Host (default: localhost): ", COLORS.MAGENTA)).strip() or "localhost"
    database = input(color_text("Database name: ", COLORS.MAGENTA)).strip()
    user = input(color_text("Username: ", COLORS.MAGENTA)).strip()
    password = input(color_text("Password: ", COLORS.MAGENTA)).strip()
    port = input(color_text("Port (default: 3306): ", COLORS.MAGENTA)).strip() or "3306"

    if not database or not user:
        print_colored("[!] Database name and username are required.", COLORS.RED)
        exit(1)

    db_config = {
        'host': host,
        'database': database,
        'user': user,
        'password': password,
        'port': int(port)
    }

    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(db_config, f, indent=2)
        print_colored(f"[✓] Configuration saved to {CONFIG_FILE}", COLORS.GREEN)
    except Exception as e:
        print_colored(f"[!] Failed to save config: {e}", COLORS.RED)

def edit_config():
    global db_config
    print("\n" + "═" * 50)
    print_colored("  EDIT DATABASE CONFIGURATION", COLORS.CYAN, bold=True)
    print("═" * 50)
    print("Current settings:")
    print(f"  Host     : {db_config.get('host', '')}")
    print(f"  Database : {db_config.get('database', '')}")
    print(f"  User     : {db_config.get('user', '')}")
    print(f"  Port     : {db_config.get('port', 3306)}")
    print("(Leave blank to keep current value)")

    host = input(color_text(f"Host [{db_config.get('host', 'localhost')}]: ", COLORS.MAGENTA)).strip() or db_config.get('host', 'localhost')
    database = input(color_text(f"Database [{db_config.get('database', '')}]: ", COLORS.MAGENTA)).strip() or db_config.get('database', '')
    user = input(color_text(f"Username [{db_config.get('user', '')}]: ", COLORS.MAGENTA)).strip() or db_config.get('user', '')
    password = input(color_text(f"Password [{db_config.get('password', '')}]: ", COLORS.MAGENTA)).strip() or db_config.get('password', '')
    port = input(color_text(f"Port [{db_config.get('port', 3306)}]: ", COLORS.MAGENTA)).strip() or db_config.get('port', 3306)

    if not database or not user:
        print_colored("[!] Database name and username are required. Aborting.", COLORS.RED)
        return

    new_config = {
        'host': host,
        'database': database,
        'user': user,
        'password': password,
        'port': int(port)
    }
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(new_config, f, indent=2)
        db_config = new_config
        print_colored("[✓] Configuration updated and saved.", COLORS.GREEN)
    except Exception as e:
        print_colored(f"[!] Failed to save config: {e}", COLORS.RED)
# File crud.py

import os
import subprocess
import mysql.connector
import glob
from .db import get_connection, TABLE_NAME, get_record_by_video_id, get_record_by_any_id
from .youtube import extract_video_id, fetch_youtube_title, get_embed_link, _ensure_cookie_file
from .utils import clean_field, get_display_title, sanitize_filename, parse_lecture_title, color_text, print_colored, COLORS, normalize_syllabus_id
from .file_manager import organize_video, sync_record_files, detect_paper, PAPER_CONFIG, get_target_path, ROOT_DIR
from .facebook_manager import add_facebook_lecture

DOWNLOAD_DIR = './downloads'

def download_video(record, output_dir=DOWNLOAD_DIR, video_id_to_download=None, silent=False):
    """
    Download a video from YouTube.
    If silent=True, no prompts – uses YouTube title and auto-organises.
    If silent=False (default), prompts for filename and organisation.
    """
    if video_id_to_download is None:
        video_id_to_download = record['video_id']

    # --- Determine default filename: use video_title (sanitised) ---
    title = record.get('video_title', '')
    if not title:
        title = fetch_youtube_title(video_id_to_download) or ""

    if title:
        filename_base = sanitize_filename(title)
        if len(filename_base) > 200:
            filename_base = filename_base[:200]
    else:
        syllabus = clean_field(record.get('syllabus_id', ''))
        chapter = get_display_title(record)
        subject = clean_field(record.get('subject', ''))
        lecturer = clean_field(record.get('lecturer', ''))
        nepali_date = clean_field(record.get('nepali_date', ''))
        time_str = clean_field(record.get('time', ''))
        parts = [syllabus, chapter, subject, lecturer, nepali_date, time_str]
        display_name = " || ".join(parts)
        filename_base = sanitize_filename(display_name)
        if len(filename_base) > 200:
            filename_base = filename_base[:200]

    if not silent:
        print(f"\nProposed filename: {color_text(filename_base + '.mp4', COLORS.CYAN)}")
        confirm = input(color_text("Download? (y/n, or custom name): ", COLORS.MAGENTA)).strip()
        if confirm.lower() == 'n':
            print_colored("Cancelled.", COLORS.YELLOW)
            return
        elif confirm and confirm.lower() != 'y':
            filename_base = sanitize_filename(confirm)

    os.makedirs(output_dir, exist_ok=True)
    url = f"https://www.youtube.com/watch?v={video_id_to_download}"
    _ensure_cookie_file()
    # Determine cookie option: use cookies.txt if exists
    if os.path.exists('cookies.txt'):
        cookie_opt = ['--cookies', 'cookies.txt']
    else:
        cookie_opt = ['--cookies-from-browser', 'edge']

    cmd = [
        'yt-dlp',
        # '-f', 'bestvideo+bestaudio/best',   # no height filter – robust
        # '-f', 'bestvideo[height<=720]+bestaudio/best[height<=720]/best',
        '-f', 'bestvideo[height<=720]+bestaudio/best[height<=720]/bestvideo[height<=480]+bestaudio/best[height<=480]/bestvideo+bestaudio',
        '-o', os.path.join(output_dir, f'{filename_base}.%(ext)s'),
        '--add-metadata',
        '--embed-thumbnail',
        '--sleep-requests', '1',
        '--remote-components', 'ejs:github',   # <-- essential for JS challenges
        '--verbose',
        *cookie_opt,
        url
    ]

    print_colored(f"[⏳] Downloading video ID: {video_id_to_download} ...", COLORS.BLUE)
    try:
        subprocess.run(cmd, check=True)
        print_colored(f"[✓] Downloaded to {output_dir}/{filename_base}.*", COLORS.GREEN)

        if not silent:
            print("\n[i] Do you want to organize this video into the syllabus folder now?")
            org_choice = input(color_text("Organize? (y/n): ", COLORS.MAGENTA)).strip().lower()
            if org_choice == 'y':
                downloaded_files = [f for f in os.listdir(output_dir) if f.startswith(filename_base)]
                if downloaded_files:
                    downloaded_file = os.path.join(output_dir, downloaded_files[0])
                    organize_video(record, downloaded_file)
                else:
                    print_colored("[!] Could not locate the downloaded file. Please organize manually.", COLORS.YELLOW)
        else:
            downloaded_files = [f for f in os.listdir(output_dir) if f.startswith(filename_base)]
            if downloaded_files:
                downloaded_file = os.path.join(output_dir, downloaded_files[0])
                organize_video(record, downloaded_file)
            else:
                print_colored("[!] Could not locate the downloaded file. Please organize manually.", COLORS.YELLOW)

    except subprocess.CalledProcessError as e:
        print_colored(f"[!] Download failed: {e}", COLORS.RED)
        print_colored("[i] If you get a 'Sign in to confirm you’re not a bot' error, try:", COLORS.YELLOW)
        print_colored("    1. Run option 26 to refresh YouTube cookies.", COLORS.YELLOW)
        print_colored("    2. Make sure you are logged into YouTube in your browser.", COLORS.YELLOW)

def add_lecture():
    print("\n" + "═" * 50)
    print_colored("  ADD NEW LECTURE", COLORS.CYAN, bold=True)
    print("═" * 50)

    url_or_id = input(color_text("YouTube URL or Video ID (or press Enter to cancel): ", COLORS.MAGENTA)).strip()
    if not url_or_id:
        print_colored("Cancelled.", COLORS.YELLOW)
        return

    # --- Detect Facebook ---
    if 'facebook.com' in url_or_id or 'fb.watch' in url_or_id:
        add_facebook_lecture(url_or_id)
        return

    # ---- Continue with YouTube logic (unchanged) ----
    video_id = extract_video_id(url_or_id)
    if not video_id:
        print_colored("[!] Invalid YouTube URL or video ID.", COLORS.RED)
        return

    # ---- Duplicate check (primary or mirror) ----
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(f"""
        SELECT id, video_id, mirror_video_id FROM {TABLE_NAME}
        WHERE video_id = %s OR mirror_video_id = %s
    """, (video_id, video_id))
    existing = cursor.fetchall()
    cursor.close()
    conn.close()

    if existing:
        used_as_primary = any(row['video_id'] == video_id for row in existing)
        used_as_mirror = any(row['mirror_video_id'] == video_id for row in existing)
        if used_as_primary and used_as_mirror:
            msg = "as both primary and mirror"
        elif used_as_primary:
            msg = "as a primary video ID"
        else:
            msg = "as a mirror ID"
        print_colored(f"[!] Video ID {video_id} already exists {msg}. Use UPDATE to modify.", COLORS.YELLOW)
        return

    # ---- Fetch title and parse ----
    title = fetch_youtube_title(video_id) or ""
    parsed = parse_lecture_title(title)

    syllabus_raw = input(color_text("Syllabus ID (or press Enter to cancel): ", COLORS.MAGENTA)).strip()
    if not syllabus_raw:
        print_colored("Cancelled.", COLORS.YELLOW)
        return
    syllabus_id = normalize_syllabus_id(syllabus_raw)

    chapter = input(color_text("Chapter/Topic: ", COLORS.MAGENTA)).strip()

    if parsed:
        # ---- Auto‑detect paper ----
        detected_paper = detect_paper(parsed['subject'], syllabus_id, chapter, interactive=True)
        if not detected_paper:
            # Fallback: ask user to pick
            print_colored("[!] Could not auto‑detect paper. Please select manually.", COLORS.YELLOW)
            print("Options: pretest, paper_i, paper_ii, paper_iii")
            paper_choice = input(color_text("Enter paper: ", COLORS.MAGENTA)).strip()
            detected_paper = paper_choice if paper_choice in ('pretest','paper_i','paper_ii','paper_iii') else None

        print("\n" + "─" * 40)
        print_colored("  Auto‑detected from video title:", COLORS.BLUE)
        print(f"  Subject      : {parsed['subject']}")
        print(f"  Lecturer     : {parsed['lecturer']}")
        print(f"  Nepali Date  : {parsed['nepali_date']}")
        print(f"  Time         : {parsed['time']}")
        paper_display = f"{detected_paper} ({PAPER_CONFIG[detected_paper]['folder']})" if detected_paper and detected_paper in PAPER_CONFIG else "unknown"
        print(f"  Paper        : {paper_display}")
        print("─" * 40)
        use = input(color_text("Use these values? (y/n, default y): ", COLORS.MAGENTA)).strip().lower()
        if use == 'n':
            # ---- Interactive edit menu with paper ----
            fields = {
                'syllabus_id': syllabus_id,
                'chapter': chapter,
                'subject': parsed['subject'],
                'lecturer': parsed['lecturer'],
                'nepali_date': parsed['nepali_date'],
                'time': parsed['time'],
                'paper': detected_paper
            }
            while True:
                print("\n" + "─" * 40)
                print_colored("  EDIT ALL FIELDS", COLORS.CYAN, bold=True)
                print("─" * 40)
                print(f"  1. Syllabus ID  : {fields['syllabus_id']}")
                print(f"  2. Chapter/Topic: {fields['chapter']}")
                print(f"  3. Subject      : {fields['subject']}")
                print(f"  4. Lecturer     : {fields['lecturer']}")
                print(f"  5. Nepali Date  : {fields['nepali_date']}")
                print(f"  6. Time         : {fields['time']}")
                print(f"  7. Paper        : {fields['paper']}")
                print("  0. Done – proceed with these values")
                print("  9. Cancel – abort adding this lecture")
                print("─" * 40)
                choice = input(color_text("Choose field to edit (1-7), 0 to proceed, or 9 to cancel: ", COLORS.MAGENTA)).strip()
                if choice == '0':
                    break
                elif choice == '9':
                    print_colored("Operation cancelled by user.", COLORS.YELLOW)
                    return
                elif choice == '1':
                    new_val = input(color_text(f"Syllabus ID [{fields['syllabus_id']}]: ", COLORS.MAGENTA)).strip()
                    if new_val:
                        fields['syllabus_id'] = normalize_syllabus_id(new_val)
                elif choice == '2':
                    new_val = input(color_text(f"Chapter/Topic [{fields['chapter']}]: ", COLORS.MAGENTA)).strip()
                    if new_val:
                        fields['chapter'] = new_val
                elif choice == '3':
                    new_val = input(color_text(f"Subject [{fields['subject']}]: ", COLORS.MAGENTA)).strip()
                    if new_val:
                        fields['subject'] = new_val
                elif choice == '4':
                    new_val = input(color_text(f"Lecturer [{fields['lecturer']}]: ", COLORS.MAGENTA)).strip()
                    if new_val:
                        fields['lecturer'] = new_val
                elif choice == '5':
                    new_val = input(color_text(f"Nepali Date [{fields['nepali_date']}]: ", COLORS.MAGENTA)).strip()
                    if new_val:
                        fields['nepali_date'] = new_val
                elif choice == '6':
                    new_val = input(color_text(f"Time [{fields['time']}]: ", COLORS.MAGENTA)).strip()
                    if new_val:
                        fields['time'] = new_val
                elif choice == '7':
                    print("\nAvailable papers:")
                    paper_options = ['pretest', 'paper_i', 'paper_ii', 'paper_iii']
                    for i, p in enumerate(paper_options, 1):
                        folder = PAPER_CONFIG.get(p, {}).get('folder', '')
                        print(f"  {i}. {p} ({folder})")
                    print("  0. Cancel (keep current)")
                    paper_choice = input(color_text(f"Choose paper (1-4, or 0 to keep '{fields['paper']}'): ", COLORS.MAGENTA)).strip()
                    if paper_choice.isdigit():
                        idx = int(paper_choice)
                        if 1 <= idx <= len(paper_options):
                            fields['paper'] = paper_options[idx-1]
                        elif idx == 0:
                            pass  # keep current
                        else:
                            print_colored("[!] Invalid choice.", COLORS.RED)
                    else:
                        # fallback: allow manual entry
                        new_val = input(color_text(f"Paper (or press Enter to keep '{fields['paper']}'): ", COLORS.MAGENTA)).strip()
                        if new_val:
                            if new_val in ('pretest','paper_i','paper_ii','paper_iii'):
                                fields['paper'] = new_val
                            else:
                                print_colored("[!] Invalid paper. Must be pretest, paper_i, paper_ii, or paper_iii.", COLORS.RED)

            syllabus_id = fields['syllabus_id']
            chapter = fields['chapter']
            subject = fields['subject']
            lecturer = fields['lecturer']
            nepali_date = fields['nepali_date']
            time_str = fields['time']
            paper = fields['paper']
        else:
            subject = parsed['subject']
            lecturer = parsed['lecturer']
            nepali_date = parsed['nepali_date']
            time_str = parsed['time']
            paper = detected_paper
    else:
        # ---- No auto‑detection – ask manually ----
        print_colored("[i] Could not auto‑parse title. Please enter manually.", COLORS.YELLOW)
        subject = input(color_text("Subject (course name): ", COLORS.MAGENTA)).strip()
        lecturer = input(color_text("Lecturer Name: ", COLORS.MAGENTA)).strip()
        nepali_date = input(color_text("Nepali Date (B.S.): ", COLORS.MAGENTA)).strip()
        time_str = input(color_text("Time: ", COLORS.MAGENTA)).strip()
        # Ask paper manually
        print("Select paper:")
        print("  pretest  - Pretest Officer")
        print("  paper_i  - First Paper: Economics")
        print("  paper_ii - Second Paper: Management")
        print("  paper_iii- Third Paper: Research, ICT & Banking")
        paper = input(color_text("Paper (default pretest): ", COLORS.MAGENTA)).strip()
        if paper not in ('pretest','paper_i','paper_ii','paper_iii'):
            paper = 'pretest'

    # ---- Mirror ID ----
    mirror_id = input(color_text("Mirror Video ID (optional, press Enter to skip): ", COLORS.MAGENTA)).strip()
    if mirror_id:
        mirror_id = extract_video_id(mirror_id) or mirror_id
        if mirror_id and len(mirror_id) != 11:
            print_colored("[!] Invalid mirror ID, will be stored as-is.", COLORS.YELLOW)

        # Duplicate mirror check
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(f"""
            SELECT id FROM {TABLE_NAME}
            WHERE video_id = %s OR mirror_video_id = %s
        """, (mirror_id, mirror_id))
        if cursor.fetchone():
            print_colored("[!] This mirror ID is already used by another record.", COLORS.YELLOW)
            proceed = input(color_text("Do you still want to use it? (y/n): ", COLORS.MAGENTA)).strip().lower()
            if proceed != 'y':
                print_colored("Aborting. Please choose another mirror ID.", COLORS.RED)
                cursor.close()
                conn.close()
                return
        cursor.close()
        conn.close()
    else:
        mirror_id = None

    notes = input(color_text("Notes (optional, press Enter to skip): ", COLORS.MAGENTA)).strip() or None

    # ---- Insert ----
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(f"""
        INSERT INTO {TABLE_NAME}
        (video_id, mirror_video_id, video_title, syllabus_id, subject, chapter, lecturer, nepali_date, time, notes, paper)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (video_id, mirror_id, title, syllabus_id, subject, chapter, lecturer, nepali_date, time_str, notes, paper))
        conn.commit()
        cursor.close()
        conn.close()
        print_colored("[✓] Record added.", COLORS.GREEN)
    except mysql.connector.IntegrityError as e:
        conn.rollback()
        cursor.close()
        conn.close()
        if "Duplicate entry" in str(e) and "mirror_video_id" in str(e):
            print_colored("[!] Mirror ID is already used by another record. Record not added.", COLORS.RED)
            print("   (The unique index on mirror_video_id prevented this duplicate.)")
        else:
            print_colored(f"[!] Database error: {e}", COLORS.RED)
        return

    # ---- Download ----
    if input(color_text("Download now? (y/n): ", COLORS.MAGENTA)).strip().lower() == 'y':
        record = get_record_by_video_id(video_id)
        if record:
            download_video(record, silent=True)

def view_all():
    conn = get_connection()
    cursor = conn.cursor()

    sort_options = {
        '1': ('syllabus_id', 'ASC'),
        '2': ('subject', 'ASC'),
        '3': ('lecturer', 'ASC'),
        '4': ('nepali_date', 'ASC'),
        '5': ('time', 'ASC'),
        '6': ('chapter', 'ASC'),
        '0': ('nepali_date', 'ASC')   # changed default from DESC to ASC
    }

    print("\n" + "═" * 50)
    print_colored("  VIEW ALL LECTURES", COLORS.CYAN, bold=True)
    print("═" * 50)
    print("Sort by:")
    print("  1. Syllabus ID")
    print("  2. Subject")
    print("  3. Lecturer")
    print("  4. Nepali Date")
    print("  5. Time")
    print("  6. Chapter")
    print("  0. Default: Nepali Date, then time (ascending)")
    choice = input(color_text("Choose (0-6, default 0): ", COLORS.MAGENTA)).strip() or '0'
    if choice not in sort_options:
        choice = '0'

    col, default_order = sort_options[choice]

    if choice == '0':
        order = 'ASC'
    else:
        order_prompt = f"Order (a=ascending, d=descending, default {default_order}): "
        order_choice = input(color_text(order_prompt, COLORS.MAGENTA)).strip().lower()
        if order_choice == 'a':
            order = 'ASC'
        elif order_choice == 'd':
            order = 'DESC'
        else:
            order = default_order

    if choice == '0':
        order_clause = "ORDER BY nepali_date ASC, time ASC"
    elif choice == '4':
        order_clause = f"ORDER BY nepali_date {order}, time {order}"
    else:
        order_clause = f"ORDER BY {col} {order}"

    query = f"""
        SELECT syllabus_id, chapter, subject, lecturer, nepali_date, time, video_id, mirror_video_id
        FROM {TABLE_NAME}
        {order_clause}
    """
    cursor.execute(query)
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    if not rows:
        print_colored("[i] No records.", COLORS.YELLOW)
        return

    sort_desc = f"{col} ({order.lower()})"
    print(f"\n--- ALL RECORDS (sorted by {sort_desc}) ---")
    for syllabus_id, chapter, subject, lecturer, nepali_date, time_str, video_id, mirror_id in rows:
        syllabus = clean_field(syllabus_id)
        chapter_display = clean_field(chapter) if chapter else get_display_title({'chapter': chapter, 'video_title': '', 'subject': subject})
        subject = clean_field(subject)
        lecturer = clean_field(lecturer)
        nepali_date = clean_field(nepali_date)
        time_str = clean_field(time_str)

        # --- Determine bracket value based on sort column ---
        if col == 'syllabus_id':
            bracket_val = syllabus
        elif col == 'subject':
            bracket_val = subject
        elif col == 'lecturer':
            bracket_val = lecturer
        elif col == 'nepali_date':
            bracket_val = nepali_date
        elif col == 'time':
            bracket_val = time_str
        elif col == 'chapter':
            bracket_val = chapter_display   # use the display title
        else:
            bracket_val = nepali_date       # fallback (should not happen)

        bracket = color_text(f"[{bracket_val}] ", COLORS.CYAN, bold=True) if bracket_val else ""

        main = f"{syllabus} || {chapter_display} || {subject} || {lecturer} || {nepali_date} || {time_str}"
        id_part = f"(original: {video_id}"
        if mirror_id:
            id_part += f" | mirror: {mirror_id}"
        id_part += ")"
        print(f"{bracket}{main} {id_part}")

def view_one():
    raw = input(color_text("Enter video ID, syllabus ID, mirror ID, or YouTube URL: ", COLORS.MAGENTA)).strip()
    if not raw:
        return

    # If it's a URL, extract the video ID; otherwise keep as-is (for syllabus ID)
    identifier = extract_video_id(raw) or raw

    conn = get_connection()
    cursor = conn.cursor(dictionary=True, buffered=True)
    cursor.execute(f"""
        SELECT id, video_id, mirror_video_id, video_title, syllabus_id, subject,
               chapter, lecturer, nepali_date, time, notes, original_filename, file_hash
        FROM {TABLE_NAME}
        WHERE video_id = %s OR syllabus_id = %s OR mirror_video_id = %s
    """, (identifier, identifier, identifier))
    row = cursor.fetchone()
    cursor.close()
    conn.close()

    if not row:
        print_colored("[!] Not found.", COLORS.RED)
        return

    # ---- Locate the actual file on disk ----
    file_path = None
    file_hash = row.get('file_hash')
    if file_hash:
        target_dir, _ = get_target_path(row, interactive=False)
        if target_dir:
            import glob
            pattern = os.path.join(target_dir, file_hash + '.*')
            matches = glob.glob(pattern)
            if matches:
                file_path = matches[0]
        # If not found in expected dir, search entire ROOT_DIR
        if not file_path:
            for root, _, files in os.walk(ROOT_DIR):
                for f in files:
                    if f.startswith(file_hash) and f.lower().endswith(('.mp4', '.mkv', '.webm', '.avi', '.mov')):
                        file_path = os.path.join(root, f)
                        break
                if file_path:
                    break

    print("\n" + "═" * 50)
    print_colored("  RECORD DETAILS", COLORS.CYAN, bold=True)
    print("═" * 50)
    print(f"ID           : {row['id']}")
    print(f"Video ID     : {row['video_id']}")
    print(f"Syllabus ID  : {clean_field(row['syllabus_id'])}")
    print(f"Subject      : {clean_field(row['subject'])}")
    print(f"Chapter      : {clean_field(row['chapter']) if row['chapter'] else '(auto: ' + get_display_title({'chapter': row['chapter'], 'video_title': row['video_title'], 'subject': row['subject']}) + ')'}")
    print(f"Lecturer     : {clean_field(row['lecturer'])}")
    print(f"Nepali Date  : {clean_field(row['nepali_date'])}")
    print(f"Time         : {clean_field(row['time'])}")
    print(f"Video Title  : {row['video_title']}")
    print(f"Mirror ID    : {row['mirror_video_id'] if row['mirror_video_id'] else '(none)'}")
    print(f"Notes        : {row['notes'] if row['notes'] else '(none)'}")
    print(f"Original Filename: {row.get('original_filename') or '(none)'}")
    if file_path:
        print_colored(f"File Location: {file_path}", COLORS.BLUE)
    else:
        print_colored("File Location: (not found on disk)", COLORS.RED)

    print(f"Embed URL (original): {get_embed_link(row['video_id'])}")
    if row['mirror_video_id']:
        print(f"Embed URL (mirror) : {get_embed_link(row['mirror_video_id'])}")
    print("═" * 50)

def update_lecture():
    while True:
        identifier = input(color_text("Enter Video ID or Mirror ID to update (or press Enter to return): ", COLORS.MAGENTA)).strip()
        if not identifier:
            print_colored("Returning to main menu.", COLORS.YELLOW)
            return

        record = get_record_by_any_id(identifier)
        if not record:
            print_colored("[!] Record not found.", COLORS.RED)
            continue

        video_id = record['video_id']
        old_record = record.copy()
        old_syllabus_id = record.get('syllabus_id')
        old_video_id = record.get('video_id')

        while True:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute(f"""
                SELECT id, video_id, mirror_video_id, video_title, syllabus_id, subject, chapter, lecturer, nepali_date, time, notes, paper
                FROM {TABLE_NAME} WHERE video_id = %s
            """, (video_id,))
            row = cursor.fetchone()
            cursor.close()
            conn.close()

            if not row:
                print_colored("[!] Record not found. Exiting update for this ID.", COLORS.RED)
                break

            print("\n" + "═" * 50)
            print_colored("  UPDATE LECTURE", COLORS.CYAN, bold=True)
            print("═" * 50)
            print(f"1. Video ID     : {row[1]}")
            print(f"2. Syllabus ID  : {row[4]}")
            print(f"3. Subject      : {row[5]}")
            print(f"4. Chapter      : {row[6] if row[6] else '(auto)'}")
            print(f"5. Lecturer     : {row[7]}")
            print(f"6. Nepali Date  : {row[8]}")
            print(f"7. Time         : {row[9]}")
            print(f"8. Video Title  : {row[3]}")
            print(f"9. Mirror ID    : {row[2] if row[2] else '(none)'}")
            print("10. Notes        : " + (row[10] if row[10] else '(none)'))
            print("11. Paper        : " + (row[11] if row[11] else '(none)'))
            print("0. Finish / Exit update mode for this lecture")

            field_map = {
                '1': 'video_id',
                '2': 'syllabus_id',
                '3': 'subject',
                '4': 'chapter',
                '5': 'lecturer',
                '6': 'nepali_date',
                '7': 'time',
                '8': 'video_title',
                '9': 'mirror_video_id',
                '10': 'notes',
                '11': 'paper'
            }

            choice = input(color_text("Choose field to update (1-11) or 0 to exit: ", COLORS.MAGENTA)).strip()
            if choice == '0':
                print_colored("Exiting update mode for this lecture.", COLORS.YELLOW)
                break

            if choice not in field_map:
                print_colored("[!] Invalid choice.", COLORS.RED)
                continue

            field = field_map[choice]

            # --- Special handling for paper field (show options) ---
            if field == 'paper':
                print("\nAvailable papers:")
                paper_options = ['pretest', 'paper_i', 'paper_ii', 'paper_iii']
                for i, p in enumerate(paper_options, 1):
                    folder = PAPER_CONFIG.get(p, {}).get('folder', '')
                    print(f"  {i}. {p} ({folder})")
                print("  0. Cancel (keep current)")
                paper_choice = input(color_text(f"Choose paper (1-4, or 0 to keep '{row[11] if row[11] else 'none'}'): ", COLORS.MAGENTA)).strip()

                if paper_choice.isdigit():
                    idx = int(paper_choice)
                    if 1 <= idx <= len(paper_options):
                        new_paper = paper_options[idx-1]
                    elif idx == 0:
                        new_paper = row[11]  # keep existing
                    else:
                        print_colored("[!] Invalid choice.", COLORS.RED)
                        continue
                else:
                    # fallback: manual entry
                    new_paper = input(color_text(f"Paper (or press Enter to keep '{row[11] if row[11] else 'none'}'): ", COLORS.MAGENTA)).strip()
                    if new_paper and new_paper not in ('pretest', 'paper_i', 'paper_ii', 'paper_iii'):
                        print_colored("[!] Invalid paper. Must be pretest, paper_i, paper_ii, or paper_iii.", COLORS.RED)
                        continue

                # Now update
                if new_paper:
                    conn = get_connection()
                    cursor = conn.cursor()
                    cursor.execute(f"UPDATE {TABLE_NAME} SET paper = %s WHERE id = %s", (new_paper, row[0]))
                    conn.commit()
                    cursor.close()
                    conn.close()
                    print_colored("[✓] Paper updated.", COLORS.GREEN)

                    # --- NEW: Ask to move the file if paper changed ---
                    if new_paper != row[11]:
                        updated_record = get_record_by_video_id(video_id)
                        if updated_record:
                            move_choice = input(color_text("Paper updated. Move the video file to the new location now? (y/n): ", COLORS.MAGENTA)).strip().lower()
                            if move_choice == 'y':
                                from .file_manager import organize_video
                                result = organize_video(updated_record, overwrite=False, interactive=False)
                                if result:
                                    print_colored("[✓] File moved to correct location.", COLORS.GREEN)
                                else:
                                    print_colored("[!] File move failed. You can manually move it later with option 15.", COLORS.YELLOW)
                else:
                    # Set to NULL if empty
                    conn = get_connection()
                    cursor = conn.cursor()
                    cursor.execute(f"UPDATE {TABLE_NAME} SET paper = NULL WHERE id = %s", (row[0],))
                    conn.commit()
                    cursor.close()
                    conn.close()
                    print_colored("[✓] Paper cleared.", COLORS.GREEN)
                continue  # skip the rest of the loop for paper

            # --- For other fields, get new value ---
            new_value = input(color_text(f"New value for {field}: ", COLORS.MAGENTA)).strip()

            # --- Handle special fields ---
            if field == 'video_id':
                if not extract_video_id(new_value):
                    print_colored("[!] Invalid ID.", COLORS.RED)
                    continue
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute(f"SELECT id FROM {TABLE_NAME} WHERE video_id = %s AND id != %s", (new_value, row[0]))
                if cursor.fetchone():
                    print_colored("[!] ID already used.", COLORS.RED)
                    cursor.close()
                    conn.close()
                    continue
                cursor.close()
                conn.close()
                new_title = fetch_youtube_title(new_value)
                conn = get_connection()
                cursor = conn.cursor()
                if new_title:
                    cursor.execute(f"UPDATE {TABLE_NAME} SET video_id = %s, video_title = %s WHERE id = %s",
                                   (new_value, new_title, row[0]))
                else:
                    cursor.execute(f"UPDATE {TABLE_NAME} SET video_id = %s WHERE id = %s", (new_value, row[0]))
                conn.commit()
                cursor.close()
                conn.close()
                video_id = new_value
                print_colored("[✓] Video ID updated.", COLORS.GREEN)

            elif field == 'syllabus_id':
                if new_value:
                    new_value = normalize_syllabus_id(new_value)
                conn = get_connection()
                cursor = conn.cursor()
                try:
                    cursor.execute(f"UPDATE {TABLE_NAME} SET syllabus_id = %s WHERE id = %s", (new_value, row[0]))
                    conn.commit()
                    cursor.close()
                    conn.close()
                    print_colored("[✓] Syllabus ID updated.", COLORS.GREEN)
                except mysql.connector.Error as e:
                    conn.rollback()
                    cursor.close()
                    conn.close()
                    print_colored(f"[!] Update failed: {e}", COLORS.RED)

            elif field == 'mirror_video_id':
                if new_value:
                    new_value = extract_video_id(new_value) or new_value
                    if len(new_value) != 11:
                        print_colored("[!] Warning: ID length not 11, storing as-is.", COLORS.YELLOW)
                    # Duplicate mirror check
                    conn = get_connection()
                    cursor = conn.cursor()
                    cursor.execute(f"""
                        SELECT id FROM {TABLE_NAME}
                        WHERE (video_id = %s OR mirror_video_id = %s) AND id != %s
                    """, (new_value, new_value, row[0]))
                    if cursor.fetchone():
                        print_colored("[!] This mirror ID is already used by another record.", COLORS.YELLOW)
                        proceed = input(color_text("Do you still want to use it? (y/n): ", COLORS.MAGENTA)).strip().lower()
                        if proceed != 'y':
                            cursor.close()
                            conn.close()
                            print_colored("Aborted.", COLORS.YELLOW)
                            continue
                    cursor.close()
                    conn.close()
                else:
                    new_value = None
                conn = get_connection()
                cursor = conn.cursor()
                try:
                    cursor.execute(f"UPDATE {TABLE_NAME} SET mirror_video_id = %s WHERE id = %s", (new_value, row[0]))
                    conn.commit()
                    cursor.close()
                    conn.close()
                    print_colored("[✓] Mirror ID updated.", COLORS.GREEN)
                except mysql.connector.IntegrityError as e:
                    conn.rollback()
                    cursor.close()
                    conn.close()
                    if "Duplicate entry" in str(e) and "mirror_video_id" in str(e):
                        print_colored("[!] Mirror ID is already used by another record. Update failed.", COLORS.RED)
                    else:
                        print_colored(f"[!] Database error: {e}", COLORS.RED)

            elif field == 'notes':
                if not new_value:
                    new_value = None
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute(f"UPDATE {TABLE_NAME} SET notes = %s WHERE id = %s", (new_value, row[0]))
                conn.commit()
                cursor.close()
                conn.close()
                print_colored("[✓] Notes updated.", COLORS.GREEN)

            else:
                # Generic update for other fields (subject, chapter, lecturer, etc.)
                conn = get_connection()
                cursor = conn.cursor()
                try:
                    cursor.execute(f"UPDATE {TABLE_NAME} SET {field} = %s WHERE id = %s", (new_value, row[0]))
                    conn.commit()
                    cursor.close()
                    conn.close()
                    print_colored(f"[✓] {field.capitalize()} updated.", COLORS.GREEN)
                except mysql.connector.Error as e:
                    conn.rollback()
                    cursor.close()
                    conn.close()
                    print_colored(f"[!] Update failed: {e}", COLORS.RED)

        # After exiting inner loop, ask if user wants to continue updating another record
        if input(color_text("Update another lecture? (y/n): ", COLORS.MAGENTA)).strip().lower() != 'y':
            print_colored("Returning to main menu.", COLORS.YELLOW)
            return

def delete_lecture():
    raw = input(color_text("Enter Video ID, Syllabus ID, or YouTube URL: ", COLORS.MAGENTA)).strip()
    if not raw:
        return

    identifier = extract_video_id(raw) or raw   # if URL -> video ID, else keep as is

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(f"""
        SELECT * FROM {TABLE_NAME}
        WHERE video_id = %s OR syllabus_id = %s
    """, (identifier, identifier))
    records = cursor.fetchall()
    cursor.close()
    conn.close()

    if not records:
        print_colored("[!] No records found for that identifier.", COLORS.RED)
        return

    # Show what will be deleted
    print("\n" + "═" * 50)
    print_colored("  RECORDS TO BE DELETED", COLORS.CYAN, bold=True)
    print("═" * 50)
    for rec in records:
        print(f"  ID: {rec['id']} | Video: {rec['video_id']} | Syllabus: {rec['syllabus_id']} | Subject: {rec['subject']}")
    print("═" * 50)

    confirm = input(color_text(f"Delete {len(records)} record(s)? (y/n): ", COLORS.MAGENTA)).strip().lower()
    if confirm != 'y':
        print_colored("Cancelled.", COLORS.YELLOW)
        return

    # Delete them
    conn = get_connection()
    cursor = conn.cursor()
    # Use a loop or IN clause
    ids = [rec['id'] for rec in records]
    placeholders = ','.join(['%s'] * len(ids))
    cursor.execute(f"DELETE FROM {TABLE_NAME} WHERE id IN ({placeholders})", ids)
    conn.commit()
    deleted = cursor.rowcount
    cursor.close()
    conn.close()

    print_colored(f"[✓] Deleted {deleted} record(s).", COLORS.GREEN)

def download_existing():
    identifier = input(color_text("Enter video ID or mirror ID to download (or URL): ", COLORS.MAGENTA)).strip()
    if not identifier:
        return

    vid_to_dl = extract_video_id(identifier)
    if not vid_to_dl:
        print_colored("[!] Invalid video ID or URL.", COLORS.RED)
        return

    # Try to get record by video_id first, then mirror
    record = get_record_by_video_id(vid_to_dl) or get_record_by_any_id(vid_to_dl)
    if not record:
        print_colored("[!] No record found for that ID.", COLORS.RED)
        return

    download_video(record, video_id_to_download=vid_to_dl)

def show_embed_link():
    raw = input(color_text("Enter video ID, mirror ID, or YouTube URL: ", COLORS.MAGENTA)).strip()
    if not raw:
        return
    identifier = extract_video_id(raw) or raw

    conn = get_connection()
    cursor = conn.cursor(buffered=True)
    cursor.execute(f"""
        SELECT video_id, mirror_video_id FROM {TABLE_NAME}
        WHERE video_id = %s OR mirror_video_id = %s
    """, (identifier, identifier))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    if not row:
        print_colored("[!] Not found.", COLORS.RED)
        return
    print(f"\nEmbed URL (original): {get_embed_link(row[0])}")
    if row[1]:
        print(f"Embed URL (mirror) : {get_embed_link(row[1])}")
    print()

def refresh_titles():
    print("\n" + "═" * 50)
    print_colored("  REFRESH VIDEO TITLES", COLORS.CYAN, bold=True)
    print("═" * 50)
    choice = input(color_text("Refresh all? (y/n, or enter video ID for single): ", COLORS.MAGENTA)).strip()
    if choice.lower() == 'y':
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(f"SELECT id, video_id FROM {TABLE_NAME}")
        rows = cursor.fetchall()
        if not rows:
            print_colored("[i] No records.", COLORS.YELLOW)
            cursor.close()
            conn.close()
            return
        updated = 0
        for id_, vid in rows:
            title = fetch_youtube_title(vid)
            if title:
                cursor.execute(f"UPDATE {TABLE_NAME} SET video_title = %s WHERE id = %s", (title, id_))
                updated += 1
                print(f"  Updated {vid} -> '{title}'")
        conn.commit()
        cursor.close()
        conn.close()
        print_colored(f"[✓] Updated {updated} records.", COLORS.GREEN)
    else:
        video_id = extract_video_id(choice)
        if not video_id:
            print_colored("[!] Invalid input.", COLORS.RED)
            return
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(f"SELECT id FROM {TABLE_NAME} WHERE video_id = %s", (video_id,))
        row = cursor.fetchone()
        if not row:
            print_colored("[!] Video ID not found.", COLORS.RED)
            cursor.close()
            conn.close()
            return
        title = fetch_youtube_title(video_id)
        if title:
            cursor.execute(f"UPDATE {TABLE_NAME} SET video_title = %s WHERE video_id = %s", (title, video_id))
            conn.commit()
            print_colored(f"[✓] Updated title for {video_id} to '{title}'", COLORS.GREEN)
        else:
            print_colored("[!] Could not fetch title.", COLORS.RED)
        cursor.close()
        conn.close()

# ========== SEARCH ==========
def search_lectures():
    print("\n" + "═" * 50)
    print_colored("  SEARCH LECTURES", COLORS.CYAN, bold=True)
    print("═" * 50)
    query = input(color_text("Enter search term: ", COLORS.MAGENTA)).strip()
    if not query:
        print_colored("Cancelled.", COLORS.YELLOW)
        return

    like = f"%{query}%"  # <--- define like here

    conn = get_connection()
    cursor = conn.cursor()
    sql = f"""
    SELECT syllabus_id, chapter, subject, lecturer, nepali_date, time, video_id, mirror_video_id
    FROM {TABLE_NAME}
    WHERE syllabus_id LIKE %s
       OR subject LIKE %s
       OR chapter LIKE %s
       OR lecturer LIKE %s
       OR nepali_date LIKE %s
       OR time LIKE %s
       OR video_id LIKE %s
       OR mirror_video_id LIKE %s
       OR video_title LIKE %s
       OR notes LIKE %s
       OR file_hash LIKE %s
    ORDER BY nepali_date DESC, time DESC
    """
    params = (like, like, like, like, like, like, like, like, like, like, like)  # 11 placeholders

    try:
        cursor.execute(sql, params)
    except Exception as e:
        print_colored(f"[!] Search failed: {e}", COLORS.RED)
        cursor.close()
        conn.close()
        return

    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    if not rows:
        print_colored("[i] No matches found.", COLORS.YELLOW)
        return

    print(f"\n--- SEARCH RESULTS ({len(rows)} found, newest first) ---")
    for syllabus_id, chapter, subject, lecturer, nepali_date, time_str, video_id, mirror_id in rows:
        syllabus = clean_field(syllabus_id)
        chapter_display = clean_field(chapter) if chapter else get_display_title({'chapter': chapter, 'video_title': '', 'subject': subject})
        subject = clean_field(subject)
        lecturer = clean_field(lecturer)
        nepali_date = clean_field(nepali_date)
        time_str = clean_field(time_str)

        bracket = color_text(f"[{nepali_date}] ", COLORS.CYAN, bold=True) if nepali_date else ""
        main = f"{syllabus} || {chapter_display} || {subject} || {lecturer} || {nepali_date} || {time_str}"
        id_part = f"(original: {video_id}"
        if mirror_id:
            id_part += f" | mirror: {mirror_id}"
        id_part += ")"
        print(f"{bracket}{main} {id_part}")
    print()

def search_all():
    print("\n" + "═" * 50)
    print_colored("  SEARCH ALL MEDIA (YouTube + Facebook)", COLORS.CYAN, bold=True)
    print("═" * 50)
    query = input(color_text("Enter search term: ", COLORS.MAGENTA)).strip()
    if not query:
        print_colored("Cancelled.", COLORS.YELLOW)
        return

    like = f"%{query}%"

    # Search YouTube (existing code, we'll copy the logic)
    conn = get_connection()
    cursor = conn.cursor()
    sql_yt = f"""
    SELECT 'youtube' as source, syllabus_id, subject, chapter, lecturer, nepali_date, time, video_id, mirror_video_id, video_title
    FROM {TABLE_NAME}
    WHERE syllabus_id LIKE %s
       OR subject LIKE %s
       OR chapter LIKE %s
       OR lecturer LIKE %s
       OR nepali_date LIKE %s
       OR time LIKE %s
       OR video_id LIKE %s
       OR mirror_video_id LIKE %s
       OR video_title LIKE %s
       OR notes LIKE %s
       OR file_hash LIKE %s
    """
    params = (like, like, like, like, like, like, like, like, like, like, like)
    cursor.execute(sql_yt, params)
    yt_rows = cursor.fetchall()

    # Search Facebook
    sql_fb = f"""
    SELECT 'facebook' as source, id as fb_id, type, title, uploader, facebook_id, url, file_hash, original_filename, notes, download_date
    FROM facebook_entries
    WHERE title LIKE %s
       OR uploader LIKE %s
       OR facebook_id LIKE %s
       OR url LIKE %s
       OR file_hash LIKE %s
       OR notes LIKE %s
    """
    params_fb = (like, like, like, like, like, like)
    cursor.execute(sql_fb, params_fb)
    fb_rows = cursor.fetchall()
    cursor.close()
    conn.close()

    if not yt_rows and not fb_rows:
        print_colored("[i] No matches found.", COLORS.YELLOW)
        return

    print(f"\n--- SEARCH RESULTS ({len(yt_rows)} YouTube, {len(fb_rows)} Facebook) ---")
    for row in yt_rows:
        syllabus = clean_field(row[1] or '')
        chapter_display = clean_field(row[2]) if row[2] else get_display_title({'chapter': row[2], 'video_title': row[10], 'subject': row[3]})
        subject = clean_field(row[3])
        lecturer = clean_field(row[4])
        nepali_date = clean_field(row[5])
        time_str = clean_field(row[6])
        bracket = color_text(f"[{nepali_date}] ", COLORS.CYAN, bold=True) if nepali_date else ""
        main = f"{syllabus} || {chapter_display} || {subject} || {lecturer} || {nepali_date} || {time_str}"
        id_part = f"(original: {row[7]}"
        if row[8]:
            id_part += f" | mirror: {row[8]}"
        id_part += ")"
        print(f"{bracket}{main} {id_part}")

    for row in fb_rows:
        # row: source, fb_id, type, title, uploader, facebook_id, url, file_hash, original_filename, notes, download_date
        fb_id = row[1]
        type_str = row[2]
        title = row[3] or ''
        uploader = row[4] or ''
        fb_hash = row[7] or ''
        bracket = color_text(f"[Facebook] ", COLORS.MAGENTA, bold=True)
        main = f"{type_str}: {title} (by {uploader})"
        id_part = f"(fb_id: {fb_id}, hash: {fb_hash})"
        print(f"{bracket}{main} {id_part}")
    print()
# lecture_manager/dashboard.py

import os
import subprocess
import glob
from datetime import datetime
from collections import Counter
from .db import get_connection, TABLE_NAME
from .file_manager import ROOT_DIR, collect_tally_data, PAPER_CONFIG
from .utils import print_colored, color_text, COLORS

def get_storage_usage(path):
    """Get total size of a directory in human-readable format."""
    try:
        result = subprocess.run(['du', '-sh', path], capture_output=True, text=True)
        return result.stdout.split()[0] if result.returncode == 0 else "N/A"
    except Exception:
        return "N/A"

def get_paper_sizes():
    """
    Return a dict mapping paper folder name to its size (human-readable).
    """
    sizes = {}
    for paper_key, config in PAPER_CONFIG.items():
        folder = config['folder']
        full_path = os.path.join(ROOT_DIR, folder)
        if os.path.exists(full_path):
            sizes[folder] = get_storage_usage(full_path)
        else:
            sizes[folder] = "0B"
    return sizes

def get_file_type_counts():
    """
    Count video files by extension in the library.
    """
    exts = ('.mp4', '.mkv', '.webm', '.avi', '.mov')
    counts = Counter()
    for root, _, files in os.walk(ROOT_DIR):
        for f in files:
            if f.lower().endswith(exts):
                ext = os.path.splitext(f)[1].lower()
                counts[ext] += 1
    return counts

def get_recent_records(limit=5):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(f"""
        SELECT id, video_id, syllabus_id, subject, lecturer, nepali_date, time
        FROM {TABLE_NAME}
        ORDER BY id DESC
        LIMIT %s
    """, (limit,))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return rows

def get_top_lecturers(limit=5):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(f"""
        SELECT lecturer, COUNT(*) as count
        FROM {TABLE_NAME}
        WHERE lecturer IS NOT NULL AND lecturer != ''
        GROUP BY lecturer
        ORDER BY count DESC
        LIMIT %s
    """, (limit,))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return rows

def get_subject_counts(limit=5):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(f"""
        SELECT subject, COUNT(*) as count
        FROM {TABLE_NAME}
        WHERE subject IS NOT NULL AND subject != ''
        GROUP BY subject
        ORDER BY count DESC
        LIMIT %s
    """, (limit,))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return rows

def show_dashboard():
    """Display a beautiful terminal dashboard with library statistics."""
    print("\n" + "═" * 60)
    print_colored("  📊 LECTURE LIBRARY DASHBOARD", COLORS.CYAN, bold=True)
    print("═" * 60)

    # ----- Collect data -----
    tally = collect_tally_data()

    total_records = len(tally['records'])
    total_files = len(tally['all_files'])
    correctly_placed = len(tally['correctly_placed'])
    missing = len(tally['missing'])
    orphan = len(tally['orphan'])
    mismatched = len(tally['mismatched'])
    unresolved = tally['unresolved']

    # Storage usage (overall and per paper)
    storage = get_storage_usage(ROOT_DIR)
    paper_sizes = get_paper_sizes()
    file_counts = get_file_type_counts()

    # Recent lectures
    recent = get_recent_records(5)

    # Top lecturers
    top_lecturers = get_top_lecturers(5)

    # Top subjects
    top_subjects = get_subject_counts(5)

    # ----- Summary cards -----
    print("\n" + "─" * 60)
    print_colored("  📈 SUMMARY", COLORS.YELLOW, bold=True)
    print("─" * 60)

    # Row of stats
    print(f"  {color_text('Total Records:', COLORS.WHITE)} {color_text(str(total_records), COLORS.CYAN)}")
    print(f"  {color_text('Total Files:', COLORS.WHITE)} {color_text(str(total_files), COLORS.CYAN)}")
    print(f"  {color_text('✅ Correctly Placed:', COLORS.WHITE)} {color_text(str(correctly_placed), COLORS.GREEN)}")
    print(f"  {color_text('❌ Missing:', COLORS.WHITE)} {color_text(str(missing), COLORS.RED)}")
    print(f"  {color_text('🗑️ Orphan Files:', COLORS.WHITE)} {color_text(str(orphan), COLORS.YELLOW)}")
    if mismatched:
        print(f"  {color_text('⚠️ Mismatched:', COLORS.WHITE)} {color_text(str(mismatched), COLORS.YELLOW)}")
    if unresolved:
        print(f"  {color_text('❓ Unresolved Records:', COLORS.WHITE)} {color_text(str(unresolved), COLORS.MAGENTA)}")
    print(f"  {color_text('💾 Library Size:', COLORS.WHITE)} {color_text(storage, COLORS.BLUE)}")

    # Health indicator
    if missing == 0 and mismatched == 0 and unresolved == 0:
        print_colored("\n  ✅ Library is perfectly synced! All records have files in the right place.", COLORS.GREEN)
    else:
        print_colored("\n  ⚠️ Some issues detected – run option 20 (Tally) to investigate and fix.", COLORS.YELLOW)

    # ----- Paper storage breakdown -----
    if paper_sizes:
        print("\n" + "─" * 60)
        print_colored("  📁 STORAGE PER PAPER", COLORS.YELLOW, bold=True)
        print("─" * 60)
        for folder, size in paper_sizes.items():
            print(f"  {folder[:35]:<35} {size}")

    # ----- File type breakdown -----
    if file_counts:
        print("\n" + "─" * 60)
        print_colored("  🎬 FILE TYPES", COLORS.YELLOW, bold=True)
        print("─" * 60)
        total_ext = sum(file_counts.values())
        for ext, count in sorted(file_counts.items(), key=lambda x: -x[1]):
            pct = (count / total_ext * 100) if total_ext else 0
            bar = "█" * int(pct / 2)  # scale 50% -> 1 char
            print(f"  {ext:<6} {count:>4} files  {bar} {pct:.1f}%")

    # ----- Recent lectures -----
    if recent:
        print("\n" + "─" * 60)
        print_colored("  🕒 RECENTLY ADDED LECTURES", COLORS.YELLOW, bold=True)
        print("─" * 60)
        for rec in recent:
            date_str = rec.get('nepali_date', '') or ''
            time_str = rec.get('time', '') or ''
            lecturer = rec.get('lecturer', '') or ''
            subject = rec.get('subject', '') or ''
            print(f"  {rec['syllabus_id']} | {subject[:30]:<30} | {lecturer:<15} | {date_str} {time_str}")

    # ----- Top lecturers (with scaled bar) -----
    if top_lecturers:
        print("\n" + "─" * 60)
        print_colored("  👨‍🏫 TOP LECTURERS", COLORS.YELLOW, bold=True)
        print("─" * 60)
        max_count = max(c for _, c in top_lecturers) if top_lecturers else 1
        for lecturer, count in top_lecturers:
            bar_len = int((count / max_count) * 20)
            bar = "█" * bar_len
            print(f"  {lecturer[:20]:<20} {bar} {count}")

    # ----- Top subjects (with scaled bar) -----
    if top_subjects:
        print("\n" + "─" * 60)
        print_colored("  📚 TOP SUBJECTS", COLORS.YELLOW, bold=True)
        print("─" * 60)
        max_count = max(c for _, c in top_subjects) if top_subjects else 1
        for subject, count in top_subjects:
            bar_len = int((count / max_count) * 20)
            bar = "█" * bar_len
            print(f"  {subject[:25]:<25} {bar} {count}")

    print("\n" + "═" * 60)
    print_colored("  Dashboard generated at " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"), COLORS.BLUE)
    print("═" * 60 + "\n")

        # ---- Facebook stats ----
    from .file_manager import collect_facebook_tally_data
    fb_tally = collect_facebook_tally_data()
    if fb_tally['total_entries'] > 0 or fb_tally['orphan'] or fb_tally['missing']:
        print("\n" + "─" * 60)
        print_colored("  📘 FACEBOOK", COLORS.MAGENTA, bold=True)
        print("─" * 60)
        print(f"  Total entries  : {fb_tally['total_entries']} (videos: {fb_tally['by_type']['video']}, photos: {fb_tally['by_type']['photo']})")
        print(f"  Files on disk  : {len(fb_tally['files_found'])}")
        if fb_tally['missing']:
            print_colored(f"  ❌ Missing      : {len(fb_tally['missing'])} entries", COLORS.RED)
        if fb_tally['orphan']:
            print_colored(f"  🗑️ Orphan       : {len(fb_tally['orphan'])} files", COLORS.YELLOW)
        if not fb_tally['missing'] and not fb_tally['orphan']:
            print_colored("  ✅ All Facebook entries are synced!", COLORS.GREEN)
# File db.py

import mysql.connector
from mysql.connector import Error
from . import config
from .utils import print_colored, COLORS

TABLE_NAME = 'youtube_lectures'

def get_connection():
    if config.db_config is None:
        config.load_or_create_config()
    try:
        return mysql.connector.connect(**config.db_config)
    except Error as e:
        print_colored(f"[!] Database connection error: {e}", COLORS.RED)
        print("Please check your credentials and try again.")
        exit(1)

def create_table():
    conn = get_connection()
    cursor = conn.cursor()
    # Main lectures table with unique index on mirror_video_id
    cursor.execute(f"""
    CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
        id INT AUTO_INCREMENT PRIMARY KEY,
        video_id VARCHAR(20) NOT NULL UNIQUE,
        video_title TEXT,
        syllabus_id VARCHAR(20),
        subject VARCHAR(255),
        chapter VARCHAR(255),
        lecturer VARCHAR(255),
        nepali_date VARCHAR(20),
        time VARCHAR(20),
        notes TEXT,
        mirror_video_id VARCHAR(20) NULL,
        file_hash VARCHAR(32) NULL,
        paper ENUM('pretest','paper_i','paper_ii','paper_iii') NULL,
        UNIQUE INDEX idx_mirror_video_id (mirror_video_id),
        INDEX idx_paper (paper)
    );
    """)
    # Trash entries
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS trash_entries (
        id INT AUTO_INCREMENT PRIMARY KEY,
        original_path VARCHAR(512) NOT NULL,
        record_id INT NULL,
        trash_filename VARCHAR(255) NOT NULL,
        deleted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (record_id) REFERENCES youtube_lectures(id) ON DELETE SET NULL
    );
    """)
    # Hash cache
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS hash_cache (
        id INT AUTO_INCREMENT PRIMARY KEY,
        file_path VARCHAR(512) NOT NULL UNIQUE,
        file_hash VARCHAR(32) NOT NULL,
        status ENUM('active', 'trashed') DEFAULT 'active',
        last_scan DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_status (status)
    );
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS cookies (
        id INT PRIMARY KEY DEFAULT 1,
        cookie_data LONGTEXT NOT NULL,
        last_refresh DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """)
        # Facebook entries
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS facebook_entries (
        id INT AUTO_INCREMENT PRIMARY KEY,
        facebook_id VARCHAR(50) NOT NULL UNIQUE,
        type ENUM('video', 'photo') NOT NULL,
        title VARCHAR(512),
        uploader VARCHAR(255),
        url VARCHAR(512) NOT NULL,
        file_hash VARCHAR(32) NULL,
        original_filename VARCHAR(512) NULL,
        download_date DATETIME DEFAULT CURRENT_TIMESTAMP,
        notes TEXT,
        INDEX idx_uploader (uploader),
        INDEX idx_type (type)
    );
    """)
    conn.commit()
    cursor.close()
    conn.close()
    print_colored(f"[✓] Tables ready.", COLORS.GREEN)

def migrate_table():
    conn = get_connection()
    cursor = conn.cursor()

    # Add paper column if missing
    cursor.execute("SHOW COLUMNS FROM youtube_lectures LIKE 'paper'")
    if not cursor.fetchone():
        cursor.execute("ALTER TABLE youtube_lectures ADD COLUMN paper ENUM('pretest','paper_i','paper_ii','paper_iii') NULL")
        print_colored("[✓] Added 'paper' column.", COLORS.GREEN)
        cursor.execute("ALTER TABLE youtube_lectures ADD INDEX idx_paper (paper)")
        print_colored("[✓] Added index on 'paper'.", COLORS.GREEN)

    # Ensure trash_entries exists
    cursor.execute("SHOW TABLES LIKE 'trash_entries'")
    if not cursor.fetchone():
        cursor.execute("""
        CREATE TABLE trash_entries (
            id INT AUTO_INCREMENT PRIMARY KEY,
            original_path VARCHAR(512) NOT NULL,
            record_id INT NULL,
            trash_filename VARCHAR(255) NOT NULL,
            deleted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (record_id) REFERENCES youtube_lectures(id) ON DELETE SET NULL
        );
        """)
        print_colored("[✓] Created 'trash_entries' table.", COLORS.GREEN)

    # Ensure hash_cache exists and has correct columns
    cursor.execute("SHOW TABLES LIKE 'hash_cache'")
    if not cursor.fetchone():
        cursor.execute("""
        CREATE TABLE hash_cache (
            id INT AUTO_INCREMENT PRIMARY KEY,
            file_path VARCHAR(512) NOT NULL UNIQUE,
            file_hash VARCHAR(32) NOT NULL,
            status ENUM('active', 'trashed') DEFAULT 'active',
            last_scan DATETIME DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_status (status)
        );
        """)
        print_colored("[✓] Created 'hash_cache' table.", COLORS.GREEN)
    # Ensure facebook_entries exists
    cursor.execute("SHOW TABLES LIKE 'facebook_entries'")
    if not cursor.fetchone():
        cursor.execute("""
        CREATE TABLE facebook_entries (
            id INT AUTO_INCREMENT PRIMARY KEY,
            facebook_id VARCHAR(50) NOT NULL UNIQUE,
            type ENUM('video', 'photo') NOT NULL,
            title VARCHAR(512),
            uploader VARCHAR(255),
            url VARCHAR(512) NOT NULL,
            file_hash VARCHAR(32) NULL,
            original_filename VARCHAR(512) NULL,
            download_date DATETIME DEFAULT CURRENT_TIMESTAMP,
            notes TEXT,
            INDEX idx_uploader (uploader),
            INDEX idx_type (type)
        );
        """)
        print_colored("[✓] Created 'facebook_entries' table.", COLORS.GREEN)
    else:
        # Drop obsolete scan_session if present
        cursor.execute("SHOW COLUMNS FROM hash_cache LIKE 'scan_session'")
        if cursor.fetchone():
            cursor.execute("ALTER TABLE hash_cache DROP COLUMN scan_session")
            print_colored("[✓] Dropped obsolete 'scan_session' column.", COLORS.GREEN)
        # Add status if missing
        cursor.execute("SHOW COLUMNS FROM hash_cache LIKE 'status'")
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE hash_cache ADD COLUMN status ENUM('active', 'trashed') DEFAULT 'active'")
            print_colored("[✓] Added 'status' column to hash_cache.", COLORS.GREEN)
        # Add last_scan if missing
        cursor.execute("SHOW COLUMNS FROM hash_cache LIKE 'last_scan'")
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE hash_cache ADD COLUMN last_scan DATETIME DEFAULT CURRENT_TIMESTAMP")
            print_colored("[✓] Added 'last_scan' column to hash_cache.", COLORS.GREEN)

    # --- New: Add unique index on mirror_video_id if missing ---
    cursor.execute("SHOW INDEX FROM youtube_lectures WHERE Key_name = 'idx_mirror_video_id'")
    if not cursor.fetchone():
        print_colored("[i] Adding unique index on mirror_video_id...", COLORS.YELLOW)
        try:
            cursor.execute("ALTER TABLE youtube_lectures ADD UNIQUE INDEX idx_mirror_video_id (mirror_video_id)")
            print_colored("[✓] Added unique index on mirror_video_id.", COLORS.GREEN)
        except mysql.connector.Error as e:
            if e.errno == 1062:  # Duplicate entry
                print_colored("[!] Cannot add unique index: duplicate mirror_video_id entries exist.", COLORS.RED)
                print("Please remove duplicate mirror_video_id entries manually, then run the migration again.")
                print("You can find duplicates with:")
                print("  SELECT mirror_video_id, COUNT(*) FROM youtube_lectures WHERE mirror_video_id IS NOT NULL GROUP BY mirror_video_id HAVING COUNT(*) > 1;")
                print("After cleaning, run 'ALTER TABLE youtube_lectures ADD UNIQUE INDEX idx_mirror_video_id (mirror_video_id);' manually.")
            else:
                print_colored(f"[!] Failed to add unique index: {e}", COLORS.RED)

    # Add original_filename column if missing
    cursor.execute("SHOW COLUMNS FROM youtube_lectures LIKE 'original_filename'")
    if not cursor.fetchone():
        cursor.execute("ALTER TABLE youtube_lectures ADD COLUMN original_filename VARCHAR(512) NULL")
        print_colored("[✓] Added 'original_filename' column.", COLORS.GREEN)

    cursor.close()
    conn.close()

def get_record_by_video_id(video_id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True, buffered=True)
    try:
        cursor.execute(f"SELECT * FROM {TABLE_NAME} WHERE video_id = %s", (video_id,))
        return cursor.fetchone()
    finally:
        cursor.close()
        conn.close()

def get_record_by_any_id(identifier):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True, buffered=True)
    try:
        cursor.execute(f"""
            SELECT * FROM {TABLE_NAME}
            WHERE video_id = %s OR mirror_video_id = %s OR file_hash = %s
        """, (identifier, identifier, identifier))
        return cursor.fetchone()
    finally:
        cursor.close()
        conn.close()

def get_any_media_record(identifier):
    """
    Search both youtube_lectures and facebook_entries for a given identifier.
    Returns a dict with 'source' ('youtube' or 'facebook') and the record data,
    or None if not found.
    """
    # Try YouTube first
    from .facebook_manager import get_facebook_entry_by_id
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(f"SELECT * FROM {TABLE_NAME} WHERE video_id = %s OR mirror_video_id = %s OR file_hash = %s OR syllabus_id = %s",
                   (identifier, identifier, identifier, identifier))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    if row:
        row['source'] = 'youtube'
        return row

    # Try Facebook
    fb_row = get_facebook_entry_by_id(identifier)
    if fb_row:
        fb_row['source'] = 'facebook'
        return fb_row

    return None
# File export.py

import os
import csv
import json
from .db import get_connection, TABLE_NAME
from .youtube import extract_video_id
from .utils import clean_field, get_display_title, print_colored, color_text, COLORS

def get_export_data():
    choice = input(color_text("Export all records? (y/n, n = search results): ", COLORS.MAGENTA)).strip().lower()
    if choice == 'y':
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(f"""
            SELECT video_id, mirror_video_id, video_title, syllabus_id, subject, chapter, lecturer, nepali_date, time, notes
            FROM {TABLE_NAME}
            ORDER BY nepali_date DESC, time DESC
        """)
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return rows
    else:
        query = input(color_text("Enter search term (or leave empty for all): ", COLORS.MAGENTA)).strip()
        conn = get_connection()
        cursor = conn.cursor()
        if query:
            sql = f"""
                SELECT video_id, mirror_video_id, video_title, syllabus_id, subject, chapter, lecturer, nepali_date, time, notes
                FROM {TABLE_NAME}
                WHERE syllabus_id LIKE %s OR subject LIKE %s OR chapter LIKE %s
                   OR lecturer LIKE %s OR nepali_date LIKE %s OR time LIKE %s
                   OR video_id LIKE %s OR mirror_video_id LIKE %s OR video_title LIKE %s OR notes LIKE %s
                ORDER BY nepali_date DESC, time DESC
            """
            like = f"%{query}%"
            params = (like, like, like, like, like, like, like, like, like, like)
            cursor.execute(sql, params)
        else:
            cursor.execute(f"""
                SELECT video_id, mirror_video_id, video_title, syllabus_id, subject, chapter, lecturer, nepali_date, time, notes
                FROM {TABLE_NAME}
                ORDER BY nepali_date DESC, time DESC
            """)
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return rows

def export_csv():
    print("\n" + "═" * 50)
    print_colored("  EXPORT TO CSV", COLORS.CYAN, bold=True)
    print("═" * 50)
    rows = get_export_data()
    if not rows:
        print_colored("[i] No records to export.", COLORS.YELLOW)
        return
    filename = input(color_text("Enter CSV filename (default: lectures_export.csv): ", COLORS.MAGENTA)).strip()
    if not filename:
        filename = "lectures_export.csv"
    if not filename.endswith('.csv'):
        filename += '.csv'

    try:
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['video_id', 'mirror_video_id', 'video_title', 'syllabus_id',
                             'subject', 'chapter', 'lecturer', 'nepali_date', 'time', 'notes'])
            writer.writerows(rows)
        print_colored(f"[✓] Exported {len(rows)} records to {filename}", COLORS.GREEN)
    except Exception as e:
        print_colored(f"[!] Export failed: {e}", COLORS.RED)

def export_json():
    print("\n" + "═" * 50)
    print_colored("  EXPORT TO JSON", COLORS.CYAN, bold=True)
    print("═" * 50)
    rows = get_export_data()
    if not rows:
        print_colored("[i] No records to export.", COLORS.YELLOW)
        return
    filename = input(color_text("Enter JSON filename (default: lectures_export.json): ", COLORS.MAGENTA)).strip()
    if not filename:
        filename = "lectures_export.json"
    if not filename.endswith('.json'):
        filename += '.json'

    columns = ['video_id', 'mirror_video_id', 'video_title', 'syllabus_id',
               'subject', 'chapter', 'lecturer', 'nepali_date', 'time', 'notes']
    data = [dict(zip(columns, row)) for row in rows]

    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print_colored(f"[✓] Exported {len(rows)} records to {filename}", COLORS.GREEN)
    except Exception as e:
        print_colored(f"[!] Export failed: {e}", COLORS.RED)

def import_csv():
    print("\n" + "═" * 50)
    print_colored("  IMPORT FROM CSV", COLORS.CYAN, bold=True)
    print("═" * 50)
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
        video_id = row.get('video_id', '').strip()
        if not video_id or not extract_video_id(video_id):
            print_colored(f"[!] Invalid video_id '{video_id}', skipping.", COLORS.YELLOW)
            skipped += 1
            continue

        cursor.execute(f"SELECT id FROM {TABLE_NAME} WHERE video_id = %s", (video_id,))
        exists = cursor.fetchone()

        if exists:
            if choice == '1':
                skipped += 1
                continue
            elif choice == '2':
                mirror_id = row.get('mirror_video_id', '').strip() or None
                video_title = row.get('video_title', '').strip() or None
                syllabus_id = row.get('syllabus_id', '').strip() or None
                subject = row.get('subject', '').strip() or None
                chapter = row.get('chapter', '').strip() or None
                lecturer = row.get('lecturer', '').strip() or None
                nepali_date = row.get('nepali_date', '').strip() or None
                time_val = row.get('time', '').strip() or None
                notes = row.get('notes', '').strip() or None

                cursor.execute(f"""
                    UPDATE {TABLE_NAME}
                    SET mirror_video_id = %s, video_title = %s, syllabus_id = %s,
                        subject = %s, chapter = %s, lecturer = %s, nepali_date = %s, time = %s, notes = %s
                    WHERE video_id = %s
                """, (mirror_id, video_title, syllabus_id, subject, chapter, lecturer, nepali_date, time_val, notes, video_id))
                updated += 1
                continue
            else:
                print_colored(f"[!] Duplicate video_id {video_id}, aborting.", COLORS.RED)
                conn.rollback()
                cursor.close()
                conn.close()
                print("Import aborted.")
                return
        else:
            mirror_id = row.get('mirror_video_id', '').strip() or None
            video_title = row.get('video_title', '').strip() or None
            syllabus_id = row.get('syllabus_id', '').strip() or None
            subject = row.get('subject', '').strip() or None
            chapter = row.get('chapter', '').strip() or None
            lecturer = row.get('lecturer', '').strip() or None
            nepali_date = row.get('nepali_date', '').strip() or None
            time_val = row.get('time', '').strip() or None
            notes = row.get('notes', '').strip() or None

            cursor.execute(f"""
                INSERT INTO {TABLE_NAME}
                (video_id, mirror_video_id, video_title, syllabus_id, subject, chapter, lecturer, nepali_date, time, notes)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (video_id, mirror_id, video_title, syllabus_id, subject, chapter, lecturer, nepali_date, time_val, notes))
            added += 1

    conn.commit()
    cursor.close()
    conn.close()
    print_colored(f"[✓] Import complete: {added} added, {updated} updated, {skipped} skipped.", COLORS.GREEN)

def import_json():
    print("\n" + "═" * 50)
    print_colored("  IMPORT FROM JSON", COLORS.CYAN, bold=True)
    print("═" * 50)
    filename = input(color_text("Enter JSON filename: ", COLORS.MAGENTA)).strip()
    if not filename:
        print_colored("[!] No filename given.", COLORS.RED)
        return
    if not os.path.exists(filename):
        print_colored(f"[!] File {filename} not found.", COLORS.RED)
        return

    try:
        with open(filename, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print_colored(f"[!] Failed to read JSON: {e}", COLORS.RED)
        return

    if not isinstance(data, list):
        print_colored("[!] JSON must be a list of objects.", COLORS.RED)
        return
    if not data:
        print_colored("[i] No data found.", COLORS.YELLOW)
        return

    print(f"Found {len(data)} records. How to handle duplicates?")
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

    for item in data:
        if not isinstance(item, dict):
            print_colored("[!] Item is not a dict, skipping.", COLORS.YELLOW)
            skipped += 1
            continue

        video_id = item.get('video_id', '').strip()
        if not video_id or not extract_video_id(video_id):
            print_colored(f"[!] Invalid video_id '{video_id}', skipping.", COLORS.YELLOW)
            skipped += 1
            continue

        cursor.execute(f"SELECT id FROM {TABLE_NAME} WHERE video_id = %s", (video_id,))
        exists = cursor.fetchone()

        # Helper to safely strip a value, returning None if empty or None
        def clean_val(val):
            if val is None:
                return None
            if isinstance(val, str):
                stripped = val.strip()
                return stripped if stripped else None
            return val

        mirror_id = clean_val(item.get('mirror_video_id'))
        video_title = clean_val(item.get('video_title'))
        syllabus_id = clean_val(item.get('syllabus_id'))
        subject = clean_val(item.get('subject'))
        chapter = clean_val(item.get('chapter'))
        lecturer = clean_val(item.get('lecturer'))
        nepali_date = clean_val(item.get('nepali_date'))
        time_val = clean_val(item.get('time'))
        notes = clean_val(item.get('notes'))

        if exists:
            if choice == '1':
                skipped += 1
                continue
            elif choice == '2':
                cursor.execute(f"""
                    UPDATE {TABLE_NAME}
                    SET mirror_video_id = %s, video_title = %s, syllabus_id = %s,
                        subject = %s, chapter = %s, lecturer = %s, nepali_date = %s, time = %s, notes = %s
                    WHERE video_id = %s
                """, (mirror_id, video_title, syllabus_id, subject, chapter, lecturer, nepali_date, time_val, notes, video_id))
                updated += 1
                continue
            else:  # choice == 3
                print_colored(f"[!] Duplicate video_id {video_id}, aborting.", COLORS.RED)
                conn.rollback()
                cursor.close()
                conn.close()
                print("Import aborted.")
                return
        else:
            cursor.execute(f"""
                INSERT INTO {TABLE_NAME}
                (video_id, mirror_video_id, video_title, syllabus_id, subject, chapter, lecturer, nepali_date, time, notes)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (video_id, mirror_id, video_title, syllabus_id, subject, chapter, lecturer, nepali_date, time_val, notes))
            added += 1

    conn.commit()
    cursor.close()
    conn.close()
    print_colored(f"[✓] Import complete: {added} added, {updated} updated, {skipped} skipped.", COLORS.GREEN)
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

def add_facebook_lecture(url_or_id):
    """
    Handle adding a Facebook video or photo.
    Detects type, downloads, organises, and stores in DB.
    """
    print("\n" + "═" * 50)
    print_colored("  ADD FACEBOOK CONTENT", COLORS.CYAN, bold=True)
    print("═" * 50)

    # Ensure we have a full URL
    if not url_or_id.startswith('http'):
        # assume it's an ID, but Facebook IDs are not reliable; we'll treat as URL with fb.watch?
        print_colored("[!] Please provide a full Facebook URL.", COLORS.RED)
        return

    # Try to fetch metadata using yt-dlp
    _ensure_cookie_file()
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
        'ignoreerrors': True,
        'cookiefile': 'cookies.txt' if os.path.exists('cookies.txt') else None,
    }

    info = None
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url_or_id, download=False)
            if not info:
                print_colored("[!] Could not fetch metadata. Check URL or cookies.", COLORS.RED)
                return
    except Exception as e:
        print_colored(f"[!] Failed to fetch metadata: {e}", COLORS.RED)
        return

    # Determine type
    is_video = info.get('_type') == 'video' or info.get('ext') in ('mp4', 'mkv', 'webm') or info.get('duration') is not None
    # Photos may be an album or single image; if `_type` is 'playlist' with entries, treat as photo album.
    # For simplicity, we'll rely on the extension or if it's a video stream.
    # Actually, yt-dlp for a single photo returns a 'video' with no duration? We'll check.

    # For albums, yt-dlp returns a playlist; we can iterate entries.
    if info.get('_type') == 'playlist':
        print_colored(f"[i] Detected as album/playlist with {len(info.get('entries', []))} items.", COLORS.BLUE)
        # We'll handle each entry (but for now, just process the first one? Better to ask user)
        # For Phase 2, we'll keep simple: process the first entry if it's a photo.
        # We'll improve later.
        if info.get('entries'):
            info = info['entries'][0]  # take first entry
            is_video = False  # assume photo

    # Fetch details
    title = info.get('title', 'Facebook Media')
    uploader = info.get('uploader', 'Unknown')
    # Extract a stable ID
    facebook_id = _extract_facebook_id(url_or_id)
    if not facebook_id:
        facebook_id = info.get('id', str(int(datetime.now().timestamp())))

    # Ask for custom name (optional)
    custom_name = input(color_text("Enter a custom name (or press Enter to auto-detect): ", COLORS.MAGENTA)).strip()
    if custom_name:
        original_base = sanitize_filename(custom_name)
    else:
        original_base = sanitize_filename(title)

    # Determine file extension
    # yt-dlp may give ext; fallback to .mp4 for video, .jpg for photo
    ext = info.get('ext', '')
    if is_video:
        if ext not in ('.mp4', '.mkv', '.webm'):
            ext = '.mp4'
        else:
            ext = '.' + ext.lstrip('.')
    else:
        ext = '.jpg'  # assume photo

    # Create temp download file with the original name
    temp_filename = original_base + ext
    temp_path = os.path.join('./downloads', temp_filename)  # use existing downloads dir

    # Download using yt-dlp
    download_opts = {
        'outtmpl': temp_path,
        'format': 'bestvideo+bestaudio/best' if is_video else 'best',
        'quiet': False,
        'no_warnings': True,
        'ignoreerrors': True,
        'cookiefile': 'cookies.txt' if os.path.exists('cookies.txt') else None,
    }
    try:
        with yt_dlp.YoutubeDL(download_opts) as ydl:
            ydl.download([url_or_id])
    except Exception as e:
        print_colored(f"[!] Download failed: {e}", COLORS.RED)
        return

    # Compute MD5 hash and move to final location
    file_hash = compute_md5(temp_path)
    final_dir = FACEBOOK_VIDEO_DIR if is_video else FACEBOOK_PHOTO_DIR
    os.makedirs(final_dir, exist_ok=True)
    new_filename = f"{file_hash}{ext}"
    final_path = os.path.join(final_dir, new_filename)

    # Rename/move
    try:
        shutil.move(temp_path, final_path)
    except Exception as e:
        print_colored(f"[!] Failed to move file: {e}", COLORS.RED)
        return

    # Insert into database
    entry_id = add_facebook_entry(
        facebook_id=facebook_id,
        entry_type='video' if is_video else 'photo',
        title=title,
        uploader=uploader,
        url=url_or_id,
        file_hash=file_hash,
        original_filename=original_base + ext,
        notes=None
    )

    if entry_id:
        print_colored(f"[✓] Facebook entry added (ID: {entry_id})", COLORS.GREEN)
        print_colored(f"[✓] File stored at: {final_path}", COLORS.BLUE)
    else:
        print_colored("[!] Database insertion failed, but file was downloaded.", COLORS.RED)

    # Clean up any leftover temp files (if any)
    if os.path.exists(temp_path):
        os.remove(temp_path)

def add_facebook_entry(facebook_id, entry_type, title, uploader, url, file_hash=None, original_filename=None, notes=None):
    """
    Insert a new Facebook entry into the database.
    Returns the inserted ID or None on error.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(f"""
            INSERT INTO {TABLE_NAME}
            (facebook_id, type, title, uploader, url, file_hash, original_filename, notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (facebook_id, entry_type, title, uploader, url, file_hash, original_filename, notes))
        conn.commit()
        inserted_id = cursor.lastrowid
        cursor.close()
        conn.close()
        return inserted_id
    except Exception as e:
        print_colored(f"[!] Failed to insert Facebook entry: {e}", COLORS.RED)
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
    # Try by facebook_id, then id, then file_hash
    sql = f"""
        SELECT * FROM {TABLE_NAME}
        WHERE facebook_id = %s OR id = %s OR file_hash = %s
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
                    print(f"  ID:{e['id']:4} | {e['type']:5} | {e['uploader']:20} | {e['title'][:40]}")
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
# facebook.py

import os
import subprocess
import shutil
import yt_dlp
from datetime import datetime
import re
from .utils import sanitize_filename, print_colored, color_text, COLORS, compute_md5
from .youtube import _ensure_cookie_file
from .file_manager import ROOT_DIR
from .facebook_manager import add_facebook_entry, get_facebook_entry_by_id

DOWNLOAD_DIR = './downloads'
PHOTO_BASE_DIR = os.path.join(DOWNLOAD_DIR, 'facebook_photos')

# Organised directories
FACEBOOK_VIDEO_DIR = os.path.join(ROOT_DIR, 'facebook', 'videos')
FACEBOOK_PHOTO_DIR = os.path.join(ROOT_DIR, 'facebook', 'photos')

def _extract_facebook_id(url):
    """Try to extract a stable ID from a Facebook URL."""
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

def _is_video_link(url):
    """Heuristic to detect if a Facebook link is for a video/Reel."""
    video_patterns = [
        '/watch',
        '/reel/',
        '/share/r/',
        '/videos/',
        '/video/',
    ]
    url_lower = url.lower()
    return any(pattern in url_lower for pattern in video_patterns)

def _download_video(url, custom_name=None):
    """
    Download a single Facebook video/Reel.
    After download, organise into ROOT_DIR/facebook/videos/ and add to DB.
    """
    # Ensure cookies.txt is fresh
    _ensure_cookie_file()

    # Determine cookie option
    if os.path.exists('cookies.txt'):
        cookie_opt = {'cookiefile': 'cookies.txt'}
    else:
        cookie_opt = {'cookiesfrombrowser': ('edge',)}

    # ---- Try to get metadata ----
    title = None
    uploader = None
    description = None
    facebook_id = None

    ydl_opts_info = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
        'ignoreerrors': True,
        **cookie_opt
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts_info) as ydl:
            info = ydl.extract_info(url, download=False)
            if info and isinstance(info, dict):
                title = info.get('title')
                uploader = info.get('uploader')
                description = info.get('description')
                if description:
                    description = description.split('\n')[0].strip()
                # Try to get a stable ID
                facebook_id = info.get('id') or _extract_facebook_id(url)
    except Exception as e:
        print_colored(f"[!] Could not fetch metadata: {e}", COLORS.YELLOW)

    # ---- Determine filename ----
    if custom_name:
        filename_base = custom_name
    elif title and title.lower() != 'video':
        filename_base = sanitize_filename(title)
    elif description:
        filename_base = sanitize_filename(description)
    elif uploader:
        filename_base = sanitize_filename(uploader)
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename_base = f"Facebook_Video_{timestamp}"

    filename_base = sanitize_filename(filename_base)
    if not filename_base:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename_base = f"Facebook_Video_{timestamp}"

    print_colored(f"[i] Saving as: {filename_base}", COLORS.GREEN)

    # ---- Download ----
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    temp_filename = f"{filename_base}.%(ext)s"
    temp_path_pattern = os.path.join(DOWNLOAD_DIR, temp_filename)

    ydl_opts_download = {
        'outtmpl': temp_path_pattern,
        'format': 'bestvideo+bestaudio/best',
        'quiet': False,
        'no_warnings': True,
        'ignoreerrors': True,
        **cookie_opt
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts_download) as ydl:
            print_colored(f"[⏳] Downloading Facebook video...", COLORS.BLUE)
            ydl.download([url])
        # Find the downloaded file
        # yt-dlp may add extra extensions; we'll glob for the base name
        downloaded_files = [f for f in os.listdir(DOWNLOAD_DIR) if f.startswith(filename_base)]
        if not downloaded_files:
            print_colored("[!] Could not locate downloaded file.", COLORS.RED)
            return
        temp_path = os.path.join(DOWNLOAD_DIR, downloaded_files[0])
        print_colored(f"[✓] Downloaded to {temp_path}", COLORS.GREEN)

        # ---- Compute MD5 and move to final directory ----
        file_hash = compute_md5(temp_path)
        _, ext = os.path.splitext(temp_path)
        if not ext:
            ext = '.mp4'
        new_filename = f"{file_hash}{ext}"
        os.makedirs(FACEBOOK_VIDEO_DIR, exist_ok=True)
        final_path = os.path.join(FACEBOOK_VIDEO_DIR, new_filename)

        # Move to final location
        shutil.move(temp_path, final_path)
        print_colored(f"[✓] File stored at: {final_path}", COLORS.BLUE)

        # ---- Insert into database ----
        if not facebook_id:
            facebook_id = _extract_facebook_id(url)
        entry_id = add_facebook_entry(
            facebook_id=facebook_id,
            entry_type='video',
            title=title or filename_base,
            uploader=uploader or 'Unknown',
            url=url,
            file_hash=file_hash,
            original_filename=os.path.basename(final_path),
            notes=None
        )
        if entry_id:
            print_colored(f"[✓] Facebook entry added (ID: {entry_id})", COLORS.GREEN)
        else:
            print_colored("[!] Database insertion failed, but file was saved.", COLORS.RED)

    except Exception as e:
        print_colored(f"[!] Download failed: {e}", COLORS.RED)

def _download_photos(url, output_dir=None):
    """
    Download all photos from a Facebook album/page/group using gallery-dl.
    This function remains unchanged – it does NOT add entries to the database.
    It's kept for quick photo album downloads.
    """
    # Ensure cookies.txt is fresh
    _ensure_cookie_file()

    cookie_file = 'cookies.txt'
    if not os.path.exists(cookie_file):
        print_colored("[!] cookies.txt not found. Please run option 26 to refresh cookies.", COLORS.RED)
        return

    # Default base directory
    if not output_dir:
        output_dir = PHOTO_BASE_DIR

    custom_dir = input(color_text(f"Output directory (default: {output_dir}): ", COLORS.MAGENTA)).strip()
    if custom_dir:
        output_dir = custom_dir

    os.makedirs(output_dir, exist_ok=True)

    # ---- Merge filename pattern into gallery-dl.conf ----
    config_file = 'gallery-dl.conf'
    config = {}

    # Load existing config if it exists
    if os.path.exists(config_file):
        try:
            import json
            with open(config_file, 'r') as f:
                config = json.load(f)
            print_colored(f"[i] Loaded existing config: {config_file}", COLORS.BLUE)
        except Exception as e:
            print_colored(f"[!] Could not parse existing config: {e}. Will create a new one.", COLORS.YELLOW)
            config = {}

    # Ensure extractor.facebook section exists
    if 'extractor' not in config:
        config['extractor'] = {}
    if 'facebook' not in config['extractor']:
        config['extractor']['facebook'] = {}

    # Set filename pattern (preserve other keys like sleep, retries)
    config['extractor']['facebook']['filename'] = "{uploader}_{date}_{caption}_{id}.{extension}"

    # Write back the config
    try:
        import json
        with open(config_file, 'w') as f:
            json.dump(config, f, indent=4)
        print_colored(f"[✓] Updated config with filename pattern: {config_file}", COLORS.GREEN)
    except Exception as e:
        print_colored(f"[!] Failed to write config: {e}", COLORS.RED)
        return

    # Build gallery-dl command
    cmd = [
        'gallery-dl',
        '--cookies', cookie_file,
        '--config', config_file,
        '-d', output_dir,
        url
    ]

    print_colored(f"[⏳] Downloading photos from: {url}", COLORS.BLUE)
    print_colored(f"[i] Output folder: {output_dir}", COLORS.BLUE)
    print_colored("[i] Filename pattern: uploader_date_caption_id", COLORS.BLUE)
    print_colored("[i] Note: Photo albums are NOT tracked in the database.", COLORS.YELLOW)

    try:
        subprocess.run(cmd, check=True)
        print_colored(f"[✓] Photos downloaded to {output_dir}", COLORS.GREEN)
    except subprocess.CalledProcessError as e:
        print_colored(f"[!] Download failed: {e}", COLORS.RED)
    except FileNotFoundError:
        print_colored("[!] gallery-dl not found. Install with: pip install gallery-dl", COLORS.RED)

def download_facebook():
    """
    Main entry point for Facebook downloads (option 28).
    Auto-detects video vs photo link.
    """
    print("\n" + "═" * 50)
    print_colored("  DOWNLOAD FROM FACEBOOK", COLORS.CYAN, bold=True)
    print("═" * 50)

    url = input(color_text("Enter Facebook video, Reel, or photo album URL: ", COLORS.MAGENTA)).strip()
    if not url:
        print_colored("Cancelled.", COLORS.YELLOW)
        return

    # Auto-detect link type
    if _is_video_link(url):
        print_colored("[i] Detected as video/Reel link.", COLORS.BLUE)
        custom_name = input(color_text("Custom filename (optional, press Enter to auto-detect): ", COLORS.MAGENTA)).strip()
        _download_video(url, custom_name if custom_name else None)
    else:
        print_colored("[i] Detected as photo album/page/group link.", COLORS.BLUE)
        _download_photos(url)
# file_compressor.py

import os
import subprocess
import shutil
from .db import get_connection, TABLE_NAME, get_record_by_any_id
from .utils import print_colored, COLORS, compute_md5, ROOT_DIR
from .file_manager import get_target_path

def get_file_path_for_record(record):
    """
    Locate the video file for a given record.
    Uses hash_cache first, then falls back to target directory, then whole ROOT_DIR.
    """
    file_hash = record.get('file_hash')
    if file_hash:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT file_path FROM hash_cache WHERE file_hash = %s AND status = 'active'", (file_hash,))
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        if row and os.path.exists(row['file_path']):
            return row['file_path']
        else:
            target_dir, _ = get_target_path(record, interactive=False)
            if target_dir and os.path.exists(target_dir):
                import glob
                pattern = os.path.join(target_dir, file_hash + '.*')
                matches = glob.glob(pattern)
                if matches:
                    return matches[0]
    # Fallback
    for root, _, files in os.walk(ROOT_DIR):
        for f in files:
            if f.lower().endswith(('.mp4','.mkv','.webm','.avi','.mov')):
                if record['video_id'] in f:
                    return os.path.join(root, f)
    return None

def compress_file(filepath):
    """
    Compress a single video file to 480p H.264 (CRF 28).
    Returns a dict with status and message.
    """
    # 1. Check resolution
    try:
        cmd = ['ffprobe', '-v', 'error', '-show_entries', 'stream=width,height', '-of', 'csv=p=0', filepath]
        result = subprocess.run(cmd, capture_output=True, text=True)
        output = result.stdout.strip()
        if not output:
            return {'status': 'failed', 'message': 'No video stream found'}
        width, height = None, None
        for line in output.split('\n'):
            if ',' in line:
                w, h = line.split(',')
                width, height = int(w), int(h)
                break
        if width is None or height is None:
            return {'status': 'failed', 'message': 'Could not determine resolution'}
    except Exception as e:
        return {'status': 'failed', 'message': f'ffprobe error: {e}'}

    # Skip if already <= 480p
    if height <= 480:
        return {'status': 'skipped', 'message': f'Already {width}x{height} (≤480p), skipping'}

    # 2. Prepare output paths and ffmpeg command
    dirname = os.path.dirname(filepath)
    basename = os.path.basename(filepath)
    temp_output = os.path.join(dirname, f"temp_{os.urandom(4).hex()}.mkv")

    cmd = [
        'ffmpeg', '-i', filepath,
        '-c:v', 'libx264',
        '-crf', '28',
        '-preset', 'medium', # medium, slow, fast
        '-vf', 'scale=854:-2',
        '-c:a', 'aac',
        '-b:a', '128k',
        '-movflags', '+faststart',
        '-y',
        temp_output
    ]
    # this is example which creates 660MB into 320MB
    # ffmpeg -i ea328ccd46284546917555b787658124.mkv -c:v libx265 -crf 28 -preset medium -c:a aac compressed_video.mkv

    print(f"  Compressing: {basename}")

    # 3. Run ffmpeg (with live output and cancellable)
    proc = None
    try:
        proc = subprocess.Popen(cmd, stdout=None, stderr=None, stdin=subprocess.DEVNULL)
        proc.wait()
        if proc.returncode != 0:
            raise subprocess.CalledProcessError(proc.returncode, cmd)
    except KeyboardInterrupt:
        # Cancel the current ffmpeg process
        if proc is not None and proc.poll() is None:
            proc.terminate()
            proc.wait()
        if os.path.exists(temp_output):
            os.remove(temp_output)
        print_colored("\n[!] Compression cancelled by user.", COLORS.YELLOW)
        return {'status': 'failed', 'message': 'Cancelled by user'}
    except Exception as e:
        # Clean up temp file on any other error
        if os.path.exists(temp_output):
            os.remove(temp_output)
        return {'status': 'failed', 'message': f'ffmpeg error: {e}'}

    # 4. Compute new hash and rename
    new_hash = compute_md5(temp_output)
    new_filename = f"{new_hash}.mkv"
    new_filepath = os.path.join(dirname, new_filename)

    try:
        shutil.move(temp_output, new_filepath)
        if os.path.exists(filepath) and filepath != new_filepath:
            os.remove(filepath)
    except Exception as e:
        return {'status': 'failed', 'message': f'Move error: {e}'}

    # 5. Update database
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT file_hash FROM hash_cache WHERE file_path = %s AND status = 'active'", (filepath,))
        row = cursor.fetchone()
        if row:
            old_hash = row[0]
            cursor.execute(f"UPDATE {TABLE_NAME} SET file_hash = %s WHERE file_hash = %s", (new_hash, old_hash))
            cursor.execute("""
                UPDATE hash_cache
                SET file_path = %s, file_hash = %s, last_scan = NOW()
                WHERE file_path = %s
            """, (new_filepath, new_hash, filepath))
            conn.commit()
        else:
            print_colored(f"  [WARN] No cache entry for {basename}, DB not updated.", COLORS.YELLOW)

        cursor.close()
        conn.close()
    except Exception as e:
        return {'status': 'failed', 'message': f'DB update error: {e}'}

    return {'status': 'compressed', 'new_path': new_filepath, 'message': f'Compressed to {new_filename} (was {basename})'}

def compress_library_to_480p():
    """
    Batch compress all video files with resolution > 480p.
    """
    video_exts = ('.mp4', '.mkv', '.webm', '.avi', '.mov')
    all_videos = []

    print_colored("[i] Scanning for video files...", COLORS.BLUE)
    for root, _, files in os.walk(ROOT_DIR):
        for f in files:
            if f.lower().endswith(video_exts):
                all_videos.append(os.path.join(root, f))

    if not all_videos:
        print_colored("[i] No video files found.", COLORS.YELLOW)
        return

    total = len(all_videos)
    processed = 0
    skipped = 0
    failed = 0

    print_colored(f"[i] Found {total} video files. Checking resolutions...", COLORS.BLUE)

    for idx, filepath in enumerate(all_videos, 1):
        basename = os.path.basename(filepath)
        print(f"  [{idx}/{total}] {basename[:60]}", end="\r")
        result = compress_file(filepath)
        if result['status'] == 'compressed':
            processed += 1
            print(f"  [{idx}/{total}] {result['message']}")
        elif result['status'] == 'skipped':
            skipped += 1
        else:
            failed += 1
            print_colored(f"  [{idx}/{total}] FAIL: {result['message']}", COLORS.RED)

    print_colored(f"\n[✓] Compression complete: {processed} processed, {skipped} skipped, {failed} failed.", COLORS.GREEN)

def compress_single_by_id(identifier):
    record = get_record_by_any_id(identifier)
    if not record:
        return {'status': 'failed', 'message': f'No record found for ID: {identifier}'}

    filepath = get_file_path_for_record(record)
    if not filepath:
        return {'status': 'failed', 'message': f'Could not locate file for record {identifier}'}

    print_colored(f"Found file: {filepath}", COLORS.BLUE)
    return compress_file(filepath)

def list_largest_files(n=5):
    """Find and list the n largest video files with height > 480.
       Returns a list of (hash, size_mb, filepath) for easy selection.
    """
    video_exts = ('.mp4', '.mkv', '.webm', '.avi', '.mov')
    candidates = []
    for root, _, files in os.walk(ROOT_DIR):
        for f in files:
            if f.lower().endswith(video_exts):
                fp = os.path.join(root, f)
                try:
                    cmd = ['ffprobe', '-v', 'error', '-show_entries', 'stream=height', '-of', 'csv=p=0', fp]
                    result = subprocess.run(cmd, capture_output=True, text=True)
                    h = result.stdout.strip().split('\n')[0]
                    if h.isdigit() and int(h) > 480:
                        size = os.path.getsize(fp)
                        hash_part = os.path.splitext(f)[0]
                        candidates.append((size, fp, hash_part))
                except:
                    pass
    candidates.sort(reverse=True)  # largest first
    print("\n" + "═" * 60)
    print_colored(f"  TOP {min(n, len(candidates))} LARGE VIDEOS (≥720p)", COLORS.CYAN, bold=True)
    print("═" * 60)
    result_list = []
    for i, (size, fp, hash_part) in enumerate(candidates[:n], 1):
        size_mb = size / (1024*1024)
        print(f"  {i}. {hash_part}  ({size_mb:.1f} MB)")
        result_list.append({'number': i, 'hash': hash_part, 'path': fp, 'size_mb': size_mb})
    print("═" * 60)
    print("Enter the number (1-5) or hash to compress that file.\n")
    return result_list
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
    for root, _, files in os.walk(ROOT_DIR):
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
    for root, dirs, files in os.walk(ROOT_DIR):
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
# File __init__.py

"""
YouTube Lecture Manager package.
"""

from .facebook_manager import add_facebook_entry, get_facebook_entry_by_id, list_facebook_entries, delete_facebook_entry

__version__ = "2.2.0"
# main.py

import readline
import sys
from .config import load_or_create_config, edit_config
from .db import create_table, migrate_table
from .crud import (
    add_lecture, view_all, view_one, update_lecture, delete_lecture,
    download_existing, show_embed_link, refresh_titles, search_lectures
)
from .dashboard import show_dashboard
from .export import export_csv, export_json, import_csv, import_json
from .file_manager import (
    move_video_interactive,
    delete_video_to_trash, restore_from_trash, empty_trash,
    tally_db_with_files, scan_duplicates, resolve_duplicates, backfill_hashes, play_video,
    backfill_hash_naming   # <-- new
)
# NEW: import web server runner
from .web import run_web_server
from .utils import print_colored, color_text, COLORS
from .youtube import refresh_cookies
from .facebook import download_facebook

def show_banner():
    width = 60
    title = "YOUTUBE LECTURE MANAGER  v2.3.0"
    subtitle = "Manage your lecture library with style"
    owner = "By Udaya Raj Joshi"

    # Build box with fixed width
    top = "╔" + "═" * width + "╗"
    mid1 = "║" + color_text(title.center(width), COLORS.CYAN, bold=True) + "║"
    mid2 = "║" + color_text(subtitle.center(width), COLORS.BLUE) + "║"
    mid3 = "║" + color_text(owner.center(width), COLORS.BLUE) + "║"
    bottom = "╚" + "═" * width + "╝"
    print("\n" + top)
    print(mid1)
    print(mid2)
    print(mid3)
    print(bottom)
    print()

def main():
    load_or_create_config()
    create_table()
    migrate_table()

    while True:
        show_banner()
        print("  " + color_text("MAIN MENU", COLORS.YELLOW, bold=True))
        print("  " + "─" * 40)
        print("  1. " + color_text("Add new lecture", COLORS.WHITE))
        print("  2. " + color_text("View all lectures (with sorting)", COLORS.WHITE))
        print("  3. " + color_text("View a single lecture", COLORS.WHITE))
        print("  4. " + color_text("Update a lecture", COLORS.WHITE))
        print("  5. " + color_text("Delete a lecture", COLORS.WHITE))
        print("  6. " + color_text("Download a video (from existing record)", COLORS.WHITE))
        print("  7. " + color_text("Show YouTube embed link", COLORS.WHITE))
        print("  8. " + color_text("Refresh video titles from YouTube", COLORS.WHITE))
        print("  9. " + color_text("Search lectures", COLORS.WHITE))
        print(" 10. " + color_text("Export to CSV", COLORS.WHITE))
        print(" 11. " + color_text("Export to JSON", COLORS.WHITE))
        print(" 12. " + color_text("Import from CSV", COLORS.WHITE))
        print(" 13. " + color_text("Import from JSON", COLORS.WHITE))
        print(" 14. " + color_text("Edit database configuration", COLORS.WHITE))
        print(" 15. " + color_text("Move/rename a video manually", COLORS.WHITE))
        print(" 16. " + color_text("Delete a video (move to trash)", COLORS.WHITE))
        print(" 17. " + color_text("Restore from trash", COLORS.WHITE))
        print(" 18. " + color_text("Empty trash", COLORS.WHITE))
        print(" 19. " + color_text("Tally database with video files", COLORS.WHITE))
        print(" 20. " + color_text("Start web interface", COLORS.WHITE))
        print(" 21. " + color_text("Scan for duplicate video files", COLORS.WHITE))
        print(" 22. " + color_text("Auto-resolve duplicate video files", COLORS.WHITE))
        print(" 23. " + color_text("Backfill file hashes (one-time)", COLORS.WHITE))
        print(" 24. " + color_text("Show library dashboard", COLORS.WHITE))
        print(" 25. " + color_text("Play a video (local file)", COLORS.WHITE))
        print(" 26. " + color_text("Refresh YouTube cookies", COLORS.WHITE))
        print(" 27. " + color_text("Backfill hash naming (rename files to MD5)", COLORS.WHITE))
        print(" 28. " + color_text("Download Facebook video/photos", COLORS.WHITE))
        print(" 29. " + color_text("Manage Facebook downloads", COLORS.WHITE))
        print("  0. " + color_text("Exit", COLORS.RED, bold=True))
        print("  " + "─" * 40)
        choice = input(color_text("Choose an option: ", COLORS.MAGENTA)).strip()

        if choice == '1':
            add_lecture()
        elif choice == '2':
            view_all()
        elif choice == '3':
            view_one()
        elif choice == '4':
            update_lecture()
        elif choice == '5':
            delete_lecture()
        elif choice == '6':
            download_existing()
        elif choice == '7':
            show_embed_link()
        elif choice == '8':
            refresh_titles()
        elif choice == '9':
            from .crud import search_all
            search_all()
        elif choice == '10':
            export_csv()
        elif choice == '11':
            export_json()
        elif choice == '12':
            import_csv()
        elif choice == '13':
            import_json()
        elif choice == '14':
            edit_config()
        elif choice == '15':
            move_video_interactive()
        elif choice == '16':
            delete_video_to_trash()
        elif choice == '17':
            restore_from_trash()
        elif choice == '18':
            empty_trash()
        elif choice == '19':
            tally_db_with_files()
        elif choice == '20':
            print_colored("\nStarting web server at http://127.0.0.1:5000", COLORS.GREEN)
            print_colored("Press Ctrl+C to stop the server and return to CLI", COLORS.YELLOW)
            try:
                run_web_server()
            except KeyboardInterrupt:
                print_colored("\n[✓] Web server stopped.", COLORS.GREEN)
            except Exception as e:
                print_colored(f"[!] Failed to start web server: {e}", COLORS.RED)
        elif choice == '21':
            scan_duplicates()
        elif choice == '22':
            resolve_duplicates()
        elif choice == '23':
            backfill_hashes()
        elif choice == '24':
            show_dashboard()
        elif choice == '25':
            play_video()
        elif choice == '26':
            refresh_cookies()
        elif choice == '27':
            backfill_hash_naming()
        elif choice == '28':
            download_facebook()
        elif choice == '29':
            from .facebook_manager import facebook_menu
            facebook_menu()
        elif choice == '0':
            print_colored("\nGoodbye! Have a great day! 👋", COLORS.CYAN)
            break
        else:
            print_colored("[!] Invalid option. Please try again.", COLORS.RED)

        input("\nPress Enter to continue...")

# if __name__ == "__main__":
#    main()
# File utils.py (unchanged, except clear_screen kept but not used)

import re
import sys
import os
import hashlib

ROOT_DIR = os.path.expanduser("~/foxCloud/office/Udaan")
TRASH_DIR = os.path.expanduser("~/.lecture_trash")


# ANSI color codes
class COLORS:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    MAGENTA = '\033[95m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    END = '\033[0m'
    WHITE = '\033[97m'
    RESET = '\033[0m'

# Map color names to codes for convenience
COLOR_MAP = {
    'header': COLORS.HEADER,
    'blue': COLORS.BLUE,
    'cyan': COLORS.CYAN,
    'green': COLORS.GREEN,
    'yellow': COLORS.YELLOW,
    'red': COLORS.RED,
    'magenta': COLORS.MAGENTA,
    'bold': COLORS.BOLD,
    'underline': COLORS.UNDERLINE,
    'white': COLORS.WHITE
}

# This function should be placed after ROOT_DIR is defined
def get_file_path_for_record(record):
    """
    Locate the video file for a given record.
    Uses hash_cache first, then falls back to target directory, then whole ROOT_DIR.
    """
    from .file_manager import get_target_path  # local import to avoid circular
    file_hash = record.get('file_hash')
    if file_hash:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT file_path FROM hash_cache WHERE file_hash = %s AND status = 'active'", (file_hash,))
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        if row and os.path.exists(row['file_path']):
            return row['file_path']
        else:
            target_dir, _ = get_target_path(record, interactive=False)
            if target_dir and os.path.exists(target_dir):
                pattern = os.path.join(target_dir, file_hash + '.*')
                matches = glob.glob(pattern)
                if matches:
                    return matches[0]
    # Fallback: search whole ROOT_DIR by video_id in filename
    for root, _, files in os.walk(ROOT_DIR):
        for f in files:
            if f.lower().endswith(('.mp4','.mkv','.webm','.avi','.mov')):
                if record['video_id'] in f:
                    return os.path.join(root, f)
    return None

def normalize_syllabus_id(raw):
    """
    Convert syllabus ID to a standard format: XX.XX.XX (with optional -n suffix).
    Examples:
        '4.2.5'       -> '04.02.05'
        '04.02.05'    -> '04.02.05'
        '4.02.5-1'    -> '04.02.05-1'
        '04.2.05-2'   -> '04.02.05-2'
        '4.2'         -> '04.02'  (if only two parts)
        '4'           -> '04'
    """
    if not raw:
        return raw
    raw = raw.strip()
    # Split off optional suffix like -1, -2
    suffix = ''
    if '-' in raw:
        raw, suffix = raw.split('-', 1)
        suffix = '-' + suffix
    parts = raw.split('.')
    # Pad each part to 2 digits
    padded = []
    for p in parts:
        if p.isdigit():
            padded.append(p.zfill(2))
        else:
            padded.append(p)   # Keep non‑numeric as‑is (unlikely)
    return '.'.join(padded) + suffix

def color_text(text, color=None, bold=False):
    """
    Wrap text with ANSI color codes.
    color: string key from COLOR_MAP or a direct ANSI code.
    bold: boolean.
    """
    if not sys.stdout.isatty():
        return text
    if color is None:
        color = ''
    elif color in COLOR_MAP:
        color = COLOR_MAP[color]
    prefix = ''
    if bold:
        prefix += COLORS.BOLD
    if color:
        prefix += color
    suffix = COLORS.RESET
    return f"{prefix}{text}{suffix}"

def print_colored(text, color=None, bold=False):
    print(color_text(text, color, bold))

def sanitize_filename(text):
    text = re.sub(r'[\\/*?"<>]', '', text)
    text = re.sub(r'[\x00-\x1f\x7f]', '', text)
    text = text.strip()
    return text

def clean_field(text):
    return text.strip() if text else ""

def get_display_title(record):
    if record.get('chapter'):
        return clean_field(record['chapter'])
    raw = record.get('video_title', '')
    if raw and '||' in raw:
        parts = [p.strip() for p in raw.split('||') if p.strip()]
        return parts[0] if parts else raw.strip()
    return clean_field(record.get('subject', ''))

def parse_lecture_title(title):
    if not title:
        return None

    parts = [p.strip() for p in title.split('||') if p.strip()]
    if not parts:
        return None

    # Patterns for date, time, and name indicators
    date_pattern = re.compile(r'\b\d{4}-\d{2}-\d{2}\b')
    time_pattern = re.compile(r'\b\d{1,2}:\d{2}\s*[AP]M\b', re.IGNORECASE)
    name_pattern = re.compile(r'\b(MRS?|MR|MS|SIR|MAM|PROF|DR)\b', re.IGNORECASE)

    # Find date and time positions
    date_idx = None
    time_idx = None
    for i, p in enumerate(parts):
        if date_pattern.search(p):
            date_idx = i
        if time_pattern.search(p):
            time_idx = i

    # If date or time missing, fallback to old 4‑part logic
    if date_idx is None or time_idx is None:
        if len(parts) == 4:
            return {
                'subject': parts[0],
                'lecturer': parts[1],
                'nepali_date': parts[2],
                'time': parts[3]
            }
        return None

    nepali_date = parts[date_idx]
    time_str = parts[time_idx]

    # Remove date and time from the list
    remaining = [p for j, p in enumerate(parts) if j not in (date_idx, time_idx)]
    if not remaining:
        return None

    # Try to find the lecturer: the part that contains a name title
    lecturer_idx = None
    for i, p in enumerate(remaining):
        if name_pattern.search(p):
            lecturer_idx = i
            break

    if lecturer_idx is not None:
        lecturer = remaining.pop(lecturer_idx)
    else:
        # If no title found, assume the last part before date/time is the lecturer
        lecturer = remaining.pop(-1)

    # The first remaining part becomes the subject
    subject = remaining[0] if remaining else ''

    return {
        'subject': subject,
        'lecturer': lecturer,
        'nepali_date': nepali_date,
        'time': time_str
    }

def clear_screen():
    """Clear the terminal screen (optional, not used automatically)."""
    os.system('cls' if os.name == 'nt' else 'clear')

def compute_md5(file_path, chunk_size=8192):
    """Compute MD5 hash of a file."""
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()
# web.py


import os
from flask import Flask, render_template, request, redirect, url_for, flash, send_file
from .db import get_connection, TABLE_NAME, get_record_by_video_id
from .file_manager import (
    get_target_path,
    organize_video,
    sync_record_files,
    get_tally_data,
    trash_video_by_record,
    collect_facebook_tally_data
)
from .facebook_manager import list_facebook_entries, get_facebook_entry_by_id, delete_facebook_entry, get_facebook_file_path
from .youtube import fetch_youtube_title
from .file_manager import collect_tally_data   # add this

# ===== PLAYBACK CONFIGURATION =====
PLAYBACK_SOURCE = 'mirror_only'   # Change this to your preference
# ==================================

template_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'templates')
app = Flask(__name__, template_folder=template_dir)
app.secret_key = os.urandom(24)

def get_all_youtube_records():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(f"SELECT * FROM {TABLE_NAME} ORDER BY nepali_date DESC, time DESC")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return rows

# ---------- YouTube routes ----------
@app.route('/')
def index():
    # Get YouTube tally using hash-based matching
    yt_tally = collect_tally_data()
    total_yt = len(yt_tally['records'])
    missing_yt = len(yt_tally['missing'])
    orphan_yt = len(yt_tally['orphan'])

    # Get Facebook stats
    fb_stats = collect_facebook_tally_data()
    total_fb = fb_stats['total_entries']
    missing_fb = len(fb_stats['missing'])
    orphan_fb = len(fb_stats['orphan'])

    return render_template('index.html',
                           total_yt=total_yt,
                           missing_yt=missing_yt,
                           total_fb=total_fb,
                           missing_fb=missing_fb,
                           orphan_fb=orphan_fb,
                           orphan_yt=orphan_yt,       # pass orphan count
                           tally=yt_tally,            # for backward compatibility with template
                           playback_config=PLAYBACK_SOURCE)

@app.route('/lectures')
def lectures():
    search = request.args.get('search', '')
    sort_by = request.args.get('sort', 'nepali_date')
    order = request.args.get('order', 'desc')
    records = get_all_youtube_records()
    if search:
        search_lower = search.lower()
        records = [r for r in records if
                   search_lower in (r.get('syllabus_id') or '').lower() or
                   search_lower in (r.get('subject') or '').lower() or
                   search_lower in (r.get('chapter') or '').lower() or
                   search_lower in (r.get('lecturer') or '').lower() or
                   search_lower in (r.get('video_id') or '').lower()]
    reverse = (order == 'desc')
    if sort_by == 'syllabus_id':
        records.sort(key=lambda x: x.get('syllabus_id') or '', reverse=reverse)
    elif sort_by == 'subject':
        records.sort(key=lambda x: x.get('subject') or '', reverse=reverse)
    elif sort_by == 'lecturer':
        records.sort(key=lambda x: x.get('lecturer') or '', reverse=reverse)
    elif sort_by == 'nepali_date':
        records.sort(key=lambda x: x.get('nepali_date') or '', reverse=reverse)
    elif sort_by == 'time':
        records.sort(key=lambda x: x.get('time') or '', reverse=reverse)
    else:
        records.sort(key=lambda x: x.get('nepali_date') or '', reverse=True)
    return render_template('lectures.html', records=records, search=search, sort_by=sort_by, order=order)

@app.route('/lecture/<int:id>')
def lecture_detail(id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(f"SELECT * FROM {TABLE_NAME} WHERE id = %s", (id,))
    record = cursor.fetchone()
    cursor.close()
    conn.close()
    if not record:
        flash('Record not found', 'danger')
        return redirect(url_for('lectures'))

    mirror_id = record.get('mirror_video_id')
    original_id = record['video_id']

    using_mirror = False
    embed_vid = None
    config_status = None

    if PLAYBACK_SOURCE == 'mirror_only':
        if mirror_id:
            embed_vid = mirror_id
            using_mirror = True
            config_status = 'ok'
        else:
            embed_vid = None
            config_status = 'missing_mirror'
    elif PLAYBACK_SOURCE == 'original_only':
        embed_vid = original_id
        using_mirror = False
        config_status = 'ok'
    else:  # prefer_mirror
        if mirror_id:
            embed_vid = mirror_id
            using_mirror = True
            config_status = 'ok'
        else:
            embed_vid = original_id
            using_mirror = False
            config_status = 'using_original'

    embed_url = f"https://www.youtube.com/embed/{embed_vid}" if embed_vid else None

    return render_template('detail.html',
                           record=record,
                           embed_url=embed_url,
                           embed_vid=embed_vid,
                           using_mirror=using_mirror,
                           config_status=config_status,
                           playback_config=PLAYBACK_SOURCE)

@app.route('/lecture/add', methods=['GET', 'POST'])
def add_lecture_web():
    if request.method == 'POST':
        video_id = request.form.get('video_id')
        if not video_id:
            flash('Video ID is required', 'danger')
            return redirect(url_for('add_lecture_web'))
        title = fetch_youtube_title(video_id) or ''
        syllabus_id = request.form.get('syllabus_id')
        subject = request.form.get('subject')
        chapter = request.form.get('chapter')
        lecturer = request.form.get('lecturer')
        nepali_date = request.form.get('nepali_date')
        time_str = request.form.get('time')
        mirror_id = request.form.get('mirror_id') or None
        notes = request.form.get('notes') or None

        conn = get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(f"""
                INSERT INTO {TABLE_NAME}
                (video_id, mirror_video_id, video_title, syllabus_id, subject, chapter, lecturer, nepali_date, time, notes)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (video_id, mirror_id, title, syllabus_id, subject, chapter, lecturer, nepali_date, time_str, notes))
            conn.commit()
            flash('Lecture added successfully!', 'success')
        except Exception as e:
            flash(f'Error: {e}', 'danger')
        finally:
            cursor.close()
            conn.close()
        return redirect(url_for('lectures'))
    return render_template('add_edit.html', record=None, title='Add Lecture')

@app.route('/lecture/edit/<int:id>', methods=['GET', 'POST'])
def edit_lecture_web(id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(f"SELECT * FROM {TABLE_NAME} WHERE id = %s", (id,))
    record = cursor.fetchone()
    cursor.close()
    conn.close()
    if not record:
        flash('Record not found', 'danger')
        return redirect(url_for('lectures'))
    if request.method == 'POST':
        video_id = request.form.get('video_id')
        if not video_id:
            flash('Video ID is required', 'danger')
            return redirect(url_for('edit_lecture_web', id=id))
        syllabus_id = request.form.get('syllabus_id')
        subject = request.form.get('subject')
        chapter = request.form.get('chapter')
        lecturer = request.form.get('lecturer')
        nepali_date = request.form.get('nepali_date')
        time_str = request.form.get('time')
        mirror_id = request.form.get('mirror_id') or None
        notes = request.form.get('notes') or None

        if video_id != record['video_id']:
            new_title = fetch_youtube_title(video_id)
        else:
            new_title = record['video_title']

        conn = get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(f"""
                UPDATE {TABLE_NAME}
                SET video_id = %s, mirror_video_id = %s, video_title = %s,
                    syllabus_id = %s, subject = %s, chapter = %s,
                    lecturer = %s, nepali_date = %s, time = %s, notes = %s
                WHERE id = %s
            """, (video_id, mirror_id, new_title, syllabus_id, subject, chapter,
                  lecturer, nepali_date, time_str, notes, id))
            conn.commit()
            flash('Lecture updated successfully!', 'success')
            updated_record = get_record_by_video_id(video_id)
            if updated_record:
                sync_record_files(updated_record, record.get('syllabus_id'), record.get('video_id'), record)
        except Exception as e:
            flash(f'Error: {e}', 'danger')
        finally:
            cursor.close()
            conn.close()
        return redirect(url_for('lecture_detail', id=id))
    return render_template('add_edit.html', record=record, title='Edit Lecture')

@app.route('/lecture/delete/<int:id>', methods=['POST'])
def delete_lecture_web(id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(f"SELECT * FROM {TABLE_NAME} WHERE id = %s", (id,))
    record = cursor.fetchone()
    cursor.close()
    if not record:
        flash('Record not found', 'danger')
        return redirect(url_for('lectures'))
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(f"DELETE FROM {TABLE_NAME} WHERE id = %s", (id,))
        conn.commit()
        flash('Record deleted successfully', 'success')
    except Exception as e:
        flash(f'Error: {e}', 'danger')
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for('lectures'))

@app.route('/organize/<int:id>', methods=['POST'])
def organize_lecture(id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(f"SELECT * FROM {TABLE_NAME} WHERE id = %s", (id,))
    record = cursor.fetchone()
    cursor.close()
    conn.close()
    if not record:
        flash('Record not found', 'danger')
        return redirect(url_for('lectures'))
    result = organize_video(record)
    if result:
        flash(f'Video organized to {result}', 'success')
    else:
        flash('Failed to organize video. Check if file exists.', 'warning')
    return redirect(url_for('lecture_detail', id=id))

@app.route('/trash/<int:id>', methods=['POST'])
def trash_lecture(id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(f"SELECT * FROM {TABLE_NAME} WHERE id = %s", (id,))
    record = cursor.fetchone()
    cursor.close()
    conn.close()
    if not record:
        flash('Record not found', 'danger')
        return redirect(url_for('lectures'))
    result = trash_video_by_record(record)
    if result:
        flash('Video moved to trash', 'success')
    else:
        flash('Failed to move video to trash', 'warning')
    return redirect(url_for('lecture_detail', id=id))

@app.route('/tally')
def tally():
    tally_data = collect_tally_data()
    tally_data = get_tally_data()
    return render_template('tally.html', tally=tally_data)

@app.route('/stream/<int:id>')
def stream_video(id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(f"SELECT * FROM {TABLE_NAME} WHERE id = %s", (id,))
    record = cursor.fetchone()
    cursor.close()
    conn.close()

    if not record:
        flash('Record not found', 'danger')
        return redirect(url_for('index'))

    # Determine which video to use (original or mirror)
    mirror_id = record.get('mirror_video_id')
    original_id = record['video_id']

    # Check if mirror is available and should be used
    use_mirror = False
    video_id_to_play = original_id

    if PLAYBACK_SOURCE == 'mirror_only' and mirror_id:
        video_id_to_play = mirror_id
        use_mirror = True
    elif PLAYBACK_SOURCE == 'prefer_mirror' and mirror_id:
        video_id_to_play = mirror_id
        use_mirror = True
    elif PLAYBACK_SOURCE == 'original_only':
        video_id_to_play = original_id

    # ---- Locate the file using the chosen video ID ----
    # We need to find the file based on the video ID we want to play.
    # Since files are stored by hash, we need to look up the file_hash for that video ID.
    # If we're using the mirror, but the mirror hasn't been downloaded, fallback to original.
    target_dir, filename_base = get_target_path(record, interactive=False)

    # Try to find the file using the record's file_hash (original)
    file_path = None
    file_hash = record.get('file_hash')
    if file_hash and target_dir:
        import glob
        pattern = os.path.join(target_dir, file_hash + '.*')
        matches = glob.glob(pattern)
        if matches:
            file_path = matches[0]

    # If using mirror and file not found, try original
    if use_mirror and not file_path:
        # Try to find the original video
        original_file_hash = record.get('file_hash')  # This is the original's hash
        if original_file_hash and target_dir:
            pattern = os.path.join(target_dir, original_file_hash + '.*')
            matches = glob.glob(pattern)
            if matches:
                file_path = matches[0]
                print(f"[INFO] Mirror file not found, falling back to original for {record['video_id']}")

    # If still not found, search entire ROOT_DIR
    if not file_path:
        from .file_manager import ROOT_DIR
        for root, _, files in os.walk(ROOT_DIR):
            for f in files:
                if f.startswith(file_hash) and f.lower().endswith(('.mp4', '.mkv', '.webm', '.avi', '.mov')):
                    file_path = os.path.join(root, f)
                    break
            if file_path:
                break

    if not file_path or not os.path.exists(file_path):
        flash('Video file not found on disk.', 'warning')
        return redirect(url_for('lecture_detail', id=id))

    return send_file(file_path, as_attachment=False)

@app.route('/stream_facebook/<int:id>')
def stream_facebook_video(id):
    """Stream a Facebook video file."""
    from .facebook_manager import get_facebook_entry_by_id, get_facebook_file_path
    record = get_facebook_entry_by_id(id)
    if not record:
        flash('Entry not found', 'danger')
        return redirect(url_for('facebook_entries'))
    if record['type'] != 'video':
        flash('Not a video', 'warning')
        return redirect(url_for('facebook_detail', id=id))
    file_path = get_facebook_file_path(record)
    if not file_path or not os.path.exists(file_path):
        flash('Video file not found on disk.', 'warning')
        return redirect(url_for('facebook_detail', id=id))
    return send_file(file_path, as_attachment=False)

# ---------- Facebook routes ----------
@app.route('/facebook')
def facebook_entries():
    search = request.args.get('search', '')
    sort_by = request.args.get('sort', 'download_date')
    order = request.args.get('order', 'desc')
    records = list_facebook_entries()
    if search:
        search_lower = search.lower()
        records = [r for r in records if
                   search_lower in (r.get('title') or '').lower() or
                   search_lower in (r.get('uploader') or '').lower() or
                   search_lower in (r.get('facebook_id') or '').lower()]
    reverse = (order == 'desc')
    if sort_by == 'title':
        records.sort(key=lambda x: x.get('title') or '', reverse=reverse)
    elif sort_by == 'uploader':
        records.sort(key=lambda x: x.get('uploader') or '', reverse=reverse)
    elif sort_by == 'type':
        records.sort(key=lambda x: x.get('type') or '', reverse=reverse)
    elif sort_by == 'download_date':
        records.sort(key=lambda x: x.get('download_date') or '', reverse=reverse)
    else:
        records.sort(key=lambda x: x.get('download_date') or '', reverse=True)
    return render_template('facebook_entries.html', records=records, search=search, sort_by=sort_by, order=order)

@app.route('/facebook/<int:id>')
def facebook_detail(id):
    record = get_facebook_entry_by_id(id)
    if not record:
        flash('Entry not found', 'danger')
        return redirect(url_for('facebook_entries'))
    file_path = get_facebook_file_path(record)
    return render_template('facebook_detail.html', record=record, file_path=file_path)

@app.route('/facebook/delete/<int:id>', methods=['POST'])
def facebook_delete(id):
    record = get_facebook_entry_by_id(id)
    if not record:
        flash('Entry not found', 'danger')
        return redirect(url_for('facebook_entries'))
    # Delete file if exists
    file_path = get_facebook_file_path(record)
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
            flash(f'File {os.path.basename(file_path)} deleted', 'success')
        except Exception as e:
            flash(f'Failed to delete file: {e}', 'danger')
    if delete_facebook_entry(id):
        flash('Entry deleted successfully', 'success')
    else:
        flash('Failed to delete entry', 'danger')
    return redirect(url_for('facebook_entries'))

def run_web_server(host='127.0.0.1', port=5000):
    app.run(host=host, port=port, debug=False, threaded=True)
# File youtube.py (unchanged)

import re
import os
import time
import yt_dlp
from .db import get_connection
from .utils import print_colored, COLORS

COOKIE_FILE = 'cookies.txt'
COOKIE_MAX_AGE = 7 * 24 * 60 * 60  # 7 days in seconds

def refresh_cookies():
    """Force‑refresh cookies from browser, update DB and cookies.txt."""
    print_colored("[i] Forcing cookie refresh...", COLORS.BLUE)
    _ensure_cookie_file(force=True)
    print_colored("[✓] Cookies refreshed successfully.", COLORS.GREEN)

def extract_video_id(url_or_id):
    if re.fullmatch(r'[0-9A-Za-z_-]{11}', url_or_id):
        return url_or_id
    patterns = [
        r'(?:v=|\/)([0-9A-Za-z_-]{11})(?:[?&]|$)',
        r'youtu\.be\/([0-9A-Za-z_-]{11})',
        r'shorts\/([0-9A-Za-z_-]{11})'
    ]
    for pattern in patterns:
        match = re.search(pattern, url_or_id)
        if match:
            return match.group(1)
    return None

def _format_cookie(cookie):
    """Format a cookie object into Netscape format line."""
    return f"{cookie.domain}\tTRUE\t{cookie.path}\t{'TRUE' if cookie.secure else 'FALSE'}\t{cookie.expires if cookie.expires else 0}\t{cookie.name}\t{cookie.value}"

def _extract_cookies_from_browser():
    """Extract cookies from browser using browser-cookie3."""
    try:
        import browser_cookie3
    except ImportError:
        print_colored("[!] browser-cookie3 not installed. Install with: pip install browser-cookie3", COLORS.YELLOW)
        return None

    browsers = [
        ('edge', browser_cookie3.edge),
        ('chrome', browser_cookie3.chrome),
        ('firefox', browser_cookie3.firefox),
        ('brave', browser_cookie3.brave),
        ('opera', browser_cookie3.opera),
    ]
    for name, get_cookies in browsers:
        try:
            print_colored(f"[i] Extracting cookies from {name}...", COLORS.BLUE)
            cookies = get_cookies(domain_name='youtube.com')
            # Filter essential cookies (optional, but keep most)
            lines = []
            for cookie in cookies:
                # Skip some cookies that might be large or unnecessary
                if cookie.name in ('__cf_bm', 'cf_clearance'):
                    continue
                lines.append(_format_cookie(cookie))
            if lines:
                cookie_data = "# Netscape HTTP Cookie File\n"
                cookie_data += "# This file was generated by browser-cookie3\n\n"
                cookie_data += "\n".join(lines)
                return cookie_data
        except Exception as e:
            print_colored(f"[!] Failed from {name}: {e}", COLORS.RED)
            continue
    return None

def _get_cookie_data_from_db():
    """Retrieve cookie data from database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT cookie_data, last_refresh FROM cookies WHERE id = 1")
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    if row:
        return row[0], row[1]
    return None, None

def _update_cookie_data_in_db(cookie_data):
    """Store cookie data in database."""
    conn = get_connection()
    cursor = conn.cursor()
    # Upsert: replace if exists
    cursor.execute("REPLACE INTO cookies (id, cookie_data, last_refresh) VALUES (1, %s, NOW())", (cookie_data,))
    conn.commit()
    cursor.close()
    conn.close()

def _ensure_cookie_file(force=False):
    """
    Ensure cookies.txt exists and is fresh.
    If force=True, always re‑extract from browser and update DB.
    """
    need_refresh = force

    # Check if file exists and is fresh (if not forced)
    if not force and os.path.exists(COOKIE_FILE):
        mtime = os.path.getmtime(COOKIE_FILE)
        if time.time() - mtime > COOKIE_MAX_AGE:
            print_colored("[i] cookies.txt is older than 7 days. Refreshing...", COLORS.YELLOW)
            need_refresh = True
        else:
            return  # all good

    if not force and not os.path.exists(COOKIE_FILE):
        print_colored("[i] cookies.txt not found. Trying to create it...", COLORS.YELLOW)
        need_refresh = True

    if need_refresh:
        # Try DB first (if fresh)
        cookie_data, last_refresh = _get_cookie_data_from_db()
        if not force and cookie_data and last_refresh:
            if time.time() - last_refresh.timestamp() < COOKIE_MAX_AGE:
                print_colored("[i] Using fresh cookie data from database.", COLORS.GREEN)
                with open(COOKIE_FILE, 'w') as f:
                    f.write(cookie_data)
                return

        # Extract from browser
        print_colored("[i] Extracting cookies from browser (this may take a moment)...", COLORS.BLUE)
        cookie_data = _extract_cookies_from_browser()
        if cookie_data:
            _update_cookie_data_in_db(cookie_data)
            with open(COOKIE_FILE, 'w') as f:
                f.write(cookie_data)
            print_colored(f"[✓] cookies.txt created/refreshed.", COLORS.GREEN)
        else:
            print_colored("[!] Could not extract cookies. Falling back to browser cookies.", COLORS.YELLOW)

def fetch_youtube_title(video_id):
    """Fetch video title, managing cookies automatically."""
    _ensure_cookie_file()

    url = f"https://www.youtube.com/watch?v={video_id}"
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': True,           # fetch only metadata
        'skip_download': True,
        'ignoreerrors': True,
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'web'],  # fallback clients
                'skip': ['hls', 'dash'],
            }
        }
    }

    # Prefer cookies.txt if it exists
    if os.path.exists(COOKIE_FILE):
        ydl_opts['cookiefile'] = COOKIE_FILE
    else:
        ydl_opts['cookiesfrombrowser'] = ('edge',)

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if info and isinstance(info, dict):
                return info.get('title')
            return None
    except Exception as e:
        print_colored(f"[!] Error fetching title for {video_id}: {e}", COLORS.RED)
        return None

def get_embed_link(video_id):
    return f"https://www.youtube.com/embed/{video_id}"
<!-- add_edit.html -->
{% extends "base.html" %}
{% block content %}
<h2>{{ title }}</h2>
<form method="post">
  <div class="mb-3">
    <label for="video_id" class="form-label">Video ID *</label>
    <input type="text" class="form-control" id="video_id" name="video_id" value="{{ record.video_id if record else '' }}" required>
  </div>
  <div class="mb-3">
    <label for="syllabus_id" class="form-label">Syllabus ID</label>
    <input type="text" class="form-control" id="syllabus_id" name="syllabus_id" value="{{ record.syllabus_id if record else '' }}">
  </div>
  <div class="mb-3">
    <label for="subject" class="form-label">Subject</label>
    <input type="text" class="form-control" id="subject" name="subject" value="{{ record.subject if record else '' }}">
  </div>
  <div class="mb-3">
    <label for="chapter" class="form-label">Chapter</label>
    <input type="text" class="form-control" id="chapter" name="chapter" value="{{ record.chapter if record else '' }}">
  </div>
  <div class="mb-3">
    <label for="lecturer" class="form-label">Lecturer</label>
    <input type="text" class="form-control" id="lecturer" name="lecturer" value="{{ record.lecturer if record else '' }}">
  </div>
  <div class="mb-3">
    <label for="nepali_date" class="form-label">Nepali Date</label>
    <input type="text" class="form-control" id="nepali_date" name="nepali_date" value="{{ record.nepali_date if record else '' }}">
  </div>
  <div class="mb-3">
    <label for="time" class="form-label">Time</label>
    <input type="text" class="form-control" id="time" name="time" value="{{ record.time if record else '' }}">
  </div>
  <div class="mb-3">
    <label for="mirror_id" class="form-label">Mirror Video ID</label>
    <input type="text" class="form-control" id="mirror_id" name="mirror_id" value="{{ record.mirror_video_id if record else '' }}">
  </div>
  <div class="mb-3">
    <label for="notes" class="form-label">Notes</label>
    <textarea class="form-control" id="notes" name="notes" rows="3">{{ record.notes if record else '' }}</textarea>
  </div>
  <button type="submit" class="btn btn-primary">Save</button>
  <a href="{{ url_for('lectures') if record else url_for('index') }}" class="btn btn-secondary">Cancel</a>
</form>
{% endblock %}
<!-- base.html -->

<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Lecture Manager</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.0/font/bootstrap-icons.css">
  </head>
  <body>
    <nav class="navbar navbar-expand-lg navbar-dark bg-dark">
      <div class="container-fluid">
        <a class="navbar-brand" href="{{ url_for('index') }}">📚 Media Manager</a>
        <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNav">
          <span class="navbar-toggler-icon"></span>
        </button>
        <div class="collapse navbar-collapse" id="navbarNav">
          <ul class="navbar-nav ms-auto">
            <li class="nav-item"><a class="nav-link" href="{{ url_for('index') }}">Dashboard</a></li>
            <li class="nav-item"><a class="nav-link" href="{{ url_for('lectures') }}">YouTube</a></li>
            <li class="nav-item"><a class="nav-link" href="{{ url_for('facebook_entries') }}">Facebook</a></li>
            <li class="nav-item"><a class="nav-link" href="{{ url_for('tally') }}">Tally</a></li>
            <li class="nav-item"><a class="nav-link" href="{{ url_for('add_lecture_web') }}">Add YouTube</a></li>
          </ul>
        </div>
      </div>
    </nav>
    <div class="container mt-4">
      {% with messages = get_flashed_messages(with_categories=true) %}
        {% if messages %}
          {% for category, message in messages %}
            <div class="alert alert-{{ category if category != 'message' else 'info' }} alert-dismissible fade show" role="alert">
              {{ message }}
              <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
            </div>
          {% endfor %}
        {% endif %}
      {% endwith %}
      {% block content %}{% endblock %}
    </div>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
  </body>
</html>
<!-- detail.html -->
{% extends "base.html" %}
{% block content %}
<h2>Lecture Details</h2>
<div class="card">
  <div class="card-body">
    <dl class="row">
      <dt class="col-sm-3">ID</dt>
      <dd class="col-sm-9">{{ record.id }}</dd>

      <dt class="col-sm-3">Video ID</dt>
      <dd class="col-sm-9">{{ record.video_id }}</dd>

      <dt class="col-sm-3">Mirror ID</dt>
      <dd class="col-sm-9">
        {% if record.mirror_video_id %}
          {{ record.mirror_video_id }}
          <span class="badge bg-success">available</span>
        {% else %}
          <span class="text-muted">Not available</span>
          <span class="badge bg-secondary">no mirror</span>
        {% endif %}
      </dd>

      <dt class="col-sm-3">Syllabus</dt>
      <dd class="col-sm-9">{{ record.syllabus_id or '' }}</dd>

      <dt class="col-sm-3">Subject</dt>
      <dd class="col-sm-9">{{ record.subject or '' }}</dd>

      <dt class="col-sm-3">Chapter</dt>
      <dd class="col-sm-9">{{ record.chapter or '' }}</dd>

      <dt class="col-sm-3">Lecturer</dt>
      <dd class="col-sm-9">{{ record.lecturer or '' }}</dd>

      <dt class="col-sm-3">Nepali Date</dt>
      <dd class="col-sm-9">{{ record.nepali_date or '' }}</dd>

      <dt class="col-sm-3">Time</dt>
      <dd class="col-sm-9">{{ record.time or '' }}</dd>

      <dt class="col-sm-3">Notes</dt>
      <dd class="col-sm-9">{{ record.notes or '' }}</dd>
    </dl>

    <div class="mt-4">
      <h5>Playback source:</h5>
      {% if config_status == 'missing_mirror' %}
        <div class="alert alert-warning">
          <i class="bi bi-exclamation-triangle"></i>
          <strong>Mirror ID is not available</strong> for this lecture, but your config is set to <code>mirror_only</code>.
          <br>
          <small>You can change the <code>PLAYBACK_SOURCE</code> variable in <code>web.py</code> to <code>prefer_mirror</code> or <code>original_only</code>.</small>
        </div>
      {% elif config_status == 'using_original' %}
        <div class="alert alert-info">
          <i class="bi bi-info-circle"></i>
          <strong>Using original video</strong> (no mirror available). Config: <code>{{ playback_config }}</code>
        </div>
      {% else %}
        <span class="badge {% if using_mirror %}bg-info{% else %}bg-secondary{% endif %}">
          {% if using_mirror %}
            Mirror (ID: {{ embed_vid }})
          {% else %}
            Original (ID: {{ embed_vid }})
          {% endif %}
        </span>
      {% endif %}

      {% if embed_url %}
        <div class="ratio ratio-16x9 mt-2">
          <iframe src="{{ embed_url }}" frameborder="0" allowfullscreen></iframe>
        </div>
      {% else %}
        <div class="alert alert-danger mt-2">
          <i class="bi bi-x-circle"></i>
          <strong>No video can be played.</strong>
          {% if config_status == 'missing_mirror' %}
            Please add a mirror ID to this lecture or change the playback config.
          {% endif %}
        </div>
      {% endif %}
    </div>

    <div class="mt-4">
      <a href="{{ url_for('lectures') }}" class="btn btn-secondary">Back to list</a>
      <a href="{{ url_for('edit_lecture_web', id=record.id) }}" class="btn btn-warning">Edit</a>
      <form method="post" action="{{ url_for('organize_lecture', id=record.id) }}" style="display:inline;">
        <button type="submit" class="btn btn-success">Organize File</button>
      </form>
      <form method="post" action="{{ url_for('trash_lecture', id=record.id) }}" style="display:inline;" onsubmit="return confirm('Move video to trash?')">
        <button type="submit" class="btn btn-secondary">Trash Video</button>
      </form>
      <a href="{{ url_for('stream_video', id=record.id) }}" class="btn btn-primary" target="_blank">
        <i class="bi bi-play-circle"></i> Watch Local Video
      </a>
    </div>
  </div>
</div>
{% endblock %}
<!-- facebook_detail.html -->

{% extends "base.html" %}
{% block content %}
<h2>Facebook Entry Details</h2>
<div class="card">
  <div class="card-body">
    <dl class="row">
      <dt class="col-sm-3">ID</dt>
      <dd class="col-sm-9">{{ record.id }}</dd>

      <dt class="col-sm-3">Facebook ID</dt>
      <dd class="col-sm-9">{{ record.facebook_id }}</dd>

      <dt class="col-sm-3">Type</dt>
      <dd class="col-sm-9"><span class="badge {% if record.type == 'video' %}bg-success{% else %}bg-secondary{% endif %}">{{ record.type }}</span></dd>

      <dt class="col-sm-3">Title</dt>
      <dd class="col-sm-9">{{ record.title or '—' }}</dd>

      <dt class="col-sm-3">Uploader</dt>
      <dd class="col-sm-9">{{ record.uploader or '—' }}</dd>

      <dt class="col-sm-3">URL</dt>
      <dd class="col-sm-9"><a href="{{ record.url }}" target="_blank">{{ record.url }}</a></dd>

      <dt class="col-sm-3">File Hash</dt>
      <dd class="col-sm-9"><code>{{ record.file_hash or '—' }}</code></dd>

      <dt class="col-sm-3">Original Filename</dt>
      <dd class="col-sm-9">{{ record.original_filename or '—' }}</dd>

      <dt class="col-sm-3">Download Date</dt>
      <dd class="col-sm-9">{{ record.download_date }}</dd>

      <dt class="col-sm-3">Notes</dt>
      <dd class="col-sm-9">{{ record.notes or '—' }}</dd>
    </dl>

    {% if file_path %}
      <div class="mt-4">
        <h5>File Location</h5>
        <p><code>{{ file_path }}</code></p>
        {% if record.type == 'video' %}
          <!-- ⚠️ IMPORTANT: This link MUST use 'stream_facebook_video' -->
          <a href="{{ url_for('stream_facebook_video', id=record.id) }}" class="btn btn-primary" target="_blank">
            <i class="bi bi-play-circle"></i> Watch Video
          </a>
        {% else %}
          <a href="{{ url_for('static', filename=file_path) }}" class="btn btn-primary" target="_blank">
            <i class="bi bi-image"></i> View Photo
          </a>
        {% endif %}
      </div>
    {% else %}
      <div class="alert alert-warning mt-4">
        <i class="bi bi-exclamation-triangle"></i> File not found on disk.
      </div>
    {% endif %}

    <div class="mt-4">
      <a href="{{ url_for('facebook_entries') }}" class="btn btn-secondary">Back to list</a>
      <form method="post" action="{{ url_for('facebook_delete', id=record.id) }}" style="display:inline;" onsubmit="return confirm('Delete this entry and file?')">
        <button type="submit" class="btn btn-danger">Delete Entry & File</button>
      </form>
    </div>
  </div>
</div>
{% endblock %}
<!-- facebook_entries.html -->

{% extends "base.html" %}
{% block content %}
<h2>Facebook Entries</h2>
<div class="row mb-3">
  <div class="col">
    <form method="get" class="row g-3">
      <div class="col-auto">
        <input type="text" name="search" value="{{ search }}" class="form-control" placeholder="Search...">
      </div>
      <div class="col-auto">
        <button type="submit" class="btn btn-primary">Search</button>
      </div>
      <div class="col-auto">
        <a href="{{ url_for('facebook_entries') }}" class="btn btn-secondary">Clear</a>
      </div>
    </form>
  </div>
</div>
<div class="table-responsive">
  <table class="table table-striped table-hover">
    <thead>
      <tr>
        <th>ID</th>
        <th><a href="{{ url_for('facebook_entries', sort='type', order='asc') }}">Type</a></th>
        <th><a href="{{ url_for('facebook_entries', sort='title', order='asc') }}">Title</a></th>
        <th><a href="{{ url_for('facebook_entries', sort='uploader', order='asc') }}">Uploader</a></th>
        <th><a href="{{ url_for('facebook_entries', sort='download_date', order='asc') }}">Date</a></th>
        <th>File Hash</th>
        <th>Actions</th>
      </tr>
    </thead>
    <tbody>
      {% for rec in records %}
      <tr>
        <td>{{ rec.id }}</td>
        <td><span class="badge {% if rec.type == 'video' %}bg-success{% else %}bg-secondary{% endif %}">{{ rec.type }}</span></td>
        <td>{{ rec.title or '—' }}</td>
        <td>{{ rec.uploader or '—' }}</td>
        <td>{{ rec.download_date }}</td>
        <td><code>{{ rec.file_hash[:8] if rec.file_hash else '—' }}</code></td>
        <td>
          <a href="{{ url_for('facebook_detail', id=rec.id) }}" class="btn btn-sm btn-info"><i class="bi bi-eye"></i></a>
          {% if rec.type == 'video' %}
          <a href="{{ url_for('stream_facebook_video', id=rec.id) }}" class="btn btn-sm btn-success" target="_blank"><i class="bi bi-play-circle"></i></a>
          {% endif %}
          <form method="post" action="{{ url_for('facebook_delete', id=rec.id) }}" style="display:inline;" onsubmit="return confirm('Delete this entry and file?')">
            <button type="submit" class="btn btn-sm btn-danger"><i class="bi bi-trash"></i></button>
          </form>
        </td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
</div>
{% endblock %}
<!-- index.html -->

{% extends "base.html" %}
{% block content %}
<div class="row">
  <div class="col-md-4">
    <div class="card text-white bg-primary mb-3">
      <div class="card-body">
        <h5 class="card-title">YouTube Lectures</h5>
        <p class="card-text display-4">{{ total_yt }}</p>
        <p class="card-text">Missing: {{ missing_yt }}</p>
      </div>
    </div>
  </div>
  <div class="col-md-4">
    <div class="card text-white bg-info mb-3">
      <div class="card-body">
        <h5 class="card-title">Facebook Entries</h5>
        <p class="card-text display-4">{{ total_fb }}</p>
        <p class="card-text">Missing: {{ missing_fb }} | Orphan: {{ orphan_fb }}</p>
      </div>
    </div>
  </div>
  <div class="col-md-4">
  <div class="card text-white bg-warning mb-3">
    <div class="card-body">
      <h5 class="card-title">Orphan Files (YouTube)</h5>
      <p class="card-text display-4">{{ orphan_yt }}</p>
    </div>
  </div>
</div>
</div>
<div class="row">
  <div class="col">
    <div class="card">
      <div class="card-header">
        Quick Actions
      </div>
      <div class="card-body">
        <a href="{{ url_for('add_lecture_web') }}" class="btn btn-success"><i class="bi bi-plus-circle"></i> Add YouTube Lecture</a>
        <a href="{{ url_for('tally') }}" class="btn btn-info"><i class="bi bi-list-check"></i> Tally Files</a>
        <a href="{{ url_for('lectures') }}" class="btn btn-secondary"><i class="bi bi-table"></i> View YouTube Lectures</a>
        <a href="{{ url_for('facebook_entries') }}" class="btn btn-primary"><i class="bi bi-facebook"></i> View Facebook</a>
      </div>
    </div>
  </div>
</div>
<div class="row mt-4">
  <div class="col">
    <div class="card">
      <div class="card-header">
        <i class="bi bi-gear"></i> Current Configuration
      </div>
      <div class="card-body">
        <p><strong>Playback Source:</strong> <code>{{ playback_config }}</code></p>
        <p class="text-muted small">
          Change in <code>web.py</code> (PLAYBACK_SOURCE variable).
        </p>
      </div>
    </div>
  </div>
</div>
{% endblock %}
<!-- lectures.html -->
{% extends "base.html" %}
{% block content %}
<h2>Lectures</h2>
<div class="row mb-3">
  <div class="col">
    <form method="get" class="row g-3">
      <div class="col-auto">
        <input type="text" name="search" value="{{ search }}" class="form-control" placeholder="Search...">
      </div>
      <div class="col-auto">
        <button type="submit" class="btn btn-primary">Search</button>
      </div>
      <div class="col-auto">
        <a href="{{ url_for('lectures') }}" class="btn btn-secondary">Clear</a>
      </div>
    </form>
  </div>
</div>
<div class="table-responsive">
  <table class="table table-striped table-hover">
    <thead>
      <tr>
        <th><a href="{{ url_for('lectures', sort='syllabus_id', order='asc') }}">Syllabus</a></th>
        <th><a href="{{ url_for('lectures', sort='subject', order='asc') }}">Subject</a></th>
        <th>Chapter</th>
        <th><a href="{{ url_for('lectures', sort='lecturer', order='asc') }}">Lecturer</a></th>
        <th><a href="{{ url_for('lectures', sort='nepali_date', order='asc') }}">Date</a></th>
        <th><a href="{{ url_for('lectures', sort='time', order='asc') }}">Time</a></th>
        <th>Video ID</th>
        <th>Mirror ID</th>
        <th>Actions</th>
      </tr>
    </thead>
    <tbody>
      {% for rec in records %}
      <tr>
        <td>{{ rec.syllabus_id or '' }}</td>
        <td>{{ rec.subject or '' }}</td>
        <td>{{ rec.chapter or '' }}</td>
        <td>{{ rec.lecturer or '' }}</td>
        <td>{{ rec.nepali_date or '' }}</td>
        <td>{{ rec.time or '' }}</td>
        <td>{{ rec.video_id }}</td>
        <td>{{ rec.mirror_video_id or '—' }}</td>
        <td>
          <a href="{{ url_for('lecture_detail', id=rec.id) }}" class="btn btn-sm btn-info"><i class="bi bi-eye"></i></a>
          <a href="{{ url_for('edit_lecture_web', id=rec.id) }}" class="btn btn-sm btn-warning"><i class="bi bi-pencil"></i></a>
          <form method="post" action="{{ url_for('delete_lecture_web', id=rec.id) }}" style="display:inline;" onsubmit="return confirm('Delete this lecture?')">
            <button type="submit" class="btn btn-sm btn-danger"><i class="bi bi-trash"></i></button>
          </form>
          <form method="post" action="{{ url_for('organize_lecture', id=rec.id) }}" style="display:inline;">
            <button type="submit" class="btn btn-sm btn-success"><i class="bi bi-folder-symlink"></i></button>
          </form>
          <form method="post" action="{{ url_for('trash_lecture', id=rec.id) }}" style="display:inline;" onsubmit="return confirm('Move video to trash?')">
            <button type="submit" class="btn btn-sm btn-secondary"><i class="bi bi-archive"></i></button>
          </form>
        </td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
</div>
{% endblock %}
<!-- tally.html -->
{% extends "base.html" %}
{% block content %}
<h2>Tally Report</h2>
<div class="row">
  <div class="col-md-3"><div class="card text-white bg-primary"><div class="card-body"><h5>Records</h5><p class="display-4">{{ tally.total_records }}</p></div></div></div>
  <div class="col-md-3"><div class="card text-white bg-success"><div class="card-body"><h5>Matched</h5><p class="display-4">{{ tally.matched }}</p></div></div></div>
  <div class="col-md-3"><div class="card text-white bg-danger"><div class="card-body"><h5>Missing</h5><p class="display-4">{{ tally.missing }}</p></div></div></div>
  <div class="col-md-3"><div class="card text-white bg-warning"><div class="card-body"><h5>Orphan</h5><p class="display-4">{{ tally.orphan }}</p></div></div></div>
</div>
<div class="row mt-4">
  <div class="col-md-6">
    <h4>Missing Records</h4>
    <ul class="list-group">
      {% for rec in tally.missing_list %}
      <li class="list-group-item">{{ rec.syllabus_id }} - {{ rec.subject }} ({{ rec.video_id }})</li>
      {% else %}
      <li class="list-group-item">None</li>
      {% endfor %}
    </ul>
  </div>
  <div class="col-md-6">
    <h4>Orphan Files</h4>
    <ul class="list-group">
      {% for f in tally.orphan_list[:20] %}
      <li class="list-group-item">{{ f }}</li>
      {% else %}
      <li class="list-group-item">None</li>
      {% endfor %}
      {% if tally.orphan_list|length > 20 %}
      <li class="list-group-item">... and {{ tally.orphan_list|length - 20 }} more</li>
      {% endif %}
    </ul>
  </div>
</div>
<div class="row mt-4">
  <div class="col">
    <h4>Mismatched</h4>
    <ul class="list-group">
      {% for item in tally.mismatched_list %}
      <li class="list-group-item">{{ item.record.syllabus_id }} - {{ item.record.subject }} (found: {{ item.files|join(', ') }})</li>
      {% else %}
      <li class="list-group-item">None</li>
      {% endfor %}
    </ul>
  </div>
</div>
{% endblock %}
# File lecture-manager.py (entry point)

#!/usr/bin/env python3

import readline
from lecture_manager.main import main

if __name__ == "__main__":
    main()
from setuptools import setup, find_packages

setup(
    name="youtube-lecture-manager",
    version="2.3.0",
    description="Organise and manage YouTube lecture libraries with a terminal interface, web UI, and local playback",
    long_description=open("README.md").read() if open("README.md").read() else "",
    long_description_content_type="text/markdown",
    author="Udaya Raj Joshi",
    author_email="udayarajjoshi@gmail.com",   # update if needed
    url="https://github.com/yourusername/lecture-manager",  # update with your repo
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        "mysql-connector-python>=8.0.0",
        "yt-dlp>=2023.0.0",
        "flask>=2.0.0",
        "browser-cookie3",
        "bgutil-ytdlp-pot-provider",
    ],
    entry_points={
        "console_scripts": [
            "lecture-manager = lecture_manager.main:main",
        ],
    },
    python_requires=">=3.6",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: POSIX :: Linux",
    ],
)
# Makefile for YouTube Lecture Manager

# --- Project settings ---
PROJECT_NAME   := youtube-lecture-manager
BACKUP_DIR     := ./backups
TIMESTAMP      := $(shell date +%Y%m%d_%H%M%S)
BACKUP_FILE    := $(BACKUP_DIR)/$(PROJECT_NAME)_backup_$(TIMESTAMP).tar.gz

# --- Database settings (for backup-db) ---
DB_HOST        ?= localhost
DB_USER        ?= fox
DB_PASSWORD    ?= fox
DB_NAME        ?= fox
DB_DUMP_FILE   := $(BACKUP_DIR)/$(PROJECT_NAME)_db_$(TIMESTAMP).sql

# --- Files/directories to exclude from backup ---
EXCLUDE := --exclude='__pycache__' \
           --exclude='*.pyc' \
           --exclude='*.pyo' \
           --exclude='*.db' \
           --exclude='cookies.txt' \
           --exclude='.git' \
           --exclude='.env' \
           --exclude='downloads' \
           --exclude='backups' \
           --exclude='.lecture_trash' \
           --exclude='*.log' \
           --exclude='*.sql' \
           --exclude='.DS_Store'

# --- Targets ---

.PHONY: help backup backup-db clean install dist

help:
	@echo "Available targets:"
	@echo "  make backup      - Create a timestamped backup tarball of the project."
	@echo "  make backup-db   - Dump the MariaDB database to a SQL file (requires DB credentials)."
	@echo "  make clean       - Remove Python cache files and temporary files."
	@echo "  make install     - Install the package in editable (development) mode."
	@echo "  make dist        - Build a source distribution (.tar.xz) for distribution."

backup: $(BACKUP_DIR)
	@echo "Creating backup of $(PROJECT_NAME)..."
	tar -czf $(BACKUP_FILE) $(EXCLUDE) .
	@echo "Backup created: $(BACKUP_FILE)"

$(BACKUP_DIR):
	mkdir -p $(BACKUP_DIR)

backup-db: $(BACKUP_DIR)
	@echo "Dumping database $(DB_NAME)..."
	mysqldump -h $(DB_HOST) -u $(DB_USER) -p$(DB_PASSWORD) $(DB_NAME) > $(DB_DUMP_FILE)
	@echo "Database dump saved: $(DB_DUMP_FILE)"

clean:
	@echo "Removing Python cache files..."
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	@echo "Clean complete."

install:
	@echo "Installing $(PROJECT_NAME) in development mode..."
	pip install -e .
	@echo "Installation complete."

dist:
	@echo "Building source distribution (.tar.xz)..."
	python setup.py sdist --formats=xztar
	@echo "Distribution created in ./dist/"
	@ls -lh dist/*.tar.xz
# 📚 YouTube Lecture Manager

A powerful terminal‑based tool to organise, manage, and play YouTube lecture libraries.  
It keeps your videos structured by syllabus, paper, subject, and date – with a beautiful dashboard, local playback, and a web interface.

---

## ✨ Features

- **Add lectures** – Paste a YouTube URL, auto‑detect title, lecturer, date, and time.
- **Automatic organisation** – Files are renamed and moved into a clean folder structure (`Paper / Subject / Chapter /`).
- **Paper‑aware** – Distinguishes Pretest, Paper I, II, and III using a dedicated `paper` column.
- **Tally & verification** – Scan your filesystem and compare against the database; find orphaned files, missing videos, or content mismatches.
- **Duplicate resolution** – Find and remove duplicate video files using MD5 hashes.
- **Local video playback** – Choose a player (`mpv`, `vlc`, `xdg‑open`) and play any lecture directly from the CLI.
- **Beautiful dashboard** – Quick overview of total records, storage usage, top lecturers, and more.
- **Web interface** – Browse lectures, view details, and stream local videos in your browser.
- **Export/Import** – CSV and JSON support for backups and batch editing.

---

## 🚀 Installation

### 1. Clone the repository

```bash
git clone https://github.com/yourusername/lecture-manager.git
cd lecture-manager



python3 -m venv venv
source venv/bin/activate


pip install -e .


Install Deno (required for YouTube extraction)
yt-dlp uses Deno to solve YouTube’s signature cipher.

bash
curl -fsSL https://deno.land/install.sh | sh


deno --version
