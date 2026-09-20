import signal
import subprocess
import sys
import os
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



web_server_process = None
pomodoro_process = None

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

def _first_run_setup():
    from . import syllabus_config as SC
    from .file_manager import reload_paper_cache

    if SC.is_configured():
        return

    print("\n" + "═" * 60)
    print_colored("  👋 Welcome! Let's set up your syllabus.", COLORS.CYAN, bold=True)
    print("═" * 60)
    print("  No papers or subjects are configured yet.\n")
    print("  1. Start empty (recommended — you'll add your own)")
    print("  2. Import a syllabus from a JSON file")
    choice = input(color_text("Choose (1/2, default 1): ", COLORS.MAGENTA)).strip() or "1"

    if choice == "2":
        path = input("Path to syllabus JSON file: ").strip()
        if path:
            SC.import_syllabus(path, merge=False)
            reload_paper_cache()
    else:
        print_colored("[i] OK — use '📚 Syllabus Setup' in the main menu (option 9) to add papers and subjects.", COLORS.BLUE)

def syllabus_menu():
    from . import syllabus_config as SC
    from .file_manager import reload_paper_cache

    while True:
        print("\n" + "═" * 50)
        print_colored("  📚 SYLLABUS SETUP", COLORS.CYAN, bold=True)
        print("═" * 50)
        papers = SC.get_papers(active_only=False)
        print(f"  Papers: {len(papers)}")
        for p in papers:
            n_sub = len(SC.get_subjects(p["paper_key"], active_only=False))
            print(f"    • [{p['paper_key']}] {p['display_name']}  ({n_sub} subjects)")
        print("─" * 50)
        print("  1. Add paper")
        print("  2. Add subject")
        print("  3. Edit paper")
        print("  4. Edit subject")
        print("  5. Delete paper")
        print("  6. Delete subject")
        print("  7. Export current syllabus to JSON")
        print("  8. Import syllabus from JSON")
        print("  9. Clear all (start fresh)")
        print("  0. Back")
        print("─" * 50)
        choice = input(color_text("Choose: ", COLORS.MAGENTA)).strip()

        # ---------- 1. Add paper ----------
        if choice == "1":
            key = input("Paper key (e.g. semester_1, no spaces): ").strip()
            if not key:
                print_colored("[!] Paper key required.", COLORS.RED); continue
            if not key.replace("_", "").isalnum():
                print_colored("[!] Paper key must be alphanumeric (underscores allowed).", COLORS.RED); continue
            name = input("Display name (e.g. Semester 1 — BBS): ").strip()
            if not name:
                print_colored("[!] Display name required.", COLORS.RED); continue
            folder = input(f"Folder name [{name}]: ").strip() or name
            kws = input("Keywords (comma-sep, for auto-detect): ").strip()
            if SC.add_paper(key, name, folder, kws):
                print_colored(f"[✓] Paper '{name}' added.", COLORS.GREEN)
                reload_paper_cache()
            else:
                print_colored("[!] Could not add paper (key may already exist).", COLORS.RED)

        # ---------- 2. Add subject ----------
        elif choice == "2":
            if not papers:
                print_colored("Add a paper first.", COLORS.YELLOW); continue
            for i, p in enumerate(papers, 1):
                print(f"  {i}. {p['display_name']}")
            pi = input("Paper number: ").strip()
            if not pi.isdigit() or not (1 <= int(pi) <= len(papers)):
                print_colored("[!] Invalid paper number.", COLORS.RED); continue
            paper = papers[int(pi) - 1]
            code = input("Subject code (e.g. 01, 02): ").strip()
            if not code:
                print_colored("[!] Subject code required.", COLORS.RED); continue
            name = input("Subject name: ").strip()
            if not name:
                print_colored("[!] Subject name required.", COLORS.RED); continue
            if SC.add_subject(name, paper["paper_key"], chapter=code):
                print_colored(f"[✓] Subject '{name}' added to {paper['display_name']}.", COLORS.GREEN)
                reload_paper_cache()
            else:
                print_colored("[!] Could not add subject (name may already exist).", COLORS.RED)

        # ---------- 3. Edit paper ----------
        elif choice == "3":
            if not papers:
                print_colored("No papers to edit.", COLORS.YELLOW); continue
            for i, p in enumerate(papers, 1):
                print(f"  {i}. [{p['paper_key']}] {p['display_name']}")
            pi = input("Edit which paper? number (or blank): ").strip()
            if not pi.isdigit() or not (1 <= int(pi) <= len(papers)): continue
            p = papers[int(pi) - 1]
            print(f"\n  Current display name: {p['display_name']}")
            print(f"  Current folder name : {p['folder_name']}")
            print(f"  Current keywords    : {p.get('keywords') or '(none)'}")
            new_name = input("New display name (blank to keep): ").strip()
            new_folder = input("New folder name (blank to keep): ").strip()
            new_kws = input("New keywords (blank to keep): ").strip()
            updates = {}
            if new_name:   updates['display_name'] = new_name
            if new_folder: updates['folder_name'] = new_folder
            if new_kws:    updates['keywords'] = new_kws
            if not updates:
                print_colored("No changes made.", COLORS.YELLOW); continue
            if SC.update_paper(p['id'], **updates):
                print_colored("[✓] Paper updated.", COLORS.GREEN)
                reload_paper_cache()
            else:
                print_colored("[!] Update failed.", COLORS.RED)

        # ---------- 4. Edit subject ----------
        elif choice == "4":
            subs = SC.get_subjects(active_only=False)
            if not subs:
                print_colored("No subjects to edit.", COLORS.YELLOW); continue
            for i, s in enumerate(subs, 1):
                print(f"  {i}. [{s['paper']}] {s['name']}  (code: {s['chapter']})")
            si = input("Edit which subject? number (or blank): ").strip()
            if not si.isdigit() or not (1 <= int(si) <= len(subs)): continue
            s = subs[int(si) - 1]
            print(f"\n  Current name : {s['name']}")
            print(f"  Current code : {s['chapter']}")
            new_name = input("New name (blank to keep): ").strip()
            new_code = input("New code (blank to keep): ").strip()
            updates = {}
            if new_name: updates['name'] = new_name
            if new_code: updates['chapter'] = new_code
            if not updates:
                print_colored("No changes made.", COLORS.YELLOW); continue
            if SC.update_subject(s['id'], **updates):
                print_colored("[✓] Subject updated.", COLORS.GREEN)
                reload_paper_cache()
            else:
                print_colored("[!] Update failed.", COLORS.RED)

        # ---------- 5. Delete paper ----------
        elif choice == "5":
            if not papers:
                print_colored("No papers to delete.", COLORS.YELLOW); continue
            for i, p in enumerate(papers, 1):
                n_sub = len(SC.get_subjects(p["paper_key"], active_only=False))
                print(f"  {i}. [{p['paper_key']}] {p['display_name']}  ({n_sub} subjects)")
            pi = input("Delete which paper? number (or blank to cancel): ").strip()
            if not pi.isdigit() or not (1 <= int(pi) <= len(papers)): continue
            p = papers[int(pi) - 1]
            n_sub = len(SC.get_subjects(p["paper_key"], active_only=False))
            print_colored(f"[!] Deleting '{p['display_name']}' affects {n_sub} subject(s).", COLORS.YELLOW)
            print_colored("[!] Lectures already assigned stay in DB but become 'unknown paper'.", COLORS.YELLOW)
            cascade = False
            if n_sub > 0:
                cascade = input("Also delete its subjects? (y/n): ").strip().lower() == 'y'
            confirm = input("Type 'yes' to confirm: ").strip().lower()
            if confirm != 'yes':
                print_colored("Cancelled.", COLORS.YELLOW); continue
            if SC.delete_paper(p['id'], cascade_subjects=cascade):
                print_colored("[✓] Paper deleted.", COLORS.GREEN)
                reload_paper_cache()
            else:
                print_colored("[!] Delete failed.", COLORS.RED)

        # ---------- 6. Delete subject ----------
        elif choice == "6":
            subs = SC.get_subjects(active_only=False)
            if not subs:
                print_colored("No subjects to delete.", COLORS.YELLOW); continue
            for i, s in enumerate(subs, 1):
                print(f"  {i}. [{s['paper']}] {s['name']}  (code: {s['chapter']})")
            si = input("Delete which subject? number (or blank to cancel): ").strip()
            if not si.isdigit() or not (1 <= int(si) <= len(subs)): continue
            s = subs[int(si) - 1]
            confirm = input(f"Delete '{s['name']}'? (y/n): ").strip().lower()
            if confirm != 'y':
                print_colored("Cancelled.", COLORS.YELLOW); continue
            if SC.delete_subject(s['id']):
                print_colored("[✓] Subject deleted.", COLORS.GREEN)
                reload_paper_cache()
            else:
                print_colored("[!] Delete failed.", COLORS.RED)

        # ---------- 7. Export syllabus to JSON ----------
        elif choice == "7":
            if not papers:
                print_colored("Nothing to export.", COLORS.YELLOW); continue
            from datetime import datetime
            default_name = f"syllabus_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            path = input(f"Output path [{default_name}]: ").strip() or default_name
            try:
                SC.export_syllabus(path)
            except Exception as e:
                print_colored(f"[!] Export failed: {e}", COLORS.RED)

        # ---------- 8. Import syllabus from JSON ----------
        elif choice == "8":
            path = input("Path to syllabus JSON file: ").strip()
            if not path:
                continue
            existing = SC.get_papers(active_only=False)
            if existing:
                print_colored(f"[i] You already have {len(existing)} paper(s).", COLORS.YELLOW)
                mode = input("(m)erge — add new only, or (r)eplace — wipe first? [m/r]: ").strip().lower()
                if mode == 'r':
                    confirm = input("Type 'yes' to wipe existing syllabus: ").strip().lower()
                    if confirm != 'yes':
                        print_colored("Cancelled.", COLORS.YELLOW); continue
                    SC.import_syllabus(path, merge=False)
                else:
                    SC.import_syllabus(path, merge=True)
            else:
                SC.import_syllabus(path, merge=False)
            reload_paper_cache()

        # ---------- 9. Clear all ----------
        elif choice == "9":
            if input("Really clear everything? Type 'yes' to confirm: ").strip().lower() == "yes":
                SC.clear_all()
                reload_paper_cache()
                print_colored("[✓] Syllabus cleared.", COLORS.GREEN)

        # ---------- 0. Back ----------
        elif choice == "0":
            break
        else:
            print_colored("[!] Invalid option.", COLORS.RED)

def main():
    load_or_create_config()
    create_table()
    migrate_table()
    ensure_subjects_populated()
    from .question_converter import create_tables
    create_tables()
    _first_run_setup()

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
        global pomodoro_process

        try:
            pomodoro_process = subprocess.Popen(
                [sys.executable, "-m", "lecture_manager.pomodoro"],
                stdout=None,
                stderr=None,
                stdin=None
            )
            print_colored("[✓] Pomodoro timer launched.", COLORS.GREEN)
            print_colored("[i] Pomodoro will survive Ctrl+C on the web server.", COLORS.BLUE)
        except Exception as e:
            print_colored(f"[!] Failed to launch Pomodoro: {e}", COLORS.RED)

    def launch_web_server_with_signals():
        global web_server_process

        # Start web server as a subprocess (inherit stdout/stderr)
        web_server_process = subprocess.Popen(
            [sys.executable, "-m", "lecture_manager.web"],
            stdout=None,
            stderr=None,
            stdin=subprocess.DEVNULL
        )

        print_colored(f"[i] Web server started (PID {web_server_process.pid})", COLORS.GREEN)
        print_colored("[i] Press Ctrl+C to stop the web server only.", COLORS.BLUE)

        # Define a custom SIGINT handler
        def sigint_handler(sig, frame):
            global web_server_process
            if web_server_process and web_server_process.poll() is None:
                print_colored("\n[!] Stopping web server...", COLORS.YELLOW)
                web_server_process.terminate()
                web_server_process.wait()
                web_server_process = None
                print_colored("[✓] Web server stopped. Returning to menu.", COLORS.GREEN)
                # Raise KeyboardInterrupt to break out of the wait loop
                raise KeyboardInterrupt

        # Set the handler
        original_handler = signal.signal(signal.SIGINT, sigint_handler)

        try:
            # Wait for the web server to exit (normally or by our handler)
            web_server_process.wait()
        except KeyboardInterrupt:
            # Our handler raised this to break out of wait
            pass
        finally:
            # Restore original handler
            signal.signal(signal.SIGINT, original_handler)
            # If web server is still running (shouldn't happen), kill it
            if web_server_process and web_server_process.poll() is None:
                web_server_process.terminate()
                web_server_process.wait()
            web_server_process = None

    def kill_pomodoro():
        global pomodoro_process
        if pomodoro_process and pomodoro_process.poll() is None:
            print_colored("[i] Stopping Pomodoro...", COLORS.BLUE)
            pomodoro_process.terminate()
            pomodoro_process.wait()
            pomodoro_process = None

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
        '9': [
            ("📚 Syllabus Setup (papers & subjects)", syllabus_menu),
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
            '9': "📚 SYLLABUS SETUP",
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

    # ----- Main loop (with Ctrl+C handling) -----
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
        print("  9. 📚 Syllabus Setup (papers & subjects)")
        print("  0. 🚪 Exit")
        print("  " + "─" * 40)

        try:
            choice = input(color_text("Choose a category (0-9): ", COLORS.MAGENTA)).strip()
            if choice == '0':
                kill_pomodoro()
                print_colored("\nGoodbye! Have a great day! 👋", COLORS.CYAN)
                break
            if choice in menus:
                show_submenu(choice)
            else:
                print_colored("[!] Invalid category.", COLORS.RED)
                input("\nPress Enter to continue...")
        except KeyboardInterrupt:
            # Ctrl+C pressed at the main menu – exit everything
            print_colored("\n[!] Exiting...", COLORS.YELLOW)
            kill_pomodoro()
            break

if __name__ == "__main__":
    main()
