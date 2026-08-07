# db_handler.py

import sys
from .constants import C
from .text_parser import parse_text_file
from .xml_handler import xml_to_questions
from .json_handler import json_to_questions
from ..db import get_connection
from ..utils import print_colored, COLORS
from ..question_bank import (
    add_question,
    get_question_by_id,
    get_all_questions,
    update_question as update_q,
    delete_question as delete_q,
    check_duplicate
)
from .exceptions import DuplicateQuestionError

# -------------------- Table Creation --------------------
def create_tables():
    """Create unified tables if they don't exist."""
    conn = get_connection()
    cursor = conn.cursor()

    # Ensure the questions table has the new columns (they should already exist from SQL)
    # We'll just check if the columns exist and add if missing (optional)
    # But we already ran the ALTER, so we can skip. However, we can make it idempotent.

    # We'll not create qc_* tables anymore. They should be dropped after migration.

    # Ensure supporting tables exist
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS question_options (
        id INT AUTO_INCREMENT PRIMARY KEY,
        question_id INT NOT NULL,
        text LONGTEXT NOT NULL,
        fraction DECIMAL(10,2) DEFAULT 0.00,
        feedback LONGTEXT,
        display_order INT DEFAULT 0,
        FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE CASCADE
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS question_matching_pairs (
        id INT AUTO_INCREMENT PRIMARY KEY,
        question_id INT NOT NULL,
        subquestion LONGTEXT NOT NULL,
        answer LONGTEXT NOT NULL,
        display_order INT DEFAULT 0,
        FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE CASCADE
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS question_hints (
        id INT AUTO_INCREMENT PRIMARY KEY,
        question_id INT NOT NULL,
        hint_text LONGTEXT NOT NULL,
        clear_incorrect BOOLEAN DEFAULT FALSE,
        show_num_correct BOOLEAN DEFAULT FALSE,
        hint_number INT NOT NULL,
        FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE CASCADE
    );
    """)

    conn.commit()
    cursor.close()
    conn.close()
    print_colored("[✓] Converter database tables ready (unified).", COLORS.GREEN)

# -------------------- Insert / Update / Delete --------------------
def insert_question(q_dict, source=None, force=False):
    """
    Insert a single question into the unified database.
    Uses the composite key (date, institution, level, paper, group, question_number)
    to detect duplicates.
    """
    # Extract fields from q_dict (converter's internal format)
    date = q_dict.get('question_date') or ''
    institution = q_dict.get('institution') or ''
    level = q_dict.get('level') or ''
    paper = q_dict.get('paper') or ''
    group = q_dict.get('group') or ''
    question_number = str(q_dict.get('question_no', '')).zfill(2)
    subject = q_dict.get('subject', '')
    marks = q_dict.get('marks', None)
    chapter = q_dict.get('chapter', '')
    nepali = q_dict.get('nepali_transcription') or q_dict.get('text', '')
    english = q_dict.get('english_transcription') or q_dict.get('english', '')
    notes = q_dict.get('notes', None)

    # Duplicate check (uses question_bank's check_duplicate)
    if not force:
        dup_id = check_duplicate(date, institution, level, paper, group, question_number)
        if dup_id:
            if source and not force:
                # If not forcing, raise an error – caller can catch and handle
                raise DuplicateQuestionError(
                    f"Question already exists with ID {dup_id} for {date} {institution} {level} {paper} {group} Q{question_number}"
                )
            # If we want to update, we can call update_question later – handled by caller
            return dup_id  # return existing ID

    # Build additional fields
    general_feedback = q_dict.get('general_feedback')
    fraction_correct = q_dict.get('fraction_correct', 100)
    fraction_wrong = q_dict.get('fraction_wrong', -20)
    shuffle_answers = q_dict.get('shuffle_answers', True)
    show_num_correct = q_dict.get('show_num_correct', False)
    correct_feedback = q_dict.get('correct_feedback')
    partially_correct_feedback = q_dict.get('partially_correct_feedback')
    incorrect_feedback = q_dict.get('incorrect_feedback')
    response_lines = q_dict.get('lines', 15)
    attachments = q_dict.get('attachments', 0)
    filetypes = q_dict.get('filetypes', '.doc,.docx,.pdf,.png,.jpg,.jpeg')
    maxbytes = q_dict.get('maxbytes', 2097152)
    grader_info = q_dict.get('grader_info')

    # Options, pairs, hints
    options = q_dict.get('options', [])  # list of dicts with 'text', 'fraction', 'feedback'
    pairs = q_dict.get('pairs', [])      # list of dicts with 'subquestion', 'answer'
    hints = q_dict.get('hints', [])      # list of dicts with 'text', 'clear_incorrect', 'show_num_correct'

    # Insert using add_question from question_bank (enhanced version)
    qid = add_question(
        date=date,
        institution=institution,
        subject=subject,
        paper=paper,
        group=group,
        marks=marks,
        chapter=chapter,
        question_number=question_number,
        nepali=nepali,
        english=english,
        level=level,
        notes=notes,
        force=force,
        options=options,
        pairs=pairs,
        hints=hints,
        general_feedback=general_feedback,
        fraction_correct=fraction_correct,
        fraction_wrong=fraction_wrong,
        shuffle_answers=shuffle_answers,
        show_num_correct=show_num_correct,
        correct_feedback=correct_feedback,
        partially_correct_feedback=partially_correct_feedback,
        incorrect_feedback=incorrect_feedback,
        response_lines=response_lines,
        attachments=attachments,
        filetypes=filetypes,
        maxbytes=maxbytes,
        grader_info=grader_info
    )
    return qid

def update_question(qid, **kwargs):
    """
    Update an existing question in the unified database.
    Expects qid (the question ID) and any fields to update.
    Automatically replaces options, pairs, and hints if provided.
    """
    # Extract related data from kwargs
    options = kwargs.pop('options', None)
    pairs = kwargs.pop('pairs', None)
    hints = kwargs.pop('hints', None)

    # Call the question_bank update function
    return update_q(qid,
                    options=options,
                    pairs=pairs,
                    hints=hints,
                    **kwargs)  # pass all other fields (text, grade, etc.)

def delete_question(qid):
    """Delete a question (cascade will remove dependent rows)."""
    return delete_q(qid)

# -------------------- Get Questions --------------------
def get_questions(filters=None):
    """
    Filters can include:
    - source, type, group_name
    - question_no_min, question_no_max
    - question_nos: a list of question numbers (e.g., [1,3,5])
    """
    # Since the unified schema doesn't have 'source' in questions table, we ignore 'source' filter.
    # We'll map filters to the question_bank's get_questions_by_criteria or get_all_questions.
    # But we need to return the converter's dict format with options/pairs/hints.
    # We'll fetch the rows using question_bank functions and then convert.

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    # Build WHERE clause based on filters
    conditions = []
    params = []
    if filters:
        if 'type' in filters:
            # The type is not a column in questions; it's derived from the presence of options/pairs.
            # For simplicity, we can filter after fetching.
            pass
        if 'group_name' in filters:
            conditions.append("`group` = %s")
            params.append(filters['group_name'])
        if 'question_no_min' in filters:
            conditions.append("question_number >= %s")
            params.append(str(filters['question_no_min']).zfill(2))
        if 'question_no_max' in filters:
            conditions.append("question_number <= %s")
            params.append(str(filters['question_no_max']).zfill(2))
        if 'question_nos' in filters and filters['question_nos']:
            placeholders = ','.join(['%s'] * len(filters['question_nos']))
            conditions.append(f"question_number IN ({placeholders})")
            params.extend([str(n).zfill(2) for n in filters['question_nos']])

    sql = "SELECT * FROM questions"
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY question_number ASC"
    cursor.execute(sql, params)
    rows = cursor.fetchall()

    # Convert to converter format
    questions = []
    for row in rows:
        qid = row['id']
        q = {
            'id': qid,
            'type': None,  # we'll determine type later
            'text': row.get('nepali_transcription') or row.get('english_transcription') or '',
            'general_feedback': row.get('general_feedback') or '',
            'grade': float(row.get('marks') or 1),
            'penalty': 0,  # not stored; default
            'fraction_correct': float(row.get('fraction_correct', 100)),
            'fraction_wrong': float(row.get('fraction_wrong', -20)),
            'shuffle_answers': bool(row.get('shuffle_answers', True)),
            'show_num_correct': bool(row.get('show_num_correct', False)),
            'correct_feedback': row.get('correct_feedback') or '',
            'partially_correct_feedback': row.get('partially_correct_feedback') or '',
            'incorrect_feedback': row.get('incorrect_feedback') or '',
            'question_no': int(row.get('question_number', 0)),
            'original_question_no': int(row.get('question_number', 0)),
            'group': row.get('group') or '',
            'source': row.get('institution') or '',  # map institution as source
            'options': [],
            'pairs': [],
            'hints': [],
            'question_date': row.get('question_date') or '',
            'institution': row.get('institution') or '',
            'level': row.get('level') or '',
            'paper': row.get('paper') or '',
            'subject': row.get('subject') or '',
            'chapter': row.get('chapter') or '',
            'marks': row.get('marks'),
            'nepali_transcription': row.get('nepali_transcription') or '',
            'english_transcription': row.get('english_transcription') or '',
            'notes': row.get('notes') or '',
        }

        # Fetch options
        cursor.execute("SELECT * FROM question_options WHERE question_id = %s ORDER BY display_order", (qid,))
        opts = cursor.fetchall()
        for opt in opts:
            q['options'].append({
                'text': opt['text'],
                'fraction': float(opt['fraction']),
                'feedback': opt['feedback'] or '',
                'correct': float(opt['fraction']) > 0
            })

        # Fetch matching pairs
        cursor.execute("SELECT * FROM question_matching_pairs WHERE question_id = %s ORDER BY display_order", (qid,))
        pairs = cursor.fetchall()
        for pair in pairs:
            q['pairs'].append({
                'subquestion': pair['subquestion'],
                'answer': pair['answer']
            })

        # Fetch hints
        cursor.execute("SELECT * FROM question_hints WHERE question_id = %s ORDER BY hint_number", (qid,))
        hints_rows = cursor.fetchall()
        for hint in hints_rows:
            q['hints'].append({
                'text': hint['hint_text'],
                'clear_incorrect': bool(hint['clear_incorrect']),
                'show_num_correct': bool(hint['show_num_correct'])
            })

        # Determine type based on content
        if q['options']:
            # If there are exactly 2 options and they are 'true'/'false' (case-insensitive)
            if len(q['options']) == 2:
                opt_texts = [opt['text'].lower().strip() for opt in q['options']]
                if set(opt_texts) == {'true', 'false'}:
                    q['type'] = 'truefalse'
                else:
                    q['type'] = 'multichoice'
            else:
                q['type'] = 'multichoice'
        elif q['pairs']:
            q['type'] = 'matching'
        else:
            q['type'] = 'essay'  # fallback

        questions.append(q)

    cursor.close()
    conn.close()
    return questions

# -------------------- High‑level Import/Export --------------------
def import_from_file(file_path, format, source=None, args=None):
    """
    Parse a file (txt, xml, json) and insert all questions into the DB.
    Returns (inserted_count, errors).
    """
    if args is None:
        args = type('Args', (), {
            'verbose': False,
            'bypass_duplicate': False,
            'bypass_option': False,
            'questions': None
        })()

    if format == 'txt':
        questions, bypass_used, skipped_lines = parse_text_file(file_path, args)
    elif format == 'xml':
        questions = xml_to_questions(file_path, args.verbose)
    elif format == 'json':
        questions = json_to_questions(file_path, args.verbose)
    else:
        raise ValueError(f"Unsupported import format: {format}")

    count = 0
    errors = []
    for q in questions:
        try:
            # Insert with force=False to catch duplicates
            insert_question(q, source=source, force=args.bypass_duplicate)
            count += 1
        except DuplicateQuestionError as e:
            if args.bypass_duplicate:
                # Update existing question
                # We need to find the existing ID
                dup_id = check_duplicate(
                    q.get('question_date', ''),
                    q.get('institution', ''),
                    q.get('level', ''),
                    q.get('paper', ''),
                    q.get('group', ''),
                    str(q.get('question_no', '')).zfill(2)
                )
                if dup_id:
                    # Update
                    try:
                        update_question(dup_id, **q)
                        count += 1
                    except Exception as e2:
                        errors.append(f"Error updating question {q.get('question_no', '?')}: {e2}")
                else:
                    errors.append(f"Could not find duplicate ID for question {q.get('question_no', '?')}")
            else:
                errors.append(str(e))
        except Exception as e:
            errors.append(f"Error inserting question {q.get('question_no', '?')}: {e}")

    return count, errors

def export_to_file(questions, output_file, format, args=None):
    """
    Export a list of questions (as converter dicts) to a file.
    """
    if args is None:
        args = type('Args', (), {'verbose': False})()

    if format == 'xml':
        from .xml_handler import create_moodle_xml
        create_moodle_xml(questions, output_file, args.verbose)
    elif format == 'json':
        from .json_handler import create_json_output
        create_json_output(questions, output_file, args.verbose)
    elif format == 'html':
        from .html_output import create_html_output
        create_html_output(questions, output_file, args.verbose)
    elif format == 'txt':
        from .text_output import create_text_output
        create_text_output(questions, output_file, args.verbose)
    else:
        raise ValueError(f"Unsupported export format: {format}")
