import os
import csv
import json
from datetime import datetime, date
from .db import get_connection
from .utils import print_colored, COLORS, color_text, resolve_export_path, resolve_import_path, export_default_hint

def export_pomodoro_json():
    print("\n" + "═" * 50)
    print_colored("  EXPORT POMODORO DATA TO JSON", COLORS.CYAN, bold=True)
    print("═" * 50)

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM pomodoro_tasks")
    tasks = cursor.fetchall()
    cursor.execute("SELECT * FROM pomodoro_log")
    logs = cursor.fetchall()
    cursor.close(); conn.close()

    if not tasks and not logs:
        print_colored("[i] No Pomodoro data to export.", COLORS.YELLOW)
        return

    default_name = "pomodoro_export.json"
    hint = export_default_hint('pomodoro', default_name)
    filename = input(color_text(f"Enter JSON filename (default: {hint}): ", COLORS.MAGENTA)).strip()
    if not filename: filename = default_name
    if not filename.endswith('.json'): filename += '.json'
    filename = resolve_export_path(filename, 'pomodoro')

    def serialize_dt(obj):
        if isinstance(obj, (datetime, date)): return obj.isoformat()
        raise TypeError("Type not serializable")

    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump({"tasks": tasks, "logs": logs}, f, indent=2, default=serialize_dt)
        print_colored(f"[✓] Exported {len(tasks)} tasks and {len(logs)} logs to {filename}", COLORS.GREEN)
    except Exception as e:
        print_colored(f"[!] Export failed: {e}", COLORS.RED)

def export_pomodoro_csv():
    print("\n" + "═" * 50)
    print_colored("  EXPORT POMODORO LOGS TO CSV", COLORS.CYAN, bold=True)
    print("═" * 50)

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT l.id, l.timestamp, l.phase, l.duration_min, COALESCE(s.name, l.subject) as subject,
               l.session_type, l.notes, t.task_text, l.pause_count, l.pause_total_sec
        FROM pomodoro_log l
        LEFT JOIN pomodoro_tasks t ON l.task_id = t.id
        LEFT JOIN subjects s ON l.subject_id = s.id
        ORDER BY l.timestamp
    """)
    logs = cursor.fetchall()
    cursor.close(); conn.close()

    if not logs:
        print_colored("[i] No Pomodoro logs to export.", COLORS.YELLOW)
        return

    default_name = "pomodoro_logs.csv"
    hint = export_default_hint('pomodoro', default_name)
    filename = input(color_text(f"Enter CSV filename (default: {hint}): ", COLORS.MAGENTA)).strip()
    if not filename: filename = default_name
    if not filename.endswith('.csv'): filename += '.csv'
    filename = resolve_export_path(filename, 'pomodoro')

    fieldnames = ['id', 'timestamp', 'phase', 'duration_min', 'subject', 'session_type', 'notes', 'task_text', 'pause_count', 'pause_total_sec']

    try:
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(logs)
        print_colored(f"[✓] Exported {len(logs)} logs to {filename}", COLORS.GREEN)
    except Exception as e:
        print_colored(f"[!] Export failed: {e}", COLORS.RED)

def import_pomodoro_json():
    print("\n" + "═" * 50)
    print_colored("  IMPORT POMODORO DATA FROM JSON", COLORS.CYAN, bold=True)
    print("═" * 50)

    raw = input(color_text("Enter JSON filename: ", COLORS.MAGENTA)).strip()
    if not raw: return
    filename = resolve_import_path(raw, 'pomodoro')
    if not os.path.exists(filename):
        print_colored(f"[!] File {filename} not found.", COLORS.RED)
        return

    try:
        with open(filename, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print_colored(f"[!] Failed to read JSON: {e}", COLORS.RED)
        return

    tasks, logs = data.get('tasks', []), data.get('logs', [])
    if not tasks and not logs:
        print_colored("[i] No data found in JSON.", COLORS.YELLOW)
        return

    print(f"\nFound {len(tasks)} tasks and {len(logs)} logs.")
    print("  1. Skip duplicates  2. Overwrite duplicates  3. Abort on duplicate")
    choice = input(color_text("Choose (1-3, default 1): ", COLORS.MAGENTA)).strip() or '1'

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    added_t = updated_t = skipped_t = added_l = updated_l = skipped_l = 0

    try:
        # Import Tasks
        for t in tasks:
            cursor.execute("SELECT id FROM pomodoro_tasks WHERE id = %s", (t['id'],))
            if cursor.fetchone():
                if choice == '1': skipped_t += 1; continue
                elif choice == '2':
                    cursor.execute("UPDATE pomodoro_tasks SET task_text=%s, priority=%s, completed=%s WHERE id=%s", (t['task_text'], t.get('priority',3), t.get('completed',False), t['id']))
                    updated_t += 1
                else: raise Exception(f"Duplicate task ID {t['id']}")
            else:
                cursor.execute("INSERT INTO pomodoro_tasks (id, task_text, priority, completed) VALUES (%s, %s, %s, %s)", (t['id'], t['task_text'], t.get('priority',3), t.get('completed',False)))
                added_t += 1

        # Import Logs
        for l in logs:
            cursor.execute("SELECT id FROM pomodoro_log WHERE id = %s", (l['id'],))
            if cursor.fetchone():
                if choice == '1': skipped_l += 1; continue
                elif choice == '2':
                    cursor.execute("""
                        UPDATE pomodoro_log SET timestamp=%s, phase=%s, duration_min=%s, subject=%s, subject_id=%s, notes=%s, task_id=%s, session_type=%s WHERE id=%s
                    """, (l['timestamp'], l['phase'], l['duration_min'], l.get('subject'), l.get('subject_id'), l.get('notes'), l.get('task_id'), l.get('session_type'), l['id']))
                    updated_l += 1
                else: raise Exception(f"Duplicate log ID {l['id']}")
            else:
                cursor.execute("""
                    INSERT INTO pomodoro_log (id, timestamp, phase, duration_min, subject, subject_id, notes, task_id, session_type)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (l['id'], l['timestamp'], l['phase'], l['duration_min'], l.get('subject'), l.get('subject_id'), l.get('notes'), l.get('task_id'), l.get('session_type')))
                added_l += 1
        conn.commit()
        print_colored(f"[✓] Tasks: {added_t} added, {updated_t} updated, {skipped_t} skipped.", COLORS.GREEN)
        print_colored(f"[✓] Logs : {added_l} added, {updated_l} updated, {skipped_l} skipped.", COLORS.GREEN)
    except Exception as e:
        conn.rollback()
        print_colored(f"[!] Import aborted: {e}", COLORS.RED)
    finally:
        cursor.close(); conn.close()

def import_pomodoro_csv():
    print("\n" + "═" * 50)
    print_colored("  IMPORT POMODORO LOGS FROM CSV", COLORS.CYAN, bold=True)
    print("═" * 50)

    raw = input(color_text("Enter CSV filename: ", COLORS.MAGENTA)).strip()
    if not raw: return
    filename = resolve_import_path(raw, 'pomodoro')
    if not os.path.exists(filename):
        print_colored(f"[!] File {filename} not found.", COLORS.RED)
        return

    try:
        with open(filename, 'r', encoding='utf-8') as f:
            logs = list(csv.DictReader(f))
    except Exception as e:
        print_colored(f"[!] Failed to read CSV: {e}", COLORS.RED)
        return

    if not logs:
        print_colored("[i] No data found in CSV.", COLORS.YELLOW)
        return

    print(f"\nFound {len(logs)} log rows.")
    print("  1. Skip duplicates  2. Overwrite duplicates  3. Abort on duplicate")
    choice = input(color_text("Choose (1-3, default 1): ", COLORS.MAGENTA)).strip() or '1'

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    added, updated, skipped = 0, 0, 0

    try:
        for l in logs:
            task_id = None
            if l.get('task_text'):
                cursor.execute("SELECT id FROM pomodoro_tasks WHERE task_text = %s", (l['task_text'],))
                row = cursor.fetchone()
                if row: task_id = row['id']
                else:
                    cursor.execute("INSERT INTO pomodoro_tasks (task_text, priority, completed) VALUES (%s, 3, 0)", (l['task_text'],))
                    task_id = cursor.lastrowid

            cursor.execute("SELECT id FROM pomodoro_log WHERE id = %s", (l['id'],))
            if cursor.fetchone():
                if choice == '1': skipped += 1; continue
                elif choice == '2':
                    cursor.execute("UPDATE pomodoro_log SET timestamp=%s, phase=%s, duration_min=%s, subject=%s, session_type=%s, notes=%s, task_id=%s WHERE id=%s",
                                   (l['timestamp'], l['phase'], int(l['duration_min']), l.get('subject'), l.get('session_type','study'), l.get('notes'), task_id, l['id']))
                    updated += 1
                else: raise Exception(f"Duplicate log ID {l['id']}")
            else:
                cursor.execute("INSERT INTO pomodoro_log (id, timestamp, phase, duration_min, subject, session_type, notes, task_id) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                               (l['id'], l['timestamp'], l['phase'], int(l['duration_min']), l.get('subject'), l.get('session_type','study'), l.get('notes'), task_id))
                added += 1
        conn.commit()
        print_colored(f"[✓] Logs: {added} added, {updated} updated, {skipped} skipped.", COLORS.GREEN)
    except Exception as e:
        conn.rollback()
        print_colored(f"[!] Import aborted: {e}", COLORS.RED)
    finally:
        cursor.close(); conn.close()

def pomodoro_io_menu():
    while True:
        print()
        print_colored("  ⏱️  POMODORO CLI TOOLS", COLORS.CYAN, bold=True)
        print_colored("  " + "─" * 46, COLORS.CYAN)
        print("   1. Export logs to CSV")
        print("   2. Export full backup (Tasks + Logs) to JSON")
        print("   3. Import logs from CSV")
        print("   4. Import full backup from JSON")
        print_colored("   0. Back", COLORS.WHITE)
        print_colored("  " + "─" * 46, COLORS.CYAN)
        choice = input(color_text("  Choose (0-4): ", COLORS.MAGENTA)).strip()

        if choice == '0': return
        elif choice == '1': export_pomodoro_csv()
        elif choice == '2': export_pomodoro_json()
        elif choice == '3': import_pomodoro_csv()
        elif choice == '4': import_pomodoro_json()
        else: print_colored("[!] Invalid choice.", COLORS.RED)

        input(color_text("\nPress Enter to continue...", COLORS.MAGENTA))
