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
from decimal import Decimal
from types import SimpleNamespace
from .db import get_connection
from .utils import print_colored, color_text, COLORS, clean_field, html_to_terminal, sanitize_for_json
from .question_converter.exceptions import (
    ConverterError,
    ValidationError,
    ParseError,
    DuplicateQuestionError,
    IOError,
    MissingCorrectOptionError,
    MultipleCorrectOptionsError,
    InsufficientOptionsError,
    MatchingPairError,
    UnknownQuestionTypeError,
)

_last_filtered_questions = None

TABLE_NAME = 'questions'

# ---------- Database ----------
def create_question_table():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
            id INT AUTO_INCREMENT PRIMARY KEY,
            source VARCHAR(255) NULL,
            question_date VARCHAR(20),
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
            notes TEXT NULL,
            general_feedback TEXT NULL,
            fraction_correct DECIMAL(10,2) DEFAULT 100.00,
            fraction_wrong DECIMAL(10,2) DEFAULT -20.00,
            shuffle_answers BOOLEAN DEFAULT TRUE,
            show_num_correct BOOLEAN DEFAULT FALSE,
            correct_feedback TEXT NULL,
            partially_correct_feedback TEXT NULL,
            incorrect_feedback TEXT NULL,
            response_lines INT DEFAULT 15,
            attachments INT DEFAULT 0,
            filetypes VARCHAR(255) DEFAULT '.doc,.docx,.pdf,.png,.jpg,.jpeg',
            maxbytes INT DEFAULT 2097152,
            grader_info TEXT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX idx_subject (subject),
            INDEX idx_institution (institution),
            INDEX idx_paper (paper),
            INDEX idx_level (level)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
    """)
    conn.commit()
    cursor.close()
    conn.close()
    print_colored("[✓] Question table ready.", COLORS.GREEN)

def search_questions_by_chapter(chapter_pattern):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM questions WHERE chapter LIKE %s", (f"%{chapter_pattern}%",))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return rows

def _should_clear_english(nepali, english):
    """Return True if english is non‑empty and identical to nepali (ignoring case/trim)."""
    if not english or not nepali:
        return False
    return nepali.strip().lower() == english.strip().lower()

def normalize_question_number(qno):
    """Convert to zero‑padded two‑digit string (e.g., 1 → '01', 10 → '10')."""
    if qno is None:
        return None
    try:
        return f"{int(qno):02d}"
    except (ValueError, TypeError):
        return str(qno).strip().zfill(2)

def format_bilingual_text(nepali, english):
    """Display Nepali and English combined.
    - Both present: 'Nepali (English)'
    - Only one present: just that one, no brackets
    - Neither: empty string
    """
    nepali = (nepali or '').strip()
    english = (english or '').strip()
    if nepali and english:
        return f"{nepali} ({english})"
    return nepali or english

def _get_filtered_questions_interactive():
    """
    Show the filter menu, let the user set filters, and return the filtered questions.
    Returns: (filtered_questions, cancelled)
    - filtered_questions: list of question dicts matching the filters, or [] if none
    - cancelled: True if user chose 0 to cancel
    """
    from .question_converter.db_handler import get_questions

    filters = {
        'date': '',
        'institution': '',
        'level': '',
        'paper': '',
        'group': '',
        'subject': '',
        'chapter': '',
        'type': ''
    }

    display_labels = {
        'date': 'Question Date',
        'institution': 'Institution',
        'level': 'Level',
        'paper': 'Paper',
        'group': 'Group',
        'subject': 'Subject',
        'chapter': 'Chapter',
        'type': 'Type'
    }

    def show_filters():
        print("\n" + "─" * 60)
        print_colored("  CURRENT FILTERS", COLORS.YELLOW, bold=True)
        print("─" * 60)
        for i, (key, value) in enumerate(filters.items(), 1):
            display = value if value else color_text("(not set)", COLORS.RED)
            label = display_labels.get(key, key.replace('_', ' ').title())
            print(f"  {i}. {label:15}: {display}")
        print("─" * 60)

    all_questions = get_questions()
    filtered = all_questions

    while True:
        show_filters()

        # Apply filters (substring for text, exact for date/type)
        filtered = all_questions
        for key, value in filters.items():
            if not value:
                continue
            if key == 'type':
                filtered = [q for q in filtered if q.get('type', '').lower() == value.lower()]
            elif key == 'date':
                filtered = [q for q in filtered if q.get('date', '') == value]
            else:
                filtered = [q for q in filtered if value.lower() in q.get(key, '').lower()]

        print_colored(f"[i] {len(filtered)} questions match current filters.", COLORS.BLUE)

        # Show preview of matches
        if filtered:
            print(f"\n  {color_text('Preview (first 5):', COLORS.CYAN)}")
            for q in filtered[:5]:
                qid = q.get('id', '?')
                date = q.get('date', '')
                inst = q.get('institution', '')[:25]
                subj = q.get('subject', '')[:25]
                paper = q.get('paper', '')[:15]
                level = q.get('level', '')[:12]
                qno = q.get('question_no', '')
                print(f"  [{date}] {qid} | {inst} | {subj} | {paper} | {level} | Q{qno}")
            if len(filtered) > 5:
                print(f"  ... and {len(filtered) - 5} more")

        print("\n  " + color_text("OPTIONS:", COLORS.WHITE, bold=True))
        print("  1-8. Edit filter (by number)")
        print("  9.  " + color_text("Execute with current filters", COLORS.GREEN, bold=True))
        print("  0.  " + color_text("Cancel", COLORS.RED))
        print("  c.  " + color_text("Clear all filters", COLORS.YELLOW))
        print("─" * 60)

        choice = input(color_text("Choose an option: ", COLORS.MAGENTA)).strip().lower()

        if choice == '9':
            return filtered, False

        elif choice == '0':
            return [], True

        elif choice == 'c':
            for key in filters:
                filters[key] = ''
            print_colored("[✓] All filters cleared.", COLORS.GREEN)
            continue

        elif choice.isdigit() and 1 <= int(choice) <= 8:
            idx = int(choice) - 1
            key = list(filters.keys())[idx]
            current = filters[key]
            label = display_labels.get(key, key.replace('_', ' ').title())
            new_val = input(color_text(f"New value for {label} [{current}]: ", COLORS.MAGENTA)).strip()
            if new_val:
                filters[key] = new_val
                print_colored(f"[✓] {label} set to: {new_val}", COLORS.GREEN)
            else:
                print_colored("[i] No change.", COLORS.YELLOW)
            continue

        else:
            print_colored("[!] Invalid choice.", COLORS.RED)
            continue

def add_question(date, institution, subject, paper, group, marks, chapter,
                 question_number, nepali, english, level, notes=None,
                 force=False, options=None, pairs=None, hints=None,
                 general_feedback=None, fraction_correct=100, fraction_wrong=-20,
                 shuffle_answers=True, show_num_correct=False,
                 correct_feedback=None, partially_correct_feedback=None,
                 incorrect_feedback=None,
                 response_lines=15, attachments=0,
                 filetypes='.doc,.docx,.pdf,.png,.jpg,.jpeg',
                 maxbytes=2097152, grader_info=None,
                 syllabus_code=None, q_type='essay'):
    # Convert empty strings to None for nullable fields
    if paper == '':
        paper = None
    if group == '':
        group = None
    if notes == '':
        notes = None

    # Check duplicate
    if not force:
        existing = check_duplicate(date, institution, level, paper, group, question_number)
        if existing:
            print_colored(f"[!] Duplicate found! Question already exists with ID: {existing}", COLORS.YELLOW)
            overwrite = input(color_text("Overwrite existing question? (y/n): ", COLORS.MAGENTA)).strip().lower()
            if overwrite == 'y':
                # Update existing
                updates = {
                    'subject': subject,
                    'paper': paper,
                    'group': group,
                    'marks': marks,
                    'chapter': chapter,
                    'nepali_transcription': nepali,
                    'english_transcription': english,
                    'notes': notes,
                    'general_feedback': general_feedback,
                    'fraction_correct': fraction_correct,
                    'fraction_wrong': fraction_wrong,
                    'shuffle_answers': shuffle_answers,
                    'show_num_correct': show_num_correct,
                    'correct_feedback': correct_feedback,
                    'partially_correct_feedback': partially_correct_feedback,
                    'incorrect_feedback': incorrect_feedback,
                    'response_lines': response_lines,
                    'attachments': attachments,
                    'filetypes': filetypes,
                    'maxbytes': maxbytes,
                    'grader_info': grader_info,
                    'type': q_type,
                }
                # Remove None values
                updates = {k: v for k, v in updates.items() if v is not None}
                if update_question(existing, **updates, options=options, pairs=pairs, hints=hints):
                    print_colored(f"[✓] Question {existing} updated.", COLORS.GREEN)
                    return existing
                else:
                    print_colored("[!] Update failed.", COLORS.RED)
                    return None
            else:
                print_colored("[i] Keeping existing question. No changes made.", COLORS.YELLOW)
                return existing

    # Insert new question
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(f"""
        INSERT INTO questions
        (question_date, institution, subject, paper, `group`, marks, chapter,
         question_number, nepali_transcription, english_transcription, level, notes,
         general_feedback, fraction_correct, fraction_wrong, shuffle_answers,
         show_num_correct, correct_feedback, partially_correct_feedback,
         incorrect_feedback, response_lines, attachments, filetypes, maxbytes,
         grader_info, type, syllabus_code)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (date, institution, subject, paper, group, marks, chapter,
          question_number, nepali, english, level, notes,
          general_feedback, fraction_correct, fraction_wrong,
          shuffle_answers, show_num_correct,
          correct_feedback, partially_correct_feedback, incorrect_feedback,
          response_lines, attachments, filetypes, maxbytes, grader_info, q_type, syllabus_code))
    conn.commit()
    qid = cursor.lastrowid

    # Insert options
    if options:
        for idx, opt in enumerate(options):
            cursor.execute("""
                INSERT INTO question_options (question_id, text, fraction, feedback, display_order)
                VALUES (%s, %s, %s, %s, %s)
            """, (qid, opt['text'], opt.get('fraction', 0), opt.get('feedback', ''), idx))

    # Insert matching pairs
    if pairs:
        for idx, pair in enumerate(pairs):
            cursor.execute("""
                INSERT INTO question_matching_pairs (question_id, subquestion, answer, display_order)
                VALUES (%s, %s, %s, %s)
            """, (qid, pair['subquestion'], pair['answer'], idx))

    # Insert hints
    if hints:
        for idx, hint in enumerate(hints, 1):
            cursor.execute("""
                INSERT INTO question_hints (question_id, hint_text, clear_incorrect, show_num_correct, hint_number)
                VALUES (%s, %s, %s, %s, %s)
            """, (qid, hint['text'], hint.get('clear_incorrect', False),
                  hint.get('show_num_correct', False), idx))

    conn.commit()
    cursor.close()
    conn.close()
    print_colored(f"[✓] Question added with ID: {qid}", COLORS.GREEN)
    return qid

def get_question_by_id(qid):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM questions WHERE id = %s", (qid,))
    q = cursor.fetchone()
    if q:
        cursor.execute("SELECT * FROM question_options WHERE question_id = %s ORDER BY display_order", (qid,))
        q['options'] = cursor.fetchall()
        cursor.execute("SELECT * FROM question_matching_pairs WHERE question_id = %s ORDER BY display_order", (qid,))
        q['pairs'] = cursor.fetchall()
        cursor.execute("SELECT * FROM question_hints WHERE question_id = %s ORDER BY hint_number", (qid,))
        q['hints'] = cursor.fetchall()
    cursor.close()
    conn.close()
    return q

def get_questions_by_criteria(date=None, institution=None, level=None, paper=None, group=None, subject=None, question_number=None, chapter=None, syllabus_code=None):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    conditions = []
    params = []

    if date:
        conditions.append("question_date = %s")
        params.append(date)
    if institution:
        conditions.append("institution LIKE %s")
        params.append(f"{institution}%")
    if level:
        conditions.append("level LIKE %s")
        params.append(f"{level}%")
    if paper:
        conditions.append("paper LIKE %s")
        params.append(f"{paper}%")
    if group:
        conditions.append("`group` LIKE %s")
        params.append(f"{group}%")
    if subject:
        conditions.append("subject LIKE %s")
        params.append(f"{subject}%")
    if question_number:
        conditions.append("question_number LIKE %s")
        params.append(f"{question_number}%")
    if chapter:
        conditions.append("LOWER(chapter) LIKE LOWER(%s)")
        params.append(f"%{chapter}%")
    if syllabus_code:
        conditions.append("syllabus_code LIKE %s")
        params.append(f"%{syllabus_code}%")

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
    if search:
        sql = """
            SELECT *, MATCH(subject, institution, paper, `group`, chapter,
                            nepali_transcription, english_transcription, notes)
                   AGAINST (%s IN NATURAL LANGUAGE MODE) AS relevance
            FROM questions
            WHERE MATCH(subject, institution, paper, `group`, chapter,
                        nepali_transcription, english_transcription, notes)
                  AGAINST (%s IN NATURAL LANGUAGE MODE)
            ORDER BY relevance DESC
        """
        cursor.execute(sql, (search, search))
    else:
        cursor.execute(f"SELECT * FROM questions ORDER BY {sort_by} {order}")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return rows

def search_questions_all_fields(search_term):
    """
    Return question rows (full data) that match search_term in main table
    or in options/pairs.
    This is the same function used by the web interface.
    """
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    like = f"%{search_term}%"

    # Search main table
    sql_main = """
        SELECT id FROM questions
        WHERE subject LIKE %s OR institution LIKE %s OR chapter LIKE %s
           OR nepali_transcription LIKE %s OR english_transcription LIKE %s
           OR notes LIKE %s
    """
    cursor.execute(sql_main, (like, like, like, like, like, like))
    main_ids = [row['id'] for row in cursor.fetchall()]

    # Search options
    sql_options = """
        SELECT DISTINCT question_id FROM question_options
        WHERE text LIKE %s
    """
    cursor.execute(sql_options, (like,))
    option_ids = [row['question_id'] for row in cursor.fetchall()]

    # Search matching pairs (subquestion and answer)
    sql_pairs = """
        SELECT DISTINCT question_id FROM question_matching_pairs
        WHERE subquestion LIKE %s OR answer LIKE %s
    """
    cursor.execute(sql_pairs, (like, like))
    pair_ids = [row['question_id'] for row in cursor.fetchall()]

    # Union all IDs
    all_ids = set(main_ids + option_ids + pair_ids)

    cursor.close()
    conn.close()

    if not all_ids:
        return []

    # Fetch full question rows
    placeholders = ','.join(['%s'] * len(all_ids))
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(f"SELECT * FROM questions WHERE id IN ({placeholders})", list(all_ids))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return rows

def update_question(qid, **kwargs):
    options = kwargs.pop('options', None)
    pairs = kwargs.pop('pairs', None)
    hints = kwargs.pop('hints', None)

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
    sql = f"UPDATE questions SET {', '.join(fields)} WHERE id = %s"

    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(sql, values)
        conn.commit()
        affected = cursor.rowcount

        if options is not None or pairs is not None or hints is not None:
            if options is not None:
                cursor.execute("DELETE FROM question_options WHERE question_id = %s", (qid,))
                for idx, opt in enumerate(options):
                    cursor.execute("""
                        INSERT INTO question_options (question_id, text, fraction, feedback, display_order)
                        VALUES (%s, %s, %s, %s, %s)
                    """, (qid, opt['text'], opt.get('fraction', 0), opt.get('feedback', ''), idx))
            if pairs is not None:
                cursor.execute("DELETE FROM question_matching_pairs WHERE question_id = %s", (qid,))
                for idx, pair in enumerate(pairs):
                    cursor.execute("""
                        INSERT INTO question_matching_pairs (question_id, subquestion, answer, display_order)
                        VALUES (%s, %s, %s, %s)
                    """, (qid, pair['subquestion'], pair['answer'], idx))
            if hints is not None:
                cursor.execute("DELETE FROM question_hints WHERE question_id = %s", (qid,))
                for idx, hint in enumerate(hints, 1):
                    cursor.execute("""
                        INSERT INTO question_hints (question_id, hint_text, clear_incorrect, show_num_correct, hint_number)
                        VALUES (%s, %s, %s, %s, %s)
                    """, (qid, hint['text'], hint.get('clear_incorrect', False),
                          hint.get('show_num_correct', False), idx))
            conn.commit()

        cursor.close()
        conn.close()
        return 'updated' if affected > 0 else 'no_change'
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

def check_duplicate(date, institution, level, paper, group, question_number, exclude_id=None):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        conditions = []
        params = []

        def add_condition(field, value):
            if value is None:
                conditions.append(f"{field} IS NULL")
            else:
                conditions.append(f"{field} = %s")
                params.append(value)

        add_condition("question_date", date)
        add_condition("institution", institution)
        add_condition("level", level)
        add_condition("paper", paper)
        add_condition("`group`", group)
        add_condition("question_number", question_number)

        sql = "SELECT id FROM questions WHERE " + " AND ".join(conditions)
        if exclude_id:
            sql += " AND id != %s"
            params.append(exclude_id)
        sql += " LIMIT 1"

        cursor.execute(sql, params)
        row = cursor.fetchone()
        return row['id'] if row else None
    finally:
        cursor.close()
        conn.close()

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
    if q.get('syllabus_code'):
        print(f"  Syllabus Code: {color_text(q['syllabus_code'], COLORS.MAGENTA)}")

    q_no = normalize_question_number(q.get('question_number'))
    from .utils import html_to_terminal
    nepali = html_to_terminal(q.get('nepali_transcription', ''))
    english = html_to_terminal(q.get('english_transcription', ''))
    marks = q.get('marks', '')
    notes = q.get('notes')
    q_type = q.get('type', 'essay')

    print("\n" + "─" * 70)
    line = f"  {color_text(f'Q.No. {q_no}.', COLORS.CYAN, bold=True)}"
    if marks and str(marks).isdigit():
        line += f" {color_text(f'[{marks} marks]', COLORS.YELLOW)}"
    line += f"  {color_text(f'Type: {q_type}', COLORS.BLUE)}"
    print(line)

    # Question text
    # Question text — only wrap in brackets when both exist
    question_text = format_bilingual_text(nepali, english)
    print(f"    {question_text}")

    if notes:
        print(f"    {color_text('📝 Note:', COLORS.YELLOW)} {notes}")

    # ---- Type-specific details ----
    if q_type == 'multichoice':
        options = q.get('options', [])
        if options:
            print("\n  Options:")
            for opt in options:
                marker = " *" if opt.get('correct', False) else ""
                print(f"    - {opt.get('text', '')}{marker}")
            if q.get('fraction_correct') is not None or q.get('fraction_wrong') is not None:
                print(f"    Correct fraction: {q.get('fraction_correct', 100)}% | Wrong fraction: {q.get('fraction_wrong', -20)}%")
    elif q_type == 'truefalse':
        options = q.get('options', [])
        correct_opt = next((opt for opt in options if opt.get('correct', False)), None)
        if correct_opt:
            print(f"\n  Correct answer: {color_text(correct_opt.get('text', ''), COLORS.GREEN)}")
        if q.get('feedback_true'):
            print(f"    Feedback if True: {q['feedback_true']}")
        if q.get('feedback_false'):
            print(f"    Feedback if False: {q['feedback_false']}")
        if q.get('fraction_correct') is not None or q.get('fraction_wrong') is not None:
            print(f"    Correct fraction: {q.get('fraction_correct', 100)}% | Wrong fraction: {q.get('fraction_wrong', -20)}%")
    elif q_type == 'matching':
        pairs = q.get('pairs', [])
        if pairs:
            print("\n  Matching pairs:")
            for pair in pairs:
                print(f"    {pair.get('subquestion', '')} ↔ {pair.get('answer', '')}")
        if q.get('shuffle_answers') is not None:
            print(f"    Shuffle answers: {'Yes' if q['shuffle_answers'] else 'No'}")
        if q.get('show_num_correct'):
            print("    Show number correct: Yes")
        if q.get('correct_feedback'):
            print(f"    Correct feedback: {q['correct_feedback']}")
        if q.get('partially_correct_feedback'):
            print(f"    Partially correct feedback: {q['partially_correct_feedback']}")
        if q.get('incorrect_feedback'):
            print(f"    Incorrect feedback: {q['incorrect_feedback']}")
        hints = q.get('hints', [])
        if hints:
            print("    Hints:")
            for hint in hints:
                line = f"      - {hint.get('text', '')}"
                if hint.get('clear_incorrect'):
                    line += " (clears incorrect)"
                if hint.get('show_num_correct'):
                    line += " (shows number correct)"
                print(line)
    else:  # essay
        print(f"\n  Response lines: {q.get('response_lines', 15)}")
        print(f"  Attachments: {q.get('attachments', 0)}")
        if q.get('filetypes'):
            print(f"  File types: {q['filetypes']}")
        if q.get('maxbytes'):
            print(f"  Max bytes: {q['maxbytes']}")
        if q.get('grader_info'):
            print(f"  Grader info: {q['grader_info']}")

    if q.get('general_feedback'):
        print(f"\n  {color_text('General Feedback:', COLORS.BLUE)} {q['general_feedback']}")

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
                nepali = html_to_terminal(q.get('nepali_transcription', ''))
                english = html_to_terminal(q.get('english_transcription', ''))
                marks = q.get('marks', '')
                chapter = q.get('chapter', '')
                notes = q.get('notes')
                q_type = q.get('type', 'essay')

                line = f"      {color_text(f'Q.No. {q_no}.', COLORS.CYAN, bold=True)}"
                if marks and str(marks).isdigit():
                    line += f" {color_text(f'[{marks} marks]', COLORS.YELLOW)}"
                line += f"  {color_text(f'[{q_type}]', COLORS.BLUE)}"
                print(line)

                if chapter:
                    print(f"        {color_text('Chapter:', COLORS.GREEN)} {chapter}")
                if q.get('syllabus_code'):
                    print(f"        {color_text('Syllabus Code:', COLORS.MAGENTA)} {q['syllabus_code']}")

                question_text = format_bilingual_text(nepali, english)
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
            raw = input(color_text(f"({len(current_results)} results) > ", COLORS.MAGENTA)).strip()

        if not raw:
            continue

        if raw.lower() in ('0', 'exit', 'quit'):
            print_colored("Returning to Question Bank menu.", COLORS.YELLOW)
            break

        if raw.lower() in ('b', 'back'):
            current_results = None
            current_query = None
            continue

        if current_results is not None and raw.isdigit():
            qid = int(raw)
            q = next((r for r in current_results if r['id'] == qid), None)
            if q:
                # Fetch full question with options/pairs/hints
                full_q = get_question_by_id(qid)
                _display_single_question(full_q)
                print()
                continue
            else:
                print_colored("[!] ID not found in current results.", COLORS.YELLOW)
                continue

        # Parse and search
        date, inst, level, q_no = parse_quick_input(raw)

        if date and inst:
            if q_no:
                results = get_questions_by_criteria(date=date, institution=inst, level=level, question_number=q_no)
                if not results:
                    print_colored("[i] No matching question found.", COLORS.YELLOW)
                    continue
                elif len(results) == 1:
                    full_q = get_question_by_id(results[0]['id'])
                    _display_single_question(full_q)
                    print()
                    continue
                else:
                    print_colored(f"[i] Found {len(results)} questions. Showing all:", COLORS.BLUE)
                    _display_paper(results)
                    current_results = None
                    continue
            else:
                results = get_questions_by_criteria(date=date, institution=inst, level=level)
                if not results:
                    print_colored("[i] No questions found for this paper.", COLORS.YELLOW)
                    continue
                else:
                    _display_paper(results)
                    current_results = None
                    continue

        # ---- Full-text search using the enhanced function ----
        results = search_questions_all_fields(raw)
        if not results:
            # Try searching by chapter (for syllabus codes like P1-B4.1)
            results = search_questions_by_chapter(raw)
            if not results:
                # Try searching by syllabus_code
                results = get_questions_by_criteria(syllabus_code=raw)
                if not results:
                    print_colored("[i] No matches.", COLORS.YELLOW)
                    current_results = None
                    current_query = None
                    continue

        current_results = results
        current_query = raw

        # Display results with numbering
        print(f"\n--- SEARCH RESULTS ({len(results)} matches) ---")
        for i, r in enumerate(results, 1):
            # Preview: use Nepali or English
            preview = r.get('nepali_transcription') or r.get('english_transcription') or ''
            preview = preview[:40] + '...' if len(preview) > 40 else preview
            print(f"  {i:2}. [{r['id']:3}] | {r['question_date']} | {r['institution'][:20]:20} | {r['subject'][:25]:25} | {r['level'][:12]:12} | Q{r['question_number']} | {r.get('type', 'essay'):10} | {preview}")

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
        print("  3. Export to TXT")
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
            export_questions_txt()
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

# Question bank menu
def unified_question_menu():
    global _last_filtered_questions
    from .question_converter.db_handler import get_questions as get_questions_db
    from .question_converter.constants import C
    verbose_mode = False

    while True:
        print("\n" + "═" * 60)
        print_colored("  📚 QUESTION BANK (Unified)", COLORS.CYAN, bold=True)
        print("═" * 60)
        print("  1. Add question (manual)")
        print("  2. View all questions")
        print("  3. Quick lookup (by date/institution/level)")
        print("  4. View whole paper")
        print("  5. Advanced search")
        print("  6. Update question")
        print("  7. Delete question")
        print("\n  " + color_text("📥 Import", COLORS.YELLOW, bold=True))
        print("  a. From TXT (human-readable, universal)")
        print("  b. From CSV (full backup, all columns)")
        print("  c. From JSON (full backup, all columns)")
        print("  d. From XML (Moodle format)")
        print("  e. Advanced import (with --questions filter)")
        print("\n  " + color_text("📤 Export", COLORS.YELLOW, bold=True))
        print("  f. To TXT (human-readable)")
        print("  g. To CSV (full backup, all columns)")
        print("  h. To JSON (full backup, all columns)")
        print("  i. To XML (Moodle format)")
        print("  j. To HTML (web view)")
        print("  k. To Exam HTML (interactive exam)")
        print("  l. Advanced export (with question number filter)")
        print("\n  " + color_text("🔄 Convert file to file (standalone, no DB)", COLORS.WHITE))
        print("  m. Run converter with custom arguments (file‑to‑file)")
        print("  0. Back to main menu")
        print("═" * 60)

        choice = input(color_text("Choose an option: ", COLORS.MAGENTA)).strip().lower()

        # ----- Bank operations (1-7) -----
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

        # ----- Import -----
        elif choice == 'a':
            from .question_converter import import_from_file
            from .question_converter.exceptions import ConverterError
            filepath = input(color_text("TXT file path: ", COLORS.MAGENTA)).strip()
            if not filepath:
                continue
            source = input(color_text("Source name (optional): ", COLORS.MAGENTA)).strip() or None

            print("\nHow to handle duplicates?")
            print("  1. Skip duplicates (keep existing)")
            print("  2. Overwrite existing (by duplicate key)")
            dup_choice = input(color_text("Choose (1-2): ", COLORS.MAGENTA)).strip()
            if dup_choice not in ('1', '2'):
                print_colored("[!] Invalid choice. Aborting.", COLORS.RED)
                continue

            force = (dup_choice == '2')
            args = SimpleNamespace(verbose=True, bypass_duplicate=force,
                                bypass_option=False, questions=None)
            try:
                count, errors = import_from_file(filepath, 'txt', source=source, args=args)
                if count == 0 and not errors:
                    print_colored("[i] No questions were imported.", COLORS.YELLOW)
                else:
                    print_colored(f"[✓] Imported {count} questions.", COLORS.GREEN)
                    if errors:
                        print_colored(f"[!] {len(errors)} errors occurred.", COLORS.RED)
                        for e in errors[:5]:
                            print(f"  {e}")
            except ConverterError as e:
                print_colored(f"[!] {e}", COLORS.RED)

        elif choice == 'b':
            import_questions_csv()

        elif choice == 'c':
            from .question_converter import import_from_file
            from .question_converter.exceptions import ConverterError
            filepath = input(color_text("JSON file path: ", COLORS.MAGENTA)).strip()
            if not filepath:
                continue
            source = input(color_text("Source name (optional): ", COLORS.MAGENTA)).strip() or None

            print("\nHow to handle duplicates?")
            print("  1. Skip duplicates (keep existing)")
            print("  2. Overwrite existing (by duplicate key)")
            dup_choice = input(color_text("Choose (1-2): ", COLORS.MAGENTA)).strip()
            if dup_choice not in ('1', '2'):
                print_colored("[!] Invalid choice. Aborting.", COLORS.RED)
                continue

            force = (dup_choice == '2')
            args = SimpleNamespace(verbose=True, bypass_duplicate=force,
                                bypass_option=False, questions=None)
            try:
                count, errors = import_from_file(filepath, 'json', source=source, args=args)
                if count == 0 and not errors:
                    print_colored("[i] No questions were imported.", COLORS.YELLOW)
                else:
                    print_colored(f"[✓] Imported {count} questions.", COLORS.GREEN)
                    if errors:
                        print_colored(f"[!] {len(errors)} errors occurred.", COLORS.RED)
                        for e in errors[:5]:
                            print(f"  {e}")
            except ConverterError as e:
                print_colored(f"[!] {e}", COLORS.RED)

        elif choice == 'd':
            from .question_converter import import_from_file
            from .question_converter.exceptions import ConverterError
            filepath = input(color_text("XML file path: ", COLORS.MAGENTA)).strip()
            if not filepath:
                continue
            source = input(color_text("Source name (optional): ", COLORS.MAGENTA)).strip() or None

            print("\nHow to handle duplicates?")
            print("  1. Skip duplicates (keep existing)")
            print("  2. Overwrite existing (by duplicate key)")
            dup_choice = input(color_text("Choose (1-2): ", COLORS.MAGENTA)).strip()
            if dup_choice not in ('1', '2'):
                print_colored("[!] Invalid choice. Aborting.", COLORS.RED)
                continue

            force = (dup_choice == '2')
            args = SimpleNamespace(verbose=True, bypass_duplicate=force,
                                bypass_option=False, questions=None)
            try:
                count, errors = import_from_file(filepath, 'xml', source=source, args=args)
                if count == 0 and not errors:
                    print_colored("[i] No questions were imported.", COLORS.YELLOW)
                else:
                    print_colored(f"[✓] Imported {count} questions.", COLORS.GREEN)
                    if errors:
                        print_colored(f"[!] {len(errors)} errors occurred.", COLORS.RED)
                        for e in errors[:5]:
                            print(f"  {e}")
            except ConverterError as e:
                print_colored(f"[!] {e}", COLORS.RED)

        elif choice == 'e':
            from .question_converter.converter_main import parser
            from .question_converter import import_from_file
            from .question_converter.exceptions import ConverterError, DuplicateQuestionError, ParseError
            import shlex
            import os

            print("\n" + "═" * 50)
            print_colored("  ADVANCED IMPORT (with filters)", COLORS.CYAN, bold=True)
            print("═" * 50)
            print("You can use the same arguments as the converter, e.g.:")
            print("  -i input.txt --questions 1,5,10 --bypass-duplicate")
            print("  -i input.xml --questions 3..7")
            print("  -i input.json --questions 2,4,6")
            print("The input file format is auto-detected from extension.")
            print("The questions will be imported into the database.\n")

            args_str = input(color_text("Arguments: ", COLORS.MAGENTA)).strip()
            if not args_str:
                continue

            try:
                argv = shlex.split(args_str)
                parsed = parser.parse_args(argv)

                input_file = parsed.input
                if not os.path.exists(input_file):
                    print_colored(f"[!] Input file not found: {input_file}", COLORS.RED)
                    continue

                ext = os.path.splitext(input_file)[1].lower().lstrip('.')
                if ext in ('txt', 'text'):
                    fmt = 'txt'
                elif ext == 'xml':
                    fmt = 'xml'
                elif ext == 'json':
                    fmt = 'json'
                else:
                    print_colored(f"[!] Unsupported file extension: {ext}. Please use .txt, .xml, or .json.", COLORS.RED)
                    continue

                source = input(color_text("Source name (optional, press Enter to skip): ", COLORS.MAGENTA)).strip() or None

                import_args = SimpleNamespace(
                    verbose=parsed.verbose,
                    bypass_duplicate=parsed.bypass_duplicate,
                    bypass_option=parsed.bypass_option,
                    questions=parsed.questions
                )

                print_colored(f"\n📥 Importing from {input_file} (format: {fmt})", COLORS.BLUE)
                if import_args.questions:
                    print_colored(f"   Filter: {import_args.questions}", COLORS.BLUE)
                if import_args.bypass_duplicate:
                    print_colored("   Duplicates will be overwritten (--bypass-duplicate)", COLORS.YELLOW)
                else:
                    print_colored("   Duplicates will be skipped (use --bypass-duplicate to overwrite)", COLORS.YELLOW)

                count, errors = import_from_file(input_file, fmt, source=source, args=import_args)

                if count == 0 and not errors:
                    print_colored("[i] No questions were imported.", COLORS.YELLOW)
                else:
                    print_colored(f"[✓] Imported {count} questions.", COLORS.GREEN)
                    if errors:
                        print_colored(f"[!] {len(errors)} errors occurred.", COLORS.RED)
                        for e in errors[:5]:
                            print(f"  {e}")

            except SystemExit:
                print_colored("[!] Invalid arguments. Please check your syntax.", COLORS.RED)
                print("  Example: -i questions.txt --questions 1,5,10")
            except (ConverterError, ParseError, DuplicateQuestionError) as e:
                print_colored(f"[!] {e}", COLORS.RED)
            except Exception as e:
                print_colored(f"[!] Unexpected error: {e}", COLORS.RED)
                import traceback
                traceback.print_exc()

        # ----- Export -----
        elif choice == 'f':
            from .question_converter import export_to_file
            from .question_converter.db_handler import get_questions as get_questions_db
            questions = get_questions_db()
            if not questions:
                print_colored("[i] No questions to export.", COLORS.YELLOW)
                continue
            default_name = f"questions_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            outfile = input(color_text(f"Output TXT file (default: {default_name}): ", COLORS.MAGENTA)).strip()
            if not outfile:
                outfile = default_name
            try:
                args = SimpleNamespace(verbose=True)
                export_to_file(questions, outfile, 'txt', args=args)
                print_colored(f"[✓] Exported to {outfile}", COLORS.GREEN)
            except Exception as e:
                print_colored(f"[!] {e}", COLORS.RED)

        elif choice == 'g':
            export_questions_csv()

        elif choice == 'h':
            from .question_converter import export_to_file
            from .question_converter.db_handler import get_questions as get_questions_db
            questions = get_questions_db()
            if not questions:
                print_colored("[i] No questions to export.", COLORS.YELLOW)
                continue
            default_name = f"questions_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            outfile = input(color_text(f"Output JSON file (default: {default_name}): ", COLORS.MAGENTA)).strip()
            if not outfile:
                outfile = default_name
            try:
                args = SimpleNamespace(verbose=True)
                export_to_file(questions, outfile, 'json', args=args)
                print_colored(f"[✓] Exported to {outfile}", COLORS.GREEN)
            except Exception as e:
                print_colored(f"[!] {e}", COLORS.RED)

        elif choice == 'i':
            from .question_converter import export_to_file
            from .question_converter.db_handler import get_questions
            questions = get_questions_db()
            if not questions:
                print_colored("[i] No questions to export.", COLORS.YELLOW)
                continue
            default_name = f"questions_export_moodle_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xml"
            outfile = input(color_text(f"Output XML file (default: {default_name}): ", COLORS.MAGENTA)).strip()
            if not outfile:
                outfile = default_name
            try:
                args = SimpleNamespace(verbose=True)
                export_to_file(questions, outfile, 'xml', args=args)
                print_colored(f"[✓] Exported to {outfile}", COLORS.GREEN)
            except Exception as e:
                print_colored(f"[!] {e}", COLORS.RED)

        elif choice == 'j':
            from .question_converter import export_to_file
            from .question_converter.db_handler import get_questions
            questions = get_questions_db()
            if not questions:
                print_colored("[i] No questions to export.", COLORS.YELLOW)
                continue
            default_name = f"questions_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
            outfile = input(color_text(f"Output HTML file (default: {default_name}): ", COLORS.MAGENTA)).strip()
            if not outfile:
                outfile = default_name
            try:
                args = SimpleNamespace(verbose=True)
                export_to_file(questions, outfile, 'html', args=args)
                print_colored(f"[✓] Exported to {outfile}", COLORS.GREEN)
            except Exception as e:
                print_colored(f"[!] {e}", COLORS.RED)

        elif choice == 'k':
            filtered, cancelled = _get_filtered_questions_interactive()
            if cancelled:
                print_colored("Cancelled.", COLORS.YELLOW)
                continue
            if not filtered:
                print_colored("[i] No questions match the filters. Export cancelled.", COLORS.YELLOW)
                continue
            _last_filtered_questions = filtered
            from .question_converter.exam_output import create_exam_html
            default_name = f"exam_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
            outfile = input(color_text(f"Output Exam HTML file (default: {default_name}): ", COLORS.MAGENTA)).strip()
            if not outfile:
                outfile = default_name
            time_str = input(color_text("Time limit in minutes (default 90): ", COLORS.MAGENTA)).strip()
            time_min = int(time_str) if time_str.isdigit() else 90
            create_exam_html(filtered, outfile, verbose=True, time_minutes=time_min, pass_marks=45)
            print_colored(f"[✓] Exported to {outfile}", COLORS.GREEN)

        elif choice == 'l':
            filtered, cancelled = _get_filtered_questions_interactive()
            if cancelled:
                print_colored("Cancelled.", COLORS.YELLOW)
                continue
            if not filtered:
                print_colored("[i] No questions match the filters. Export cancelled.", COLORS.YELLOW)
                continue

            _last_filtered_questions = filtered

            fmt = input(color_text("Format (xml, json, html, txt): ", COLORS.MAGENTA)).strip()
            if not fmt:
                print_colored("[!] Format is required.", COLORS.RED)
                continue

            default_name = f"questions_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{fmt}"
            outfile = input(color_text(f"Output file (default: {default_name}): ", COLORS.MAGENTA)).strip()
            if not outfile:
                outfile = default_name

            try:
                from .question_converter import export_to_file
                args = SimpleNamespace(verbose=True)
                export_to_file(filtered, outfile, fmt)
                print_colored(f"[✓] Exported {len(filtered)} questions to {outfile}", COLORS.GREEN)
            except Exception as e:
                print_colored(f"[!] {e}", COLORS.RED)

        # ----- Convert file to file -----
        elif choice == 'm':
            from .question_converter.converter_main import parser, run_conversion
            print("\n[Run converter with custom arguments]")
            print("💡 If your file paths contain spaces, enclose them in quotes (e.g., -i \"my file.txt\").")
            args_str = input(color_text("Arguments (e.g., -i input.txt -o output.xml --shuffle): ", COLORS.MAGENTA)).strip()
            if not args_str:
                continue
            import shlex
            try:
                argv = shlex.split(args_str)
                parsed = parser.parse_args(argv)
                run_conversion(parsed)
            except SystemExit:
                print_colored("💡 If your path contains spaces, try wrapping it in quotes, e.g., -i \"my file.txt\"", COLORS.YELLOW)
            except Exception as e:
                print_colored(f"[!] Unexpected error: {e}", COLORS.RED)

        elif choice == '0':
            break

        else:
            print_colored("[!] Invalid option.", COLORS.RED)

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
    print("  6. Type")
    sort_choice = input(color_text("Choose (1-6, default 1): ", COLORS.MAGENTA)).strip()
    sort_map = {
        '1': ('question_date', 'Date'),
        '2': ('subject', 'Subject'),
        '3': ('institution', 'Institution'),
        '4': ('paper', 'Paper'),
        '5': ('level', 'Level'),
        '6': ('type', 'Type')
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

    sort_desc = f"{display_name} {arrow}"
    print(f"\n--- ALL QUESTIONS (sorted by {color_text(sort_desc, COLORS.CYAN, bold=True)}) ---")

    for row in rows:
        val = row.get(col)
        if col == 'question_date' and isinstance(val, (date, datetime)):
            val = val.strftime('%Y-%m-%d')
        elif val is None:
            val = ''

        bracket_val = color_text(f"[{val}] ", COLORS.CYAN, bold=True)
        id_str = f"{row['id']:3}"
        date_str = row.get('question_date', '')
        if isinstance(date_str, (date, datetime)):
            date_str = date_str.strftime('%Y-%m-%d')
        inst = (row.get('institution') or '')[:25]
        subj = (row.get('subject') or '')[:25]
        paper = (row.get('paper') or '')[:15]
        level = (row.get('level') or '')[:12]
        qno = row.get('question_number', '')
        qtype = row.get('type', 'essay')
        # Preview
        preview = row.get('nepali_transcription') or row.get('english_transcription') or ''
        preview = preview[:40] + '...' if len(preview) > 40 else preview

        print(f"{bracket_val}{id_str} | {date_str} | {inst:<25} | {subj:<25} | {paper:<15} | {level:<12} | Q{qno} | {qtype:<10} | {preview}")

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

    fields = ['date', 'institution', 'level', 'paper', 'group', 'subject', 'question_number', 'chapter', 'syllabus_code', 'type']
    display_names = {
        'date': 'question_date',
        'institution': 'institution',
        'level': 'level',
        'paper': 'paper',
        'group': 'group',
        'subject': 'subject',
        'question_number': 'question_number',
        'chapter': 'chapter',
        'syllabus_code': 'syllabus_code',
        'type': 'type'
    }
    criteria = {f: '' for f in fields}

    while True:
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
        print("  90. " + color_text("Search with current criteria", COLORS.CYAN, bold=True))
        print("  0. " + color_text("Return to Question Bank menu", COLORS.YELLOW))
        choice = input(color_text("\nChoose a field to edit (1-10), 90 to search, or 0 to return: ", COLORS.MAGENTA)).strip()

        if choice == '90':
            kwargs = {}
            for field in fields:
                val = criteria[field].strip()
                if val:
                    kwargs[field] = val
            # If type is set, we need to fetch and filter manually because get_questions_by_criteria doesn't have type
            results = get_questions_by_criteria(**{k: v for k, v in kwargs.items() if k != 'type'})
            if 'type' in kwargs:
                results = [q for q in results if q.get('type', '').lower() == kwargs['type'].lower()]
            if not results:
                print_colored("[i] No matches found.", COLORS.YELLOW)
                continue

            if len(results) == 1:
                full_q = get_question_by_id(results[0]['id'])
                _display_single_question(full_q)
            else:
                print(f"\n--- SEARCH RESULTS ({len(results)} matches) ---")
                for r in results:
                    preview = r.get('nepali_transcription') or r.get('english_transcription') or ''
                    preview = preview[:50] + '...' if len(preview) > 50 else preview
                    print(f"  {r['id']:3} | {r['question_date']} | {r['institution'][:20]:20} | {r['subject'][:20]:20} | {r['chapter'][:15]:15} | Q{r['question_number']} | {r.get('type', 'essay'):10}")
                    print(f"      {preview}")
                print(f"  Total: {len(results)} matches.")
                choice_id = input(color_text("\nEnter ID to view full details, or press Enter to continue: ", COLORS.MAGENTA)).strip()
                if choice_id.isdigit():
                    q = get_question_by_id(int(choice_id))
                    if q:
                        _display_single_question(q)
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

    fields = [
        'question_date', 'institution', 'subject', 'paper', 'group',
        'marks', 'chapter', 'question_number',
        'nepali_transcription', 'english_transcription', 'level', 'notes', 'type'
    ]
    updates = {}

    while True:
        print("\n" + "═" * 50)
        print_colored("  UPDATE QUESTION", COLORS.CYAN, bold=True)
        print("═" * 50)

        for i, field in enumerate(fields, 1):
            val = row.get(field)
            if val is None or val == '':
                display_val = "None"
            else:
                display_val = str(val)
                if len(display_val) > 60:
                    display_val = display_val[:57] + "..."
            print(f"  {i:2}. {field:22}: {display_val}")

        print("\n" + "─" * 50)
        print("  Enter the number of the field to edit, or 0 to save and exit.")
        print("  0. " + color_text("Save changes and exit", COLORS.GREEN))
        print("─" * 50)

        choice = input(color_text("Choose field (0-13): ", COLORS.MAGENTA)).strip()

        if choice == '0':
            if not updates:
                print_colored("[i] No changes made.", COLORS.YELLOW)
                return

            status = update_question(int(qid), **updates)
            if status == 'updated':
                print_colored("[✓] Question updated successfully.", COLORS.GREEN)
            elif status == 'no_change':
                print_colored("[i] No changes were made (values already the same).", COLORS.YELLOW)
            elif status.startswith('error'):
                print_colored(f"[!] Update failed: {status}", COLORS.RED)
            else:
                print_colored(f"[!] Unexpected status: {status}", COLORS.RED)
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

        print(f"\nCurrent value: {color_text(current if current != '' else '(empty)', COLORS.BLUE)}")
        prompt = color_text(f"New value (press Enter to skip, or type 'clear' to empty): ", COLORS.MAGENTA)
        raw = input(prompt).strip()

        if raw == '':
            print_colored("[i] Skipped (no change).", COLORS.YELLOW)
            continue

        if raw.lower() in ('clear', 'null', 'none'):
            if field == 'marks':
                updates[field] = None
                row[field] = None
                print_colored("[✓] Marks will be cleared (set to NULL).", COLORS.GREEN)
            else:
                updates[field] = ''   # empty string
                row[field] = ''
                print_colored("[✓] Field will be cleared (set to empty string).", COLORS.GREEN)
            continue

        if field == 'marks':
            if raw.isdigit():
                updates[field] = int(raw)
                row[field] = int(raw)
                print_colored(f"[✓] Marks will be updated to {raw}", COLORS.GREEN)
            else:
                print_colored("[!] Marks must be a number. Keeping current value.", COLORS.YELLOW)
        else:
            updates[field] = raw
            row[field] = raw
            print_colored(f"[✓] {field} will be updated to: {raw}", COLORS.GREEN)

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
    print("\n" + "═" * 50)
    print_colored("  EXPORT QUESTIONS TO CSV (FULL)", COLORS.CYAN, bold=True)
    print("═" * 50)

    print_colored("[i] Fetching questions from database...", COLORS.BLUE)
    rows = get_all_questions()
    if not rows:
        print_colored("[i] No questions to export.", COLORS.YELLOW)
        return

    filename = input(color_text("Enter CSV filename (default: questions_export_full.csv): ", COLORS.MAGENTA)).strip()
    if not filename:
        filename = "questions_export_full.csv"
    if not filename.endswith('.csv'):
        filename += '.csv'

    import json
    from decimal import Decimal
    from datetime import date, datetime

    export_fields = [
        'id',
        'question_date', 'institution', 'level', 'paper', 'group',
        'subject', 'chapter', 'question_number', 'marks',
        'nepali_transcription', 'english_transcription', 'notes',
        'source', 'type',
        'general_feedback', 'fraction_correct', 'fraction_wrong',
        'syllabus_code',
        'shuffle_answers', 'show_num_correct',
        'correct_feedback', 'partially_correct_feedback', 'incorrect_feedback',
        'response_lines', 'attachments', 'filetypes', 'maxbytes',
        'grader_info'
    ]

    data = []
    conn = get_connection()
    total = len(rows)
    print_colored(f"[i] Processing {total} questions...", COLORS.BLUE)

    for idx, row in enumerate(rows, 1):
        if idx % 10 == 0 or idx == 1 or idx == total:
            qid = row.get('id', '?')
            qno = row.get('question_number', '?')
            print(f"{COLORS.CYAN}  [{idx}/{total}] Processing ID {qid} (Q{qno})...{COLORS.RESET}")

        qid = row['id']
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT * FROM question_options WHERE question_id = %s ORDER BY display_order", (qid,))
        options = cursor.fetchall()
        cursor.execute("SELECT * FROM question_matching_pairs WHERE question_id = %s ORDER BY display_order", (qid,))
        pairs = cursor.fetchall()
        cursor.execute("SELECT * FROM question_hints WHERE question_id = %s ORDER BY hint_number", (qid,))
        hints = cursor.fetchall()
        cursor.close()

        out_row = {}
        for f in export_fields:
            val = row.get(f)
            if isinstance(val, (datetime, date)):
                val = str(val)
            if isinstance(val, Decimal):
                val = int(val) if val % 1 == 0 else float(val)
            out_row[f] = val

        out_row['options_json'] = json.dumps(options, ensure_ascii=False) if options else None
        out_row['pairs_json'] = json.dumps(pairs, ensure_ascii=False) if pairs else None
        out_row['hints_json'] = json.dumps(hints, ensure_ascii=False) if hints else None

        data.append(out_row)

    conn.close()

    fieldnames = export_fields + ['options_json', 'pairs_json', 'hints_json']
    print_colored(f"[i] Writing CSV file: {filename}...", COLORS.BLUE)
    try:
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(data)
        print_colored(f"[✓] Exported {len(data)} questions to {filename}", COLORS.GREEN)
        print_colored(f"[i] File size: {os.path.getsize(filename) / 1024:.2f} KB", COLORS.BLUE)
        print_colored("[i] Options, pairs, hints are saved as JSON strings in separate columns.", COLORS.YELLOW)
        print_colored("[i] To re-import this CSV, use the enhanced import function (option b).", COLORS.YELLOW)
    except Exception as e:
        print_colored(f"[!] Export failed: {e}", COLORS.RED)

def import_questions_csv():
    print("\n" + "═" * 50)
    print_colored("  IMPORT QUESTIONS FROM CSV (FULL)", COLORS.CYAN, bold=True)
    print("═" * 50)
    print("Expects a CSV with all scalar columns + options_json, pairs_json, hints_json.\n")

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

    # Normalise rows
    for row in rows:
        row.pop('id', None)
        for field in ['paper', 'group', 'chapter', 'notes', 'source']:
            if field in row and row[field] == '':
                row[field] = None

        if row.get('marks'):
            try:
                row['marks'] = int(row['marks'])
            except ValueError:
                row['marks'] = None
        if row.get('grade'):
            try:
                row['grade'] = float(row['grade'])
            except ValueError:
                row['grade'] = 1

        for json_col in ['options_json', 'pairs_json', 'hints_json']:
            if row.get(json_col):
                try:
                    row[json_col] = json.loads(row[json_col])
                except json.JSONDecodeError:
                    row[json_col] = None
            else:
                row[json_col] = None

        if 'question_number' in row:
            row['question_no'] = row['question_number']
        if 'response_lines' in row:
            row['lines'] = row['response_lines']

    from .question_converter.db_handler import insert_question
    from .question_converter.exceptions import DuplicateQuestionError

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
    skipped = 0
    errors = []

    total = len(rows)
    for idx, row in enumerate(rows, 1):
        if idx % 5 == 0 or idx == total:
            qno = row.get('question_no', '?')
            print(f"{COLORS.CYAN}  [{idx}/{total}] Processing Q{qno}...{COLORS.RESET}")

        q_dict = {
            'question_date': row.get('question_date'),
            'institution': row.get('institution'),
            'level': row.get('level'),
            'paper': row.get('paper'),
            'group': row.get('group'),
            'subject': row.get('subject'),
            'chapter': row.get('chapter'),
            'question_no': row.get('question_no'),
            'marks': row.get('marks'),
            'nepali_transcription': row.get('nepali_transcription'),
            'english_transcription': row.get('english_transcription'),
            'notes': row.get('notes'),
            'source': row.get('source'),
            'type': row.get('type', 'essay'),
            'grade': row.get('grade', 1),
            'lines': row.get('lines', 15),
            'penalty': row.get('penalty', 0),
            'general_feedback': row.get('general_feedback'),
            'fraction_correct': row.get('fraction_correct', 100),
            'fraction_wrong': row.get('fraction_wrong', -20),
            'shuffle_answers': row.get('shuffle_answers', True),
            'show_num_correct': row.get('show_num_correct', False),
            'correct_feedback': row.get('correct_feedback'),
            'partially_correct_feedback': row.get('partially_correct_feedback'),
            'incorrect_feedback': row.get('incorrect_feedback'),
            'attachments': row.get('attachments', 0),
            'filetypes': row.get('filetypes', '.doc,.docx,.pdf,.png,.jpg,.jpeg'),
            'maxbytes': row.get('maxbytes', 2097152),
            'grader_info': row.get('grader_info'),
            'options': row.get('options_json'),
            'pairs': row.get('pairs_json'),
            'hints': row.get('hints_json'),
        }
        q_dict = {k: v for k, v in q_dict.items() if v is not None}

        try:
            if choice == '1':
                insert_question(q_dict, source=row.get('source'), force=False)
                added += 1
            elif choice == '2':
                insert_question(q_dict, source=row.get('source'), force=True)
                updated += 1
            else:
                insert_question(q_dict, source=row.get('source'), force=False)
                added += 1
        except DuplicateQuestionError as e:
            if choice == '1':
                skipped += 1
            elif choice == '3':
                print_colored(f"\n[!] Duplicate found. Aborting: {e}", COLORS.RED)
                conn.rollback()
                cursor.close()
                conn.close()
                return
            else:
                skipped += 1
        except Exception as e:
            errors.append(str(e))

    conn.commit()
    cursor.close()
    conn.close()

    print("\n" + "═" * 50)
    print_colored("  IMPORT COMPLETE", COLORS.CYAN, bold=True)
    print(f"  {COLORS.GREEN}✅ Added   : {added}{COLORS.RESET}")
    print(f"  {COLORS.BLUE}🔄 Updated : {updated}{COLORS.RESET}")
    print(f"  {COLORS.YELLOW}⏭️ Skipped : {skipped}{COLORS.RESET}")
    if errors:
        print(f"  {COLORS.RED}❌ Errors  : {len(errors)}{COLORS.RESET}")
    print("═" * 50)

def export_questions_txt():
    print("\n" + "═" * 50)
    print_colored("  📤 EXPORT TO TXT", COLORS.CYAN, bold=True)
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

    field_order = [
        'question_date', 'institution', 'level', 'paper', 'group',
        'subject', 'chapter', 'marks', 'notes', 'source'
    ]
    labels = {
        'question_date': 'Date',
        'institution': 'Institution',
        'level': 'Level',
        'paper': 'Paper',
        'group': 'Group',
        'subject': 'Subject',
        'chapter': 'Chapter',
        'marks': 'Marks',
        'notes': 'Notes',
        'source': 'Source'
    }

    total = len(rows)
    import time
    start_time = time.time()

    print_colored(f"\n📤 Exporting {total} questions to {filename}...", COLORS.CYAN)

    type_counts = {}
    exported = 0
    skipped = 0

    try:
        with open(filename, 'w', encoding='utf-8') as f:
            f.write("# Exported Question Bank (with IDs)\n")
            f.write(f"# Total: {total} questions\n")
            f.write("# Each block is separated by '---'\n")
            f.write("# The 'Question No.' line must come first in each block.\n\n")

            for idx, row in enumerate(rows, 1):
                q = get_question_by_id(row['id'])
                if not q:
                    print_colored(f"[!] Skipping question {row['id']} (not found)", COLORS.YELLOW)
                    skipped += 1
                    continue

                q_type = q.get('type', 'essay')
                type_counts[q_type] = type_counts.get(q_type, 0) + 1

                f.write("---\n")

                qno = q.get('question_number', '')
                q_text = q.get('nepali_transcription') or q.get('english_transcription') or ''
                if qno:
                    f.write(f"Question No. {qno}: {q_text}\n")
                else:
                    f.write(f"Question: {q_text}\n")

                if q.get('id'):
                    f.write(f"ID: {q['id']}\n")

                for key in field_order:
                    val = q.get(key)
                    if val is not None and val != '':
                        if key == 'marks' and val:
                            val = str(val)
                        elif isinstance(val, (date, datetime)):
                            val = str(val)
                        f.write(f"{labels.get(key, key)}: {val}\n")
                if q.get('syllabus_code'):
                    f.write(f"Syllabus Code: {q['syllabus_code']}\n")

                nep = q.get('nepali_transcription', '').strip()
                eng = q.get('english_transcription', '').strip()
                if nep:
                    f.write(f"Nepali: {nep}\n")
                if eng:
                    f.write(f"English: {eng}\n")

                f.write(f"Type: {q_type}\n")

                if q_type == "multichoice":
                    for opt in q.get('options', []):
                        marker = " *" if opt.get('correct', False) else ""
                        f.write(f"Option: {opt.get('text', '')}{marker}\n")
                    if q.get('grade', 1) != 1:
                        f.write(f"Grade: {q.get('grade', 1)}\n")
                    if q.get('penalty', 0) != 0:
                        f.write(f"Penalty: {q.get('penalty', 0)}\n")
                    if q.get('fraction_correct', 100) != 100 or q.get('fraction_wrong', -20) != -20:
                        f.write(f"Fraction: {q.get('fraction_correct', 100)} {q.get('fraction_wrong', -20)}\n")

                elif q_type == "truefalse":
                    for opt in q.get('options', []):
                        if opt.get('correct', False):
                            f.write(f"Correct: {opt.get('text', '').lower()}\n")
                            break
                    if q.get('grade', 1) != 1:
                        f.write(f"Grade: {q.get('grade', 1)}\n")
                    if q.get('penalty', 0) != 0:
                        f.write(f"Penalty: {q.get('penalty', 0)}\n")
                    if q.get('feedback_true'):
                        f.write(f"Feedback True: {q.get('feedback_true')}\n")
                    if q.get('feedback_false'):
                        f.write(f"Feedback False: {q.get('feedback_false')}\n")
                    if q.get('fraction_correct', 100) != 100 or q.get('fraction_wrong', -20) != -20:
                        f.write(f"Fraction: {q.get('fraction_correct', 100)} {q.get('fraction_wrong', -20)}\n")

                elif q_type == "matching":
                    for pair in q.get('pairs', []):
                        f.write(f"Subquestion: {pair.get('subquestion', '')}\n")
                        f.write(f"Answer: {pair.get('answer', '')}\n")
                    if q.get('grade', 1) != 1:
                        f.write(f"Grade: {q.get('grade', 1)}\n")
                    if q.get('penalty', 0) != 0:
                        f.write(f"Penalty: {q.get('penalty', 0)}\n")
                    if q.get('shuffle_answers', True) is False:
                        f.write("Shuffle Answers: false\n")
                    if q.get('show_num_correct', False):
                        f.write("Show Number Correct: true\n")
                    if q.get('correct_feedback') and q.get('correct_feedback') != "Your answer is correct.":
                        f.write(f"Correct Feedback: {q.get('correct_feedback')}\n")
                    if q.get('partially_correct_feedback') and q.get('partially_correct_feedback') != "Your answer is partially correct.":
                        f.write(f"Partially Correct Feedback: {q.get('partially_correct_feedback')}\n")
                    if q.get('incorrect_feedback') and q.get('incorrect_feedback') != "Your answer is incorrect.":
                        f.write(f"Incorrect Feedback: {q.get('incorrect_feedback')}\n")
                    for hint in q.get('hints', []):
                        f.write(f"Hint: {hint.get('text', '')}\n")
                        if hint.get('clear_incorrect', False):
                            f.write("Hint Clear Incorrect: true\n")
                        if hint.get('show_num_correct', False):
                            f.write("Hint Show Number Correct: true\n")

                else:  # essay
                    if q.get('grade', 1) != 1:
                        f.write(f"Grade: {q.get('grade', 1)}\n")
                    if q.get('lines', 15) != 15:
                        f.write(f"Lines: {q.get('lines', 15)}\n")
                    if q.get('attachments', 0) > 0:
                        f.write(f"Attachments: {q.get('attachments')}\n")
                        f.write(f"FileTypes: {q.get('filetypes', '.doc,.docx,.pdf,.png,.jpg,.jpeg')}\n")
                        max_mb = q.get('maxbytes', 2 * 1024 * 1024) / (1024 * 1024)
                        f.write(f"MaxFileSizeMB: {max_mb:.0f}\n")
                    if q.get('grader_info'):
                        f.write(f"Grader Information: {q.get('grader_info')}\n")

                if q.get('general_feedback'):
                    f.write(f"General Feedback: {q.get('general_feedback')}\n")

                f.write("\n")
                exported += 1

                if idx % 5 == 0 or idx == total:
                    print(f"  [{idx}/{total}] Processed {idx} questions...")

            f.write("---\n")

    except Exception as e:
        print_colored(f"[!] Export failed: {e}", COLORS.RED)
        return

    elapsed = time.time() - start_time
    file_size = os.path.getsize(filename) / 1024

    print("\n" + "═" * 60)
    print_colored("  📤 EXPORT SUMMARY", COLORS.CYAN, bold=True)
    print("═" * 60)
    print(f"  📁 Output file: {filename}")
    print(f"  📊 Questions  : {exported} (skipped: {skipped})")
    print(f"  🏷️  Format     : TXT")
    print(f"  💾 File size  : {file_size:.2f} KB")
    print(f"  ⏱️  Time       : {elapsed:.2f}s")
    if type_counts:
        print(f"  📈 Types      : {', '.join(f'{k}: {v}' for k, v in type_counts.items())}")
    print("═" * 60)

def import_questions_txt():
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
            if key == 'question_number':
                val = normalize_question_number(val)
            block_data[key] = val

        if 'question_number' not in block_data:
            context.update(block_data)
            continue

        merged = context.copy()
        merged.update(block_data)

        required = ('date', 'institution', 'level', 'question_number')
        missing = [r for r in required if r not in merged]
        if missing:
            print_colored(f"[!] Skipping block: missing {', '.join(missing)}", COLORS.YELLOW)
            continue

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
        date = q.get('question_date')
        institution = q.get('institution')
        level = q.get('level')
        paper = q.get('paper')
        group = q.get('group')
        question_number = q.get('question_number')

        dup_id = check_duplicate(date, institution, level, paper, group, question_number)

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
            else:
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

    total = len(rows)
    print_colored(f"[i] Processing {total} questions...", COLORS.BLUE)

    export_data = []
    for idx, row in enumerate(rows, 1):
        if idx % 10 == 0 or idx == 1 or idx == total:
            qid = row.get('id', '?')
            qno = row.get('question_number', '?')
            print(f"{COLORS.CYAN}  [{idx}/{total}] Processing ID {qid} (Q{qno})...{COLORS.RESET}")

        clean_row = row.copy()
        clean_row.pop('created_at', None)
        clean_row.pop('updated_at', None)
        if 'question_date' in clean_row and clean_row['question_date']:
            if hasattr(clean_row['question_date'], 'isoformat'):
                clean_row['question_date'] = clean_row['question_date'].isoformat()
            else:
                clean_row['question_date'] = str(clean_row['question_date'])
        for key, value in clean_row.items():
            if isinstance(value, Decimal):
                clean_row[key] = int(value) if value % 1 == 0 else float(value)
        export_data.append(sanitize_for_json(clean_row))

    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)
        file_size = os.path.getsize(filename) / 1024
        print_colored(f"[✓] Exported {len(export_data)} questions to {filename}", COLORS.GREEN)
        print_colored(f"[i] File size: {file_size:.2f} KB", COLORS.BLUE)
    except Exception as e:
        print_colored(f"[!] Export failed: {e}", COLORS.RED)

def import_questions_json():
    from .question_converter.constants import C
    print("\n" + "═" * 50)
    print_colored("  IMPORT QUESTIONS FROM JSON", COLORS.CYAN, bold=True)
    print("═" * 50)
    print("The JSON file should be an array of question objects.")
    print("Each object can have keys matching the database columns (except 'id', 'created_at', 'updated_at').")
    print("If a duplicate is found (same date, institution, level, paper, group, question_number), you can skip, overwrite, or abort.\n")

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

    for obj in rows:
        obj.pop('id', None)
        if 'question_number' in obj and obj['question_number']:
            obj['question_number'] = normalize_question_number(obj['question_number'])
        for field in ['paper', 'group', 'chapter', 'notes']:
            if field in obj and obj[field] == '':
                obj[field] = None

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
        date = obj.get('question_date')
        institution = obj.get('institution')
        level = obj.get('level')
        paper = obj.get('paper')
        group = obj.get('group')
        question_number = obj.get('question_number')

        dup_id = None
        if date and institution and level and paper is not None and group is not None and question_number:
            dup_id = check_duplicate(date, institution, level, paper, group, question_number)

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
            else:
                print_colored(f"\n[!] Duplicate found for question {question_number} (ID: {dup_id}). Aborting.", COLORS.RED)
                conn.rollback()
                cursor.close()
                conn.close()
                return
        else:
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
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(f"SELECT DISTINCT chapter FROM {TABLE_NAME} WHERE chapter IS NOT NULL AND chapter != '' ORDER BY chapter")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return [row[0] for row in rows]

def get_distinct_values(column, search_term, limit=10):
    conn = get_connection()
    cursor = conn.cursor()
    sql = f"SELECT DISTINCT {column} FROM {TABLE_NAME} WHERE {column} LIKE %s ORDER BY {column} LIMIT %s"
    cursor.execute(sql, (f"{search_term}%", limit))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    result = []
    for row in rows:
        val = row[0]
        if val is None:
            continue
        if column == 'question_date' and isinstance(val, (date, datetime)):
            val = val.strftime('%Y-%m-%d')
        else:
            val = str(val)
        result.append(val)
    return result

def get_questions_by_chapter(chapter_code):
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
