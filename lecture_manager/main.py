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

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _load_syllabus(sid):
        if sid is None:
            return None
        for s in SC.get_syllabi(active_only=False):
            if s['id'] == sid:
                return s
        return None

    def _pick_syllabus(prompt="Choose syllabus"):
        syllabi = SC.get_syllabi(active_only=False)
        if not syllabi:
            print_colored("[i] No syllabi yet. Add one from 'sy' first.", COLORS.YELLOW)
            return None
        print()
        for i, s in enumerate(syllabi, 1):
            n_papers = len(SC.get_papers(active_only=False, syllabus_id=s['id']))
            lvl = f"  (Level {s['level']})" if s.get('level') else ""
            print(f"  {i}. {s['display_name']}{lvl}  —  {n_papers} paper(s)")
        print("  0. Cancel")
        c = input(color_text(f"{prompt} (1-{len(syllabi)}, 0=cancel): ",
                             COLORS.MAGENTA)).strip()
        if not c.isdigit():
            return None
        idx = int(c)
        if idx == 0 or idx > len(syllabi):
            return None
        return syllabi[idx - 1]

    def _syllabus_stats(syllabus):
        """Return (n_papers, n_subjects, n_chapters) scoped to a syllabus."""
        papers = SC.get_papers(active_only=False, syllabus_id=syllabus['id'])
        keys = {p['paper_key'] for p in papers}
        subjects = [s for s in SC.get_subjects(active_only=False)
                    if s.get('paper') in keys]
        n_chapters = sum(
            len(SC.get_chapters(subject_id=s['id'], active_only=False))
            for s in subjects
        )
        return len(papers), len(subjects), n_chapters

    # Seed the current syllabus with the first one (if any)
    current_id = None
    all_syll = SC.get_syllabi(active_only=False)
    if all_syll:
        current_id = all_syll[0]['id']

    # ------------------------------------------------------------------
    # Main menu loop
    # ------------------------------------------------------------------
    while True:
        current = _load_syllabus(current_id)

        print()
        print_colored("  📚  SYLLABUS SETUP", COLORS.CYAN, bold=True)
        print_colored("  " + "─" * 62, COLORS.CYAN)

        if current:
            n_p, n_s, n_c = _syllabus_stats(current)
            lvl = f"  •  Level {current['level']}" if current.get('level') else ""
            print(f"  Current: {color_text(current['display_name'], COLORS.GREEN, bold=True)}{lvl}")
            print(f"           {n_p} paper(s)  •  {n_s} subject(s)  •  {n_c} chapter(s)")
        else:
            print_colored("  No syllabus selected.", COLORS.YELLOW)

        print_colored("  " + "─" * 62, COLORS.CYAN)
        print("  sy. " + color_text("Manage syllabi", COLORS.YELLOW) +
              "       (add / edit / delete / reassign papers)")
        print("  sw. " + color_text("Switch current syllabus", COLORS.YELLOW))
        print("  " + "─" * 62)
        print("   1. Add paper")
        print("   2. Add subject")
        print("   3. Edit paper")
        print("   4. Edit subject")
        print("   5. Delete paper")
        print("   6. Delete subject")
        print("   7. Export current syllabus to JSON")
        print("   8. Import syllabus from JSON")
        print("   9. Clear current syllabus (papers & subjects)")
        print("   c. Manage chapters (add / edit / delete)")
        print("   0. Back to main menu")
        print_colored("  " + "─" * 62, COLORS.CYAN)

        choice = input(color_text("Choose: ", COLORS.MAGENTA)).strip().lower()

        # ---------- sy: manage syllabi ----------
        if choice == 'sy':
            new_id = _manage_syllabi_submenu(SC, current_id)
            if new_id is not None:
                current_id = new_id
                reload_paper_cache()
            # If the current was deleted, _manage_syllabi_submenu returns None
            # → fall back to first available
            if _load_syllabus(current_id) is None:
                remaining = SC.get_syllabi(active_only=False)
                current_id = remaining[0]['id'] if remaining else None
            continue

        # ---------- sw: switch current ----------
        if choice == 'sw':
            picked = _pick_syllabus("Switch to")
            if picked:
                current_id = picked['id']
                reload_paper_cache()
                print_colored(f"[✓] Switched to '{picked['display_name']}'.", COLORS.GREEN)
            continue

        # ---------- Everything else needs a current syllabus ----------
        if choice in ('1','2','3','4','5','6','7','8','9','c') and not current:
            print_colored("[!] Pick a syllabus first ('sw') or add one ('sy').",
                          COLORS.RED)
            input("\nPress Enter to continue...")
            continue

        # ==============================================================
        # 1. Add paper
        # ==============================================================
        if choice == "1":
            key = input("Paper key (lowercase, no spaces, e.g. l6_pretest): ").strip()
            if not key:
                continue
            if not key.replace("_", "").isalnum():
                print_colored("[!] Key must be alphanumeric (underscores ok).", COLORS.RED)
                continue
            if key in {p['paper_key'] for p in SC.get_papers(active_only=False)}:
                print_colored(f"[!] Paper key '{key}' already exists.", COLORS.RED)
                continue
            name = input("Display name: ").strip()
            if not name:
                print_colored("[!] Display name required.", COLORS.RED)
                continue
            folder = input(f"Folder name [{name}]: ").strip() or name
            kws = input("Auto-detect keywords (comma-separated, optional): ").strip()
            if SC.add_paper(key, name, folder, kws, syllabus_id=current['id']):
                print_colored(f"[✓] Paper '{name}' added to '{current['display_name']}'.",
                              COLORS.GREEN)
                reload_paper_cache()
            else:
                print_colored("[!] Could not add paper.", COLORS.RED)

        # ==============================================================
        # 2. Add subject
        # ==============================================================
        elif choice == "2":
            papers = SC.get_papers(active_only=False, syllabus_id=current['id'])
            if not papers:
                print_colored("Add a paper first.", COLORS.YELLOW)
                continue
            for i, p in enumerate(papers, 1):
                print(f"  {i}. {p['display_name']}")
            pi = input("Paper number: ").strip()
            if not pi.isdigit() or not (1 <= int(pi) <= len(papers)):
                print_colored("[!] Invalid paper number.", COLORS.RED)
                continue
            paper = papers[int(pi) - 1]
            code = input("Subject code (e.g. 01, 02): ").strip()
            if not code:
                print_colored("[!] Subject code required.", COLORS.RED)
                continue
            name = input("Subject name: ").strip()
            if not name:
                print_colored("[!] Subject name required.", COLORS.RED)
                continue
            if SC.add_subject(name, paper['paper_key'], chapter=code):
                print_colored(f"[✓] Subject '{name}' added under {paper['display_name']}.",
                              COLORS.GREEN)
                reload_paper_cache()
            else:
                print_colored("[!] Could not add (name may already exist).", COLORS.RED)

        # ==============================================================
        # 3. Edit paper
        # ==============================================================
        elif choice == "3":
            papers = SC.get_papers(active_only=False, syllabus_id=current['id'])
            if not papers:
                print_colored("No papers to edit.", COLORS.YELLOW)
                continue
            for i, p in enumerate(papers, 1):
                print(f"  {i}. [{p['paper_key']}] {p['display_name']}")
            pi = input("Edit which paper? number (blank to cancel): ").strip()
            if not pi.isdigit() or not (1 <= int(pi) <= len(papers)):
                continue
            p = papers[int(pi) - 1]
            print(f"\n  Display name : {p['display_name']}")
            print(f"  Folder name  : {p['folder_name']}")
            print(f"  Keywords     : {p.get('keywords') or '(none)'}")
            new_name = input("New display name (blank to keep): ").strip()
            new_folder = input("New folder name (blank to keep): ").strip()
            new_kws = input("New keywords (blank to keep): ").strip()
            updates = {}
            if new_name:   updates['display_name'] = new_name
            if new_folder: updates['folder_name'] = new_folder
            if new_kws:    updates['keywords'] = new_kws
            if not updates:
                print_colored("No changes made.", COLORS.YELLOW)
                continue
            if SC.update_paper(p['id'], **updates):
                print_colored("[✓] Paper updated.", COLORS.GREEN)
                reload_paper_cache()

        # ==============================================================
        # 4. Edit subject
        # ==============================================================
        elif choice == "4":
            papers = SC.get_papers(active_only=False, syllabus_id=current['id'])
            keys = {p['paper_key'] for p in papers}
            subs = [s for s in SC.get_subjects(active_only=False)
                    if s.get('paper') in keys]
            if not subs:
                print_colored("No subjects to edit.", COLORS.YELLOW)
                continue
            for i, s in enumerate(subs, 1):
                print(f"  {i}. [{s['paper']}] {s['name']}  (code: {s['chapter']})")
            si = input("Edit which subject? number (blank to cancel): ").strip()
            if not si.isdigit() or not (1 <= int(si) <= len(subs)):
                continue
            s = subs[int(si) - 1]
            print(f"\n  Current name : {s['name']}")
            print(f"  Current code : {s['chapter']}")
            new_name = input("New name (blank to keep): ").strip()
            new_code = input("New code (blank to keep): ").strip()
            updates = {}
            if new_name: updates['name'] = new_name
            if new_code: updates['chapter'] = new_code
            if not updates:
                print_colored("No changes made.", COLORS.YELLOW)
                continue
            if SC.update_subject(s['id'], **updates):
                print_colored("[✓] Subject updated.", COLORS.GREEN)
                reload_paper_cache()

        # ==============================================================
        # 5. Delete paper
        # ==============================================================
        elif choice == "5":
            papers = SC.get_papers(active_only=False, syllabus_id=current['id'])
            if not papers:
                print_colored("No papers to delete.", COLORS.YELLOW)
                continue
            for i, p in enumerate(papers, 1):
                n_sub = len(SC.get_subjects(paper_key=p['paper_key'], active_only=False))
                print(f"  {i}. [{p['paper_key']}] {p['display_name']}  ({n_sub} subjects)")
            pi = input("Delete which paper? number (blank to cancel): ").strip()
            if not pi.isdigit() or not (1 <= int(pi) <= len(papers)):
                continue
            p = papers[int(pi) - 1]
            n_sub = len(SC.get_subjects(paper_key=p['paper_key'], active_only=False))
            print_colored(f"[!] Deleting '{p['display_name']}' will affect {n_sub} subject(s).",
                          COLORS.YELLOW)
            cascade = False
            if n_sub > 0:
                cascade = input("Also delete its subjects? (y/n): ").strip().lower() == 'y'
            if input("Type 'yes' to confirm: ").strip().lower() != 'yes':
                print_colored("Cancelled.", COLORS.YELLOW)
                continue
            if SC.delete_paper(p['id'], cascade_subjects=cascade):
                print_colored("[✓] Paper deleted.", COLORS.GREEN)
                reload_paper_cache()

        # ==============================================================
        # 6. Delete subject
        # ==============================================================
        elif choice == "6":
            papers = SC.get_papers(active_only=False, syllabus_id=current['id'])
            keys = {p['paper_key'] for p in papers}
            subs = [s for s in SC.get_subjects(active_only=False)
                    if s.get('paper') in keys]
            if not subs:
                print_colored("No subjects to delete.", COLORS.YELLOW)
                continue
            for i, s in enumerate(subs, 1):
                print(f"  {i}. [{s['paper']}] {s['name']}  (code: {s['chapter']})")
            si = input("Delete which subject? number (blank to cancel): ").strip()
            if not si.isdigit() or not (1 <= int(si) <= len(subs)):
                continue
            s = subs[int(si) - 1]
            if input(f"Delete '{s['name']}'? (y/n): ").strip().lower() != 'y':
                print_colored("Cancelled.", COLORS.YELLOW)
                continue
            if SC.delete_subject(s['id']):
                print_colored("[✓] Subject deleted.", COLORS.GREEN)
                reload_paper_cache()

        # ==============================================================
        # 7. Export current syllabus to JSON
        # ==============================================================
        elif choice == "7":
            from datetime import datetime
            print()
            print("Export scope:")
            print("  1. Current syllabus only")
            print("  2. All syllabi (full backup)")
            scope = input("Choose (1/2, default 1): ").strip() or "1"

            ts = datetime.now().strftime('%Y%m%d_%H%M%S')
            if scope == "2":
                default_name = f"syllabus_ALL_{ts}.json"
            else:
                default_name = f"syllabus_{current['syllabus_key']}_{ts}.json"

            path = input(f"Output path [{default_name}]: ").strip() or default_name

            try:
                if scope == "2":
                    SC.export_syllabus(path)          # no syllabus_id → all
                    print_colored(f"[✓] All syllabi exported to {path}", COLORS.GREEN)
                else:
                    SC.export_syllabus(path, syllabus_id=current['id'])
            except Exception as e:
                print_colored(f"[!] Export failed: {e}", COLORS.RED)

        # ==============================================================
        # 8. Import syllabus from JSON
        # ==============================================================
        elif choice == "8":
            path = input("Path to syllabus JSON file: ").strip()
            if not path:
                continue
            # Ask whether to import into the current syllabus, or create a new one
            print()
            print("Import into:")
            print("  1. Current syllabus (merge papers into it)")
            print("  2. As a new syllabus (create fresh from the file)")
            print("  0. Cancel")
            mode = input("Choose (1/2/0): ").strip()
            if mode == '0' or not mode:
                continue

            if mode == '1':
                target_id = current['id']
            elif mode == '2':
                # Let the file's syllabus_key create a new syllabi row
                target_id = None  # SC.import_syllabus will create from file
            else:
                print_colored("[!] Invalid choice.", COLORS.RED)
                continue

            try:
                result = SC.import_syllabus(path, target_syllabus_id=target_id)
                if isinstance(result, tuple) and len(result) == 3:
                    p, s, c = result
                    print_colored(
                        f"[✓] Imported {p} new papers, {s} new subjects, {c} new chapters.",
                        COLORS.GREEN
                    )
                reload_paper_cache()
            except Exception as e:
                print_colored(f"[!] Import failed: {e}", COLORS.RED)

        # ==============================================================
        # 9. Clear current syllabus
        # ==============================================================
        elif choice == "9":
            print_colored(
                f"[!] This will delete all papers and subjects under "
                f"'{current['display_name']}'.",
                COLORS.YELLOW
            )
            print_colored(
                "[!] Questions already linked to those papers stay in the DB "
                "but become 'unknown paper'.",
                COLORS.YELLOW
            )
            if input("Type 'yes' to confirm: ").strip().lower() != 'yes':
                print_colored("Cancelled.", COLORS.YELLOW)
                continue
            SC.clear_syllabus(current['id'])
            reload_paper_cache()
            print_colored("[✓] Syllabus cleared.", COLORS.GREEN)

        # ==============================================================
        # c. Chapters submenu
        # ==============================================================
        elif choice == "c":
            papers = SC.get_papers(active_only=False, syllabus_id=current['id'])
            chapters_submenu(SC, reload_paper_cache, papers)

        # ==============================================================
        # 0. Back
        # ==============================================================
        elif choice == "0":
            return

        else:
            print_colored("[!] Invalid option.", COLORS.RED)

def _manage_syllabi_submenu(SC, current_id):
    """
    Sub-submenu for CRUD on the syllabi themselves.
    Returns the id of the syllabus that should become 'current', or None.
    """
    from .file_manager import reload_paper_cache

    while True:
        syllabi = SC.get_syllabi(active_only=False)

        print()
        print_colored("  🗂️   MANAGE SYLLABI", COLORS.CYAN, bold=True)
        print_colored("  " + "─" * 62, COLORS.CYAN)

        if syllabi:
            for i, s in enumerate(syllabi, 1):
                n_papers = len(SC.get_papers(active_only=False, syllabus_id=s['id']))
                n_all    = len(SC.get_papers(active_only=False))
                lvl = f"  (L{s['level']})" if s.get('level') else ""
                marker = "  ← current" if s['id'] == current_id else ""
                print(f"  {i}. {s['display_name']}{lvl}  "
                      f"— {n_papers} paper(s){marker}")
        else:
            print_colored("  No syllabi yet.", COLORS.YELLOW)

        print_colored("  " + "─" * 62, COLORS.CYAN)
        print("   1. Add syllabus")
        print("   2. Edit syllabus")
        print("   3. Delete syllabus")
        print("   4. Reassign orphan papers to a syllabus")
        print("   0. Back")
        print_colored("  " + "─" * 62, COLORS.CYAN)

        choice = input(color_text("Choose: ", COLORS.MAGENTA)).strip()

        # ---------- 1. Add ----------
        if choice == "1":
            key = input("Syllabus key (lowercase, no spaces, e.g. l4_psc_kharidar): ").strip()
            if not key:
                continue
            if not key.replace("_", "").isalnum():
                print_colored("[!] Key must be alphanumeric.", COLORS.RED)
                continue
            if key in {s['syllabus_key'] for s in syllabi}:
                print_colored(f"[!] Key '{key}' already exists.", COLORS.RED)
                continue
            name = input("Display name (e.g. 'PSC Kharidar Level 4'): ").strip()
            if not name:
                print_colored("[!] Display name required.", COLORS.RED)
                continue
            level = input("Level (e.g. 4, 6, pretest — optional): ").strip() or None
            desc = input("Description (optional): ").strip() or None
            if SC.add_syllabus(key, name, level, desc):
                print_colored(f"[✓] Syllabus '{name}' added.", COLORS.GREEN)

        # ---------- 2. Edit ----------
        elif choice == "2":
            if not syllabi:
                print_colored("No syllabi to edit.", COLORS.YELLOW)
                continue
            for i, s in enumerate(syllabi, 1):
                print(f"  {i}. {s['display_name']}")
            si = input("Edit which? number (blank to cancel): ").strip()
            if not si.isdigit() or not (1 <= int(si) <= len(syllabi)):
                continue
            s = syllabi[int(si) - 1]
            print(f"\n  Current display name : {s['display_name']}")
            print(f"  Current level        : {s.get('level') or '(none)'}")
            print(f"  Current description  : {s.get('description') or '(none)'}")
            new_name = input("New display name (blank to keep): ").strip()
            new_lvl  = input("New level (blank to keep, 'clear' to blank): ").strip()
            new_desc = input("New description (blank to keep): ").strip()
            updates = {}
            if new_name: updates['display_name'] = new_name
            if new_lvl:
                updates['level'] = None if new_lvl.lower() == 'clear' else new_lvl
            if new_desc: updates['description'] = new_desc
            if not updates:
                print_colored("No changes.", COLORS.YELLOW)
                continue
            if SC.update_syllabus(s['id'], **updates):
                print_colored("[✓] Syllabus updated.", COLORS.GREEN)

        # ---------- 3. Delete ----------
        elif choice == "3":
            if not syllabi:
                print_colored("No syllabi to delete.", COLORS.YELLOW)
                continue
            for i, s in enumerate(syllabi, 1):
                n_papers = len(SC.get_papers(active_only=False, syllabus_id=s['id']))
                print(f"  {i}. {s['display_name']}  ({n_papers} papers)")
            si = input("Delete which? number (blank to cancel): ").strip()
            if not si.isdigit() or not (1 <= int(si) <= len(syllabi)):
                continue
            s = syllabi[int(si) - 1]
            n_papers = len(SC.get_papers(active_only=False, syllabus_id=s['id']))
            print_colored(
                f"[!] Deleting '{s['display_name']}' will also delete its "
                f"{n_papers} paper(s), subjects, and chapters.",
                COLORS.YELLOW,
            )
            print_colored(
                "[!] Questions stay in the DB but become 'unknown paper'.",
                COLORS.YELLOW,
            )
            if input("Type 'yes' to confirm: ").strip().lower() != 'yes':
                print_colored("Cancelled.", COLORS.YELLOW)
                continue
            try:
                if SC.delete_syllabus(s['id'], cascade_papers=True):
                    print_colored("[✓] Syllabus deleted.", COLORS.GREEN)
                    if s['id'] == current_id:
                        current_id = None
            except Exception as e:
                print_colored(f"[!] Delete failed: {e}", COLORS.RED)

        # ---------- 4. Reassign orphans ----------
        elif choice == "4":
            orphans = [p for p in SC.get_papers(active_only=False)
                       if p.get('syllabus_id') is None]
            if not orphans:
                print_colored("[i] No orphan papers — all papers have a syllabus.",
                              COLORS.GREEN)
                continue
            print()
            print_colored(f"  {len(orphans)} paper(s) with no syllabus:",
                          COLORS.YELLOW)
            for i, p in enumerate(orphans, 1):
                print(f"  {i}. [{p['paper_key']}] {p['display_name']}")

            if not syllabi:
                print_colored("[!] No syllabi exist yet. Add one first.", COLORS.RED)
                continue
            print()
            print("  Assign all of them to which syllabus?")
            for i, s in enumerate(syllabi, 1):
                print(f"  {i}. {s['display_name']}")
            print("  0. Cancel")
            ti = input("Choose: ").strip()
            if not ti.isdigit() or int(ti) == 0 or int(ti) > len(syllabi):
                continue
            target = syllabi[int(ti) - 1]
            if input(f"Assign {len(orphans)} paper(s) to '{target['display_name']}'? (y/n): "
                     ).strip().lower() != 'y':
                print_colored("Cancelled.", COLORS.YELLOW)
                continue
            for p in orphans:
                SC.update_paper(p['id'], syllabus_id=target['id'])
            print_colored(f"[✓] Reassigned {len(orphans)} paper(s).", COLORS.GREEN)
            reload_paper_cache()

        # ---------- 0. Back ----------
        elif choice == "0":
            return current_id

        else:
            print_colored("[!] Invalid option.", COLORS.RED)

def chapters_submenu(SC, reload_paper_cache, papers):
    """Nested menu for managing chapters under subjects (scoped to one syllabus)."""
    while True:
        print()
        print_colored("  📖 CHAPTER MANAGEMENT", COLORS.CYAN, bold=True)
        print_colored("  " + "─" * 46, COLORS.CYAN)
        print("   1. List chapters of a subject")
        print("   2. Add a chapter")
        print("   3. Edit a chapter")
        print("   4. Delete a chapter")
        print("   0. Back")
        choice = input(color_text("Choose: ", COLORS.MAGENTA)).strip()

        if choice == "0":
            return

        if not papers and choice in ("1", "2", "3", "4"):
            print_colored("No papers in this syllabus. Add a paper first.",
                          COLORS.YELLOW)
            continue

        # Common helper: pick paper → pick subject → return (paper, subject)
        def _pick_paper_and_subject():
            for i, p in enumerate(papers, 1):
                print(f"  {i}. {p['display_name']}")
            pi = input("Paper number (blank to cancel): ").strip()
            if not pi.isdigit() or not (1 <= int(pi) <= len(papers)):
                return None, None
            paper = papers[int(pi) - 1]
            subj_list = SC.get_subjects(paper_key=paper['paper_key'], active_only=False)
            if not subj_list:
                print_colored("No subjects in that paper.", COLORS.YELLOW)
                return None, None
            for i, s in enumerate(subj_list, 1):
                print(f"  {i}. [{s['chapter']}] {s['name']}")
            si = input("Subject number (blank to cancel): ").strip()
            if not si.isdigit() or not (1 <= int(si) <= len(subj_list)):
                return None, None
            return paper, subj_list[int(si) - 1]

        # ---------- 1. List ----------
        if choice == "1":
            _, subj = _pick_paper_and_subject()
            if not subj:
                continue
            chs = SC.get_chapters(subject_id=subj["id"], active_only=False)
            print(f"\n  Chapters of [{subj['chapter']}] {subj['name']}:")
            if not chs:
                print("    (none)")
            for c in chs:
                print(f"    [{c['chapter_code']}] {c['name']}")

        # ---------- 2. Add ----------
        elif choice == "2":
            _, subj = _pick_paper_and_subject()
            if not subj:
                continue
            code = input("Chapter code (e.g. 01, 02): ").strip()
            if not code:
                continue
            name = input("Chapter name: ").strip()
            if not name:
                continue
            desc = input("Description (optional): ").strip() or None
            if SC.add_chapter(subj["id"], code, name, description=desc):
                print_colored("[✓] Chapter added.", COLORS.GREEN)
                reload_paper_cache()

        # ---------- 3. Edit ----------
        elif choice == "3":
            _, subj = _pick_paper_and_subject()
            if not subj:
                continue
            chs = SC.get_chapters(subject_id=subj["id"], active_only=False)
            if not chs:
                print_colored("No chapters.", COLORS.YELLOW)
                continue
            for i, c in enumerate(chs, 1):
                print(f"  {i}. [{c['chapter_code']}] {c['name']}")
            ci = input("Chapter number (blank to cancel): ").strip()
            if not ci.isdigit() or not (1 <= int(ci) <= len(chs)):
                continue
            c = chs[int(ci) - 1]
            print(f"\n  Current name       : {c['name']}")
            print(f"  Current description: {c.get('description') or '(none)'}")
            new_name = input("New name (blank to keep): ").strip()
            new_desc = input("New description (blank to keep): ").strip()
            updates = {}
            if new_name: updates['name'] = new_name
            if new_desc: updates['description'] = new_desc
            if not updates:
                print_colored("No changes.", COLORS.YELLOW)
                continue
            if SC.update_chapter(c['id'], **updates):
                print_colored("[✓] Chapter updated.", COLORS.GREEN)
                reload_paper_cache()

        # ---------- 4. Delete ----------
        elif choice == "4":
            _, subj = _pick_paper_and_subject()
            if not subj:
                continue
            chs = SC.get_chapters(subject_id=subj["id"], active_only=False)
            if not chs:
                print_colored("No chapters.", COLORS.YELLOW)
                continue
            for i, c in enumerate(chs, 1):
                print(f"  {i}. [{c['chapter_code']}] {c['name']}")
            ci = input("Delete which chapter? number: ").strip()
            if not ci.isdigit() or not (1 <= int(ci) <= len(chs)):
                continue
            c = chs[int(ci) - 1]
            if input(f"Delete '{c['name']}'? (y/n): ").strip().lower() == 'y':
                if SC.delete_chapter(c['id']):
                    print_colored("[✓] Chapter deleted.", COLORS.GREEN)
                    reload_paper_cache()

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
