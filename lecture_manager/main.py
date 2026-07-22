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
    backfill_hash_naming, show_paper_breakdown
)

# NEW: import web server runner
from .web import run_web_server
from .utils import print_colored, color_text, COLORS
from .youtube import refresh_cookies
from .facebook import download_facebook
from .instapaper import add_to_instapaper, setup_credentials_interactive

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
        print(" 10. " + color_text("Export/Import (CSV, JSON)", COLORS.WHITE))
        print(" 11. " + color_text("Edit database configuration", COLORS.WHITE))
        print(" 12. " + color_text("Move/rename a video manually", COLORS.WHITE))
        print(" 13. " + color_text("Delete a video (move to trash)", COLORS.WHITE))
        print(" 14. " + color_text("Restore from trash", COLORS.WHITE))
        print(" 15. " + color_text("Empty trash", COLORS.WHITE))
        print(" 16. " + color_text("Tally database with video files", COLORS.WHITE))
        print(" 17. " + color_text("Start web interface", COLORS.WHITE))
        print(" 18. " + color_text("Scan for duplicate video files", COLORS.WHITE))
        print(" 19. " + color_text("Auto-resolve duplicate video files", COLORS.WHITE))
        print(" 20. " + color_text("Backfill file hashes (one-time)", COLORS.WHITE))
        print(" 21. " + color_text("Show library dashboard", COLORS.WHITE))
        print(" 22. " + color_text("Play a video (local file)", COLORS.WHITE))
        print(" 23. " + color_text("Refresh YouTube cookies", COLORS.WHITE))
        print(" 24. " + color_text("Backfill hash naming (rename files to MD5)", COLORS.WHITE))
        print(" 25. " + color_text("Download Facebook video/photos", COLORS.WHITE))
        print(" 26. " + color_text("Manage Facebook downloads", COLORS.WHITE))
        print(" 27. " + color_text("Scan YouTube channel and match mirrors", COLORS.WHITE))
        print(" 28. " + color_text("Upload video to YouTube (unlisted)", COLORS.WHITE))
        print(" 29. " + color_text("Sync YouTube OAuth token to database", COLORS.WHITE))
        print(" 30. " + color_text("Question Bank", COLORS.WHITE))
        print(" 31. " + color_text("Save a lecture/question to Instapaper", COLORS.WHITE))
        print(" 32. " + color_text("Set up/re‑enter Instapaper credentials", COLORS.WHITE))
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
            export_import_submenu()
        elif choice == '11':
            edit_config()
        elif choice == '12':
            move_video_interactive()
        elif choice == '13':
            delete_video_to_trash()
        elif choice == '14':
            restore_from_trash()
        elif choice == '15':
            empty_trash()
        elif choice == '16':
            tally_db_with_files()
        elif choice == '17':
            print_colored("\nStarting web server at http://0.0.0.0:5000", COLORS.GREEN)
            print_colored("Access from other devices using your local IP (e.g., http://192.168.1.100:5000)", COLORS.BLUE)
            print_colored("Press Ctrl+C to stop the server and return to CLI", COLORS.YELLOW)
            try:
                run_web_server(host='0.0.0.0')
            except KeyboardInterrupt:
                print_colored("\n[✓] Web server stopped.", COLORS.GREEN)
            except Exception as e:
                print_colored(f"[!] Failed to start web server: {e}", COLORS.RED)
        elif choice == '18':
            scan_duplicates()
        elif choice == '19':
            resolve_duplicates()
        elif choice == '20':
            backfill_hashes()
        elif choice == '21':
            show_dashboard()
        elif choice == '22':
            play_video()
        elif choice == '23':
            refresh_cookies()
        elif choice == '24':
            backfill_hash_naming()
        elif choice == '25':
            download_facebook()
        elif choice == '26':
            from .facebook_manager import facebook_menu
            facebook_menu()
        elif choice == '27':
            from .upload import scan_and_match_youtube_videos
            scan_and_match_youtube_videos()
        elif choice == '28':
            identifier = input(color_text("Enter Video ID, Syllabus ID, or mirror ID: ", COLORS.MAGENTA)).strip()
            if not identifier:
                continue
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
        elif choice == '29':
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
                print_colored(f"[!] File not found: {e}. Please run Option 31 first to generate the token.", COLORS.YELLOW)
            except Exception as e:
                print_colored(f"[!] Sync failed: {e}", COLORS.RED)
        elif choice == '30':
            from .question_bank import question_bank_menu
            question_bank_menu()
        elif choice == '31':
            # Save a lecture/question to Instapaper
            print("\nWhat do you want to save to Instapaper?")
            print("  1. A YouTube lecture (by ID)")
            print("  2. A question (by ID)")
            sub = input(color_text("Choose (1-2): ", COLORS.MAGENTA)).strip()
            if sub == '1':
                vid = input(color_text("Enter Video ID, Syllabus ID, or mirror ID: ", COLORS.MAGENTA)).strip()
                if not vid:
                    continue
                from .db import get_record_by_any_id
                rec = get_record_by_any_id(vid)
                if not rec:
                    print_colored("[!] Record not found.", COLORS.RED)
                    continue
                url = f"https://youtu.be/{rec['video_id']}"
                title = rec.get('original_filename') or rec.get('video_title') or f"Lecture {rec['syllabus_id']}"
                tags = f"lecture,{rec.get('subject', '')}"
                ok, msg = add_to_instapaper(url, title=title, tags=tags)
                print_colored(msg, COLORS.GREEN if ok else COLORS.RED)

            elif sub == '2':
                qid = input(color_text("Enter question ID: ", COLORS.MAGENTA)).strip()
                if not qid or not qid.isdigit():
                    print_colored("[!] Invalid ID.", COLORS.RED)
                    continue
                from .question_bank import get_question_by_id
                q = get_question_by_id(int(qid))
                if not q:
                    print_colored("[!] Question not found.", COLORS.RED)
                    continue
                # Build a URL to the web interface (assumes web server is running on port 5000)
                title = f"{q['institution']} {q['level']} Q{q['question_number']} – {q['subject']}"
                url = f"http://localhost:5000/question/{qid}"
                tags = f"question,{q['subject']}"
                ok, msg = add_to_instapaper(url, title=title, tags=tags)
                print_colored(msg, COLORS.GREEN if ok else COLORS.RED)
            else:
                print_colored("[!] Invalid choice.", COLORS.RED)

        elif choice == '32':
            # Set up / re-enter Instapaper credentials
            setup_credentials_interactive()
        elif choice == '0':
            print_colored("\nGoodbye! Have a great day! 👋", COLORS.CYAN)
            break
        else:
            print_colored("[!] Invalid option. Please try again.", COLORS.RED)

        input("\nPress Enter to continue...")

if __name__ == "__main__":
    main()
