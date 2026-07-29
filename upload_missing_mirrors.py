# upload_missing_mirrors.py

#!/usr/bin/env python3
"""
Standalone script to upload YouTube videos for records that lack a mirror ID.
Run once, then delete.
"""

import os
import sys
import time
import argparse
import builtins

# 👇 CHANGE THIS to your actual project path
PROJECT_ROOT = "/home/udaya/projects/lecture-manager"
sys.path.insert(0, PROJECT_ROOT)

from lecture_manager.db import get_connection, TABLE_NAME
from lecture_manager.upload import upload_video_to_youtube
from lecture_manager.utils import print_colored, COLORS, get_file_path_for_record

def batch_upload_missing_mirrors(privacy="unlisted", dry_run=False, delay=3):
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

    # 🧠 Monkey‑patch `input()` to auto‑confirm everything
    original_input = builtins.input
    builtins.input = lambda prompt: 'y'

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
            success_flag, msg, vid = upload_video_to_youtube(rec, privacy_status=privacy)
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

    # Restore original input
    builtins.input = original_input

    print("\n" + "═" * 50)
    print_colored("  BATCH UPLOAD COMPLETE", COLORS.CYAN, bold=True)
    print(f"  ✅ Success: {success}")
    print(f"  ❌ Failed : {failed}")
    print(f"  ⏭️ Skipped: {skipped}")
    print("═" * 50)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--privacy", default="unlisted",
                        choices=["private", "unlisted", "public"],
                        help="YouTube privacy setting")
    parser.add_argument("--dry-run", action="store_true",
                        help="Only list records, no upload")
    parser.add_argument("--delay", type=int, default=3,
                        help="Seconds delay between uploads")
    args = parser.parse_args()
    batch_upload_missing_mirrors(privacy=args.privacy, dry_run=args.dry_run, delay=args.delay)
