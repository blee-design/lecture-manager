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
from .question_converter import create_tables, import_from_file, get_questions, delete_question, export_to_file, run_conversion

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

def converter_submenu():
    from .question_converter import create_tables, import_from_file, get_questions, delete_question, export_to_file, run_conversion
    import os
    import argparse

    while True:
        print("\n" + "─" * 50)
        print_colored("  📝 QUESTION CONVERTER (Moodle)", COLORS.CYAN, bold=True)
        print("─" * 50)
        print("  1. Convert file to file (original)")
        print("  2. Import file to database")
        print("  3. Export database to file")
        print("  4. List questions in database")
        print("  5. Delete a question from database")
        print("  6. Advanced import (with --questions filter)")
        print("  7. Advanced export (with question number filter)")
        print("  8. Run converter with custom arguments (file‑to‑file)")
        print("  0. Back to main menu")
        print("─" * 50)

        choice = input(color_text("Choose an option: ", COLORS.MAGENTA)).strip()

        if choice == '0':
            break

        elif choice == '1':
            print("\n[File‑to‑file conversion]")
            input_file = input(color_text("Input file: ", COLORS.MAGENTA)).strip()
            if not input_file:
                print_colored("Cancelled.", COLORS.YELLOW)
                continue
            output_file = input(color_text("Output file (or press Enter to auto‑generate): ", COLORS.MAGENTA)).strip()
            if not output_file:
                output_file = None
            fmt = input(color_text("Output format (xml, json, html, txt, exam): ", COLORS.MAGENTA)).strip()
            shuffle = input(color_text("Shuffle questions? (y/n): ", COLORS.MAGENTA)).strip().lower() == 'y'
            args = argparse.Namespace(
                input=input_file,
                output=output_file,
                format=fmt,
                shuffle=shuffle,
                questions=None,
                bypass_option=False,
                bypass_duplicate=False,
                verbose=True,
                exam=False,
                time=90
            )
            run_conversion(args)
            input("\nPress Enter to continue...")

        elif choice == '2':
            print("\n[Import file to database]")
            input_file = input(color_text("Input file: ", COLORS.MAGENTA)).strip()
            if not input_file:
                print_colored("Cancelled.", COLORS.YELLOW)
                continue
            ext = os.path.splitext(input_file)[1].lower().lstrip('.')
            if ext in ('txt', 'text'):
                fmt = 'txt'
            elif ext == 'xml':
                fmt = 'xml'
            elif ext == 'json':
                fmt = 'json'
            else:
                fmt = input(color_text("File format (txt, xml, json): ", COLORS.MAGENTA)).strip()
            source = input(color_text("Source name (e.g., Officer_2078): ", COLORS.MAGENTA)).strip()
            if not source:
                print_colored("[!] Source name is required to separate exam sets.", COLORS.RED)
                continue
            args = type('Args', (), {'verbose': True, 'bypass_duplicate': False, 'bypass_option': False, 'questions': None})()
            count, errors = import_from_file(input_file, fmt, source=source, args=args)
            print_colored(f"[✓] Imported {count} questions.", COLORS.GREEN)
            if errors:
                print_colored(f"[!] {len(errors)} errors occurred.", COLORS.RED)
                for e in errors[:5]:
                    print(f"  {e}")
            input("\nPress Enter to continue...")

        elif choice == '3':
            print("\n[Export database to file]")
            output_file = input(color_text("Output file: ", COLORS.MAGENTA)).strip()
            if not output_file:
                print_colored("Cancelled.", COLORS.YELLOW)
                continue
            fmt = input(color_text("Output format (xml, json, html, txt): ", COLORS.MAGENTA)).strip()
            filters = {}
            source = input(color_text("Filter by source (or press Enter to skip): ", COLORS.MAGENTA)).strip()
            if source:
                filters['source'] = source
            group = input(color_text("Filter by group (or press Enter to skip): ", COLORS.MAGENTA)).strip()
            if group:
                filters['group_name'] = group
            qtype = input(color_text("Filter by type (multichoice, essay, truefalse, matching) (or skip): ", COLORS.MAGENTA)).strip()
            if qtype:
                filters['type'] = qtype
            questions = get_questions(filters)
            if not questions:
                print_colored("[i] No questions found.", COLORS.YELLOW)
                continue
            print_colored(f"[i] Exporting {len(questions)} questions...", COLORS.BLUE)
            args = type('Args', (), {'verbose': True})()
            export_to_file(questions, output_file, fmt, args)
            print_colored(f"[✓] Exported to {output_file}", COLORS.GREEN)
            input("\nPress Enter to continue...")

        elif choice == '4':
            filters = {}
            source = input(color_text("Filter by source (or press Enter to skip): ", COLORS.MAGENTA)).strip()
            if source:
                filters['source'] = source
            group = input(color_text("Filter by group (or press Enter to skip): ", COLORS.MAGENTA)).strip()
            if group:
                filters['group_name'] = group
            qtype = input(color_text("Filter by type (or skip): ", COLORS.MAGENTA)).strip()
            if qtype:
                filters['type'] = qtype
            questions = get_questions(filters)
            if not questions:
                print_colored("[i] No questions found.", COLORS.YELLOW)
            else:
                print(f"\n--- Questions in Database ({len(questions)}) ---")
                for q in questions:
                    print(f"  ID: {q.get('id', '?')} | Source: {q.get('source', '?')} | QNo: {q.get('question_no', '?')} | Type: {q.get('type')} | Group: {q.get('group')} | {q.get('text')[:50]}...")
            input("\nPress Enter to continue...")

        elif choice == '5':
            qid = input(color_text("Enter question ID to delete: ", COLORS.MAGENTA)).strip()
            if not qid.isdigit():
                print_colored("Invalid ID.", COLORS.RED)
                continue
            if delete_question(int(qid)):
                print_colored("[✓] Deleted.", COLORS.GREEN)
            else:
                print_colored("[!] Not found.", COLORS.RED)
            input("\nPress Enter to continue...")

        elif choice == '6':
            # Advanced import
            print("\n[Advanced import – with question filter]")
            input_file = input(color_text("Input file: ", COLORS.MAGENTA)).strip()
            if not input_file:
                print_colored("Cancelled.", COLORS.YELLOW)
                continue
            # detect format
            ext = os.path.splitext(input_file)[1].lower().lstrip('.')
            if ext in ('txt', 'text'):
                fmt = 'txt'
            elif ext == 'xml':
                fmt = 'xml'
            elif ext == 'json':
                fmt = 'json'
            else:
                fmt = input(color_text("File format (txt, xml, json): ", COLORS.MAGENTA)).strip()
            source = input(color_text("Source name: ", COLORS.MAGENTA)).strip()
            if not source:
                print_colored("[!] Source is required.", COLORS.RED)
                continue
            qfilter = input(color_text("Filter questions (e.g., 1,5,10 or 5..10) (or skip): ", COLORS.MAGENTA)).strip()
            if not qfilter:
                qfilter = None
            bypass_dup = input(color_text("Bypass duplicates? (y/n): ", COLORS.MAGENTA)).strip().lower() == 'y'
            bypass_opt = input(color_text("Bypass missing options? (y/n): ", COLORS.MAGENTA)).strip().lower() == 'y'

            args = type('Args', (), {
                'verbose': True,
                'bypass_duplicate': bypass_dup,
                'bypass_option': bypass_opt,
                'questions': qfilter
            })()
            count, errors = import_from_file(input_file, fmt, source=source, args=args)
            print_colored(f"[✓] Imported {count} questions.", COLORS.GREEN)
            if errors:
                print_colored(f"[!] {len(errors)} errors.", COLORS.RED)
            input("\nPress Enter to continue...")

        elif choice == '7':
            # Advanced export with question number filter
            print("\n[Advanced export]")
            output_file = input(color_text("Output file: ", COLORS.MAGENTA)).strip()
            if not output_file:
                print_colored("Cancelled.", COLORS.YELLOW)
                continue
            fmt = input(color_text("Format (xml, json, html, txt): ", COLORS.MAGENTA)).strip()
            filters = {}
            source = input(color_text("Filter by source (or skip): ", COLORS.MAGENTA)).strip()
            if source:
                filters['source'] = source
            group = input(color_text("Filter by group (or skip): ", COLORS.MAGENTA)).strip()
            if group:
                filters['group_name'] = group
            qtype = input(color_text("Filter by type (or skip): ", COLORS.MAGENTA)).strip()
            if qtype:
                filters['type'] = qtype

            qnos = input(color_text("Filter by question numbers (e.g., 1,5,10 or 5..10) (or skip): ", COLORS.MAGENTA)).strip()
            if qnos:
                # Parse the filter string into a list of ints
                qnos_list = []
                for part in qnos.split(','):
                    part = part.strip()
                    if '..' in part:
                        start, end = part.split('..')
                        start = int(start); end = int(end)
                        qnos_list.extend(range(start, end+1))
                    else:
                        qnos_list.append(int(part))
                if qnos_list:
                    filters['question_nos'] = qnos_list

            questions = get_questions(filters)
            if not questions:
                print_colored("[i] No questions found.", COLORS.YELLOW)
                continue
            args = type('Args', (), {'verbose': True})()
            export_to_file(questions, output_file, fmt, args)
            print_colored(f"[✓] Exported {len(questions)} questions.", COLORS.GREEN)
            input("\nPress Enter to continue...")

        elif choice == '8':
            # Run converter with full custom arguments (file‑to‑file)
            print("\n[Run converter with custom arguments]")
            print("Enter the arguments as you would on the command line.")
            print("Example: -i input.txt -o output.xml --shuffle --time 60")
            args_str = input(color_text("Arguments: ", COLORS.MAGENTA)).strip()
            if not args_str:
                print_colored("Cancelled.", COLORS.YELLOW)
                continue
            import argparse
            # We can't easily parse a string with argparse without splitting, so we use shlex
            import shlex
            argv = shlex.split(args_str)
            # Build a Namespace; we need to define parser (the same one from converter_main)
            # But we can reuse the parser defined in converter_main
            from .question_converter.converter_main import parser
            parsed_args = parser.parse_args(argv)
            run_conversion(parsed_args)
            input("\nPress Enter to continue...")

        else:
            print_colored("[!] Invalid choice.", COLORS.RED)
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
            ("📝 Question Converter (Moodle)", converter_submenu),
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
