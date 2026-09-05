from datetime import datetime
from .config import load_or_create_config, edit_config
from .db import create_table, migrate_table, ensure_subjects_populated
from .crud import (
    add_lecture, view_all, view_one, update_lecture, delete_lecture,
    download_existing, show_embed_link, refresh_titles, search_all
)
from .dashboard import show_dashboard
from .export import export_csv, export_json, import_csv, import_json
from .file_manager import (
    move_video_interactive,
    delete_video_to_trash, restore_from_trash, empty_trash,
    tally_db_with_files, scan_duplicates, resolve_duplicates,
    backfill_hashes, play_video,
    backfill_hash_naming, show_paper_breakdown
)
from .web import run_web_server
from .utils import print_colored, color_text, COLORS
from .youtube import refresh_cookies
from .facebook import download_facebook
from .facebook_manager import facebook_menu
from .upload import scan_and_match_youtube_videos, batch_upload_missing_mirrors
from .question_bank import unified_question_menu
from .instapaper import instapaper_menu
from .question_converter import create_tables, import_from_file, get_questions, delete_question, export_to_file, run_conversion
from .question_converter.exceptions import ConverterError

#==============================================================================
# Toggle for Flask debug mode True/False
WEB_DEBUG = False
#==============================================================================

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

def export_import_submenu():
    """Sub‑menu for all import/export operations (main menu)."""
    while True:
        print("\n" + "═" * 50)
        print_colored("  EXPORT / IMPORT", COLORS.CYAN, bold=True)
        print("═" * 50)
        print("  1. Export to CSV")
        print("  2. Export to JSON")
        print("  3. Import from CSV")
        print("  4. Import from JSON")
        print("  0. Return to main menu")
        print("═" * 50)

        choice = input(color_text("Choose an option (0-4): ", COLORS.MAGENTA)).strip()

        if choice == '1':
            from .export import export_csv
            export_csv()
        elif choice == '2':
            from .export import export_json
            export_json()
        elif choice == '3':
            from .export import import_csv
            import_csv()
        elif choice == '4':
            from .export import import_json
            import_json()
        elif choice == '0':
            print_colored("Returning to main menu.", COLORS.YELLOW)
            break
        else:
            print_colored("[!] Invalid option.", COLORS.RED)

        input("\nPress Enter to continue...")

def main():
    load_or_create_config()
    create_table()
    migrate_table()
    ensure_subjects_populated()
    from .question_converter import create_tables
    create_tables()

    # ----- Helper wrappers (must be defined before menus) -----
    def upload_single_video():
        identifier = input(color_text("Enter Video ID, Syllabus ID, or mirror ID: ", COLORS.MAGENTA)).strip()
        if not identifier:
            return
        from .db import get_record_by_any_id
        record = get_record_by_any_id(identifier)
        if not record:
            print_colored("[!] Record not found.", COLORS.RED)
        else:
            from .upload import upload_video_to_youtube
            print_colored(f"[i] Uploading video for record {record['video_id']} ...", COLORS.BLUE)
            success, msg, vid = upload_video_to_youtube(record)
            if success:
                print_colored(f"[✓] {msg}", COLORS.GREEN)
            else:
                print_colored(f"[!] {msg}", COLORS.RED)

    def sync_oauth_token():
        print_colored("[i] Syncing YouTube OAuth token to database...", COLORS.BLUE)
        import pickle
        from .upload import _save_oauth_to_db
        try:
            with open('youtube_token.pickle', 'rb') as f:
                token_data = pickle.load(f)
            with open('client_secrets.json', 'r') as f:
                secrets = f.read()
            _save_oauth_to_db(pickle.dumps(token_data), secrets)
            print_colored("[✓] Token and client secrets saved to database.", COLORS.GREEN)
        except FileNotFoundError as e:
            print_colored(f"[!] File not found: {e}. Please run option 28 first to generate the token.", COLORS.YELLOW)
        except Exception as e:
            print_colored(f"[!] Sync failed: {e}", COLORS.RED)

    def refresh_youtube_token_wrapper():
        from .upload import refresh_youtube_token
        refresh_youtube_token()

    def batch_update_youtube_titles(force=False):
        from .upload import update_youtube_title, QuotaExceededError
        from .db import get_connection
        import time

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        # If force=True, include all videos with youtube_upload_id; else only those not yet updated
        if force:
            cursor.execute("""
                SELECT id, youtube_upload_id, subject, lecturer, nepali_date, time
                FROM youtube_lectures
                WHERE youtube_upload_id IS NOT NULL
            """)
        else:
            cursor.execute("""
                SELECT id, youtube_upload_id, subject, lecturer, nepali_date, time
                FROM youtube_lectures
                WHERE youtube_upload_id IS NOT NULL
                AND (youtube_title_updated IS NULL OR youtube_title_updated = 0)
            """)
        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        if not rows:
            print_colored("✅ No videos to update.", COLORS.GREEN)
            return

        total = len(rows)
        print_colored(f"📌 Found {total} videos to process.", COLORS.BLUE)

        success = 0
        skipped = 0
        failed = 0
        quota_exceeded = False

        for idx, rec in enumerate(rows, 1):
            # Build new title using the YouTube naming strategy (heart separator)
            from .utils import build_youtube_title
            new_title = build_youtube_title(rec)
            if not new_title:
                print_colored(f"[{idx}/{total}] Skipping (no title built)", COLORS.YELLOW)
                skipped += 1
                continue

            # YouTube title limit is 100 characters
            if len(new_title) > 100:
                new_title = new_title[:100]

            print(f"[{idx}/{total}] Updating {rec['youtube_upload_id']} → '{new_title[:60]}...'", end=" ", flush=True)

            # Optional: check current title to avoid unnecessary updates
            # (This would require an extra API call, so we skip it to save quota)
            # But we can still update; if it's already the same, YouTube will return success.

            try:
                ok, msg = update_youtube_title(rec['youtube_upload_id'], new_title)
                if ok:
                    conn2 = get_connection()
                    cur2 = conn2.cursor()
                    cur2.execute("UPDATE youtube_lectures SET youtube_title_updated = 1 WHERE id = %s", (rec['id'],))
                    conn2.commit()
                    cur2.close()
                    conn2.close()
                    print_colored("✅", COLORS.GREEN)
                    success += 1
                else:
                    print_colored(f"❌ {msg}", COLORS.RED)
                    failed += 1
            except QuotaExceededError:
                print_colored("❌ Quota exceeded. Stopping batch. Please run again tomorrow.", COLORS.RED)
                quota_exceeded = True
                break
            except Exception as e:
                print_colored(f"❌ Unexpected error: {e}", COLORS.RED)
                failed += 1

            # Delay to avoid quota burn
            time.sleep(1)

        print_colored(f"\n✅ Updated: {success}, ⏭️ Skipped: {skipped}, ❌ Failed: {failed}", COLORS.CYAN)
        if quota_exceeded:
            print_colored(f"[i] {total - (success + failed + skipped)} videos remain. Run again tomorrow.", COLORS.YELLOW)

    def pomodoro_launcher():
        import subprocess
        import sys
        subprocess.Popen([sys.executable, "-m", "lecture_manager.pomodoro"])
        print_colored("[✓] Pomodoro timer launched in a separate window.", COLORS.GREEN)
        print_colored("[i] You can now continue using the CLI while the timer runs.", COLORS.BLUE)

    # Zoom link extractor
    def zoom_extractor_launcher():
        from .zoom_utils import interactive_zoom_extractor
        interactive_zoom_extractor()

    # ----- Define all sub‑menus with icons -----
    menus = {
        '1': [
            ("➕ Add new lecture", add_lecture),
            ("👁️ View all lectures", view_all),
            ("🔍 View a single lecture", view_one),
            ("✏️ Update a lecture", update_lecture),
            ("🗑️ Delete a lecture", delete_lecture),
            ("🔎 Search lectures", search_all),
        ],
        '2': [
            ("⬇️ Download a video (from existing record)", download_existing),
            ("🔗 Show YouTube embed link", show_embed_link),
            ("🔄 Refresh video titles from YouTube", refresh_titles),
            ("▶️ Play a video (local file)", play_video),
            ("🍪 Refresh YouTube cookies", refresh_cookies),
        ],
        '3': [
            ("📂 Move/rename a video manually", move_video_interactive),
            ("🗑️ Delete a video (move to trash)", delete_video_to_trash),
            ("↩️ Restore from trash", restore_from_trash),
            ("🧹 Empty trash", empty_trash),
            ("📊 Tally database with video files", tally_db_with_files),
            ("🔎 Scan for duplicate video files", scan_duplicates),
            ("✅ Auto-resolve duplicate video files", resolve_duplicates),
            ("🔄 Backfill file hashes (one‑time)", backfill_hashes),
            ("🏷️ Backfill hash naming (rename files to MD5)", backfill_hash_naming),
        ],
        '4': [
            ("📤 Export/Import (CSV, JSON)", export_import_submenu),
            ("⚙️ Edit database configuration", edit_config),
        ],
        '5': [
            ("🌐 Start web interface", lambda: run_web_server(host='0.0.0.0', debug=WEB_DEBUG)),
            ("📈 Show library dashboard", show_dashboard),
        ],
        '6': [
            ("📘 Download Facebook video/photos", download_facebook),
            ("📋 Manage Facebook downloads", facebook_menu),
        ],
        '7': [
            ("📡 Scan YouTube channel and match mirrors", scan_and_match_youtube_videos),
            ("☁️ Upload video to YouTube (unlisted)", upload_single_video),
            ("🔐 Sync YouTube OAuth token to database", sync_oauth_token),
            ("🔄 Refresh YouTube OAuth token (full scopes)", refresh_youtube_token_wrapper),
            ("📦 Batch upload missing mirrors", lambda: batch_upload_missing_mirrors(auto_confirm=True)),
            ("🔄 Update YouTube titles (force all)", lambda: batch_update_youtube_titles(force=True)),
        ],
        '8': [
            ("❓ Question Bank", unified_question_menu),
            ("📰 Instapaper", instapaper_menu),
            ("⏱️ Pomodoro Timer", pomodoro_launcher),
            ("🔗 Zoom Link Extractor", zoom_extractor_launcher),
        ],
    }

    # ----- Helper to display a sub‑menu -----
    def show_submenu(category_key):
        items = menus[category_key]
        category_names = {
            '1': "📚 LECTURE MANAGEMENT",
            '2': "🎬 YOUTUBE LOCAL OPERATIONS",
            '3': "📁 FILE SYSTEM & MAINTENANCE",
            '4': "📦 EXPORT / IMPORT & CONFIG",
            '5': "🌐 WEB & DASHBOARD",
            '6': "📘 FACEBOOK",
            '7': "☁️ YOUTUBE UPLOAD & MIRROR MANAGEMENT",
            '8': "🧰 EXTERNAL TOOLS",
        }
        while True:
            print("\n" + "─" * 50)
            print_colored(f"  {category_names[category_key]}", COLORS.CYAN, bold=True)
            print("─" * 50)
            for i, (label, _) in enumerate(items, start=1):
                print(f"  {i}. {label}")
            print("  0. 🔙 Back to main menu")
            print("─" * 50)

            choice = input(color_text("Choose an option: ", COLORS.MAGENTA)).strip()
            if choice == '0':
                return
            if choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(items):
                    items[idx][1]()
                    input("\nPress Enter to continue...")
                else:
                    print_colored("[!] Invalid option.", COLORS.RED)
                    input("\nPress Enter to continue...")
            else:
                print_colored("[!] Please enter a number.", COLORS.RED)
                input("\nPress Enter to continue...")

    # ----- Main loop -----
    while True:
        show_banner()
        print("  " + color_text("MAIN MENU", COLORS.YELLOW, bold=True))
        print("  " + "─" * 40)
        print("  1. 📚 Lecture Management")
        print("  2. 🎬 YouTube Local Operations")
        print("  3. 📁 File System & Maintenance")
        print("  4. 📦 Export / Import & Config")
        print("  5. 🌐 Web & Dashboard")
        print("  6. 📘 Facebook")
        print("  7. ☁️ YouTube Upload & Mirror Management")
        print("  8. 🧰 External Tools")
        print("  0. 🚪 Exit")
        print("  " + "─" * 40)

        choice = input(color_text("Choose a category (0-8): ", COLORS.MAGENTA)).strip()
        if choice == '0':
            print_colored("\nGoodbye! Have a great day! 👋", COLORS.CYAN)
            break
        if choice in menus:
            show_submenu(choice)
        else:
            print_colored("[!] Invalid category.", COLORS.RED)
            input("\nPress Enter to continue...")

if __name__ == "__main__":
    main()
