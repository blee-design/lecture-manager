# lecture_manager/dashboard.py

import os
import subprocess
import glob
from datetime import datetime
from collections import Counter
from .db import get_connection, TABLE_NAME
from .file_manager import ROOT_DIR, collect_tally_data, PAPER_CONFIG, show_paper_breakdown
from .utils import print_colored, color_text, COLORS

def get_storage_usage(path):
    """Get total size of a directory in human-readable format."""
    try:
        result = subprocess.run(['du', '-sh', path], capture_output=True, text=True)
        return result.stdout.split()[0] if result.returncode == 0 else "N/A"
    except Exception:
        return "N/A"

def get_paper_sizes():
    """
    Return a dict mapping paper folder name to its size (human-readable).
    """
    sizes = {}
    for paper_key, config in PAPER_CONFIG.items():
        folder = config['folder']
        full_path = os.path.join(ROOT_DIR, folder)
        if os.path.exists(full_path):
            sizes[folder] = get_storage_usage(full_path)
        else:
            sizes[folder] = "0B"
    return sizes

def get_file_type_counts():
    """
    Count video files by extension in the library.
    """
    exts = ('.mp4', '.mkv', '.webm', '.avi', '.mov')
    counts = Counter()
    for root, _, files in os.walk(ROOT_DIR):
        for f in files:
            if f.lower().endswith(exts):
                ext = os.path.splitext(f)[1].lower()
                counts[ext] += 1
    return counts

def get_recent_records(limit=5):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(f"""
        SELECT id, video_id, syllabus_id, subject, lecturer, nepali_date, time
        FROM {TABLE_NAME}
        ORDER BY id DESC
        LIMIT %s
    """, (limit,))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return rows

def get_top_lecturers(limit=5):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(f"""
        SELECT lecturer, COUNT(*) as count
        FROM {TABLE_NAME}
        WHERE lecturer IS NOT NULL AND lecturer != ''
        GROUP BY lecturer
        ORDER BY count DESC
        LIMIT %s
    """, (limit,))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return rows

def get_subject_counts(limit=5):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(f"""
        SELECT subject, COUNT(*) as count
        FROM {TABLE_NAME}
        WHERE subject IS NOT NULL AND subject != ''
        GROUP BY subject
        ORDER BY count DESC
        LIMIT %s
    """, (limit,))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return rows

def show_dashboard():
    """Display a beautiful terminal dashboard with library statistics and paper breakdown."""
    print("\n" + "═" * 60)
    print_colored("  📊 LECTURE LIBRARY DASHBOARD", COLORS.CYAN, bold=True)
    print("═" * 60)

    # ----- Collect data -----
    tally = collect_tally_data()

    total_records = len(tally['records'])
    total_files = len(tally['all_files'])
    correctly_placed = len(tally['correctly_placed'])
    missing = len(tally['missing'])
    orphan = len(tally['orphan'])
    mismatched = len(tally['mismatched'])
    unresolved = tally['unresolved']

    # Storage usage (overall and per paper)
    storage = get_storage_usage(ROOT_DIR)
    paper_sizes = get_paper_sizes()
    file_counts = get_file_type_counts()

    # Recent lectures
    recent = get_recent_records(5)

    # Top lecturers
    top_lecturers = get_top_lecturers(5)

    # Top subjects
    top_subjects = get_subject_counts(5)

    # ----- Summary cards -----
    print("\n" + "─" * 60)
    print_colored("  📈 SUMMARY", COLORS.YELLOW, bold=True)
    print("─" * 60)

    # Row of stats
    print(f"  {color_text('Total Records:', COLORS.WHITE)} {color_text(str(total_records), COLORS.CYAN)}")
    print(f"  {color_text('Total Files:', COLORS.WHITE)} {color_text(str(total_files), COLORS.CYAN)}")
    print(f"  {color_text('✅ Correctly Placed:', COLORS.WHITE)} {color_text(str(correctly_placed), COLORS.GREEN)}")
    print(f"  {color_text('❌ Missing:', COLORS.WHITE)} {color_text(str(missing), COLORS.RED)}")
    print(f"  {color_text('🗑️ Orphan Files:', COLORS.WHITE)} {color_text(str(orphan), COLORS.YELLOW)}")
    if mismatched:
        print(f"  {color_text('⚠️ Mismatched:', COLORS.WHITE)} {color_text(str(mismatched), COLORS.YELLOW)}")
    if unresolved:
        print(f"  {color_text('❓ Unresolved Records:', COLORS.WHITE)} {color_text(str(unresolved), COLORS.MAGENTA)}")
    print(f"  {color_text('💾 Library Size:', COLORS.WHITE)} {color_text(storage, COLORS.BLUE)}")

    # Health indicator
    if missing == 0 and mismatched == 0 and unresolved == 0:
        print_colored("\n  ✅ Library is perfectly synced! All records have files in the right place.", COLORS.GREEN)
    else:
        print_colored("\n  ⚠️ Some issues detected – run option 19 (Tally) to investigate and fix.", COLORS.YELLOW)

    # ----- Paper storage breakdown -----
    if paper_sizes:
        print("\n" + "─" * 60)
        print_colored("  📁 STORAGE PER PAPER", COLORS.YELLOW, bold=True)
        print("─" * 60)
        for folder, size in paper_sizes.items():
            print(f"  {folder[:35]:<35} {size}")

    # ----- File type breakdown -----
    if file_counts:
        print("\n" + "─" * 60)
        print_colored("  🎬 FILE TYPES", COLORS.YELLOW, bold=True)
        print("─" * 60)
        total_ext = sum(file_counts.values())
        for ext, count in sorted(file_counts.items(), key=lambda x: -x[1]):
            pct = (count / total_ext * 100) if total_ext else 0
            bar = "█" * int(pct / 2)  # scale 50% -> 1 char
            print(f"  {ext:<6} {count:>4} files  {bar} {pct:.1f}%")

    # ----- Recent lectures -----
    if recent:
        print("\n" + "─" * 60)
        print_colored("  🕒 RECENTLY ADDED LECTURES", COLORS.YELLOW, bold=True)
        print("─" * 60)
        for rec in recent:
            date_str = rec.get('nepali_date', '') or ''
            time_str = rec.get('time', '') or ''
            lecturer = rec.get('lecturer', '') or ''
            subject = rec.get('subject', '') or ''
            print(f"  {rec['syllabus_id']} | {subject[:30]:<30} | {lecturer:<15} | {date_str} {time_str}")

    # ----- Top lecturers (with scaled bar) -----
    if top_lecturers:
        print("\n" + "─" * 60)
        print_colored("  👨‍🏫 TOP LECTURERS", COLORS.YELLOW, bold=True)
        print("─" * 60)
        max_count = max(c for _, c in top_lecturers) if top_lecturers else 1
        for lecturer, count in top_lecturers:
            bar_len = int((count / max_count) * 20)
            bar = "█" * bar_len
            print(f"  {lecturer[:20]:<20} {bar} {count}")

    # ----- Top subjects (with scaled bar) -----
    if top_subjects:
        print("\n" + "─" * 60)
        print_colored("  📚 TOP SUBJECTS", COLORS.YELLOW, bold=True)
        print("─" * 60)
        max_count = max(c for _, c in top_subjects) if top_subjects else 1
        for subject, count in top_subjects:
            bar_len = int((count / max_count) * 20)
            bar = "█" * bar_len
            print(f"  {subject[:25]:<25} {bar} {count}")

    # ----- Facebook stats -----
    from .file_manager import collect_facebook_tally_data
    fb_tally = collect_facebook_tally_data()
    if fb_tally['total_entries'] > 0 or fb_tally['orphan'] or fb_tally['missing']:
        print("\n" + "─" * 60)
        print_colored("  📘 FACEBOOK", COLORS.MAGENTA, bold=True)
        print("─" * 60)
        print(f"  Total entries  : {fb_tally['total_entries']} (videos: {fb_tally['by_type']['video']}, photos: {fb_tally['by_type']['photo']})")
        print(f"  Files on disk  : {len(fb_tally['files_found'])}")
        if fb_tally['missing']:
            print_colored(f"  ❌ Missing      : {len(fb_tally['missing'])} entries", COLORS.RED)
        if fb_tally['orphan']:
            print_colored(f"  🗑️ Orphan       : {len(fb_tally['orphan'])} files", COLORS.YELLOW)
        if not fb_tally['missing'] and not fb_tally['orphan']:
            print_colored("  ✅ All Facebook entries are synced!", COLORS.GREEN)

    # ===== NEW: PAPER BREAKDOWN =====
    # This will print the same table as Option 33.
    show_paper_breakdown()

    # ----- Final footer -----
    print("\n" + "═" * 60)
    print_colored("  Dashboard generated at " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"), COLORS.BLUE)
    print("═" * 60 + "\n")
