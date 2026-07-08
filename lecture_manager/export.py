# File export.py

import os
import csv
import json
from .db import get_connection, TABLE_NAME
from .youtube import extract_video_id
from .utils import clean_field, get_display_title, print_colored, color_text, COLORS

def get_export_data():
    choice = input(color_text("Export all records? (y/n, n = search results): ", COLORS.MAGENTA)).strip().lower()
    if choice == 'y':
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(f"""
            SELECT video_id, mirror_video_id, video_title, syllabus_id, subject, chapter, lecturer, nepali_date, time, notes
            FROM {TABLE_NAME}
            ORDER BY nepali_date DESC, time DESC
        """)
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return rows
    else:
        query = input(color_text("Enter search term (or leave empty for all): ", COLORS.MAGENTA)).strip()
        conn = get_connection()
        cursor = conn.cursor()
        if query:
            sql = f"""
                SELECT video_id, mirror_video_id, video_title, syllabus_id, subject, chapter, lecturer, nepali_date, time, notes
                FROM {TABLE_NAME}
                WHERE syllabus_id LIKE %s OR subject LIKE %s OR chapter LIKE %s
                   OR lecturer LIKE %s OR nepali_date LIKE %s OR time LIKE %s
                   OR video_id LIKE %s OR mirror_video_id LIKE %s OR video_title LIKE %s OR notes LIKE %s
                ORDER BY nepali_date DESC, time DESC
            """
            like = f"%{query}%"
            params = (like, like, like, like, like, like, like, like, like, like)
            cursor.execute(sql, params)
        else:
            cursor.execute(f"""
                SELECT video_id, mirror_video_id, video_title, syllabus_id, subject, chapter, lecturer, nepali_date, time, notes
                FROM {TABLE_NAME}
                ORDER BY nepali_date DESC, time DESC
            """)
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return rows

def export_csv():
    print("\n" + "═" * 50)
    print_colored("  EXPORT TO CSV", COLORS.CYAN, bold=True)
    print("═" * 50)
    rows = get_export_data()
    if not rows:
        print_colored("[i] No records to export.", COLORS.YELLOW)
        return
    filename = input(color_text("Enter CSV filename (default: lectures_export.csv): ", COLORS.MAGENTA)).strip()
    if not filename:
        filename = "lectures_export.csv"
    if not filename.endswith('.csv'):
        filename += '.csv'

    try:
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['video_id', 'mirror_video_id', 'video_title', 'syllabus_id',
                             'subject', 'chapter', 'lecturer', 'nepali_date', 'time', 'notes'])
            writer.writerows(rows)
        print_colored(f"[✓] Exported {len(rows)} records to {filename}", COLORS.GREEN)
    except Exception as e:
        print_colored(f"[!] Export failed: {e}", COLORS.RED)

def export_json():
    print("\n" + "═" * 50)
    print_colored("  EXPORT TO JSON", COLORS.CYAN, bold=True)
    print("═" * 50)
    rows = get_export_data()
    if not rows:
        print_colored("[i] No records to export.", COLORS.YELLOW)
        return
    filename = input(color_text("Enter JSON filename (default: lectures_export.json): ", COLORS.MAGENTA)).strip()
    if not filename:
        filename = "lectures_export.json"
    if not filename.endswith('.json'):
        filename += '.json'

    columns = ['video_id', 'mirror_video_id', 'video_title', 'syllabus_id',
               'subject', 'chapter', 'lecturer', 'nepali_date', 'time', 'notes']
    data = [dict(zip(columns, row)) for row in rows]

    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print_colored(f"[✓] Exported {len(rows)} records to {filename}", COLORS.GREEN)
    except Exception as e:
        print_colored(f"[!] Export failed: {e}", COLORS.RED)

def import_csv():
    print("\n" + "═" * 50)
    print_colored("  IMPORT FROM CSV", COLORS.CYAN, bold=True)
    print("═" * 50)
    filename = input(color_text("Enter CSV filename: ", COLORS.MAGENTA)).strip()
    if not filename:
        print_colored("[!] No filename given.", COLORS.RED)
        return
    if not os.path.exists(filename):
        print_colored(f"[!] File {filename} not found.", COLORS.RED)
        return

    try:
        with open(filename, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
    except Exception as e:
        print_colored(f"[!] Failed to read CSV: {e}", COLORS.RED)
        return

    if not rows:
        print_colored("[i] No data found.", COLORS.YELLOW)
        return

    print(f"Found {len(rows)} records. How to handle duplicates?")
    print("  1. Skip duplicates (keep existing)")
    print("  2. Update existing records")
    print("  3. Abort on any duplicate")
    choice = input(color_text("Choose (1-3): ", COLORS.MAGENTA)).strip()
    if choice not in ('1', '2', '3'):
        print_colored("[!] Invalid choice. Aborting.", COLORS.RED)
        return

    conn = get_connection()
    cursor = conn.cursor()
    added = 0
    updated = 0
    skipped = 0

    for row in rows:
        video_id = row.get('video_id', '').strip()
        if not video_id or not extract_video_id(video_id):
            print_colored(f"[!] Invalid video_id '{video_id}', skipping.", COLORS.YELLOW)
            skipped += 1
            continue

        cursor.execute(f"SELECT id FROM {TABLE_NAME} WHERE video_id = %s", (video_id,))
        exists = cursor.fetchone()

        if exists:
            if choice == '1':
                skipped += 1
                continue
            elif choice == '2':
                mirror_id = row.get('mirror_video_id', '').strip() or None
                video_title = row.get('video_title', '').strip() or None
                syllabus_id = row.get('syllabus_id', '').strip() or None
                subject = row.get('subject', '').strip() or None
                chapter = row.get('chapter', '').strip() or None
                lecturer = row.get('lecturer', '').strip() or None
                nepali_date = row.get('nepali_date', '').strip() or None
                time_val = row.get('time', '').strip() or None
                notes = row.get('notes', '').strip() or None

                cursor.execute(f"""
                    UPDATE {TABLE_NAME}
                    SET mirror_video_id = %s, video_title = %s, syllabus_id = %s,
                        subject = %s, chapter = %s, lecturer = %s, nepali_date = %s, time = %s, notes = %s
                    WHERE video_id = %s
                """, (mirror_id, video_title, syllabus_id, subject, chapter, lecturer, nepali_date, time_val, notes, video_id))
                updated += 1
                continue
            else:
                print_colored(f"[!] Duplicate video_id {video_id}, aborting.", COLORS.RED)
                conn.rollback()
                cursor.close()
                conn.close()
                print("Import aborted.")
                return
        else:
            mirror_id = row.get('mirror_video_id', '').strip() or None
            video_title = row.get('video_title', '').strip() or None
            syllabus_id = row.get('syllabus_id', '').strip() or None
            subject = row.get('subject', '').strip() or None
            chapter = row.get('chapter', '').strip() or None
            lecturer = row.get('lecturer', '').strip() or None
            nepali_date = row.get('nepali_date', '').strip() or None
            time_val = row.get('time', '').strip() or None
            notes = row.get('notes', '').strip() or None

            cursor.execute(f"""
                INSERT INTO {TABLE_NAME}
                (video_id, mirror_video_id, video_title, syllabus_id, subject, chapter, lecturer, nepali_date, time, notes)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (video_id, mirror_id, video_title, syllabus_id, subject, chapter, lecturer, nepali_date, time_val, notes))
            added += 1

    conn.commit()
    cursor.close()
    conn.close()
    print_colored(f"[✓] Import complete: {added} added, {updated} updated, {skipped} skipped.", COLORS.GREEN)

def import_json():
    print("\n" + "═" * 50)
    print_colored("  IMPORT FROM JSON", COLORS.CYAN, bold=True)
    print("═" * 50)
    filename = input(color_text("Enter JSON filename: ", COLORS.MAGENTA)).strip()
    if not filename:
        print_colored("[!] No filename given.", COLORS.RED)
        return
    if not os.path.exists(filename):
        print_colored(f"[!] File {filename} not found.", COLORS.RED)
        return

    try:
        with open(filename, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print_colored(f"[!] Failed to read JSON: {e}", COLORS.RED)
        return

    if not isinstance(data, list):
        print_colored("[!] JSON must be a list of objects.", COLORS.RED)
        return
    if not data:
        print_colored("[i] No data found.", COLORS.YELLOW)
        return

    print(f"Found {len(data)} records. How to handle duplicates?")
    print("  1. Skip duplicates (keep existing)")
    print("  2. Update existing records")
    print("  3. Abort on any duplicate")
    choice = input(color_text("Choose (1-3): ", COLORS.MAGENTA)).strip()
    if choice not in ('1', '2', '3'):
        print_colored("[!] Invalid choice. Aborting.", COLORS.RED)
        return

    conn = get_connection()
    cursor = conn.cursor()
    added = 0
    updated = 0
    skipped = 0

    for item in data:
        if not isinstance(item, dict):
            print_colored("[!] Item is not a dict, skipping.", COLORS.YELLOW)
            skipped += 1
            continue

        video_id = item.get('video_id', '').strip()
        if not video_id or not extract_video_id(video_id):
            print_colored(f"[!] Invalid video_id '{video_id}', skipping.", COLORS.YELLOW)
            skipped += 1
            continue

        cursor.execute(f"SELECT id FROM {TABLE_NAME} WHERE video_id = %s", (video_id,))
        exists = cursor.fetchone()

        # Helper to safely strip a value, returning None if empty or None
        def clean_val(val):
            if val is None:
                return None
            if isinstance(val, str):
                stripped = val.strip()
                return stripped if stripped else None
            return val

        mirror_id = clean_val(item.get('mirror_video_id'))
        video_title = clean_val(item.get('video_title'))
        syllabus_id = clean_val(item.get('syllabus_id'))
        subject = clean_val(item.get('subject'))
        chapter = clean_val(item.get('chapter'))
        lecturer = clean_val(item.get('lecturer'))
        nepali_date = clean_val(item.get('nepali_date'))
        time_val = clean_val(item.get('time'))
        notes = clean_val(item.get('notes'))

        if exists:
            if choice == '1':
                skipped += 1
                continue
            elif choice == '2':
                cursor.execute(f"""
                    UPDATE {TABLE_NAME}
                    SET mirror_video_id = %s, video_title = %s, syllabus_id = %s,
                        subject = %s, chapter = %s, lecturer = %s, nepali_date = %s, time = %s, notes = %s
                    WHERE video_id = %s
                """, (mirror_id, video_title, syllabus_id, subject, chapter, lecturer, nepali_date, time_val, notes, video_id))
                updated += 1
                continue
            else:  # choice == 3
                print_colored(f"[!] Duplicate video_id {video_id}, aborting.", COLORS.RED)
                conn.rollback()
                cursor.close()
                conn.close()
                print("Import aborted.")
                return
        else:
            cursor.execute(f"""
                INSERT INTO {TABLE_NAME}
                (video_id, mirror_video_id, video_title, syllabus_id, subject, chapter, lecturer, nepali_date, time, notes)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (video_id, mirror_id, video_title, syllabus_id, subject, chapter, lecturer, nepali_date, time_val, notes))
            added += 1

    conn.commit()
    cursor.close()
    conn.close()
    print_colored(f"[✓] Import complete: {added} added, {updated} updated, {skipped} skipped.", COLORS.GREEN)
