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
from datetime import date, datetime
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

def normalize_question_number(qno):
    """Convert to zero‑padded two‑digit string (e.g., 1 → '01', 10 → '10')."""
    if qno is None:
        return None
    try:
        # If it's a number or numeric string, pad to 2 digits
        return f"{int(qno):02d}"
    except (ValueError, TypeError):
        # If it's already a string like '01', keep as is (but ensure it's stripped)
        return str(qno).strip().zfill(2)

def add_question(date, institution, subject, paper, group, marks, chapter,
                 question_number, nepali, english, level, notes=None,
                 force=False):
    """
    Add a new question, unless a duplicate exists (date + institution + level + question_number).
    If force=True, skip duplicate check and insert anyway.
    Returns the new ID or existing ID if duplicate.
    """
    if not force:
        existing = check_duplicate(date, institution, level, question_number)
        if existing:
            print_colored(f"[!] Duplicate found! Question already exists with ID: {existing}", COLORS.YELLOW)
            overwrite = input(color_text("Overwrite existing question? (y/n): ", COLORS.MAGENTA)).strip().lower()
            if overwrite == 'y':
                # Update existing question
                updates = {
                    'subject': subject,
                    'paper': paper,
                    'group': group,
                    'marks': marks,
                    'chapter': chapter,
                    'nepali_transcription': nepali,
                    'english_transcription': english,
                    'notes': notes
                }
                # Remove None values
                updates = {k: v for k, v in updates.items() if v is not None}
                if update_question(existing, **updates):
                    print_colored(f"[✓] Question {existing} updated.", COLORS.GREEN)
                    return existing
                else:
                    print_colored("[!] Update failed.", COLORS.RED)
                    return None
            else:
                print_colored("[i] Keeping existing question. No changes made.", COLORS.YELLOW)
                return existing

    # No duplicate, or force=True – insert new
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
    print_colored(f"[✓] Question added with ID: {new_id}", COLORS.GREEN)
    return new_id

def get_question_by_id(qid):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(f"SELECT * FROM {TABLE_NAME} WHERE id = %s", (qid,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return row

def get_questions_by_criteria(date=None, institution=None, level=None, paper=None, group=None, subject=None, question_number=None, chapter=None):
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
    if chapter:
        conditions.append("chapter LIKE %s")
        params.append(f"%{chapter}%")

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
        return 'no_fields'
    values.append(qid)
    sql = f"UPDATE {TABLE_NAME} SET {', '.join(fields)} WHERE id = %s"
    try:
        cursor.execute(sql, values)
        conn.commit()
        affected = cursor.rowcount
        cursor.close()
        conn.close()
        if affected > 0:
            return 'updated'
        else:
            return 'no_change'
    except Exception as e:
        cursor.close()
        conn.close()
        return f'error: {e}'

def delete_question(qid):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(f"DELETE FROM {TABLE_NAME} WHERE id = %s", (qid,))
    conn.commit()
    affected = cursor.rowcount
    cursor.close()
    conn.close()
    return affected > 0

def check_duplicate(date, institution, level, question_number, exclude_id=None):
    """
    Check if a question already exists with the same date, institution, level, and question number.
    Returns the existing question ID if found, else None.
    """
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    sql = """
        SELECT id FROM questions
        WHERE question_date = %s
        AND institution = %s
        AND level = %s
        AND question_number = %s
    """
    params = [date, institution, level, question_number]
    if exclude_id:
        sql += " AND id != %s"
        params.append(exclude_id)
    cursor.execute(sql, params)
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return row['id'] if row else None

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

    q_no = normalize_question_number(q.get('question_number'))
    nepali = q.get('nepali_transcription', '')
    english = q.get('english_transcription', '')
    marks = q.get('marks', '')
    notes = q.get('notes')

    print("\n" + "─" * 70)
    line = f"  {color_text(f'Q.No. {q_no}.', COLORS.CYAN, bold=True)}"
    if marks and str(marks).isdigit():
        line += f" {color_text(f'[{marks} marks]', COLORS.YELLOW)}"
    print(line)

    # ---- Combined question text ----
    question_text = nepali
    if english:
        question_text += f" ({english})"
    print(f"    {question_text}")

    if notes:
        print(f"    {color_text('📝 Note:', COLORS.YELLOW)} {notes}")

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
                q_no = normalize_question_number(q.get('question_number'))
                nepali = q.get('nepali_transcription', '')
                english = q.get('english_transcription', '')
                marks = q.get('marks', '')
                chapter = q.get('chapter', '')
                notes = q.get('notes')

                line = f"      {color_text(f'Q.No. {q_no}.', COLORS.CYAN, bold=True)}"
                if marks and str(marks).isdigit():
                    line += f" {color_text(f'[{marks} marks]', COLORS.YELLOW)}"
                print(line)

                if chapter:
                    print(f"        {color_text('Chapter:', COLORS.GREEN)} {chapter}")

                # ---- Combined question (Nepali + English) ----
                question_text = nepali
                if english:
                    question_text += f" ({english})"
                print(f"        {question_text}")

                if notes:
                    print(f"        {color_text('📝 Note:', COLORS.YELLOW)} {notes}")
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
    print("Type '0' or 'exit' to return to the Question Bank menu.")
    print("═" * 50)

    current_results = None
    current_query = None

    while True:
        if current_results is None:
            raw = input(color_text("> ", COLORS.MAGENTA)).strip()
        else:
            # We're still in the context of a search
            raw = input(color_text(f"({len(current_results)} results) > ", COLORS.MAGENTA)).strip()

        if not raw:
            continue

        # --- Exit commands ---
        if raw.lower() in ('0', 'exit', 'quit'):
            print_colored("Returning to Question Bank menu.", COLORS.YELLOW)
            break

        # --- Back to list / new search ---
        if raw.lower() in ('b', 'back'):
            current_results = None
            current_query = None
            continue

        # --- If we have current results, check if user typed a number to view details ---
        if current_results is not None and raw.isdigit():
            qid = int(raw)
            # Find the question in current results
            q = next((r for r in current_results if r['id'] == qid), None)
            if q:
                _display_single_question(q)
                print()
                continue
            else:
                print_colored("[!] ID not found in current results.", COLORS.YELLOW)
                continue

        # --- Parse and search ---
        date, inst, level, q_no = parse_quick_input(raw)

        if date and inst:
            if q_no:
                results = get_questions_by_criteria(date=date, institution=inst, level=level, question_number=q_no)
                if not results:
                    print_colored("[i] No matching question found.", COLORS.YELLOW)
                    continue
                elif len(results) == 1:
                    _display_single_question(results[0])
                    print()
                    continue
                else:
                    print_colored(f"[i] Found {len(results)} questions. Showing all:", COLORS.BLUE)
                    _display_paper(results)
                    current_results = None  # paper view doesn't keep sticky state
                    continue
            else:
                results = get_questions_by_criteria(date=date, institution=inst, level=level)
                if not results:
                    print_colored("[i] No questions found for this paper.", COLORS.YELLOW)
                    continue
                else:
                    _display_paper(results)
                    current_results = None  # paper view doesn't keep sticky state
                    continue

        # --- Full-text search ---
        results = get_all_questions(search=raw)
        if not results:
            print_colored("[i] No matches.", COLORS.YELLOW)
            current_results = None
            current_query = None
            continue

        # Store results for sticky browsing
        current_results = results
        current_query = raw

        # Display results with numbering
        print(f"\n--- SEARCH RESULTS ({len(results)} matches) ---")
        for i, r in enumerate(results, 1):
            print(f"  {i:2}. [{r['id']:3}] | {r['question_date']} | {r['institution'][:20]:20} | {r['subject'][:25]:25} | {r['level'][:12]:12} | Q{r['question_number']}")

        print("\n  Options:")
        print("  • Enter ID number (e.g., 29) to view details")
        print("  • Type 'b' or 'back' to clear this search")
        print("  • Type '0' or 'exit' to return to menu")
        print("  • Type a new search to start fresh")

def import_export_submenu():
    while True:
        print("\n" + "─" * 40)
        print_colored("  IMPORT / EXPORT", COLORS.CYAN, bold=True)
        print("─" * 40)
        print("  1. Export to CSV")
        print("  2. Export to JSON")
        print("  3. Export to TXT")          # new
        print("  4. Import from CSV")
        print("  5. Import from JSON")
        print("  6. Import from TXT")
        print("  0. Return to Question Bank menu")
        print("─" * 40)

        choice = input(color_text("Choose an option (0-6): ", COLORS.MAGENTA)).strip()

        if choice == '1':
            export_questions_csv()
        elif choice == '2':
            export_questions_json()
        elif choice == '3':
            export_questions_txt()   # new
        elif choice == '4':
            import_questions_csv()
        elif choice == '5':
            import_questions_json()
        elif choice == '6':
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

    force = input(color_text("Force add even if duplicate? (y/n, default n): ", COLORS.MAGENTA)).strip().lower() == 'y'

    qid = add_question(date, institution, subject, paper, group, marks,
                       chapter, question_number, nepali, english, level, notes, force)
    if qid:
        print_colored(f"[✓] Question processed with ID: {qid}", COLORS.GREEN)

def view_all_questions_interactive():
    print("\nSort by:")
    print("  1. Date (default)")
    print("  2. Subject")
    print("  3. Institution")
    print("  4. Paper")
    print("  5. Level")
    sort_choice = input(color_text("Choose (1-5, default 1): ", COLORS.MAGENTA)).strip()
    sort_map = {
        '1': ('question_date', 'Date'),
        '2': ('subject', 'Subject'),
        '3': ('institution', 'Institution'),
        '4': ('paper', 'Paper'),
        '5': ('level', 'Level')
    }
    col, display_name = sort_map.get(sort_choice, ('question_date', 'Date'))

    order = input(color_text("Order (a=ascending, d=descending, default d): ", COLORS.MAGENTA)).strip().lower()
    if order == 'a':
        order_sql = 'ASC'
        arrow = '▲'
    else:
        order_sql = 'DESC'
        arrow = '▼'

    rows = get_all_questions(sort_by=col, order=order_sql)
    if not rows:
        print_colored("[i] No questions found.", COLORS.YELLOW)
        return

    # Print header with active sort column highlighted
    sort_desc = f"{display_name} {arrow}"
    print(f"\n--- ALL QUESTIONS (sorted by {color_text(sort_desc, COLORS.CYAN, bold=True)}) ---")

    # For each row, print with a bracket showing the sort column's value
    for row in rows:
        # Get the value of the sort column
        val = row.get(col)
        # Format date if applicable
        if col == 'question_date' and isinstance(val, (date, datetime)):
            val = val.strftime('%Y-%m-%d')
        elif val is None:
            val = ''

        bracket_val = color_text(f"[{val}] ", COLORS.CYAN, bold=True)

        # Build the rest of the line (id, date, institution, subject, paper, level, question number)
        # Use fixed widths or simple concatenation
        id_str = f"{row['id']:3}"
        date_str = row.get('question_date', '')
        if isinstance(date_str, (date, datetime)):
            date_str = date_str.strftime('%Y-%m-%d')
        inst = row.get('institution', '')[:25]
        subj = row.get('subject', '')[:25]
        paper = row.get('paper', '')[:15]
        level = row.get('level', '')[:12]
        qno = row.get('question_number', '')

        # Print the line
        print(f"{bracket_val}{id_str} | {date_str} | {inst:<25} | {subj:<25} | {paper:<15} | {level:<12} | Q{qno}")

    print(f"\n  Total: {len(rows)} questions.")

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
    print("Set search criteria by choosing a field number, then enter the value.")
    print("Leave value blank to clear that criterion.")
    print("After setting criteria, choose '9. Search' to run the search.\n")

    fields = ['date', 'institution', 'level', 'paper', 'group', 'subject', 'question_number', 'chapter']
    display_names = {
        'date': 'question_date',
        'institution': 'institution',
        'level': 'level',
        'paper': 'paper',
        'group': 'group',
        'subject': 'subject',
        'question_number': 'question_number',
        'chapter': 'chapter'
    }
    criteria = {f: '' for f in fields}

    while True:
        # Show current criteria
        print("─" * 50)
        print_colored("  CURRENT CRITERIA", COLORS.YELLOW, bold=True)
        for i, field in enumerate(fields, 1):
            display_name = display_names[field]
            val = criteria[field]
            if not val:
                display = color_text("(not set)", COLORS.RED)
            else:
                display_val = str(val)
                if len(display_val) > 30:
                    display_val = display_val[:27] + "..."
                display = color_text(display_val, COLORS.GREEN)
            print(f"  {i:2}. {display_name:18}: {display}")
        print("─" * 50)
        print("  9. " + color_text("Search with current criteria", COLORS.CYAN, bold=True))
        print("  0. " + color_text("Return to Question Bank menu", COLORS.YELLOW))
        choice = input(color_text("\nChoose a field to edit (1-8), 9 to search, or 0 to return: ", COLORS.MAGENTA)).strip()

        if choice == '9':
            kwargs = {}
            for field in fields:
                val = criteria[field].strip()
                if val:
                    kwargs[field] = val
            results = get_questions_by_criteria(**kwargs)
            if not results:
                print_colored("[i] No matches found.", COLORS.YELLOW)
                continue

            # ---- IMPROVED DISPLAY ----
            if len(results) == 1:
                # Single match → show full question automatically
                _display_single_question(results[0])
            else:
                # Multiple matches → show summary with a snippet
                print(f"\n--- SEARCH RESULTS ({len(results)} matches) ---")
                for r in results:
                    # Build a snippet: use Nepali first, else English
                    nepali = r.get('nepali_transcription', '')
                    english = r.get('english_transcription', '')
                    snippet = nepali
                    if english:
                        snippet += f" ({english})"
                    if len(snippet) > 60:
                        snippet = snippet[:57] + "..."
                    print(f"  {r['id']:3} | {r['question_date']} | {r['institution'][:20]:20} | {r['subject'][:20]:20} | {r['chapter'][:15]:15} | Q{r['question_number']}")
                    print(f"      {snippet}")
                print(f"  Total: {len(results)} matches.")
                choice_id = input(color_text("\nEnter ID to view full details, or press Enter to continue: ", COLORS.MAGENTA)).strip()
                if choice_id.isdigit():
                    q = get_question_by_id(int(choice_id))
                    if q:
                        _display_single_question(q)
            # After displaying, loop back to criteria editing
            continue

        elif choice == '0':
            break

        elif choice.isdigit() and 1 <= int(choice) <= len(fields):
            idx = int(choice) - 1
            field = fields[idx]
            current = criteria[field]
            display_name = display_names[field]
            new_val = input(color_text(f"Value for {display_name} [{current}]: ", COLORS.MAGENTA)).strip()
            criteria[field] = new_val
            print_colored(f"[✓] {display_name} set to: {new_val if new_val else '(cleared)'}", COLORS.GREEN)
            continue
        else:
            print_colored("[!] Invalid option.", COLORS.RED)

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
    """Export all questions to CSV (without internal IDs)."""
    print("\n" + "═" * 50)
    print_colored("  EXPORT QUESTIONS TO CSV", COLORS.CYAN, bold=True)
    print("═" * 50)

    rows = get_all_questions()
    if not rows:
        print_colored("[i] No questions to export.", COLORS.YELLOW)
        return

    filename = input(color_text("Enter CSV filename (default: questions_export.csv): ", COLORS.MAGENTA)).strip()
    if not filename:
        filename = "questions_export.csv"
    if not filename.endswith('.csv'):
        filename += '.csv'

    # Define columns to export (excluding id, created_at, updated_at)
    export_fields = ['question_date', 'institution', 'subject', 'paper', 'group',
                     'marks', 'chapter', 'question_number', 'nepali_transcription',
                     'english_transcription', 'level', 'notes']

    # Prepare data
    data = []
    for row in rows:
        out_row = {}
        for f in export_fields:
            val = row.get(f)
            if isinstance(val, (datetime, date)):
                val = str(val)
            out_row[f] = val
        data.append(out_row)

    try:
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=export_fields)
            writer.writeheader()
            writer.writerows(data)
        print_colored(f"[✓] Exported {len(data)} questions to {filename}", COLORS.GREEN)
        print_colored(f"[i] File size: {os.path.getsize(filename) / 1024:.2f} KB", COLORS.BLUE)
    except Exception as e:
        print_colored(f"[!] Export failed: {e}", COLORS.RED)

def import_questions_csv():
    """Import questions from a CSV file (id column is ignored if present)."""
    print("\n" + "═" * 50)
    print_colored("  IMPORT QUESTIONS FROM CSV", COLORS.CYAN, bold=True)
    print("═" * 50)

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

    # Normalize question numbers and ignore id
    for row in rows:
        row.pop('id', None)
        if 'question_number' in row and row['question_number']:
            row['question_number'] = normalize_question_number(row['question_number'])
        # Convert marks to int if present
        if 'marks' in row and row['marks'] and row['marks'].isdigit():
            row['marks'] = int(row['marks'])

    print(f"\n[i] Found {len(rows)} questions in the CSV file.")
    print("How to handle duplicates?")
    print("  1. Skip duplicates (keep existing)")
    print("  2. Overwrite existing (by duplicate key)")
    print("  3. Abort on any duplicate")
    choice = input(color_text("Choose (1-3): ", COLORS.MAGENTA)).strip()
    if choice not in ('1', '2', '3'):
        print_colored("[!] Invalid choice. Aborting.", COLORS.RED)
        return

    conn = get_connection()
    cursor = conn.cursor()
    added = 0
    updated = 0
    no_change = 0
    skipped = 0

    fields = ['question_date', 'institution', 'subject', 'paper', 'group',
              'marks', 'chapter', 'question_number', 'nepali_transcription',
              'english_transcription', 'level', 'notes']
    escaped_fields = [f"`{f}`" if f == 'group' else f for f in fields]

    total = len(rows)
    for idx, row in enumerate(rows, 1):
        print(f"  Processing {idx}/{total}: Q{row.get('question_number', '?')} ...", end="\r")
        date = row.get('question_date')
        institution = row.get('institution')
        level = row.get('level')
        question_number = row.get('question_number')

        dup_id = None
        if date and institution and level and question_number:
            dup_id = check_duplicate(date, institution, level, question_number)

        if dup_id:
            if choice == '1':
                skipped += 1
                print(f"  [{idx}/{total}] Skipped Q{question_number} (ID: {dup_id})     ")
                continue
            elif choice == '2':
                updates = {}
                for f in fields:
                    val = row.get(f)
                    if val is not None and val != '':
                        updates[f] = val
                if not updates:
                    print(f"  [{idx}/{total}] Q{question_number} – no fields to update, skipping.")
                    skipped += 1
                    continue

                status = update_question(dup_id, **updates)
                if status == 'updated':
                    updated += 1
                    print(f"  [{idx}/{total}] Updated Q{question_number} (ID: {dup_id})     ")
                elif status == 'no_change':
                    no_change += 1
                    print(f"  [{idx}/{total}] Q{question_number} already up-to-date.")
                else:
                    print_colored(f"  [{idx}/{total}] Error updating Q{question_number}: {status}", COLORS.RED)
                    skipped += 1
                continue
            else:  # abort
                print_colored(f"\n[!] Duplicate found for question {question_number} (ID: {dup_id}). Aborting.", COLORS.RED)
                conn.rollback()
                cursor.close()
                conn.close()
                return
        else:
            placeholders = ','.join(['%s'] * len(fields))
            cols = ','.join(escaped_fields)
            values = [row.get(f) for f in fields]
            values = [v if v is not None else None for v in values]
            try:
                cursor.execute(f"INSERT INTO {TABLE_NAME} ({cols}) VALUES ({placeholders})", values)
                new_id = cursor.lastrowid
                added += 1
                print(f"  [{idx}/{total}] Added Q{question_number} (ID: {new_id})     ")
            except Exception as e:
                print_colored(f"  [{idx}/{total}] Failed to insert Q{question_number}: {e}", COLORS.RED)
                skipped += 1

    conn.commit()
    cursor.close()
    conn.close()
    print(f"\n[✓] Import complete: {added} added, {updated} updated, {no_change} unchanged, {skipped} skipped.")

def export_questions_txt():
    """Export all questions to a human‑readable TXT file (suitable for import later)."""
    print("\n" + "═" * 50)
    print_colored("  EXPORT QUESTIONS TO TXT", COLORS.CYAN, bold=True)
    print("═" * 50)

    rows = get_all_questions()
    if not rows:
        print_colored("[i] No questions to export.", COLORS.YELLOW)
        return

    filename = input(color_text("Enter TXT filename (default: questions_export.txt): ", COLORS.MAGENTA)).strip()
    if not filename:
        filename = "questions_export.txt"
    if not filename.endswith('.txt'):
        filename += '.txt'

    # Order fields for readability
    field_order = [
        'question_date', 'institution', 'level', 'paper', 'group',
        'subject', 'chapter', 'question_number', 'marks',
        'nepali_transcription', 'english_transcription', 'notes'
    ]

    # Map keys to nice labels
    labels = {
        'question_date': 'Date',
        'institution': 'Institution',
        'level': 'Level',
        'paper': 'Paper',
        'group': 'Group',
        'subject': 'Subject',
        'chapter': 'Chapter',
        'question_number': 'Question Number',
        'marks': 'Marks',
        'nepali_transcription': 'Nepali',
        'english_transcription': 'English',
        'notes': 'Notes'
    }

    try:
        with open(filename, 'w', encoding='utf-8') as f:
            f.write("# Exported Question Bank\n")
            f.write(f"# Total: {len(rows)} questions\n")
            f.write("# Each block is separated by '---'\n\n")

            for row in rows:
                # Write context fields if they are present and have changed (simplify: always write all)
                # To make the file compact, only write non‑empty fields.
                lines = []
                for key in field_order:
                    val = row.get(key)
                    if val is not None and val != '':
                        if key == 'marks' and val:
                            val = str(val)
                        elif isinstance(val, (date, datetime)):
                            val = str(val)
                        lines.append(f"{labels.get(key, key)}: {val}")

                # Ensure question number is always present
                if 'question_number' not in row or not row['question_number']:
                    lines.append("Question Number: (missing)")

                f.write("\n---\n")
                f.write("\n".join(lines))
                f.write("\n")
            f.write("\n---\n")  # final separator

        print_colored(f"[✓] Exported {len(rows)} questions to {filename}", COLORS.GREEN)
        print_colored(f"[i] File size: {os.path.getsize(filename) / 1024:.2f} KB", COLORS.BLUE)
    except Exception as e:
        print_colored(f"[!] Export failed: {e}", COLORS.RED)

# ---------- Import from Text File ----------
def import_questions_txt():
    """Import questions from a text file (smart format)."""
    print("\n" + "═" * 50)
    print_colored("  IMPORT FROM TEXT FILE (Smart)", COLORS.CYAN, bold=True)
    print("═" * 50)
    print("Supports both full (all fields repeated) and context‑aware formats.")
    print("Context lines (Date, Institution, Level, Paper, Group, etc.)")
    print("apply to all following question blocks until changed.\n")

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

    # Split on lines that are exactly "---"
    raw_blocks = re.split(r'\n---+\s*\n', content)
    raw_blocks = [b.strip() for b in raw_blocks if b.strip()]

    if not raw_blocks:
        print_colored("[i] No blocks found.", COLORS.YELLOW)
        return

    context = {}
    questions = []
    for block in raw_blocks:
        lines = block.split('\n')
        block_data = {}
        for line in lines:
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
            # Map keys to DB column names
            if key == 'question_number':
                val = normalize_question_number(val)
            block_data[key] = val

        # Check if it's a context block (no question number)
        if 'question_number' not in block_data:
            # Update context
            context.update(block_data)
            continue

        # It's a question block: merge with context
        merged = context.copy()
        merged.update(block_data)

        required = ('date', 'institution', 'level', 'question_number')
        missing = [r for r in required if r not in merged]
        if missing:
            print_colored(f"[!] Skipping block: missing {', '.join(missing)}", COLORS.YELLOW)
            continue

        # Build DB record
        db_q = {
            'question_date': merged.get('date'),
            'institution': merged.get('institution'),
            'level': merged.get('level'),
            'subject': merged.get('subject'),
            'paper': merged.get('paper'),
            'group': merged.get('group'),
            'marks': merged.get('marks'),
            'chapter': merged.get('chapter'),
            'question_number': merged.get('question_number'),
            'nepali_transcription': merged.get('nepali'),
            'english_transcription': merged.get('english'),
            'notes': merged.get('notes') or merged.get('note')
        }
        questions.append(db_q)

    if not questions:
        print_colored("[i] No valid question blocks found.", COLORS.YELLOW)
        return

    print(f"\n[i] Found {len(questions)} valid question(s) in the text file.")
    print("How to handle duplicates?")
    print("  1. Skip duplicates (keep existing)")
    print("  2. Overwrite existing records (update all fields)")
    print("  3. Abort on any duplicate")
    choice = input(color_text("Choose (1-3): ", COLORS.MAGENTA)).strip()
    if choice not in ('1', '2', '3'):
        print_colored("[!] Invalid choice. Aborting.", COLORS.RED)
        return

    conn = get_connection()
    cursor = conn.cursor()
    added = 0
    updated = 0
    no_change = 0
    skipped = 0

    total = len(questions)
    for idx, q in enumerate(questions, 1):
        print(f"  Processing {idx}/{total}: Q{q.get('question_number', '?')} ...", end="\r")
        date = q.get('question_date')
        institution = q.get('institution')
        level = q.get('level')
        question_number = q.get('question_number')

        dup_id = check_duplicate(date, institution, level, question_number)

        if dup_id:
            if choice == '1':
                skipped += 1
                print(f"  [{idx}/{total}] Skipped Q{question_number} (ID: {dup_id})     ")
                continue
            elif choice == '2':
                updates = {k: v for k, v in q.items() if v is not None and k != 'question_date'}
                if not updates:
                    print(f"  [{idx}/{total}] Q{question_number} – no fields to update, skipping.")
                    skipped += 1
                    continue

                status = update_question(dup_id, **updates)
                if status == 'updated':
                    updated += 1
                    print(f"  [{idx}/{total}] Updated Q{question_number} (ID: {dup_id})     ")
                elif status == 'no_change':
                    no_change += 1
                    print(f"  [{idx}/{total}] Q{question_number} already up-to-date.")
                else:
                    print_colored(f"  [{idx}/{total}] Error updating Q{question_number}: {status}", COLORS.RED)
                    skipped += 1
                continue
            else:  # abort
                print_colored(f"\n[!] Duplicate found for question {question_number} (ID: {dup_id}). Aborting.", COLORS.RED)
                conn.rollback()
                cursor.close()
                conn.close()
                return
        else:
            fields = [k for k, v in q.items() if v is not None]
            values = [v for v in q.values() if v is not None]
            escaped_fields = [f"`{f}`" if f == 'group' else f for f in fields]
            placeholders = ','.join(['%s'] * len(fields))
            sql = f"INSERT INTO {TABLE_NAME} ({', '.join(escaped_fields)}) VALUES ({placeholders})"
            try:
                cursor.execute(sql, values)
                new_id = cursor.lastrowid
                added += 1
                print(f"  [{idx}/{total}] Added Q{question_number} (ID: {new_id})     ")
            except Exception as e:
                print_colored(f"  [{idx}/{total}] Failed to insert Q{question_number}: {e}", COLORS.RED)
                skipped += 1

    conn.commit()
    cursor.close()
    conn.close()
    print(f"\n[✓] Import complete: {added} added, {updated} updated, {no_change} unchanged, {skipped} skipped.")

def export_questions_json():
    """Export all questions to a JSON file, excluding internal IDs."""
    print("\n" + "═" * 50)
    print_colored("  EXPORT QUESTIONS TO JSON", COLORS.CYAN, bold=True)
    print("═" * 50)

    rows = get_all_questions()
    if not rows:
        print_colored("[i] No questions to export.", COLORS.YELLOW)
        return

    filename = input(color_text("Enter JSON filename (default: questions_export.json): ", COLORS.MAGENTA)).strip()
    if not filename:
        filename = "questions_export.json"
    if not filename.endswith('.json'):
        filename += '.json'

    # Remove internal fields and convert dates
    export_data = []
    for row in rows:
        clean_row = row.copy()
        clean_row.pop('id', None)
        clean_row.pop('created_at', None)
        clean_row.pop('updated_at', None)
        if 'question_date' in clean_row and clean_row['question_date']:
            clean_row['question_date'] = str(clean_row['question_date'])
        export_data.append(clean_row)

    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)
        print_colored(f"[✓] Exported {len(export_data)} questions to {filename}", COLORS.GREEN)
        print_colored(f"[i] File size: {os.path.getsize(filename) / 1024:.2f} KB", COLORS.BLUE)
    except Exception as e:
        print_colored(f"[!] Export failed: {e}", COLORS.RED)

def import_questions_json():
    """Import questions from a JSON file, ignoring any 'id' field."""
    print("\n" + "═" * 50)
    print_colored("  IMPORT QUESTIONS FROM JSON", COLORS.CYAN, bold=True)
    print("═" * 50)
    print("The JSON file should be an array of question objects.")
    print("Each object can have keys matching the database columns (except 'id', 'created_at', 'updated_at').")
    print("If a duplicate is found (same date, institution, level, question_number), you can skip, overwrite, or abort.\n")

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

    # Ignore 'id' and normalize question numbers
    for obj in rows:
        obj.pop('id', None)
        if 'question_number' in obj and obj['question_number']:
            obj['question_number'] = normalize_question_number(obj['question_number'])

    print(f"\n[i] Found {len(rows)} questions in the JSON file.")
    print("How to handle duplicates?")
    print("  1. Skip duplicates (keep existing)")
    print("  2. Overwrite existing (by duplicate key)")
    print("  3. Abort on any duplicate")
    choice = input(color_text("Choose (1-3): ", COLORS.MAGENTA)).strip()
    if choice not in ('1', '2', '3'):
        print_colored("[!] Invalid choice. Aborting.", COLORS.RED)
        return

    conn = get_connection()
    cursor = conn.cursor()
    added = 0
    updated = 0
    no_change = 0
    skipped = 0

    fields = ['question_date', 'institution', 'subject', 'paper', 'group',
              'marks', 'chapter', 'question_number', 'nepali_transcription',
              'english_transcription', 'level', 'notes']
    escaped_fields = [f"`{f}`" if f == 'group' else f for f in fields]

    total = len(rows)
    for idx, obj in enumerate(rows, 1):
        print(f"  Processing {idx}/{total}: Q{obj.get('question_number', '?')} ...", end="\r")
        date = obj.get('question_date')
        institution = obj.get('institution')
        level = obj.get('level')
        question_number = obj.get('question_number')

        # Check for duplicate by natural key
        dup_id = None
        if date and institution and level and question_number:
            dup_id = check_duplicate(date, institution, level, question_number)

        if dup_id:
            if choice == '1':
                skipped += 1
                print(f"  [{idx}/{total}] Skipped Q{question_number} (ID: {dup_id})     ")
                continue
            elif choice == '2':
                updates = {}
                for f in fields:
                    val = obj.get(f)
                    if val is not None:
                        updates[f] = val
                if not updates:
                    print(f"  [{idx}/{total}] Q{question_number} (ID: {dup_id}) – no fields to update, skipping.")
                    skipped += 1
                    continue

                status = update_question(dup_id, **updates)
                if status == 'updated':
                    updated += 1
                    print(f"  [{idx}/{total}] Updated Q{question_number} (ID: {dup_id})     ")
                elif status == 'no_change':
                    no_change += 1
                    print(f"  [{idx}/{total}] Q{question_number} (ID: {dup_id}) already up-to-date.")
                else:
                    print_colored(f"  [{idx}/{total}] Error updating Q{question_number}: {status}", COLORS.RED)
                    skipped += 1
                continue
            else:  # abort
                print_colored(f"\n[!] Duplicate found for question {question_number} (ID: {dup_id}). Aborting.", COLORS.RED)
                conn.rollback()
                cursor.close()
                conn.close()
                return
        else:
            # Insert new record
            placeholders = ','.join(['%s'] * len(fields))
            cols = ','.join(escaped_fields)
            values = [obj.get(f) for f in fields]
            values = [v if v is not None else None for v in values]
            try:
                cursor.execute(f"INSERT INTO {TABLE_NAME} ({cols}) VALUES ({placeholders})", values)
                new_id = cursor.lastrowid
                added += 1
                print(f"  [{idx}/{total}] Added Q{question_number} (ID: {new_id})     ")
            except Exception as e:
                print_colored(f"  [{idx}/{total}] Failed to insert Q{question_number}: {e}", COLORS.RED)
                skipped += 1

    conn.commit()
    cursor.close()
    conn.close()
    print(f"\n[✓] Import complete: {added} added, {updated} updated, {no_change} unchanged, {skipped} skipped.")

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

def get_distinct_values(column, search_term, limit=10):
    """Return distinct values from a column matching a search term."""
    conn = get_connection()
    cursor = conn.cursor()
    # Use parameterised query to prevent SQL injection
    sql = f"SELECT DISTINCT {column} FROM {TABLE_NAME} WHERE {column} LIKE %s ORDER BY {column} LIMIT %s"
    cursor.execute(sql, (f"%{search_term}%", limit))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    result = []
    for row in rows:
        val = row[0]
        if val is None:
            continue
        # Convert datetime/date objects to string (YYYY-MM-DD)
        if column == 'question_date' and isinstance(val, (date, datetime)):
            val = val.strftime('%Y-%m-%d')
        else:
            val = str(val)
        result.append(val)
    return result

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
