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
from .exceptions import DuplicateQuestionError, ConverterError

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
    Insert a new question. If duplicate exists and force=True, update it.
    Returns the question ID (new or existing).
    """
    # Extract fields
    date = q_dict.get('question_date') or ''
    institution = q_dict.get('institution') or ''
    level = q_dict.get('level') or ''
    paper = q_dict.get('paper') or ''
    group = q_dict.get('group') or ''
    question_number = str(q_dict.get('question_no', '')).zfill(2)

    # Check duplicate
    dup_id = check_duplicate(date, institution, level, paper, group, question_number)

    if dup_id:
        if force:
            # Update existing question
            update_question(
                dup_id,
                source=source,
                subject=q_dict.get('subject', ''),
                paper=paper,
                group=group,
                marks=q_dict.get('marks'),
                chapter=q_dict.get('chapter', ''),
                question_number=question_number,
                nepali=q_dict.get('nepali_transcription') or q_dict.get('text', ''),
                english=q_dict.get('english_transcription') or q_dict.get('english', ''),
                level=level,
                notes=q_dict.get('notes'),
                options=q_dict.get('options'),
                pairs=q_dict.get('pairs'),
                hints=q_dict.get('hints'),
                general_feedback=q_dict.get('general_feedback'),
                fraction_correct=q_dict.get('fraction_correct', 100),
                fraction_wrong=q_dict.get('fraction_wrong', -20),
                shuffle_answers=q_dict.get('shuffle_answers', True),
                show_num_correct=q_dict.get('show_num_correct', False),
                correct_feedback=q_dict.get('correct_feedback'),
                partially_correct_feedback=q_dict.get('partially_correct_feedback'),
                incorrect_feedback=q_dict.get('incorrect_feedback'),
                response_lines=q_dict.get('lines', 15),
                attachments=q_dict.get('attachments', 0),
                filetypes=q_dict.get('filetypes', '.doc,.docx,.pdf,.png,.jpg,.jpeg'),
                maxbytes=q_dict.get('maxbytes', 2097152),
                grader_info=q_dict.get('grader_info')
            )
            return dup_id
        else:
            raise DuplicateQuestionError(
                f"Question already exists with ID {dup_id} for {date} {institution} {level} {paper} {group} Q{question_number}"
            )

    # No duplicate – insert new
    return add_question(
        date=date,
        institution=institution,
        subject=q_dict.get('subject', ''),
        paper=paper,
        group=group,
        marks=q_dict.get('marks'),
        chapter=q_dict.get('chapter', ''),
        question_number=question_number,
        nepali=q_dict.get('nepali_transcription') or q_dict.get('text', ''),
        english=q_dict.get('english_transcription') or q_dict.get('english', ''),
        level=level,
        notes=q_dict.get('notes'),
        force=True,   # we already checked duplicate, so force insert
        options=q_dict.get('options'),
        pairs=q_dict.get('pairs'),
        hints=q_dict.get('hints'),
        general_feedback=q_dict.get('general_feedback'),
        fraction_correct=q_dict.get('fraction_correct', 100),
        fraction_wrong=q_dict.get('fraction_wrong', -20),
        shuffle_answers=q_dict.get('shuffle_answers', True),
        show_num_correct=q_dict.get('show_num_correct', False),
        correct_feedback=q_dict.get('correct_feedback'),
        partially_correct_feedback=q_dict.get('partially_correct_feedback'),
        incorrect_feedback=q_dict.get('incorrect_feedback'),
        response_lines=q_dict.get('lines', 15),
        attachments=q_dict.get('attachments', 0),
        filetypes=q_dict.get('filetypes', '.doc,.docx,.pdf,.png,.jpg,.jpeg'),
        maxbytes=q_dict.get('maxbytes', 2097152),
        grader_info=q_dict.get('grader_info')
    )

def _convert_to_db_fields(q_dict):
    """Map converter dict keys to database column names."""
    return {
        'question_date': q_dict.get('question_date'),
        'institution': q_dict.get('institution'),
        'level': q_dict.get('level'),
        'paper': q_dict.get('paper'),
        'group': q_dict.get('group'),
        'subject': q_dict.get('subject'),
        'marks': q_dict.get('marks'),
        'chapter': q_dict.get('chapter'),
        'question_number': str(q_dict.get('question_no', '')).zfill(2),
        'nepali_transcription': q_dict.get('nepali_transcription') or q_dict.get('text'),
        'english_transcription': q_dict.get('english_transcription') or q_dict.get('english'),
        'notes': q_dict.get('notes'),
        'general_feedback': q_dict.get('general_feedback'),
        'fraction_correct': q_dict.get('fraction_correct', 100),
        'fraction_wrong': q_dict.get('fraction_wrong', -20),
        'shuffle_answers': q_dict.get('shuffle_answers', True),
        'show_num_correct': q_dict.get('show_num_correct', False),
        'correct_feedback': q_dict.get('correct_feedback'),
        'partially_correct_feedback': q_dict.get('partially_correct_feedback'),
        'incorrect_feedback': q_dict.get('incorrect_feedback'),
        'response_lines': q_dict.get('lines', 15),
        'attachments': q_dict.get('attachments', 0),
        'filetypes': q_dict.get('filetypes', '.doc,.docx,.pdf,.png,.jpg,.jpeg'),
        'maxbytes': q_dict.get('maxbytes', 2097152),
        'grader_info': q_dict.get('grader_info'),
    }

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
    Fetch questions from the unified `questions` table,
    including options, matching pairs, and hints.
    Returns a list of question dicts in the converter's internal format.
    """
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    # Base query
    sql = """
        SELECT q.*
        FROM questions q
        WHERE 1=1
    """
    params = []

    # Apply filters if provided
    if filters:
        if 'source' in filters and filters['source']:
            sql += " AND q.source = %s"
            params.append(filters['source'])
        if 'group_name' in filters and filters['group_name']:
            sql += " AND q.`group` = %s"
            params.append(filters['group_name'])
        if 'type' in filters and filters['type']:
            # We don't have a type column; we'll handle this by checking options/pairs existence later
            pass
        if 'question_nos' in filters and filters['question_nos']:
            placeholders = ','.join(['%s'] * len(filters['question_nos']))
            sql += f" AND q.question_number IN ({placeholders})"
            params.extend(filters['question_nos'])

    sql += " ORDER BY q.question_date DESC, q.question_number ASC"
    cursor.execute(sql, params)
    rows = cursor.fetchall()

    questions = []
    for row in rows:
        qid = row['id']

        # ----- EXTRACT NEPALI AND ENGLISH -----
        nep = row.get('nepali_transcription', '') or ''
        eng = row.get('english_transcription', '') or ''
        combined = f"{nep} ({eng})" if nep and eng else (nep or eng)

        # Build the question dict in converter format
        q = {
            'id': qid,
            'question_no': row.get('question_number', ''),
            'text': combined,                     # for human-readable exports
            'nepali_transcription': nep,          # for JSON/backup
            'english_transcription': eng,         # for JSON/backup
            'type': row.get('type', 'essay'),  # default – will be overridden if options/pairs exist
            'general_feedback': row.get('general_feedback') or '',
            'grade': row.get('marks') or 1,
            'penalty': 0,
            'fraction_correct': row.get('fraction_correct', 100),
            'fraction_wrong': row.get('fraction_wrong', -20),
            'shuffle_answers': row.get('shuffle_answers', True),
            'show_num_correct': row.get('show_num_correct', False),
            'correct_feedback': row.get('correct_feedback') or '',
            'partially_correct_feedback': row.get('partially_correct_feedback') or '',
            'incorrect_feedback': row.get('incorrect_feedback') or '',
            'group': row.get('group') or '',
            'options': [],
            'pairs': [],
            'hints': [],
            'institution': row.get('institution') or '',
            'level': row.get('level') or '',
            'paper': row.get('paper') or '',
            'subject': row.get('subject') or '',
            'date': row.get('question_date') or '',
            'chapter': row.get('chapter') or '',
            'marks': row.get('marks'),
            'notes': row.get('notes') or '',
            'source': row.get('source') or '',
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
        if q['options']:
            q['type'] = 'multichoice'  # if options exist, it's MCQ or truefalse

        # Fetch matching pairs
        cursor.execute("SELECT * FROM question_matching_pairs WHERE question_id = %s ORDER BY display_order", (qid,))
        pairs = cursor.fetchall()
        for pair in pairs:
            q['pairs'].append({
                'subquestion': pair['subquestion'],
                'answer': pair['answer']
            })
        if q['pairs']:
            q['type'] = 'matching'

        # Fetch hints
        cursor.execute("SELECT * FROM question_hints WHERE question_id = %s ORDER BY hint_number", (qid,))
        hints = cursor.fetchall()
        for hint in hints:
            q['hints'].append({
                'text': hint['hint_text'],
                'clear_incorrect': bool(hint['clear_incorrect']),
                'show_num_correct': bool(hint['show_num_correct'])
            })

        # If still 'essay' but no options/pairs, keep as essay
        if q['type'] == 'essay' and not q['options'] and not q['pairs']:
            q['type'] = 'essay'

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
                        # update_question(dup_id, **q)
                        update_question(dup_id, **db_dict)
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
