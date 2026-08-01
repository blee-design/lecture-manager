# main.py

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
from .question_bank import question_bank_menu
from .instapaper import instapaper_menu

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

    def pomodoro_launcher():
        import subprocess
        import sys
        subprocess.Popen([sys.executable, "-m", "lecture_manager.pomodoro"])
        print_colored("[✓] Pomodoro timer launched in a separate window.", COLORS.GREEN)
        print_colored("[i] You can now continue using the CLI while the timer runs.", COLORS.BLUE)

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
            ("🌐 Start web interface", lambda: run_web_server(host='0.0.0.0')),
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
            ("📦 Batch upload missing mirrors (fill empty mirror IDs)", batch_upload_missing_mirrors),
        ],
        '8': [
            ("❓ Question Bank", question_bank_menu),
            ("📰 Instapaper", instapaper_menu),
            ("⏱️ Pomodoro Timer", pomodoro_launcher),
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
