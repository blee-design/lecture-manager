# lecture_manager/dashboard.py

import os
import re
import subprocess
from datetime import datetime
from collections import Counter
from .db import get_connection, TABLE_NAME
from .file_manager import ROOT_DIR, collect_tally_data, show_paper_breakdown, collect_facebook_tally_data, _papers
from .utils import print_colored, color_text, COLORS

# Box drawing helpers
BOX_WIDTH = 72
_ANSI_RE = re.compile(r'\x1b\[[0-9;]*m')


def _visible_len(s):
    return len(_ANSI_RE.sub('', s))


def _box_header(title):
    prefix = f"╭─ {title} "
    remaining = BOX_WIDTH - _visible_len(prefix) - 1
    if remaining < 2:
        remaining = 2
    return prefix + "─" * remaining + "╮"


def _box_footer():
    return "╰" + "─" * (BOX_WIDTH - 2) + "╯"


def _box_line(content=""):
    padding = BOX_WIDTH - 4 - _visible_len(content)
    if padding < 0:
        padding = 0
    return f"│ {content}{' ' * padding} │"


def _box_blank():
    return "│" + " " * (BOX_WIDTH - 2) + "│"


def get_storage_usage(path):
    """Get total size of a directory in human-readable format."""
    try:
        result = subprocess.run(['du', '-sh', path], capture_output=True, text=True)
        return result.stdout.split()[0] if result.returncode == 0 else "N/A"
    except Exception:
        return "N/A"


def get_paper_sizes():
    """Return {display_name: human-readable size} using dynamic papers."""
    sizes = {}
    for key, cfg in _papers().items():
        folder = cfg.get('folder_name', '')
        display = cfg.get('display_name', folder or key)
        if not folder:
            continue
        full_path = os.path.join(ROOT_DIR, folder)
        sizes[display] = get_storage_usage(full_path) if os.path.exists(full_path) else "0B"
    return sizes


def get_file_type_counts():
    """Count video files by extension in the library."""
    exts = ('.mp4', '.mkv', '.webm', '.avi', '.mov')
    counts = Counter()
    for root, _, files in os.walk(ROOT_DIR):
        for f in files:
            if f.lower().endswith(exts):
                counts[os.path.splitext(f)[1].lower()] += 1
    return counts


def get_recent_records(limit=5):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(f"""
        SELECT id, video_id, syllabus_id, subject, chapter, lecturer, nepali_date, time
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
        SELECT lecturer, COUNT(*) AS count
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
        SELECT subject, COUNT(*) AS count
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


def _bar(pct, width=24, fill='█', empty='░'):
    """Render a proportional bar, pct in 0..100."""
    filled = int(round((pct / 100.0) * width))
    filled = max(0, min(width, filled))
    return fill * filled + empty * (width - filled)


def show_dashboard():
    """Display a beautiful terminal dashboard with library statistics."""

    # ---------- Collect data once ----------
    tally = collect_tally_data()

    total_records = len(tally['records'])
    total_files = len(tally['all_files'])
    correctly_placed = len(tally['correctly_placed'])
    missing = len(tally['missing'])
    orphan = len(tally['orphan'])
    mismatched = len(tally['mismatched'])
    unresolved = tally['unresolved']

    storage = get_storage_usage(ROOT_DIR)
    paper_sizes = get_paper_sizes()
    file_counts = get_file_type_counts()
    recent = get_recent_records(5)
    top_lecturers = get_top_lecturers(5)
    top_subjects = get_subject_counts(5)

    # ---------- Title banner ----------
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    title = "📊  LECTURE LIBRARY DASHBOARD"
    left_pad = (BOX_WIDTH - len(title) - len(now) - 4)
    if left_pad < 4:
        left_pad = 4

    print()
    print("╔" + "═" * (BOX_WIDTH - 2) + "╗")
    title_line = f"  {title}{' ' * left_pad}{now}  "
    print("║" + title_line[:BOX_WIDTH - 2].ljust(BOX_WIDTH - 2) + "║")
    print("╚" + "═" * (BOX_WIDTH - 2) + "╝")
    print()

    # ---------- Quick stats (2 rows of 3) ----------
    print(_box_header("📈  QUICK STATS"))
    print(_box_blank())

    def stat_cell(label, value, color=COLORS.CYAN, ok=False):
        mark = "  ✓" if ok else ""
        return f"{label:<20}{color_text(str(value) + mark, color)}"

    print(_box_line(
        stat_cell("Total Records", total_records) + "     " +
        stat_cell("Total Files", total_files)
    ))
    print(_box_line(
        stat_cell("Correctly Placed", correctly_placed, COLORS.GREEN, ok=True) + "     " +
        stat_cell("Library Size", storage, COLORS.BLUE)
    ))
    print(_box_blank())

    missing_cell = stat_cell("Missing", missing, COLORS.RED if missing else COLORS.GREEN)
    orphan_cell = stat_cell("Orphan", orphan, COLORS.YELLOW if orphan else COLORS.GREEN)
    print(_box_line(missing_cell + "     " + orphan_cell))

    mismatched_cell = stat_cell("Mismatched", mismatched,
                                COLORS.YELLOW if mismatched else COLORS.GREEN)
    unresolved_cell = stat_cell("Unresolved", unresolved,
                                COLORS.MAGENTA if unresolved else COLORS.GREEN)
    print(_box_line(mismatched_cell + "     " + unresolved_cell))
    print(_box_blank())

    # Health summary
    if missing == 0 and mismatched == 0 and unresolved == 0 and orphan == 0:
        health = color_text("✅  Library is perfectly synced.", COLORS.GREEN)
    else:
        health = color_text("⚠️  Run Tally (menu 3 → 5) to investigate issues.", COLORS.YELLOW)
    print(_box_line(health))
    print(_box_blank())
    print(_box_footer())
    print()

    # ---------- Storage per paper ----------
    if paper_sizes:
        print(_box_header("📁  STORAGE PER PAPER"))
        print(_box_blank())
        for folder, size in paper_sizes.items():
            name = folder if len(folder) <= 52 else folder[:49] + "..."
            content = f"{name:<54}{color_text(size, COLORS.BLUE)}"
            print(_box_line(content))
        print(_box_blank())
        print(_box_footer())
        print()

    # ---------- File types ----------
    if file_counts:
        total_ext = sum(file_counts.values())
        print(_box_header("🎬  FILE TYPES"))
        print(_box_blank())
        for ext, count in sorted(file_counts.items(), key=lambda x: -x[1]):
            pct = (count / total_ext * 100) if total_ext else 0
            bar = _bar(pct, width=24)
            line = f"{ext:<6} {count:>5} files  {color_text(bar, COLORS.CYAN)}  {pct:5.1f}%"
            print(_box_line(line))
        print(_box_blank())
        print(_box_footer())
        print()

    # ---------- Recent lectures ----------
    if recent:
        print(_box_header("🕒  RECENTLY ADDED LECTURES"))
        print(_box_blank())
        for rec in recent:
            syllabus = (rec.get('syllabus_id') or '')[:12]
            subject = (rec.get('subject') or '')[:28]
            lecturer = (rec.get('lecturer') or '')[:16]
            date_str = rec.get('nepali_date') or ''
            time_str = rec.get('time') or ''
            line = f"{syllabus:<12}  {subject:<28}  {lecturer:<16}  {date_str} {time_str}"
            if _visible_len(line) > BOX_WIDTH - 4:
                line = line[:BOX_WIDTH - 5]
            print(_box_line(line))
        print(_box_blank())
        print(_box_footer())
        print()

    # ---------- Top lecturers ----------
    if top_lecturers:
        print(_box_header("👨‍🏫  TOP LECTURERS"))
        print(_box_blank())
        max_count = max(c for _, c in top_lecturers) or 1
        for lecturer, count in top_lecturers:
            name = (lecturer or '')[:22]
            pct = count / max_count * 100
            bar = _bar(pct, width=20)
            line = f"{name:<22}  {color_text(bar, COLORS.MAGENTA)}  {count}"
            print(_box_line(line))
        print(_box_blank())
        print(_box_footer())
        print()

    # ---------- Top subjects ----------
    if top_subjects:
        print(_box_header("📚  TOP SUBJECTS"))
        print(_box_blank())
        max_count = max(c for _, c in top_subjects) or 1
        for subject, count in top_subjects:
            name = (subject or '')[:34]
            pct = count / max_count * 100
            bar = _bar(pct, width=16)
            line = f"{name:<34}  {color_text(bar, COLORS.GREEN)}  {count}"
            print(_box_line(line))
        print(_box_blank())
        print(_box_footer())
        print()

    # ---------- Facebook ----------
    fb_tally = collect_facebook_tally_data()
    if fb_tally['total_entries'] > 0 or fb_tally['orphan'] or fb_tally['missing']:
        print(_box_header("📘  FACEBOOK"))
        print(_box_blank())
        print(_box_line(f"  Entries : {fb_tally['total_entries']}  "
                        f"(videos: {fb_tally['by_type']['video']}, "
                        f"photos: {fb_tally['by_type']['photo']})"))
        print(_box_line(f"  Files   : {len(fb_tally['files_found'])} on disk"))
        if fb_tally['missing']:
            print(_box_line(color_text(f"  ❌ Missing: {len(fb_tally['missing'])} entries", COLORS.RED)))
        if fb_tally['orphan']:
            print(_box_line(color_text(f"  🗑️  Orphan: {len(fb_tally['orphan'])} files", COLORS.YELLOW)))
        if not fb_tally['missing'] and not fb_tally['orphan']:
            print(_box_line(color_text("  ✅ All synced.", COLORS.GREEN)))
        print(_box_blank())
        print(_box_footer())
        print()

    # ---------- Paper breakdown (existing, shared tally) ----------
    show_paper_breakdown(tally_data=tally)

    # ---------- Footer ----------
    print()
    print_colored(f"  Dashboard generated at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", COLORS.BLUE)
    print()
