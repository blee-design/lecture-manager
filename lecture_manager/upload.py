# File upload.py

import os
import pickle
import sys
import re
from datetime import datetime
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from .db import get_connection, TABLE_NAME
from .utils import print_colored, COLORS, get_file_path_for_record, color_text

try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False
    print_colored("[i] Install 'tqdm' for a better progress bar: pip install tqdm", COLORS.YELLOW)

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly"
]
TOKEN_PICKLE = "youtube_token.pickle"
CLIENT_SECRETS = "client_secrets.json"

def normalize_syllabus_for_matching(syllabus):
    """
    Remove leading zeros from each dot-separated part.
    Example: '09.02.12-2' -> '9.2.12-2'
    Also handles cases without suffix.
    """
    if not syllabus:
        return syllabus
    parts = syllabus.split('.')
    normalized_parts = []
    suffix = ''
    for part in parts:
        if '-' in part:
            main, dash = part.split('-', 1)
            main_stripped = main.lstrip('0') or '0'
            normalized_parts.append(main_stripped)
            suffix = '-' + dash
        else:
            main_stripped = part.lstrip('0') or '0'
            normalized_parts.append(main_stripped)
    return '.'.join(normalized_parts) + suffix

# ---------- Database helpers for OAuth credentials ----------
def _get_oauth_from_db():
    """Retrieve token_data and client_secrets from DB."""
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT token_data, client_secrets FROM oauth_credentials WHERE id = 1")
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        if row:
            return row['token_data'], row['client_secrets']
    except Exception as e:
        print_colored(f"[!] Failed to read OAuth credentials from DB: {e}", COLORS.RED)
    return None, None

def _save_oauth_to_db(token_data, client_secrets=None):
    """Save token_data and optionally client_secrets to DB."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        if client_secrets is not None:
            cursor.execute("""
                REPLACE INTO oauth_credentials (id, token_data, client_secrets, last_refresh)
                VALUES (1, %s, %s, NOW())
            """, (token_data, client_secrets))
        else:
            cursor.execute("""
                REPLACE INTO oauth_credentials (id, token_data, last_refresh)
                VALUES (1, %s, NOW())
            """, (token_data,))
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        print_colored(f"[!] Failed to save OAuth credentials to DB: {e}", COLORS.RED)
        return False

# ---------- OAuth service ----------
def _get_authenticated_service(force=False):
    """
    Get authenticated YouTube service.
    Tries local token file, then DB, then runs OAuth flow.
    Always saves to DB after loading/creating.
    """
    credentials = None
    token_loaded_from = None

    # Ensure client_secrets.json exists (same as before)
    if not os.path.exists(CLIENT_SECRETS):
        # ... (keep your existing code to restore from DB) ...
        pass

    # -------- Load token from local file --------
    if not force and os.path.exists(TOKEN_PICKLE):
        try:
            with open(TOKEN_PICKLE, "rb") as token:
                credentials = pickle.load(token)
            token_loaded_from = "local file"
            print_colored("[i] Loaded token from local file.", COLORS.BLUE)
        except Exception as e:
            print_colored(f"[i] Failed to load local token: {e}", COLORS.YELLOW)

    # -------- If no valid credentials, try DB --------
    if not force and (not credentials or not credentials.valid):
        token_data_from_db, _ = _get_oauth_from_db()
        if token_data_from_db:
            try:
                credentials = pickle.loads(token_data_from_db)
                token_loaded_from = "database"
                print_colored("[i] Loaded token from database.", COLORS.BLUE)
                # Write to local file for next time
                with open(TOKEN_PICKLE, "wb") as token:
                    pickle.dump(credentials, token)
            except Exception as e:
                print_colored(f"[i] Failed to load token from DB: {e}", COLORS.YELLOW)

    # -------- Auto‑refresh if expired --------
    if credentials and not credentials.valid and credentials.refresh_token:
        try:
            from google.auth.transport.requests import Request
            print_colored("[i] Token expired – refreshing automatically...", COLORS.BLUE)
            credentials.refresh(Request())
            token_loaded_from = "refreshed"
            # Save refreshed token to file and DB
            with open(TOKEN_PICKLE, "wb") as token:
                pickle.dump(credentials, token)
            token_data = pickle.dumps(credentials)
            secrets_content = None
            if os.path.exists(CLIENT_SECRETS):
                with open(CLIENT_SECRETS, 'r') as f:
                    secrets_content = f.read()
            _save_oauth_to_db(token_data, secrets_content)
            print_colored("[✓] Token refreshed and saved.", COLORS.GREEN)
        except Exception as e:
            print_colored(f"[i] Refresh failed: {e}", COLORS.YELLOW)
            credentials = None   # fall back to OAuth flow

    # -------- If still no valid credentials, run OAuth flow --------
    if force or not credentials or not credentials.valid:
        print_colored("[i] Running OAuth flow... (browser will open)", COLORS.BLUE)
        flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS, SCOPES)
        # Ensure offline access to get a refresh token
        flow.oauth2session.scope = SCOPES
        credentials = flow.run_local_server(port=0)
        token_loaded_from = "OAuth flow"
        # Save to local file
        with open(TOKEN_PICKLE, "wb") as token:
            pickle.dump(credentials, token)
        print_colored(f"[✓] Token saved to {TOKEN_PICKLE}", COLORS.GREEN)

    # -------- Always save to database --------
    if credentials and credentials.valid:
        token_data = pickle.dumps(credentials)
        secrets_content = None
        if os.path.exists(CLIENT_SECRETS):
            with open(CLIENT_SECRETS, 'r') as f:
                secrets_content = f.read()
        if token_loaded_from != "database":
            _save_oauth_to_db(token_data, secrets_content)
            print_colored("[✓] Token saved to database.", COLORS.GREEN)
        else:
            if secrets_content:
                _save_oauth_to_db(token_data, secrets_content)

    return build("youtube", "v3", credentials=credentials)

def extract_syllabus_from_title(title):
    pattern = r'\b(\d{1,2}\.\d{1,2}\.\d{1,2}(?:-\d+)?)\b'
    match = re.search(pattern, title)
    if match:
        return match.group(1)
    return None

def display_comparison(db_record, youtube_video):
    print("\n" + "═" * 70)
    print_colored("  COMPARISON: Database Record vs YouTube Video", COLORS.CYAN, bold=True)
    print("═" * 70)

    print(f"\n{color_text('📚 DATABASE RECORD:', COLORS.BLUE, bold=True)}")
    print(f"  Syllabus ID : {db_record.get('syllabus_id', 'N/A')}")
    print(f"  Subject     : {db_record.get('subject', 'N/A')}")
    print(f"  Chapter     : {db_record.get('chapter', 'N/A')[:50]}...")
    print(f"  Lecturer    : {db_record.get('lecturer', 'N/A')}")
    print(f"  Date        : {db_record.get('nepali_date', 'N/A')} {db_record.get('time', '')}")
    print(f"  Video ID    : {db_record.get('video_id', 'N/A')}")

    print(f"\n{color_text('▶️  YOUTUBE VIDEO:', COLORS.GREEN, bold=True)}")
    print(f"  Video ID    : {youtube_video['id']}")
    print(f"  Title       : {youtube_video['title'][:80]}...")
    print(f"  Published   : {youtube_video.get('publishedAt', 'N/A')}")
    print(f"  URL         : https://youtu.be/{youtube_video['id']}")

    print("\n" + "─" * 70)
    print_colored("  MATCH ANALYSIS", COLORS.YELLOW, bold=True)
    print("─" * 70)

    db_syllabus = db_record.get('syllabus_id', '')
    db_subject = db_record.get('subject', '')
    db_chapter = db_record.get('chapter', '')
    video_title = youtube_video['title'].lower()
    video_syllabus = extract_syllabus_from_title(youtube_video['title']) or ''

    matches = []

    # ---- Flexible syllabus match ----
    if db_syllabus:
        if db_syllabus in youtube_video['title']:
            matches.append(f"✅ Syllabus ID '{db_syllabus}' found in title")
        elif normalize_syllabus_for_matching(db_syllabus) == normalize_syllabus_for_matching(video_syllabus):
            matches.append(f"✅ Syllabus ID '{db_syllabus}' matches (normalized) in title")
        else:
            matches.append(f"⚠️  Syllabus ID '{db_syllabus}' NOT found in title")

    if db_subject and db_subject.lower() in video_title:
        matches.append(f"✅ Subject '{db_subject}' found in title")
    elif db_subject:
        matches.append(f"⚠️  Subject '{db_subject}' NOT found in title")

    if db_chapter and db_chapter.lower() in video_title:
        matches.append(f"✅ Chapter found in title")
    elif db_chapter:
        matches.append(f"⚠️  Chapter NOT found in title")

    for match in matches:
        print(f"  {match}")

    score = sum(10 for m in matches if m.startswith('✅'))
    print(f"\n  {color_text(f'Match Score: {score}/30', COLORS.CYAN, bold=True)}")

    if score >= 20:
        print_colored("  → High confidence match (likely correct)", COLORS.GREEN)
    elif score >= 10:
        print_colored("  → Medium confidence match (check carefully)", COLORS.YELLOW)
    else:
        print_colored("  → Low confidence match (probably wrong)", COLORS.RED)

def scan_and_match_youtube_videos(interactive=True):
    youtube = _get_authenticated_service(force=False)
    if not youtube:
        print_colored("[!] Authentication failed.", COLORS.RED)
        return

    print_colored("[i] Fetching your uploaded videos via playlist...", COLORS.BLUE)

    # 1. Get the "uploads" playlist ID for the authenticated user
    channels_response = youtube.channels().list(
        part="contentDetails",
        mine=True
    ).execute()
    try:
        uploads_playlist_id = channels_response['items'][0]['contentDetails']['relatedPlaylists']['uploads']
    except (KeyError, IndexError):
        print_colored("[!] Could not retrieve uploads playlist ID.", COLORS.RED)
        return

    # 2. List all videos in that playlist (max 50 per page, but you can increase)
    videos = []
    next_page_token = None
    while True:
        request = youtube.playlistItems().list(
            part="snippet",
            playlistId=uploads_playlist_id,
            maxResults=50,
            pageToken=next_page_token
        )
        response = request.execute()
        for item in response.get('items', []):
            snippet = item['snippet']
            title = snippet['title']
            video_id = snippet['resourceId']['videoId']
            published_at = snippet['publishedAt']
            # Extract syllabus and date using your existing helper functions
            syllabus = extract_syllabus_from_title(title)
            date_match = re.search(r'(\d{4}-\d{2}-\d{2})', title)
            date = date_match.group(1) if date_match else None

            videos.append({
                'id': video_id,
                'title': title,
                'description': snippet.get('description', ''),
                'publishedAt': published_at,
                'syllabus': syllabus,
                'date': date
            })
        next_page_token = response.get('nextPageToken')
        if not next_page_token:
            break

    print_colored(f"[i] Found {len(videos)} videos in your channel.", COLORS.BLUE)

    # Build an index by normalized syllabus (and also original for display)
    videos_by_norm_syllabus = {}
    for vid in videos:
        if vid['syllabus']:
            norm = normalize_syllabus_for_matching(vid['syllabus'])
            videos_by_norm_syllabus.setdefault(norm, []).append(vid)

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(f"SELECT * FROM {TABLE_NAME} WHERE mirror_video_id IS NULL OR mirror_video_id = ''")
    records = cursor.fetchall()
    cursor.close()
    conn.close()

    if not records:
        print_colored("[i] No records without a mirror ID. All linked!", COLORS.GREEN)
        return

    print_colored(f"[i] Found {len(records)} records without a mirror ID.", COLORS.BLUE)

    auto_matched = 0
    manual_review = []

    # First pass: exact or normalized syllabus match + date
    for rec in records:
        syllabus = rec.get('syllabus_id', '').strip()
        if not syllabus:
            continue

        norm_syll = normalize_syllabus_for_matching(syllabus)
        # Try to find videos with same normalized syllabus
        candidate_vids = videos_by_norm_syllabus.get(norm_syll, [])
        if candidate_vids:
            best_vid = None
            best_score = 0
            rec_date = rec.get('nepali_date', '').strip()
            for vid in candidate_vids:
                score = 10  # base for normalized syllabus match
                # Date bonus
                if rec_date and vid.get('date') == rec_date:
                    score += 20
                elif rec_date and vid.get('date') and rec_date in vid.get('date', ''):
                    score += 10
                if score > best_score:
                    best_score = score
                    best_vid = vid

            if best_vid:
                vid_id = best_vid['id']
                # Check if already used as mirror
                conn = get_connection()
                cursor = conn.cursor(dictionary=True)
                cursor.execute("""
                    SELECT id FROM youtube_lectures
                    WHERE mirror_video_id = %s AND video_id != %s
                """, (vid_id, rec['video_id']))
                existing = cursor.fetchone()
                cursor.close()
                conn.close()

                if existing:
                    print_colored(f"  ⚠️ Skipping {syllabus} → {vid_id} (already used by another record)", COLORS.YELLOW)
                    continue

                print_colored(f"  ✅ Auto-matched: {syllabus} → {vid_id} (date: {best_vid.get('date', 'unknown')})", COLORS.GREEN)
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute(f"""
                    UPDATE {TABLE_NAME}
                    SET mirror_video_id = %s, youtube_upload_id = %s, youtube_upload_status = 'uploaded'
                    WHERE video_id = %s
                """, (vid_id, vid_id, rec['video_id']))
                conn.commit()
                cursor.close()
                conn.close()
                auto_matched += 1
            else:
                manual_review.append(rec)
        else:
            manual_review.append(rec)

    print_colored(f"\n✅ Auto-matched {auto_matched} records by syllabus ID + date (with normalization).", COLORS.GREEN)

    # Second pass: manual review with ranked candidates (date-aware + normalized syllabus)
    if manual_review and interactive:
        print_colored(f"\n[i] {len(manual_review)} records need manual review.", COLORS.YELLOW)
        print_colored("[i] Candidates are scored by: syllabus ID (10pts), date match (20pts), subject (5pts), lecturer (3pts).", COLORS.BLUE)
        print_colored("[i] Syllabus matching is now flexible (leading zeros ignored).\n", COLORS.BLUE)

        for rec in manual_review:
            syllabus = rec.get('syllabus_id', '')
            subject = rec.get('subject', '')
            lecturer = rec.get('lecturer', '')
            chapter = rec.get('chapter', '')
            rec_date = rec.get('nepali_date', '')

            # Score candidates
            scored = []
            for vid in videos:
                title_lower = vid['title'].lower()
                score = 0
                # Check syllabus with normalization
                vid_syll = vid.get('syllabus', '')
                if syllabus:
                    if syllabus in vid['title']:
                        score += 10
                    elif normalize_syllabus_for_matching(syllabus) == normalize_syllabus_for_matching(vid_syll):
                        score += 10  # same as exact match
                # Date match
                if rec_date and vid.get('date') == rec_date:
                    score += 20
                elif rec_date and vid.get('date') and rec_date in vid.get('date', ''):
                    score += 10
                if subject and subject.lower() in title_lower:
                    score += 5
                if lecturer and lecturer.lower() in title_lower:
                    score += 3
                if chapter and chapter.lower() in title_lower:
                    score += 2
                if score > 0:
                    scored.append((score, vid))

            if not scored:
                print_colored(f"\n📌 No candidates found for {syllabus} - {subject}", COLORS.YELLOW)
                continue

            scored.sort(reverse=True, key=lambda x: x[0])
            top_candidates = scored[:5]

            print("\n" + "═" * 70)
            print_colored(f"  RECORD: {syllabus} - {subject}", COLORS.CYAN, bold=True)
            print(f"  Lecturer: {lecturer}")
            print(f"  Chapter : {chapter[:60]}...")
            print(f"  Date    : {rec_date}")
            print("─" * 70)
            print_colored("  TOP CANDIDATES:", COLORS.YELLOW, bold=True)
            for i, (score, vid) in enumerate(top_candidates, 1):
                date_info = f" | Date: {vid.get('date', 'unknown')}"
                print(f"  {i}. Score: {score:2d}  |  {vid['title'][:65]}...{date_info[:20]}")
                print(f"     ID: {vid['id']}  |  Published: {vid['publishedAt'][:10]}")
            print("─" * 70)
            print("  Options: (1-5) to pick, 's' to skip, 'a' to abort all")
            choice = input(color_text("  Your choice: ", COLORS.MAGENTA)).strip().lower()

            if choice == 'a':
                print_colored("Aborting scan.", COLORS.YELLOW)
                break
            if choice == 's':
                continue
            if choice.isdigit() and 1 <= int(choice) <= len(top_candidates):
                idx = int(choice) - 1
                vid = top_candidates[idx][1]
                print_colored("\n[i] Final confirmation:", COLORS.BLUE)
                display_comparison(rec, vid)
                confirm = input(color_text("  Link to this video? (y/n): ", COLORS.MAGENTA)).strip().lower()
                if confirm == 'y':
                    conn = get_connection()
                    cursor = conn.cursor()
                    cursor.execute(f"""
                        UPDATE {TABLE_NAME}
                        SET mirror_video_id = %s, youtube_upload_id = %s, youtube_upload_status = 'uploaded'
                        WHERE video_id = %s
                    """, (vid['id'], vid['id'], rec['video_id']))
                    conn.commit()
                    cursor.close()
                    conn.close()
                    print_colored("  ✅ Updated.", COLORS.GREEN)
                    auto_matched += 1
                else:
                    print_colored("  Skipped.", COLORS.YELLOW)
            else:
                print_colored("Invalid choice. Skipping.", COLORS.YELLOW)

    print_colored(f"\n✅ Total matched: {auto_matched} records.", COLORS.GREEN)

def batch_upload_missing_mirrors(privacy="private", dry_run=False, delay=3):
    """
    Upload all records with empty mirror_video_id.
    """
    from .db import get_connection, TABLE_NAME
    from .utils import print_colored, COLORS, get_file_path_for_record
    import time

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(f"""
        SELECT * FROM {TABLE_NAME}
        WHERE (mirror_video_id IS NULL OR mirror_video_id = '')
          AND (youtube_upload_status IS NULL OR youtube_upload_status != 'uploaded')
        ORDER BY id
    """)
    records = cursor.fetchall()
    cursor.close()
    conn.close()

    if not records:
        print_colored("✅ No records without a mirror ID.", COLORS.GREEN)
        return

    print_colored(f"📌 Found {len(records)} records to process.", COLORS.BLUE)

    if dry_run:
        print("\n🔍 DRY RUN – these records would be processed:")
        for rec in records:
            print(f"  ID: {rec['id']} | Syllabus: {rec['syllabus_id']} | Video: {rec['video_id']}")
        return

    success = 0
    failed = 0
    skipped = 0

    for idx, rec in enumerate(records, 1):
        print(f"\n[{idx}/{len(records)}] Processing {rec['syllabus_id']} (video: {rec['video_id']})")

        file_path = get_file_path_for_record(rec)
        if not file_path or not os.path.exists(file_path):
            print_colored("  ⚠️ File not found – skipping", COLORS.YELLOW)
            skipped += 1
            continue

        print_colored(f"  📁 File: {os.path.basename(file_path)}", COLORS.BLUE)
        print_colored(f"  ⏳ Uploading... (privacy: {privacy})", COLORS.BLUE)

        try:
            # Pass interactive=False to avoid prompts
            success_flag, msg, vid = upload_video_to_youtube(
                rec,
                privacy_status=privacy,
                interactive=False
            )
            if success_flag:
                print_colored(f"  ✅ {msg}", COLORS.GREEN)
                success += 1
            else:
                print_colored(f"  ❌ {msg}", COLORS.RED)
                failed += 1
        except Exception as e:
            print_colored(f"  ❌ Exception: {e}", COLORS.RED)
            failed += 1

        time.sleep(delay)

    print("\n" + "═" * 50)
    print_colored("  BATCH UPLOAD COMPLETE", COLORS.CYAN, bold=True)
    print(f"  ✅ Success: {success}")
    print(f"  ❌ Failed : {failed}")
    print(f"  ⏭️ Skipped: {skipped}")
    print("═" * 50)

def upload_video_to_youtube(record, title=None, description=None, privacy_status="private", interactive=True):
    """Upload a video, check existing, use original_filename as title, rich description."""

    youtube = _get_authenticated_service()
    if not youtube:
        return False, "Authentication failed.", None

    # ---- DEBUG: Print what the record contains ----
    print_colored(f"[DEBUG] original_filename: {record.get('original_filename')}", COLORS.BLUE)
    print_colored(f"[DEBUG] video_title      : {record.get('video_title')}", COLORS.BLUE)

    # ---- Step 2: Prepare metadata ----
    # ---- FORCE USE original_filename as title ----
    if record.get('original_filename'):
        title = record['original_filename']
        print_colored(f"[i] Using original_filename as title: {title[:80]}...", COLORS.BLUE)
    else:
        title = record.get('video_title') or f"Lecture {record['video_id']}"
        print_colored(f"[i] original_filename missing, using video_title: {title[:80]}...", COLORS.YELLOW)

    # Build rich description
    if not description:
        description_lines = [
            f"Syllabus ID  : {record.get('syllabus_id', 'N/A')}",
            f"Subject      : {record.get('subject', 'N/A')}",
            f"Chapter      : {record.get('chapter', 'N/A')}",
            f"Lecturer     : {record.get('lecturer', 'N/A')}",
            f"Nepali Date  : {record.get('nepali_date', 'N/A')}",
            f"Time         : {record.get('time', 'N/A')}",
            f"Video Title  : {record.get('video_title', 'N/A')}",
            "",
            "📚 Uploaded via Lecture Manager",
            f"🔗 Original Video ID: {record.get('video_id', 'N/A')}",
        ]
        description = "\n".join(description_lines)

    # ---- Step 3: Check file and upload ----
    file_path = get_file_path_for_record(record)
    if not file_path or not os.path.exists(file_path):
        return False, f"Video file not found: {file_path}", None

    file_size = os.path.getsize(file_path) / (1024 * 1024)
    print_colored(f"[i] Found file: {file_path} ({file_size:.1f} MB)", COLORS.BLUE)

    print("\n" + "─" * 60)
    print_colored("  VIDEO TO UPLOAD", COLORS.CYAN, bold=True)
    print("─" * 60)
    print(f"  Title       : {title[:100]}")
    print(f"  Syllabus    : {record.get('syllabus_id', 'N/A')}")
    print(f"  Subject     : {record.get('subject', 'N/A')}")
    print(f"  Lecturer    : {record.get('lecturer', 'N/A')}")
    print(f"  Privacy     : {privacy_status}")
    print(f"  Made for Kids: False")
    print("─" * 60)

    confirm = input(color_text("\nUpload this video? (y/n): ", COLORS.MAGENTA)).strip().lower()
    if confirm != 'y':
        return False, "Upload cancelled by user.", None

    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "tags": ["lecture", "education", record.get('subject', '')[:30]],
        },
        "status": {
            "privacyStatus": privacy_status,
            "madeForKids": False,
            "selfDeclaredMadeForKids": False,
        }
    }

    media = MediaFileUpload(file_path, chunksize=4*1024*1024, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    print_colored(f"[⏳] Uploading with privacy = {privacy_status}...", COLORS.BLUE)

    try:
        response = None
        if HAS_TQDM:
            with tqdm(total=file_size, unit='MB', desc="Uploading", unit_scale=True, leave=True) as pbar:
                while response is None:
                    status, response = request.next_chunk()
                    if status:
                        uploaded = status.resumable_progress / (1024 * 1024)
                        pbar.update(uploaded - pbar.n)
            print()
        else:
            sys.stdout.write("  Uploading")
            sys.stdout.flush()
            last_percent = 0
            while response is None:
                status, response = request.next_chunk()
                if status:
                    percent = int(status.resumable_progress / file_size * 100)
                    if percent > last_percent:
                        sys.stdout.write(f" {percent}%")
                        sys.stdout.flush()
                        last_percent = percent
            print()

        video_id = response['id']

        # Update DB – keep existing mirror if present, else set new
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT mirror_video_id FROM youtube_lectures WHERE video_id = %s", (record['video_id'],))
        row = cursor.fetchone()
        existing_mirror = row['mirror_video_id'] if row else None

        if existing_mirror:
            cursor.execute("""
                UPDATE youtube_lectures
                SET youtube_upload_id = %s, youtube_upload_status = 'uploaded'
                WHERE video_id = %s
            """, (video_id, record['video_id']))
            print_colored(f"[i] Kept existing mirror ID: {existing_mirror}", COLORS.BLUE)
        else:
            cursor.execute("""
                UPDATE youtube_lectures
                SET mirror_video_id = %s, youtube_upload_id = %s, youtube_upload_status = 'uploaded'
                WHERE video_id = %s
            """, (video_id, video_id, record['video_id']))
            print_colored(f"[i] Set mirror ID to: {video_id}", COLORS.GREEN)

        conn.commit()
        cursor.close()
        conn.close()

        return True, f"✅ Uploaded! URL: https://youtu.be/{video_id}", video_id

    except Exception as e:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE youtube_lectures SET youtube_upload_status = 'failed' WHERE video_id = %s", (record['video_id'],))
        conn.commit()
        cursor.close()
        conn.close()
        return False, f"❌ Upload failed: {e}", None
