# File crud.py

import os
import subprocess
import mysql.connector
import glob
from .db import get_connection, TABLE_NAME, get_record_by_video_id, get_record_by_any_id, get_any_media_record
from .youtube import extract_video_id, fetch_youtube_title, get_embed_link, _ensure_cookie_file
from .utils import clean_field, get_display_title, sanitize_filename, parse_lecture_title, color_text, print_colored, COLORS, normalize_syllabus_id, build_original_filename
from .file_manager import organize_video, sync_record_files, detect_paper, PAPER_CONFIG, get_target_path, ROOT_DIR
from .facebook_manager import add_facebook_lecture
from .upload import upload_video_to_youtube

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

    # ---- Continue with YouTube logic ----
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
                            pass
                        else:
                            print_colored("[!] Invalid choice.", COLORS.RED)
                    else:
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
        print_colored("[i] Could not auto‑parse title. Please enter manually.", COLORS.YELLOW)
        subject = input(color_text("Subject (course name): ", COLORS.MAGENTA)).strip()
        lecturer = input(color_text("Lecturer Name: ", COLORS.MAGENTA)).strip()
        nepali_date = input(color_text("Nepali Date (B.S.): ", COLORS.MAGENTA)).strip()
        time_str = input(color_text("Time: ", COLORS.MAGENTA)).strip()
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

    # ---- Insert record ----
    conn = get_connection()
    cursor = conn.cursor()
    try:
        # Build original_filename from fields
        original_filename = " || ".join([p for p in [syllabus_id, chapter, subject, lecturer, nepali_date, time_str] if p])
        cursor.execute(f"""
        INSERT INTO {TABLE_NAME}
        (video_id, mirror_video_id, video_title, syllabus_id, subject, chapter, lecturer, nepali_date, time, notes, paper, original_filename)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (video_id, mirror_id, title, syllabus_id, subject, chapter, lecturer, nepali_date, time_str, notes, paper, original_filename))
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

    # ---- Fetch the new record ----
    record = get_record_by_video_id(video_id)
    if not record:
        print_colored("[!] Record added but could not retrieve. Skipping further actions.", COLORS.RED)
        return

    # ---- Step 1: Download the video (if user wants) ----
    if input(color_text("Download now? (y/n): ", COLORS.MAGENTA)).strip().lower() == 'y':
        download_video(record, silent=True)
        # Re‑fetch the record after download (file_hash and original_filename may have been updated)
        record = get_record_by_video_id(video_id)
        if not record:
            print_colored("[!] Could not re‑fetch record after download.", COLORS.RED)
            return

    # ---- Step 2: Upload to YouTube (if user wants and file exists) ----
    if record.get('file_hash'):
        # File exists (or was downloaded earlier)
        if input(color_text("Upload this lecture to YouTube now? (y/n): ", COLORS.MAGENTA)).strip().lower() == 'y':
            from .upload import upload_video_to_youtube
            print_colored("[i] Uploading to YouTube...", COLORS.BLUE)
            success, msg, vid = upload_video_to_youtube(record)
            if success:
                print_colored(f"[✓] {msg}", COLORS.GREEN)
            else:
                print_colored(f"[!] {msg}", COLORS.RED)
    else:
        print_colored("[i] Video file not found on disk. Please download it first to upload.", COLORS.YELLOW)

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
            cursor = conn.cursor(dictionary=True)
            cursor.execute(f"SELECT * FROM {TABLE_NAME} WHERE video_id = %s", (video_id,))
            row = cursor.fetchone()
            cursor.close()
            conn.close()

            if not row:
                print_colored("[!] Record not found. Exiting update for this ID.", COLORS.RED)
                break

            print("\n" + "═" * 50)
            print_colored("  UPDATE LECTURE", COLORS.CYAN, bold=True)
            print("═" * 50)
            print(f"1. Video ID     : {row['video_id']}")
            print(f"2. Syllabus ID  : {row['syllabus_id']}")
            print(f"3. Subject      : {row['subject']}")
            print(f"4. Chapter      : {row['chapter'] if row['chapter'] else '(auto)'}")
            print(f"5. Lecturer     : {row['lecturer']}")
            print(f"6. Nepali Date  : {row['nepali_date']}")
            print(f"7. Time         : {row['time']}")
            print(f"8. Video Title  : {row['video_title']}")
            print(f"9. Mirror ID    : {row['mirror_video_id'] if row['mirror_video_id'] else '(none)'}")
            print("10. Notes        : " + (row['notes'] if row['notes'] else '(none)'))
            print("11. Paper        : " + (row['paper'] if row['paper'] else '(none)'))
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
                paper_choice = input(color_text(f"Choose paper (1-4, or 0 to keep '{row['paper'] if row['paper'] else 'none'}'): ", COLORS.MAGENTA)).strip()

                if paper_choice.isdigit():
                    idx = int(paper_choice)
                    if 1 <= idx <= len(paper_options):
                        new_paper = paper_options[idx-1]
                    elif idx == 0:
                        new_paper = row['paper']  # keep existing
                    else:
                        print_colored("[!] Invalid choice.", COLORS.RED)
                        continue
                else:
                    new_paper = input(color_text(f"Paper (or press Enter to keep '{row['paper'] if row['paper'] else 'none'}'): ", COLORS.MAGENTA)).strip()
                    if new_paper and new_paper not in ('pretest', 'paper_i', 'paper_ii', 'paper_iii'):
                        print_colored("[!] Invalid paper. Must be pretest, paper_i, paper_ii, or paper_iii.", COLORS.RED)
                        continue

                # Now update
                if new_paper:
                    conn = get_connection()
                    cursor = conn.cursor()
                    cursor.execute(f"UPDATE {TABLE_NAME} SET paper = %s WHERE id = %s", (new_paper, row['id']))
                    conn.commit()
                    cursor.close()
                    conn.close()
                    print_colored("[✓] Paper updated.", COLORS.GREEN)

                    if new_paper != row['paper']:
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
                    conn = get_connection()
                    cursor = conn.cursor()
                    cursor.execute(f"UPDATE {TABLE_NAME} SET paper = NULL WHERE id = %s", (row['id'],))
                    conn.commit()
                    cursor.close()
                    conn.close()
                    print_colored("[✓] Paper cleared.", COLORS.GREEN)
                # After paper update, we may also want to rebuild original_filename? Paper does not affect original_filename, so skip.
                continue

            # --- For other fields, get new value ---
            new_value = input(color_text(f"New value for {field}: ", COLORS.MAGENTA)).strip()

            # --- Handle special fields ---
            if field == 'video_id':
                if not extract_video_id(new_value):
                    print_colored("[!] Invalid ID.", COLORS.RED)
                    continue
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute(f"SELECT id FROM {TABLE_NAME} WHERE video_id = %s AND id != %s", (new_value, row['id']))
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
                                   (new_value, new_title, row['id']))
                else:
                    cursor.execute(f"UPDATE {TABLE_NAME} SET video_id = %s WHERE id = %s", (new_value, row['id']))
                conn.commit()
                cursor.close()
                conn.close()
                video_id = new_value
                print_colored("[✓] Video ID updated.", COLORS.GREEN)
                # Video ID doesn't affect original_filename, skip rebuild
                continue

            elif field == 'syllabus_id':
                if new_value:
                    new_value = normalize_syllabus_id(new_value)
                conn = get_connection()
                cursor = conn.cursor()
                try:
                    cursor.execute(f"UPDATE {TABLE_NAME} SET syllabus_id = %s WHERE id = %s", (new_value, row['id']))
                    conn.commit()
                    cursor.close()
                    conn.close()
                    print_colored("[✓] Syllabus ID updated.", COLORS.GREEN)
                    # ----- AUTO-REGENERATE original_filename -----
                    # Re-fetch updated record
                    conn2 = get_connection()
                    cur2 = conn2.cursor(dictionary=True)
                    cur2.execute(f"SELECT * FROM {TABLE_NAME} WHERE id = %s", (row['id'],))
                    updated_row = cur2.fetchone()
                    cur2.close()
                    conn2.close()
                    if updated_row:
                        new_original = build_original_filename(updated_row)
                        if new_original:
                            conn3 = get_connection()
                            cur3 = conn3.cursor()
                            cur3.execute(f"UPDATE {TABLE_NAME} SET original_filename = %s WHERE id = %s", (new_original, row['id']))
                            conn3.commit()
                            cur3.close()
                            conn3.close()
                            print_colored(f"[✓] Original filename auto-regenerated to: {new_original}", COLORS.GREEN)
                except mysql.connector.Error as e:
                    conn.rollback()
                    cursor.close()
                    conn.close()
                    print_colored(f"[!] Update failed: {e}", COLORS.RED)
                continue

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
                    """, (new_value, new_value, row['id']))
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
                    cursor.execute(f"UPDATE {TABLE_NAME} SET mirror_video_id = %s WHERE id = %s", (new_value, row['id']))
                    conn.commit()
                    cursor.close()
                    conn.close()
                    print_colored("[✓] Mirror ID updated.", COLORS.GREEN)
                    # Mirror ID doesn't affect original_filename, skip rebuild
                except mysql.connector.IntegrityError as e:
                    conn.rollback()
                    cursor.close()
                    conn.close()
                    if "Duplicate entry" in str(e) and "mirror_video_id" in str(e):
                        print_colored("[!] Mirror ID is already used by another record. Update failed.", COLORS.RED)
                    else:
                        print_colored(f"[!] Database error: {e}", COLORS.RED)
                continue

            elif field == 'notes':
                if not new_value:
                    new_value = None
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute(f"UPDATE {TABLE_NAME} SET notes = %s WHERE id = %s", (new_value, row['id']))
                conn.commit()
                cursor.close()
                conn.close()
                print_colored("[✓] Notes updated.", COLORS.GREEN)
                # Notes don't affect original_filename, skip rebuild
                continue

            else:
                # Generic update for subject, chapter, lecturer, nepali_date, time
                conn = get_connection()
                cursor = conn.cursor()
                try:
                    cursor.execute(f"UPDATE {TABLE_NAME} SET {field} = %s WHERE id = %s", (new_value, row['id']))
                    conn.commit()
                    cursor.close()
                    conn.close()
                    print_colored(f"[✓] {field.capitalize()} updated.", COLORS.GREEN)

                    # ----- AUTO-REGENERATE original_filename -----
                    # Re-fetch updated record
                    conn2 = get_connection()
                    cur2 = conn2.cursor(dictionary=True)
                    cur2.execute(f"SELECT * FROM {TABLE_NAME} WHERE id = %s", (row['id'],))
                    updated_row = cur2.fetchone()
                    cur2.close()
                    conn2.close()
                    if updated_row:
                        new_original = build_original_filename(updated_row)
                        if new_original:
                            conn3 = get_connection()
                            cur3 = conn3.cursor()
                            cur3.execute(f"UPDATE {TABLE_NAME} SET original_filename = %s WHERE id = %s", (new_original, row['id']))
                            conn3.commit()
                            cur3.close()
                            conn3.close()
                            print_colored(f"[✓] Original filename auto-regenerated to: {new_original}", COLORS.GREEN)

                except mysql.connector.Error as e:
                    conn.rollback()
                    cursor.close()
                    conn.close()
                    print_colored(f"[!] Update failed: {e}", COLORS.RED)
                continue

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
    identifier = input(color_text("Enter video ID, mirror ID, Facebook ID, or URL: ", COLORS.MAGENTA)).strip()
    if not identifier:
        return

    # Try to get any media record (YouTube or Facebook)
    record = get_any_media_record(identifier)
    if not record:
        print_colored("[!] No record found for that identifier.", COLORS.RED)
        return

    if record.get('source') == 'youtube':
        vid_to_dl = extract_video_id(identifier) or record.get('video_id')
        if not vid_to_dl:
            print_colored("[!] Invalid video ID.", COLORS.RED)
            return
        download_video(record, video_id_to_download=vid_to_dl)

    elif record.get('source') == 'facebook':
        print_colored(f"[i] Re-downloading Facebook {record.get('type')}: {record.get('title', '')}", COLORS.BLUE)
        from .facebook_manager import re_download_facebook_entry
        re_download_facebook_entry(record)

    else:
        print_colored("[!] Unknown source type.", COLORS.RED)

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
