# File: db_handler.py

import sys
from .constants import C
from .text_parser import parse_text_file
from .xml_handler import xml_to_questions
from .json_handler import json_to_questions
from ..db import get_connection
from ..utils import print_colored, COLORS

# -------------------- Table Creation --------------------
def create_tables():
    """Create qc_* tables if they don't exist."""
    conn = get_connection()
    cursor = conn.cursor()

    # qc_questions – includes 'source' column
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS qc_questions (
        id INT AUTO_INCREMENT PRIMARY KEY,
        source VARCHAR(255) DEFAULT NULL,
        type ENUM('multichoice','essay','truefalse','matching') NOT NULL,
        text LONGTEXT NOT NULL,
        general_feedback LONGTEXT,
        default_grade DECIMAL(10,2) DEFAULT 1.00,
        penalty DECIMAL(10,2) DEFAULT 0.00,
        fraction_correct DECIMAL(10,2) DEFAULT 100.00,
        fraction_wrong DECIMAL(10,2) DEFAULT -20.00,
        shuffle_answers BOOLEAN DEFAULT TRUE,
        show_num_correct BOOLEAN DEFAULT FALSE,
        correct_feedback TEXT,
        partially_correct_feedback TEXT,
        incorrect_feedback TEXT,
        question_no INT,
        original_question_no INT,
        group_name VARCHAR(255),
        institution VARCHAR(255) DEFAULT NULL,
        level VARCHAR(255) DEFAULT NULL,
        paper VARCHAR(100) DEFAULT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        INDEX idx_source (source),
        INDEX idx_type (type),
        INDEX idx_group (group_name)
    );
    """)

    # qc_options
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS qc_options (
        id INT AUTO_INCREMENT PRIMARY KEY,
        question_id INT NOT NULL,
        text LONGTEXT NOT NULL,
        fraction DECIMAL(10,2) DEFAULT 0.00,
        feedback LONGTEXT,
        display_order INT DEFAULT 0,
        FOREIGN KEY (question_id) REFERENCES qc_questions(id) ON DELETE CASCADE,
        INDEX idx_question (question_id)
    );
    """)

    # qc_matching_pairs
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS qc_matching_pairs (
        id INT AUTO_INCREMENT PRIMARY KEY,
        question_id INT NOT NULL,
        subquestion LONGTEXT NOT NULL,
        answer LONGTEXT NOT NULL,
        display_order INT DEFAULT 0,
        FOREIGN KEY (question_id) REFERENCES qc_questions(id) ON DELETE CASCADE,
        INDEX idx_question (question_id)
    );
    """)

    # qc_hints
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS qc_hints (
        id INT AUTO_INCREMENT PRIMARY KEY,
        question_id INT NOT NULL,
        hint_text LONGTEXT NOT NULL,
        clear_incorrect BOOLEAN DEFAULT FALSE,
        show_num_correct BOOLEAN DEFAULT FALSE,
        hint_number INT NOT NULL,
        FOREIGN KEY (question_id) REFERENCES qc_questions(id) ON DELETE CASCADE,
        INDEX idx_question (question_id)
    );
    """)

    conn.commit()
    cursor.close()
    conn.close()
    print_colored("[✓] Converter database tables ready.", COLORS.GREEN)

# -------------------- Insert / Update / Delete --------------------
def insert_question(q_dict, source=None):
    """
    Insert a single question (with its options, pairs, hints) into the DB.
    Returns the new qc_questions.id.
    """
    conn = get_connection()
    cursor = conn.cursor()

    # 1. Insert main question
    cursor.execute("""
    INSERT INTO qc_questions (
        source, type, text, general_feedback, default_grade, penalty,
        fraction_correct, fraction_wrong, shuffle_answers, show_num_correct,
        correct_feedback, partially_correct_feedback, incorrect_feedback,
        question_no, original_question_no, group_name
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        source,
        q_dict.get('type', 'multichoice'),
        q_dict.get('text', ''),
        q_dict.get('general_feedback', ''),
        q_dict.get('grade', 1.0),
        q_dict.get('penalty', 0.0),
        q_dict.get('fraction_correct', 100.0),
        q_dict.get('fraction_wrong', -20.0),
        q_dict.get('shuffle_answers', True),
        q_dict.get('show_num_correct', False),
        q_dict.get('correct_feedback', ''),
        q_dict.get('partially_correct_feedback', ''),
        q_dict.get('incorrect_feedback', ''),
        q_dict.get('question_no', 0),
        q_dict.get('original_question_no', q_dict.get('question_no', 0)),
        q_dict.get('group', '')
    ))
    question_id = cursor.lastrowid

    # 2. Insert options (if any)
    for idx, opt in enumerate(q_dict.get('options', [])):
        cursor.execute("""
        INSERT INTO qc_options (question_id, text, fraction, feedback, display_order)
        VALUES (%s, %s, %s, %s, %s)
        """, (
            question_id,
            opt.get('text', ''),
            opt.get('fraction', 0.0),
            opt.get('feedback', ''),
            idx
        ))

    # 3. Insert matching pairs (if any)
    for idx, pair in enumerate(q_dict.get('pairs', [])):
        cursor.execute("""
        INSERT INTO qc_matching_pairs (question_id, subquestion, answer, display_order)
        VALUES (%s, %s, %s, %s)
        """, (
            question_id,
            pair.get('subquestion', ''),
            pair.get('answer', ''),
            idx
        ))

    # 4. Insert hints (if any)
    for idx, hint in enumerate(q_dict.get('hints', []), 1):
        cursor.execute("""
        INSERT INTO qc_hints (question_id, hint_text, clear_incorrect, show_num_correct, hint_number)
        VALUES (%s, %s, %s, %s, %s)
        """, (
            question_id,
            hint.get('text', ''),
            hint.get('clear_incorrect', False),
            hint.get('show_num_correct', False),
            idx
        ))

    conn.commit()
    cursor.close()
    conn.close()
    return question_id


def get_questions(filters=None):
    """
    Filters can include:
    - source, type, group_name
    - question_no_min, question_no_max
    - question_nos: a list of question numbers (e.g., [1,3,5])
    """
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    sql = "SELECT * FROM qc_questions"
    params = []
    conditions = []

    if filters:
        if 'source' in filters:
            conditions.append("source = %s")
            params.append(filters['source'])
        if 'type' in filters:
            conditions.append("type = %s")
            params.append(filters['type'])
        if 'group_name' in filters:
            conditions.append("group_name = %s")
            params.append(filters['group_name'])
        if 'question_no_min' in filters:
            conditions.append("question_no >= %s")
            params.append(filters['question_no_min'])
        if 'question_no_max' in filters:
            conditions.append("question_no <= %s")
            params.append(filters['question_no_max'])
        if 'question_nos' in filters and filters['question_nos']:
            # filters['question_nos'] is a list of integers
            placeholders = ','.join(['%s'] * len(filters['question_nos']))
            conditions.append(f"question_no IN ({placeholders})")
            params.extend(filters['question_nos'])

    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY question_no ASC"
    cursor.execute(sql, params)
    rows = cursor.fetchall()

    questions = []
    for row in rows:
        qid = row['id']
        # Build the question dict
        q = {
            'id': qid,  # we keep DB id for reference
            'type': row['type'],
            'text': row['text'],
            'general_feedback': row['general_feedback'] or '',
            'grade': float(row['default_grade']),
            'penalty': float(row['penalty']),
            'fraction_correct': float(row['fraction_correct']),
            'fraction_wrong': float(row['fraction_wrong']),
            'shuffle_answers': bool(row['shuffle_answers']),
            'show_num_correct': bool(row['show_num_correct']),
            'correct_feedback': row['correct_feedback'] or '',
            'partially_correct_feedback': row['partially_correct_feedback'] or '',
            'incorrect_feedback': row['incorrect_feedback'] or '',
            'question_no': row['question_no'],
            'original_question_no': row['original_question_no'],
            'group': row['group_name'] or '',
            'source': row['source'] or '',
            'options': [],
            'pairs': [],
            'hints': [],
        }

        # Fetch options
        cursor.execute("SELECT * FROM qc_options WHERE question_id = %s ORDER BY display_order", (qid,))
        opts = cursor.fetchall()
        for opt in opts:
            q['options'].append({
                'text': opt['text'],
                'fraction': float(opt['fraction']),
                'feedback': opt['feedback'] or '',
                'correct': float(opt['fraction']) > 0  # correct if fraction > 0
            })

        # Fetch matching pairs
        cursor.execute("SELECT * FROM qc_matching_pairs WHERE question_id = %s ORDER BY display_order", (qid,))
        pairs = cursor.fetchall()
        for pair in pairs:
            q['pairs'].append({
                'subquestion': pair['subquestion'],
                'answer': pair['answer']
            })

        # Fetch hints
        cursor.execute("SELECT * FROM qc_hints WHERE question_id = %s ORDER BY hint_number", (qid,))
        hints = cursor.fetchall()
        for hint in hints:
            q['hints'].append({
                'text': hint['hint_text'],
                'clear_incorrect': bool(hint['clear_incorrect']),
                'show_num_correct': bool(hint['show_num_correct'])
            })

        questions.append(q)

    cursor.close()
    conn.close()
    return questions


def delete_question(qid):
    """Delete a question (cascade will remove dependent rows)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM qc_questions WHERE id = %s", (qid,))
    affected = cursor.rowcount
    conn.commit()
    cursor.close()
    conn.close()
    return affected > 0


def update_question(qid, q_dict, source=None):
    """
    Update an existing question and its related rows (replace all).
    If source is provided, update the source as well.
    """
    # First delete existing related rows (options, pairs, hints)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM qc_options WHERE question_id = %s", (qid,))
    cursor.execute("DELETE FROM qc_matching_pairs WHERE question_id = %s", (qid,))
    cursor.execute("DELETE FROM qc_hints WHERE question_id = %s", (qid,))

    # Update main question
    cursor.execute("""
    UPDATE qc_questions SET
        source = COALESCE(%s, source),
        type = %s,
        text = %s,
        general_feedback = %s,
        default_grade = %s,
        penalty = %s,
        fraction_correct = %s,
        fraction_wrong = %s,
        shuffle_answers = %s,
        show_num_correct = %s,
        correct_feedback = %s,
        partially_correct_feedback = %s,
        incorrect_feedback = %s,
        question_no = %s,
        original_question_no = %s,
        group_name = %s
    WHERE id = %s
    """, (
        source,
        q_dict.get('type', 'multichoice'),
        q_dict.get('text', ''),
        q_dict.get('general_feedback', ''),
        q_dict.get('grade', 1.0),
        q_dict.get('penalty', 0.0),
        q_dict.get('fraction_correct', 100.0),
        q_dict.get('fraction_wrong', -20.0),
        q_dict.get('shuffle_answers', True),
        q_dict.get('show_num_correct', False),
        q_dict.get('correct_feedback', ''),
        q_dict.get('partially_correct_feedback', ''),
        q_dict.get('incorrect_feedback', ''),
        q_dict.get('question_no', 0),
        q_dict.get('original_question_no', q_dict.get('question_no', 0)),
        q_dict.get('group', ''),
        qid
    ))

    # Re-insert options, pairs, hints (same as insert)
    for idx, opt in enumerate(q_dict.get('options', [])):
        cursor.execute("""
        INSERT INTO qc_options (question_id, text, fraction, feedback, display_order)
        VALUES (%s, %s, %s, %s, %s)
        """, (qid, opt.get('text', ''), opt.get('fraction', 0.0), opt.get('feedback', ''), idx))

    for idx, pair in enumerate(q_dict.get('pairs', [])):
        cursor.execute("""
        INSERT INTO qc_matching_pairs (question_id, subquestion, answer, display_order)
        VALUES (%s, %s, %s, %s)
        """, (qid, pair.get('subquestion', ''), pair.get('answer', ''), idx))

    for idx, hint in enumerate(q_dict.get('hints', []), 1):
        cursor.execute("""
        INSERT INTO qc_hints (question_id, hint_text, clear_incorrect, show_num_correct, hint_number)
        VALUES (%s, %s, %s, %s, %s)
        """, (qid, hint.get('text', ''), hint.get('clear_incorrect', False), hint.get('show_num_correct', False), idx))

    conn.commit()
    cursor.close()
    conn.close()
    return True

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
            insert_question(q, source=source)
            count += 1
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
