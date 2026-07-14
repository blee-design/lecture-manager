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

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly"
]
TOKEN_PICKLE = "youtube_token.pickle"
CLIENT_SECRETS = "client_secrets.json"

def _get_authenticated_service(force=False):
    credentials = None
    if not force and os.path.exists(TOKEN_PICKLE):
        with open(TOKEN_PICKLE, "rb") as token:
            credentials = pickle.load(token)

    if force or not credentials or not credentials.valid:
        if os.path.exists(CLIENT_SECRETS):
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS, SCOPES)
            credentials = flow.run_local_server(port=0)
            with open(TOKEN_PICKLE, "wb") as token:
                pickle.dump(credentials, token)
        else:
            print_colored(f"[!] {CLIENT_SECRETS} not found. Please download OAuth credentials from Google Cloud Console.", COLORS.RED)
            return None

    return build("youtube", "v3", credentials=credentials)

def extract_syllabus_from_title(title):
    """Extract syllabus ID from video title using pattern matching."""
    pattern = r'\b(\d{1,2}\.\d{1,2}\.\d{1,2}(?:-\d+)?)\b'
    match = re.search(pattern, title)
    if match:
        return match.group(1)
    return None

def scan_and_match_youtube_videos(interactive=True):
    """Smart match with date-aware scoring."""
    youtube = _get_authenticated_service(force=False)
    if not youtube:
        print_colored("[!] Authentication failed.", COLORS.RED)
        return

    print_colored("[i] Fetching videos from your YouTube channel...", COLORS.BLUE)
    videos = []
    next_page_token = None
    while True:
        request = youtube.search().list(
            part="snippet",
            forMine=True,
            type="video",
            maxResults=50,
            pageToken=next_page_token
        )
        response = request.execute()
        for item in response.get('items', []):
            title = item['snippet']['title']
            syllabus = extract_syllabus_from_title(title)
            # Extract date from title (pattern: 2083-02-29 or 2083-02-29)
            date_match = re.search(r'(\d{4}-\d{2}-\d{2})', title)
            date = date_match.group(1) if date_match else None
            videos.append({
                'id': item['id']['videoId'],
                'title': title,
                'description': item['snippet']['description'],
                'publishedAt': item['snippet']['publishedAt'],
                'syllabus': syllabus,
                'date': date
            })
        next_page_token = response.get('nextPageToken')
        if not next_page_token:
            break

    print_colored(f"[i] Found {len(videos)} videos in your channel.", COLORS.BLUE)

    # Build index by syllabus
    videos_by_syllabus = {}
    for vid in videos:
        if vid['syllabus']:
            videos_by_syllabus.setdefault(vid['syllabus'], []).append(vid)

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

    # First pass: exact syllabus match
    for rec in records:
        syllabus = rec.get('syllabus_id', '').strip()
        if not syllabus:
            continue

        if syllabus in videos_by_syllabus:
            # Find the best match by date
            best_vid = None
            best_score = 0
            rec_date = rec.get('nepali_date', '').strip()

            for vid in videos_by_syllabus[syllabus]:
                score = 10  # base score for syllabus match
                # Date match bonus
                if rec_date and vid.get('date') == rec_date:
                    score += 20  # exact date match!
                elif rec_date and vid.get('date') and rec_date in vid.get('date', ''):
                    score += 10  # partial date match
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

    print_colored(f"\n✅ Auto-matched {auto_matched} records by syllabus ID + date.", COLORS.GREEN)

    # Second pass: manual review with ranked candidates (date-aware)
    if manual_review and interactive:
        print_colored(f"\n[i] {len(manual_review)} records need manual review.", COLORS.YELLOW)
        print_colored("[i] Candidates are scored by: syllabus ID (10pts), date match (20pts), subject (5pts), lecturer (3pts).\n", COLORS.BLUE)

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
                if syllabus and syllabus in vid['title']:
                    score += 10
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
                # Final confirmation with comparison
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

def display_comparison(db_record, youtube_video):
    """Display a rich comparison between DB record and YouTube video."""
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

    matches = []
    if db_syllabus and db_syllabus in youtube_video['title']:
        matches.append(f"✅ Syllabus ID '{db_syllabus}' found in title")
    elif db_syllabus:
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

def upload_video_to_youtube(record, title=None, description=None, privacy_status="private"):
    """Upload a video, but first check if already on YouTube and ask for confirmation."""

    youtube = _get_authenticated_service()
    if not youtube:
        return False, "Authentication failed.", None

    # ---- Step 1: Check if video already exists on YouTube ----
    syllabus = record.get('syllabus_id', '').strip()
    if syllabus:
        print_colored(f"\n[i] Searching YouTube for existing video with syllabus ID: {syllabus}", COLORS.BLUE)
        request = youtube.search().list(
            part="snippet",
            forMine=True,
            type="video",
            q=syllabus,
            maxResults=10,
            order="date"
        )
        response = request.execute()
        found_videos = []
        for item in response.get('items', []):
            title = item['snippet']['title']
            if syllabus in title:
                found_videos.append({
                    'id': item['id']['videoId'],
                    'title': item['snippet']['title'],
                    'description': item['snippet']['description'],
                    'publishedAt': item['snippet']['publishedAt']
                })

        if found_videos:
            print_colored(f"\n[i] Found {len(found_videos)} existing video(s) with syllabus ID {syllabus}", COLORS.BLUE)

            for i, vid in enumerate(found_videos, 1):
                print(f"\n  {i}. {vid['title'][:70]}...")
                print(f"     ID: {vid['id']} | Published: {vid['publishedAt'][:10]}")

            print("\n" + "─" * 60)
            print_colored("  OPTIONS:", COLORS.YELLOW, bold=True)
            print("  • Enter number (1-{}) to link to that existing video".format(len(found_videos)))
            print("  • 'n' to upload a NEW video anyway")
            print("  • 's' to SKIP this record")
            print("  • 'v' to VIEW comparison details first")
            print("─" * 60)

            choice = input(color_text("\nYour choice: ", COLORS.MAGENTA)).strip().lower()

            if choice == 's':
                return True, "⏭️ Skipped by user.", None

            if choice == 'v':
                for i, vid in enumerate(found_videos, 1):
                    print(f"\n─── Video #{i} ───")
                    display_comparison(record, vid)
                    confirm = input(color_text(f"\nLink to this video (#{i})? (y/n): ", COLORS.MAGENTA)).strip().lower()
                    if confirm == 'y':
                        vid_to_link = vid
                        break
                else:
                    print_colored("No video selected. Choose a number or 'n' for new upload.", COLORS.YELLOW)
                    choice = input(color_text("Your choice: ", COLORS.MAGENTA)).strip().lower()

            if choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(found_videos):
                    vid_to_link = found_videos[idx]
                    print_colored("\n[i] Final confirmation:", COLORS.BLUE)
                    display_comparison(record, vid_to_link)
                    confirm = input(color_text("\nLink to this video? (y/n): ", COLORS.MAGENTA)).strip().lower()
                    if confirm == 'y':
                        conn = get_connection()
                        cursor = conn.cursor()
                        cursor.execute(f"""
                            UPDATE {TABLE_NAME}
                            SET mirror_video_id = %s, youtube_upload_id = %s, youtube_upload_status = 'uploaded'
                            WHERE video_id = %s
                        """, (vid_to_link['id'], vid_to_link['id'], record['video_id']))
                        conn.commit()
                        cursor.close()
                        conn.close()
                        return True, f"✅ Linked existing video! URL: https://youtu.be/{vid_to_link['id']}", vid_to_link['id']
                    else:
                        print_colored("Cancelled. Uploading new video...", COLORS.YELLOW)

            elif choice == 'n':
                print_colored("Uploading new video...", COLORS.BLUE)
            else:
                print_colored("Invalid choice. Uploading new video...", COLORS.YELLOW)

    # ---- Step 2: Upload new video ----
    file_path = get_file_path_for_record(record)
    if not file_path or not os.path.exists(file_path):
        return False, f"Video file not found: {file_path}", None

    file_size = os.path.getsize(file_path) / (1024 * 1024)
    print_colored(f"[i] Found file: {file_path} ({file_size:.1f} MB)", COLORS.BLUE)

    print("\n" + "─" * 60)
    print_colored("  VIDEO TO UPLOAD", COLORS.CYAN, bold=True)
    print("─" * 60)
    print(f"  Title       : {title or record.get('original_filename') or record.get('video_title')}")
    print(f"  Syllabus    : {record.get('syllabus_id', 'N/A')}")
    print(f"  Subject     : {record.get('subject', 'N/A')}")
    print(f"  Lecturer    : {record.get('lecturer', 'N/A')}")
    print(f"  Privacy     : {privacy_status}")
    print("─" * 60)

    confirm = input(color_text("\nUpload this video? (y/n): ", COLORS.MAGENTA)).strip().lower()
    if confirm != 'y':
        return False, "Upload cancelled by user.", None

    if not title:
        title = record.get('original_filename') or record.get('video_title') or f"Lecture {record['video_id']}"
    if not description:
        description = f"Lecture: {record.get('syllabus_id', '')} - {record.get('subject', '')}\nChapter: {record.get('chapter', '')}\nLecturer: {record.get('lecturer', '')}"

    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "tags": ["lecture", "education", record.get('subject', '')[:30]],
        },
        "status": {
            "privacyStatus": privacy_status,
            "madeForKids": False,
        }
    }

    media = MediaFileUpload(file_path, chunksize=8*1024*1024, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    print_colored(f"[⏳] Uploading...", COLORS.BLUE)

    try:
        response = None
        if HAS_TQDM:
            with tqdm(total=file_size, unit='MB', desc="Uploading") as pbar:
                while response is None:
                    status, response = request.next_chunk()
                    if status:
                        uploaded = status.resumable_progress / (1024 * 1024)
                        pbar.update(uploaded - pbar.n)
        else:
            sys.stdout.write("  Uploading")
            sys.stdout.flush()
            while response is None:
                status, response = request.next_chunk()
                if status:
                    sys.stdout.write(".")
                    sys.stdout.flush()
            print()

        video_id = response['id']

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
