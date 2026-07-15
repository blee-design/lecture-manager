# File export.py

import os
import csv
import json
from .db import get_connection, TABLE_NAME
from .youtube import extract_video_id
from .utils import clean_field, get_display_title, print_colored, color_text, COLORS

# ----- Helper: get export data (full or basic) -----
def get_export_data(full=False):
    conn = get_connection()
    cursor = conn.cursor()

    if full:
        columns = [
            'video_id', 'mirror_video_id', 'video_title', 'syllabus_id',
            'subject', 'chapter', 'lecturer', 'nepali_date', 'time',
            'notes', 'file_hash', 'original_filename', 'paper',
            'youtube_upload_id', 'youtube_upload_status'
        ]
    else:
        columns = [
            'video_id', 'mirror_video_id', 'video_title', 'syllabus_id',
            'subject', 'chapter', 'lecturer', 'nepali_date', 'time', 'notes'
        ]

    query = f"SELECT {', '.join(columns)} FROM {TABLE_NAME} ORDER BY nepali_date DESC, time DESC"
    cursor.execute(query)
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return rows

def _get_export_columns(full=False):
    if full:
        return ['video_id', 'mirror_video_id', 'video_title', 'syllabus_id',
                'subject', 'chapter', 'lecturer', 'nepali_date', 'time',
                'notes', 'file_hash', 'original_filename', 'paper',
                'youtube_upload_id', 'youtube_upload_status']
    else:
        return ['video_id', 'mirror_video_id', 'video_title', 'syllabus_id',
                'subject', 'chapter', 'lecturer', 'nepali_date', 'time', 'notes']

def export_csv():
    print("\n" + "═" * 50)
    print_colored("  EXPORT TO CSV", COLORS.CYAN, bold=True)
    print("═" * 50)
    print("Do you want to export all columns (full backup) or basic columns?")
    print("  (b) Basic  - video_id, mirror, title, syllabus, subject, chapter, lecturer, date, time, notes")
    print("  (f) Full   - all columns including file_hash, original_filename, paper, YouTube upload data")
    choice = input(color_text("Choose (b/f, default b): ", COLORS.MAGENTA)).strip().lower()
    full = (choice == 'f')

    rows = get_export_data(full=full)
    if not rows:
        print_colored("[i] No records to export.", COLORS.YELLOW)
        return

    suffix = "-full" if full else "-basic"
    default_name = f"lectures_export{suffix}.csv"
    filename = input(color_text(f"Enter CSV filename (default: {default_name}): ", COLORS.MAGENTA)).strip()
    if not filename:
        filename = default_name
    if not filename.endswith('.csv'):
        filename += '.csv'

    columns = _get_export_columns(full)
    try:
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(columns)
            writer.writerows(rows)
        print_colored(f"[✓] Exported {len(rows)} records to {filename}", COLORS.GREEN)
    except Exception as e:
        print_colored(f"[!] Export failed: {e}", COLORS.RED)

def export_json():
    print("\n" + "═" * 50)
    print_colored("  EXPORT TO JSON", COLORS.CYAN, bold=True)
    print("═" * 50)
    print("Do you want to export all columns (full backup) or basic columns?")
    print("  (b) Basic  - video_id, mirror, title, syllabus, subject, chapter, lecturer, date, time, notes")
    print("  (f) Full   - all columns including file_hash, original_filename, paper, YouTube upload data")
    choice = input(color_text("Choose (b/f, default b): ", COLORS.MAGENTA)).strip().lower()
    full = (choice == 'f')

    rows = get_export_data(full=full)
    if not rows:
        print_colored("[i] No records to export.", COLORS.YELLOW)
        return

    suffix = "-full" if full else "-basic"
    default_name = f"lectures_export{suffix}.json"
    filename = input(color_text(f"Enter JSON filename (default: {default_name}): ", COLORS.MAGENTA)).strip()
    if not filename:
        filename = default_name
    if not filename.endswith('.json'):
        filename += '.json'

    columns = _get_export_columns(full)
    data = [dict(zip(columns, row)) for row in rows]

    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print_colored(f"[✓] Exported {len(rows)} records to {filename}", COLORS.GREEN)
    except Exception as e:
        print_colored(f"[!] Export failed: {e}", COLORS.RED)

def _clean_val(val):
    if val is None:
        return None
    if isinstance(val, str):
        stripped = val.strip()
        return stripped if stripped else None
    return val

def _import_rows(rows, format_name):
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

    for item in rows:
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

        mirror_video_id = _clean_val(item.get('mirror_video_id'))
        video_title = _clean_val(item.get('video_title'))
        syllabus_id = _clean_val(item.get('syllabus_id'))
        subject = _clean_val(item.get('subject'))
        chapter = _clean_val(item.get('chapter'))
        lecturer = _clean_val(item.get('lecturer'))
        nepali_date = _clean_val(item.get('nepali_date'))
        time_val = _clean_val(item.get('time'))
        notes = _clean_val(item.get('notes'))
        file_hash = _clean_val(item.get('file_hash'))
        original_filename = _clean_val(item.get('original_filename'))
        paper = _clean_val(item.get('paper'))
        youtube_upload_id = _clean_val(item.get('youtube_upload_id'))
        youtube_upload_status = _clean_val(item.get('youtube_upload_status'))

        if exists:
            if choice == '1':
                skipped += 1
                continue
            elif choice == '2':
                update_fields = []
                params = []
                for key, val in [
                    ('mirror_video_id', mirror_video_id),
                    ('video_title', video_title),
                    ('syllabus_id', syllabus_id),
                    ('subject', subject),
                    ('chapter', chapter),
                    ('lecturer', lecturer),
                    ('nepali_date', nepali_date),
                    ('time', time_val),
                    ('notes', notes),
                    ('file_hash', file_hash),
                    ('original_filename', original_filename),
                    ('paper', paper),
                    ('youtube_upload_id', youtube_upload_id),
                    ('youtube_upload_status', youtube_upload_status),
                ]:
                    if val is not None:
                        update_fields.append(f"{key} = %s")
                        params.append(val)
                if not update_fields:
                    skipped += 1
                    continue
                params.append(video_id)
                sql = f"UPDATE {TABLE_NAME} SET {', '.join(update_fields)} WHERE video_id = %s"
                cursor.execute(sql, params)
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
            insert_fields = [
                'video_id', 'mirror_video_id', 'video_title', 'syllabus_id',
                'subject', 'chapter', 'lecturer', 'nepali_date', 'time',
                'notes', 'file_hash', 'original_filename', 'paper',
                'youtube_upload_id', 'youtube_upload_status'
            ]
            values = [
                video_id, mirror_video_id, video_title, syllabus_id,
                subject, chapter, lecturer, nepali_date, time_val,
                notes, file_hash, original_filename, paper,
                youtube_upload_id, youtube_upload_status
            ]
            placeholders = ','.join(['%s'] * len(insert_fields))
            sql = f"INSERT INTO {TABLE_NAME} ({', '.join(insert_fields)}) VALUES ({placeholders})"
            cursor.execute(sql, values)
            added += 1

    conn.commit()
    cursor.close()
    conn.close()
    print_colored(f"[✓] Import complete: {added} added, {updated} updated, {skipped} skipped.", COLORS.GREEN)

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

    _import_rows(rows, "CSV")

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

    _import_rows(data, "JSON")
