# lecture_manager/question_bank.py

"""
Question Bank Module – Student‑friendly Quick Lookup
- Type: "YYYY-MM-DD Institution Level [QNo]" to view a single question or whole paper.
- Also supports interactive forms for advanced search.
- Displays questions with marks, chapter (if any), and both transcriptions.
- Import from human‑readable .txt files (blocks separated by ---).
- Import/Export from JSON.
"""

import os
import csv
import json
import re
import shutil
from datetime import datetime
from collections import defaultdict
from .db import get_connection
from .utils import print_colored, color_text, COLORS, clean_field

TABLE_NAME = 'questions'

# ---------- Database ----------
def create_question_table():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
            id INT AUTO_INCREMENT PRIMARY KEY,
            question_date DATE,
            institution VARCHAR(255),
            subject VARCHAR(255),
            paper VARCHAR(100),
            `group` VARCHAR(100),
            marks INT,
            chapter VARCHAR(255),
            question_number VARCHAR(50),
            nepali_transcription TEXT,
            english_transcription TEXT,
            level VARCHAR(100),
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX idx_subject (subject),
            INDEX idx_institution (institution),
            INDEX idx_paper (paper),
            INDEX idx_level (level)
        )
    """)
    conn.commit()
    cursor.close()
    conn.close()
    print_colored("[✓] Question table ready.", COLORS.GREEN)

def add_question(date, institution, subject, paper, group, marks, chapter,
                 question_number, nepali, english, level, notes=None):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(f"""
        INSERT INTO {TABLE_NAME}
        (question_date, institution, subject, paper, `group`, marks, chapter,
         question_number, nepali_transcription, english_transcription, level, notes)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (date, institution, subject, paper, group, marks, chapter,
          question_number, nepali, english, level, notes))
    conn.commit()
    new_id = cursor.lastrowid
    cursor.close()
    conn.close()
    return new_id

def get_question_by_id(qid):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(f"SELECT * FROM {TABLE_NAME} WHERE id = %s", (qid,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return row

def get_questions_by_criteria(date=None, institution=None, level=None, paper=None, group=None, subject=None, question_number=None):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    conditions = []
    params = []
    if date:
        conditions.append("question_date = %s")
        params.append(date)
    if institution:
        conditions.append("institution LIKE %s")
        params.append(f"%{institution}%")
    if level:
        conditions.append("level LIKE %s")
        params.append(f"%{level}%")
    if paper:
        conditions.append("paper LIKE %s")
        params.append(f"%{paper}%")
    if group:
        conditions.append("`group` LIKE %s")
        params.append(f"%{group}%")
    if subject:
        conditions.append("subject LIKE %s")
        params.append(f"%{subject}%")
    if question_number:
        conditions.append("question_number LIKE %s")
        params.append(f"%{question_number}%")

    sql = f"SELECT * FROM {TABLE_NAME}"
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY question_date DESC, institution, level, `group`, subject, question_number"
    cursor.execute(sql, params)
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return rows

def get_all_questions(sort_by='question_date', order='DESC', search=None):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    sql = f"SELECT * FROM {TABLE_NAME}"
    params = []
    if search:
        sql += """ WHERE subject LIKE %s
                   OR institution LIKE %s
                   OR paper LIKE %s
                   OR `group` LIKE %s
                   OR chapter LIKE %s
                   OR question_number LIKE %s
                   OR nepali_transcription LIKE %s
                   OR english_transcription LIKE %s
                   OR level LIKE %s
                   OR question_date LIKE %s"""
        like = f"%{search}%"
        params = [like] * 10   # now 10 placeholders
    sql += f" ORDER BY {sort_by} {order}"
    cursor.execute(sql, params)
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return rows

def update_question(qid, **kwargs):
    conn = get_connection()
    cursor = conn.cursor()
    fields = []
    values = []
    for key, val in kwargs.items():
        if val is not None:
            if key == 'group':
                fields.append("`group` = %s")
            else:
                fields.append(f"{key} = %s")
            values.append(val)
    if not fields:
        return False
    values.append(qid)
    sql = f"UPDATE {TABLE_NAME} SET {', '.join(fields)} WHERE id = %s"
    cursor.execute(sql, values)
    conn.commit()
    affected = cursor.rowcount
    cursor.close()
    conn.close()
    return affected > 0

def delete_question(qid):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(f"DELETE FROM {TABLE_NAME} WHERE id = %s", (qid,))
    conn.commit()
    affected = cursor.rowcount
    cursor.close()
    conn.close()
    return affected > 0

# ---------- Display helpers ----------

def _display_single_question(q):
    print("\n" + "═" * 70)
    print_colored("  QUESTION DETAILS", COLORS.CYAN, bold=True)
    print("═" * 70)

    inst = color_text(f"{q.get('institution', '')}", COLORS.BLUE, bold=True)
    level = color_text(f"({q.get('level', '')})", COLORS.BLUE)
    print(f"  {inst:^30} {level:^20}")
    date_str = q.get('question_date', '')
    print(f"  {color_text(date_str, COLORS.MAGENTA):^50}")

    group = q.get('group', '')
    subject = q.get('subject', '')
    chapter = q.get('chapter', '')
    if group:
        print(f"  Group: {color_text(group, COLORS.YELLOW)}")
    print(f"  Subject: {color_text(subject, COLORS.CYAN)}")
    if chapter:
        print(f"  Chapter: {color_text(chapter, COLORS.GREEN)}")

    q_no = q.get('question_number', '')
    nepali = q.get('nepali_transcription', '')
    if q.get('notes'):
            print(f"    {color_text('📝 Note:', COLORS.YELLOW)} {q['notes']}")
    english = q.get('english_transcription', '')
    marks = q.get('marks', '')
    if q.get('notes'):
        print(f"    {color_text('📝 Note:', COLORS.YELLOW)} {q['notes']}")

    print("\n" + "─" * 70)
    line = f"  {color_text(f'Q.No. {q_no}.', COLORS.CYAN, bold=True)}"
    if marks and str(marks).isdigit():
        line += f" {color_text(f'[{marks} marks]', COLORS.YELLOW)}"
    print(line)

    if nepali:
        print(f"    {color_text('नेपाली:', COLORS.MAGENTA)} {nepali}")
    if english:
        print(f"    {color_text('English:', COLORS.BLUE)} {english}")
    print("─" * 70)

def _display_paper(questions):
    if not questions:
        print_colored("[i] No questions found.", COLORS.YELLOW)
        return

    first = questions[0]
    inst = color_text(f"{first.get('institution', '')}", COLORS.BLUE, bold=True)
    level = color_text(f"{first.get('level', '')}", COLORS.BLUE)
    date_str = first.get('question_date', '')

    width = shutil.get_terminal_size().columns if shutil.get_terminal_size().columns else 80
    width = min(width, 100)

    print("\n" + "═" * width)
    print(f"  {inst:^30} {level:^20}")
    print(f"  {color_text(date_str, COLORS.MAGENTA):^50}")
    print("═" * width)

    grouped = defaultdict(lambda: defaultdict(list))
    for q in questions:
        grp = q.get('group', 'General')
        subj = q.get('subject', '')
        grouped[grp][subj].append(q)

    for grp, subjects in sorted(grouped.items()):
        print_colored(f"\n  Group: {grp}", COLORS.YELLOW, bold=True)
        for subj, qs in sorted(subjects.items()):
            print_colored(f"    Subject: {subj}", COLORS.CYAN)
            for q in sorted(qs, key=lambda x: x.get('question_number', '')):
                q_no = q.get('question_number', '')
                nepali = q.get('nepali_transcription', '')
                english = q.get('english_transcription', '')
                marks = q.get('marks', '')
                chapter = q.get('chapter', '')

                line = f"      {color_text(f'Q.No. {q_no}.', COLORS.CYAN, bold=True)}"
                if marks and str(marks).isdigit():
                    line += f" {color_text(f'[{marks} marks]', COLORS.YELLOW)}"
                print(line)

                if chapter:
                    print(f"        {color_text('Chapter:', COLORS.GREEN)} {chapter}")

                if nepali:
                    print(f"        नेपाली: {nepali}")
                if english:
                    print(f"        English: {english}")
                print()

# ---------- Quick parser ----------

def parse_quick_input(text):
    parts = text.strip().split()
    if len(parts) < 3:
        return None, None, None, None

    date = parts[0]
    question_no = None
    if len(parts) >= 4:
        last = parts[-1]
        if last.isdigit() or (last.startswith('Q') and last[1:].isdigit()):
            question_no = last
            parts = parts[:-1]

    if len(parts) == 2:
        institution = parts[1]
        level = ''
    elif len(parts) >= 3:
        institution = parts[1]
        level = ' '.join(parts[2:])
    else:
        institution = ''
        level = ''

    return date, institution, level, question_no

def quick_lookup_interactive():
    print("\n" + "═" * 50)
    print_colored("  QUICK LOOKUP", COLORS.CYAN, bold=True)
    print("═" * 50)
    print("Enter a line in the format:")
    print("  date institution level [question_no]")
    print("Examples:")
    print("  2081-01-25 NRB Officer         -> shows whole paper")
    print("  2081-01-25 NRB Officer 12      -> shows question 12 only")
    print("(You can also just type a keyword for a full-text search.)")
    print("═" * 50)

    raw = input(color_text("> ", COLORS.MAGENTA)).strip()
    if not raw:
        return

    date, inst, level, q_no = parse_quick_input(raw)

    if date and inst:
        if q_no:
            results = get_questions_by_criteria(date=date, institution=inst, level=level, question_number=q_no)
            if not results:
                print_colored("[i] No matching question found.", COLORS.YELLOW)
            elif len(results) == 1:
                _display_single_question(results[0])
            else:
                print_colored(f"[i] Found {len(results)} questions. Showing all:", COLORS.BLUE)
                _display_paper(results)
        else:
            results = get_questions_by_criteria(date=date, institution=inst, level=level)
            if not results:
                print_colored("[i] No questions found for this paper.", COLORS.YELLOW)
            else:
                _display_paper(results)
    else:
        rows = get_all_questions(search=raw)
        if not rows:
            print_colored("[i] No matches.", COLORS.YELLOW)
            return
        print(f"\n--- SEARCH RESULTS ({len(rows)} matches) ---")
        for r in rows:
            print(f"  {r['id']:3} | {r['question_date']} | {r['institution']:15} | {r['subject']:20} | {r['level']:10} | Q{r['question_number']}")
        if len(rows) > 1:
            choice = input(color_text("\nEnter ID to view details, or press Enter to continue: ", COLORS.MAGENTA)).strip()
            if choice.isdigit():
                q = get_question_by_id(int(choice))
                if q:
                    _display_single_question(q)

def import_export_submenu():
    """Sub‑menu for all import/export operations."""
    while True:
        print("\n" + "─" * 40)
        print_colored("  IMPORT / EXPORT", COLORS.CYAN, bold=True)
        print("─" * 40)
        print("  1. Export to CSV")
        print("  2. Export to JSON")
        print("  3. Import from CSV")
        print("  4. Import from JSON")
        print("  5. Import from Text File (.txt)")
        print("  0. Return to Question Bank menu")
        print("─" * 40)

        choice = input(color_text("Choose an option (0-5): ", COLORS.MAGENTA)).strip()

        if choice == '1':
            export_questions_csv()
        elif choice == '2':
            export_questions_json()
        elif choice == '3':
            import_questions_csv()
        elif choice == '4':
            import_questions_json()
        elif choice == '5':
            import_questions_txt()
        elif choice == '0':
            print_colored("Returning to Question Bank menu.", COLORS.YELLOW)
            break
        else:
            print_colored("[!] Invalid option.", COLORS.RED)

        input("\nPress Enter to continue...")

# ---------- CLI menu ----------
def question_bank_menu():
    while True:
        print("\n" + "═" * 50)
        print_colored("  QUESTION BANK", COLORS.CYAN, bold=True)
        print("═" * 50)
        print("  1. Add question")
        print("  2. View all questions")
        print("  3. Quick lookup (smart input)")
        print("  4. View a whole paper (interactive prompts)")
        print("  5. Advanced search (multiple fields)")
        print("  6. Update question")
        print("  7. Delete question")
        print("  8. Import/Export (CSV, JSON, TXT)")
        print("  0. Return to main menu")
        print("═" * 50)

        choice = input(color_text("Choose an option (0-8): ", COLORS.MAGENTA)).strip()

        if choice == '1':
            add_question_interactive()
        elif choice == '2':
            view_all_questions_interactive()
        elif choice == '3':
            quick_lookup_interactive()
        elif choice == '4':
            view_whole_paper_interactive()
        elif choice == '5':
            advanced_search_interactive()
        elif choice == '6':
            update_question_interactive()
        elif choice == '7':
            delete_question_interactive()
        elif choice == '8':
            import_export_submenu()
        elif choice == '0':
            print_colored("Returning to main menu.", COLORS.YELLOW)
            break
        else:
            print_colored("[!] Invalid option.", COLORS.RED)

        input("\nPress Enter to continue...")

# ---------- Interactive functions ----------

def _prompt_field(prompt, default=None):
    val = input(color_text(prompt, COLORS.MAGENTA)).strip()
    return val if val else default

def add_question_interactive():
    print("\n" + "═" * 50)
    print_colored("  ADD NEW QUESTION", COLORS.CYAN, bold=True)
    print("═" * 50)

    date = _prompt_field("Date (YYYY-MM-DD, press Enter for today): ")
    if not date:
        date = datetime.today().strftime('%Y-%m-%d')

    institution = _prompt_field("Institution: ")
    subject = _prompt_field("Subject: ")
    paper = _prompt_field("Paper: ")
    group = _prompt_field("Group: ")

    # Marks with validation
    marks = None
    while True:
        marks_raw = input(color_text("Marks (numeric, press Enter to skip): ", COLORS.MAGENTA)).strip()
        if marks_raw == '':
            break
        if marks_raw.isdigit():
            marks = int(marks_raw)
            break
        else:
            print_colored("[!] Marks must be a number. Please try again.", COLORS.YELLOW)

    chapter = _prompt_field("Chapter: ")
    question_number = _prompt_field("Question Number: ")
    nepali = _prompt_field("Nepali Transcription: ")
    english = _prompt_field("English Transcription: ")
    level = _prompt_field("Level: ")
    notes = input(color_text("Notes (optional, press Enter to skip): ", COLORS.MAGENTA)).strip()
    if not notes:
        notes = None

    qid = add_question(date, institution, subject, paper, group, marks,
                       chapter, question_number, nepali, english, level)
    print_colored(f"[✓] Question added with ID: {qid}", COLORS.GREEN)

def view_all_questions_interactive():
    print("\nSort by:")
    print("  1. Date (default)")
    print("  2. Subject")
    print("  3. Institution")
    print("  4. Paper")
    print("  5. Level")
    sort_choice = input(color_text("Choose (1-5, default 1): ", COLORS.MAGENTA)).strip()
    sort_map = {
        '1': 'question_date',
        '2': 'subject',
        '3': 'institution',
        '4': 'paper',
        '5': 'level'
    }
    sort_by = sort_map.get(sort_choice, 'question_date')

    order = input(color_text("Order (a=ascending, d=descending, default d): ", COLORS.MAGENTA)).strip().lower()
    if order == 'a':
        order = 'ASC'
    else:
        order = 'DESC'

    rows = get_all_questions(sort_by=sort_by, order=order)
    if not rows:
        print_colored("[i] No questions found.", COLORS.YELLOW)
        return

    print(f"\n--- ALL QUESTIONS (sorted by {sort_by} {order}) ---")
    for r in rows:
        print(f"  {r['id']:3} | {r['question_date']} | {r['institution']:15} | {r['subject']:20} | {r['paper']:10} | {r['level']:10} | Q{r['question_number']}")
    print(f"  Total: {len(rows)} questions.")

def view_whole_paper_interactive():
    print("\n" + "═" * 50)
    print_colored("  VIEW WHOLE PAPER (INTERACTIVE)", COLORS.CYAN, bold=True)
    print("═" * 50)
    print("Enter the paper details. At least one field is required.\n")

    date = _prompt_field("Date (YYYY-MM-DD): ")
    institution = _prompt_field("Institution (keyword): ")
    level = _prompt_field("Level (keyword): ")
    paper = _prompt_field("Paper (optional): ")

    if not any([date, institution, level, paper]):
        print_colored("[!] You must provide at least one search criterion.", COLORS.RED)
        return

    results = get_questions_by_criteria(date=date, institution=institution,
                                        level=level, paper=paper)
    if not results:
        print_colored("[i] No questions found.", COLORS.YELLOW)
        return

    _display_paper(results)

def advanced_search_interactive():
    print("\n" + "═" * 50)
    print_colored("  ADVANCED SEARCH", COLORS.CYAN, bold=True)
    print("═" * 50)
    print("Enter any combination of filters (leave blank for none).\n")

    date = _prompt_field("Date (YYYY-MM-DD): ")
    institution = _prompt_field("Institution (keyword): ")
    level = _prompt_field("Level (keyword): ")
    paper = _prompt_field("Paper (keyword): ")
    group = _prompt_field("Group: ")
    subject = _prompt_field("Subject (keyword): ")
    question_number = _prompt_field("Question Number: ")

    results = get_questions_by_criteria(date=date, institution=institution,
                                        level=level, paper=paper, group=group,
                                        subject=subject, question_number=question_number)
    if not results:
        print_colored("[i] No matches.", COLORS.YELLOW)
        return

    print(f"\n--- SEARCH RESULTS ({len(results)} matches) ---")
    for r in results:
        print(f"  {r['id']:3} | {r['question_date']} | {r['institution']:15} | {r['subject']:20} | {r['paper']:10} | {r['level']:10} | Q{r['question_number']}")

    if len(results) > 1:
        choice = input(color_text("\nEnter ID to view details, or press Enter: ", COLORS.MAGENTA)).strip()
        if choice.isdigit():
            q = get_question_by_id(int(choice))
            if q:
                _display_single_question(q)

def update_question_interactive():
    qid = input(color_text("Enter question ID to update: ", COLORS.MAGENTA)).strip()
    if not qid or not qid.isdigit():
        print_colored("[!] Invalid ID.", COLORS.RED)
        return
    row = get_question_by_id(int(qid))
    if not row:
        print_colored("[!] Question not found.", COLORS.RED)
        return

    # Define fields in a specific order
    fields = [
        'question_date',
        'institution',
        'subject',
        'paper',
        'group',
        'marks',
        'chapter',
        'question_number',
        'nepali_transcription',
        'english_transcription',
        'level',
        'notes'
    ]

    updates = {}

    while True:
        print("\n" + "═" * 50)
        print_colored("  UPDATE QUESTION", COLORS.CYAN, bold=True)
        print("═" * 50)

        # Show current values with numbers
        for i, field in enumerate(fields, 1):
            val = row.get(field)
            if val is None or val == '':
                display_val = "None"
            else:
                # Truncate long text for display
                display_val = str(val)
                if len(display_val) > 60:
                    display_val = display_val[:57] + "..."
            print(f"  {i:2}. {field:22}: {display_val}")

        print("\n" + "─" * 50)
        print("  Enter the number of the field to edit, or 0 to save and exit.")
        print("  0. " + color_text("Save changes and exit", COLORS.GREEN))
        print("─" * 50)

        choice = input(color_text("Choose field (0-12): ", COLORS.MAGENTA)).strip()

        if choice == '0':
            if not updates:
                print_colored("[i] No changes made.", COLORS.YELLOW)
                return
            if update_question(int(qid), **updates):
                print_colored("[✓] Question updated successfully.", COLORS.GREEN)
            else:
                print_colored("[!] Update failed.", COLORS.RED)
            return

        if not choice.isdigit():
            print_colored("[!] Please enter a number.", COLORS.RED)
            continue

        idx = int(choice)
        if idx < 1 or idx > len(fields):
            print_colored(f"[!] Please enter a number between 1 and {len(fields)}.", COLORS.RED)
            continue

        field = fields[idx - 1]
        current = row.get(field, '')

        # Special handling for marks
        if field == 'marks':
            new_val = input(color_text(f"New value for {field} [{current}]: ", COLORS.MAGENTA)).strip()
            if new_val == '':
                continue
            if not new_val.isdigit():
                print_colored("[!] Marks must be a number. Keeping current value.", COLORS.YELLOW)
                continue
            updates[field] = int(new_val)
            row[field] = int(new_val)  # Update display
            print_colored(f"[✓] {field} will be updated to {new_val}", COLORS.GREEN)

        else:
            new_val = input(color_text(f"New value for {field} [{current}]: ", COLORS.MAGENTA)).strip()
            if new_val == '':
                continue
            updates[field] = new_val
            row[field] = new_val  # Update display
            print_colored(f"[✓] {field} will be updated to: {new_val}", COLORS.GREEN)

def delete_question_interactive():
    qid = input(color_text("Enter question ID to delete: ", COLORS.MAGENTA)).strip()
    if not qid or not qid.isdigit():
        print_colored("[!] Invalid ID.", COLORS.RED)
        return
    row = get_question_by_id(int(qid))
    if not row:
        print_colored("[!] Question not found.", COLORS.RED)
        return
    print(f"Question: {row['subject']} - {row['question_number']} ({row['institution']})")
    confirm = input(color_text("Delete this question? (y/n): ", COLORS.RED)).strip().lower()
    if confirm == 'y':
        if delete_question(int(qid)):
            print_colored("[✓] Question deleted.", COLORS.GREEN)
        else:
            print_colored("[!] Deletion failed.", COLORS.RED)
    else:
        print_colored("Cancelled.", COLORS.YELLOW)

# ---------- Export / Import (CSV) ----------

def export_questions_csv():
    rows = get_all_questions()
    if not rows:
        print_colored("[i] No questions to export.", COLORS.YELLOW)
        return
    filename = input(color_text("Enter CSV filename (default: questions_export.csv): ", COLORS.MAGENTA)).strip()
    if not filename:
        filename = "questions_export.csv"
    if not filename.endswith('.csv'):
        filename += '.csv'

    fieldnames = ['id', 'question_date', 'institution', 'subject', 'paper', 'group',
                  'marks', 'chapter', 'question_number', 'nepali_transcription',
                  'english_transcription', 'level', 'created_at', 'updated_at']
    try:
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        print_colored(f"[✓] Exported {len(rows)} questions to {filename}", COLORS.GREEN)
    except Exception as e:
        print_colored(f"[!] Export failed: {e}", COLORS.RED)

def import_questions_csv():
    filename = input(color_text("Enter CSV filename: ", COLORS.MAGENTA)).strip()
    if not filename or not os.path.exists(filename):
        print_colored("[!] File not found.", COLORS.RED)
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

    print(f"Found {len(rows)} rows. How to handle duplicates?")
    print("  1. Skip duplicates (by id if present, else all)")
    print("  2. Overwrite existing (by id)")
    print("  3. Abort on any duplicate")
    choice = input(color_text("Choose (1-3): ", COLORS.MAGENTA)).strip()
    if choice not in ('1', '2', '3'):
        print_colored("[!] Invalid choice.", COLORS.RED)
        return

    conn = get_connection()
    cursor = conn.cursor()
    added = 0
    updated = 0
    skipped = 0

    fields = ['question_date', 'institution', 'subject', 'paper', 'group',
              'marks', 'chapter', 'question_number', 'nepali_transcription',
              'english_transcription', 'level']
    escaped_fields = [f"`{f}`" if f == 'group' else f for f in fields]

    for row in rows:
        qid = row.get('id')
        if qid and qid.isdigit():
            qid = int(qid)
        else:
            qid = None

        exists = False
        if qid:
            cursor.execute(f"SELECT id FROM {TABLE_NAME} WHERE id = %s", (qid,))
            exists = cursor.fetchone() is not None

        if exists:
            if choice == '1':
                skipped += 1
                continue
            elif choice == '2':
                set_clause = ", ".join([f"{f} = %s" for f in escaped_fields])
                values = [row.get(f) or None for f in fields]
                values.append(qid)
                cursor.execute(f"UPDATE {TABLE_NAME} SET {set_clause} WHERE id = %s", values)
                updated += 1
                continue
            else:
                print_colored(f"[!] Duplicate id {qid}, aborting.", COLORS.RED)
                conn.rollback()
                cursor.close()
                conn.close()
                return
        else:
            placeholders = ','.join(['%s'] * len(fields))
            cols = ','.join(escaped_fields)
            values = [row.get(f) or None for f in fields]
            cursor.execute(f"INSERT INTO {TABLE_NAME} ({cols}) VALUES ({placeholders})", values)
            added += 1

    conn.commit()
    cursor.close()
    conn.close()
    print_colored(f"[✓] Import complete: {added} added, {updated} updated, {skipped} skipped.", COLORS.GREEN)

# ---------- Import from Text File ----------

def import_questions_txt():
    print("\n" + "═" * 50)
    print_colored("  IMPORT FROM TEXT FILE", COLORS.CYAN, bold=True)
    print("═" * 50)
    print("The file should contain question blocks separated by '---'.")
    print("Each block has key: value pairs (one per line).")
    print("Required keys: Date, Institution, Level, Subject, Question Number.")
    print("Optional: Paper, Group, Marks, Chapter, Nepali, English.")
    print("Lines starting with '#' are ignored.\n")

    filename = input(color_text("Enter Text filename (e.g., questions.txt): ", COLORS.MAGENTA)).strip()
    if not filename or not os.path.exists(filename):
        print_colored("[!] File not found.", COLORS.RED)
        return

    try:
        with open(filename, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print_colored(f"[!] Failed to read file: {e}", COLORS.RED)
        return

    blocks = re.split(r'\n---+\s*\n', content)
    if not blocks:
        print_colored("[i] No question blocks found (separate with '---').", COLORS.YELLOW)
        return

    print_colored(f"[i] Found {len(blocks)} block(s). Parsing...", COLORS.BLUE)

    conn = get_connection()
    cursor = conn.cursor()
    added = 0
    skipped = 0

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        q_data = {}
        for line in block.split('\n'):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if ':' not in line:
                continue
            key, val = line.split(':', 1)
            key = key.strip().lower().replace(' ', '_')
            val = val.strip()
            if key == 'marks' and val.isdigit():
                val = int(val)
            q_data[key] = val

        date = q_data.get('date')
        institution = q_data.get('institution')
        level = q_data.get('level')
        subject = q_data.get('subject')
        question_number = q_data.get('question_number')

        if not all([date, institution, level, subject, question_number]):
            print_colored("[!] Skipping block: missing one of: Date, Institution, Level, Subject, Question Number.", COLORS.YELLOW)
            skipped += 1
            continue

        paper = q_data.get('paper')
        group = q_data.get('group')
        marks = q_data.get('marks')
        chapter = q_data.get('chapter')
        nepali = q_data.get('nepali')
        english = q_data.get('english')

        try:
            cursor.execute(f"""
                INSERT INTO {TABLE_NAME}
                (question_date, institution, subject, paper, `group`, marks, chapter,
                 question_number, nepali_transcription, english_transcription, level)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (date, institution, subject, paper, group, marks, chapter,
                  question_number, nepali, english, level))
            added += 1
        except Exception as e:
            print_colored(f"[!] Failed to insert question '{question_number}': {e}", COLORS.RED)
            skipped += 1

    conn.commit()
    cursor.close()
    conn.close()
    print_colored(f"\n[✓] Import complete: {added} added, {skipped} skipped.", COLORS.GREEN)

# ---------- NEW: Export to JSON ----------

def export_questions_json():
    rows = get_all_questions()
    if not rows:
        print_colored("[i] No questions to export.", COLORS.YELLOW)
        return

    filename = input(color_text("Enter JSON filename (default: questions_export.json): ", COLORS.MAGENTA)).strip()
    if not filename:
        filename = "questions_export.json"
    if not filename.endswith('.json'):
        filename += '.json'

    # Convert datetime objects to strings (if any)
    for row in rows:
        if 'created_at' in row and row['created_at']:
            row['created_at'] = str(row['created_at'])
        if 'updated_at' in row and row['updated_at']:
            row['updated_at'] = str(row['updated_at'])
        if 'question_date' in row and row['question_date']:
            row['question_date'] = str(row['question_date'])

    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(rows, f, indent=2, ensure_ascii=False)
        print_colored(f"[✓] Exported {len(rows)} questions to {filename}", COLORS.GREEN)
    except Exception as e:
        print_colored(f"[!] Export failed: {e}", COLORS.RED)

# ---------- NEW: Import from JSON ----------

def import_questions_json():
    print("\n" + "═" * 50)
    print_colored("  IMPORT FROM JSON", COLORS.CYAN, bold=True)
    print("═" * 50)
    print("The JSON file should be an array of question objects.")
    print("Each object can have keys matching the database columns.")
    print("If 'id' is present and matches, you can choose to update or skip.\n")

    filename = input(color_text("Enter JSON filename: ", COLORS.MAGENTA)).strip()
    if not filename or not os.path.exists(filename):
        print_colored("[!] File not found.", COLORS.RED)
        return

    try:
        with open(filename, 'r', encoding='utf-8') as f:
            rows = json.load(f)
    except Exception as e:
        print_colored(f"[!] Failed to read JSON: {e}", COLORS.RED)
        return

    if not isinstance(rows, list):
        print_colored("[!] JSON must be an array of objects.", COLORS.RED)
        return
    if not rows:
        print_colored("[i] No data found.", COLORS.YELLOW)
        return

    print(f"Found {len(rows)} questions. How to handle duplicates?")
    print("  1. Skip duplicates (by id if present, else all)")
    print("  2. Overwrite existing (by id)")
    print("  3. Abort on any duplicate")
    choice = input(color_text("Choose (1-3): ", COLORS.MAGENTA)).strip()
    if choice not in ('1', '2', '3'):
        print_colored("[!] Invalid choice.", COLORS.RED)
        return

    conn = get_connection()
    cursor = conn.cursor()
    added = 0
    updated = 0
    skipped = 0

    fields = ['question_date', 'institution', 'subject', 'paper', 'group',
              'marks', 'chapter', 'question_number', 'nepali_transcription',
              'english_transcription', 'level']
    escaped_fields = [f"`{f}`" if f == 'group' else f for f in fields]

    for obj in rows:
        # Extract id if present
        qid = obj.get('id')
        if qid and isinstance(qid, int):
            pass
        else:
            qid = None

        exists = False
        if qid:
            cursor.execute(f"SELECT id FROM {TABLE_NAME} WHERE id = %s", (qid,))
            exists = cursor.fetchone() is not None

        if exists:
            if choice == '1':
                skipped += 1
                continue
            elif choice == '2':
                set_clause = ", ".join([f"{f} = %s" for f in escaped_fields])
                values = [obj.get(f) for f in fields]
                # If a field is missing, use None
                values = [v if v is not None else None for v in values]
                values.append(qid)
                cursor.execute(f"UPDATE {TABLE_NAME} SET {set_clause} WHERE id = %s", values)
                updated += 1
                continue
            else:
                print_colored(f"[!] Duplicate id {qid}, aborting.", COLORS.RED)
                conn.rollback()
                cursor.close()
                conn.close()
                return
        else:
            placeholders = ','.join(['%s'] * len(fields))
            cols = ','.join(escaped_fields)
            values = [obj.get(f) for f in fields]
            values = [v if v is not None else None for v in values]
            cursor.execute(f"INSERT INTO {TABLE_NAME} ({cols}) VALUES ({placeholders})", values)
            added += 1

    conn.commit()
    cursor.close()
    conn.close()
    print_colored(f"[✓] Import complete: {added} added, {updated} updated, {skipped} skipped.", COLORS.GREEN)

# ---------- Chapter browsing ----------
def get_distinct_chapters():
    """Return a list of distinct chapter strings from the questions table."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(f"SELECT DISTINCT chapter FROM {TABLE_NAME} WHERE chapter IS NOT NULL AND chapter != '' ORDER BY chapter")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return [row[0] for row in rows]

def get_questions_by_chapter(chapter_code):
    """
    Return all questions that contain the given chapter code.
    We use LIKE so that 'P3-B2.3' matches 'ICT (P3-B2.3)'.
    """
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(f"""
        SELECT * FROM {TABLE_NAME}
        WHERE chapter LIKE %s
        ORDER BY question_number
    """, (f"%{chapter_code}%",))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return rows

def get_distinct_chapters_like(search_term):
    """Return distinct chapter strings that contain the search term."""
    conn = get_connection()
    cursor = conn.cursor()
    like = f"%{search_term}%"
    cursor.execute(
        "SELECT DISTINCT chapter FROM questions WHERE chapter LIKE %s ORDER BY chapter LIMIT 10",
        (like,)
    )
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return [row[0] for row in rows]
