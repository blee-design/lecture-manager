import sys
import time
from collections import Counter
from types import SimpleNamespace

from .constants import C          # <-- add this
from .utils import log, filter_questions
from ..utils import print_colored, COLORS, color_text
from ..db import get_connection
from .exceptions import DuplicateQuestionError, ConverterError
from .text_parser import parse_text_file
from .xml_handler import xml_to_questions
from .json_handler import json_to_questions

def map_paper_value(paper_str):
    if not paper_str:
        return None
    paper_str = paper_str.strip()
    lower = paper_str.lower()

    # Direct exact mapping
    exact_map = {
        'pretest': 'pretest',
        'pretest officer': 'pretest',
        'paper_i': 'paper_i',
        'paper i': 'paper_i',
        'paper 1': 'paper_i',
        'first paper': 'paper_i',
        'first paper: economics': 'paper_i',
        'paper_ii': 'paper_ii',
        'paper ii': 'paper_ii',
        'paper 2': 'paper_ii',
        'second paper': 'paper_ii',
        'second paper: management': 'paper_ii',
        'paper_iii': 'paper_iii',
        'paper iii': 'paper_iii',
        'paper 3': 'paper_iii',
        'third paper': 'paper_iii',
        'third paper: research methodologies, ict and banking laws & regulation': 'paper_iii',
    }

    if lower in exact_map:
        return exact_map[lower]

    # If no match, return None to avoid invalid ENUM values
    return None

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
    from ..question_bank import add_question, check_duplicate

    def clean_value(val):
        if val is None:
            return None
        if isinstance(val, str):
            val = val.strip()
            return val if val != '' else None
        return val

    # Extract and clean all fields
    date = clean_value(q_dict.get('question_date'))
    institution = clean_value(q_dict.get('institution'))
    level = clean_value(q_dict.get('level'))
    paper = map_paper_value(clean_value(q_dict.get('paper')))
    group = clean_value(q_dict.get('group'))

    qno = q_dict.get('question_no')
    if qno is not None and str(qno).strip():
        question_number = str(qno).strip().zfill(2)
    else:
        question_number = None

    # Check duplicate (now uses NULL for empty fields)
    dup_id = check_duplicate(date, institution, level, paper, group, question_number)
    print(f"[DEBUG] Checking duplicate: date={date}, institution={institution}, level={level}, paper={paper}, group={group}, qno={question_number}")

    if dup_id:
        if force:
            # ... existing update logic (unchanged) ...
            update_question(dup_id, ...)
            return dup_id
        else:
            raise DuplicateQuestionError(
                f"Question already exists with ID {dup_id} for {date} {institution} {level} {paper} {group} Q{question_number}"
            )

    # No duplicate – insert new (call add_question with the same cleaned values)
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
        force=True,
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
        grader_info=q_dict.get('grader_info'),
        syllabus_code=q_dict.get('syllabus_code'),
        q_type=q_dict.get('type', 'essay')
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
    from ..question_bank import update_question as update_q
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
    from ..question_bank import delete_question as delete_q
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
    if args is None:
        args = SimpleNamespace(verbose=False, bypass_duplicate=False, bypass_option=False, questions=None)

    log(f"📂 Importing from {file_path} (format: {format})", "INFO", args.verbose)

    start_time = time.time()

    # Parse questions
    if format == 'txt':
        questions, bypass_used, skipped_lines = parse_text_file(file_path, args)
    elif format == 'xml':
        questions = xml_to_questions(file_path, args.verbose)
    elif format == 'json':
        questions = json_to_questions(file_path, args.verbose)
    else:
        raise ValueError(f"Unsupported import format: {format}")

    # --- Apply question filter if specified ---
    if args.questions:
        original_count = len(questions)
        questions = filter_questions(questions, args.questions, args.verbose)
        filtered_out = original_count - len(questions)
        if args.verbose and filtered_out > 0:
            log(f"Filtered out {filtered_out} questions, keeping {len(questions)}", "INFO", args.verbose)

    total = len(questions)
    if total == 0:
        print_colored("⚠️  No questions found in the file.", COLORS.YELLOW)
        return 0, []

    # Count types
    type_counts = Counter(q.get('type', 'essay') for q in questions)

    count = 0
    skipped = 0
    errors = []

    print_colored(f"\n📥 Starting import of {total} questions...", COLORS.CYAN)
    if source:
        print_colored(f"   Source: {source}", COLORS.BLUE)
    if args.verbose:
        print_colored(f"   Types: {', '.join(f'{k}: {v}' for k, v in type_counts.items())}", COLORS.BLUE)

        for idx, q in enumerate(questions, 1):
            if args.verbose and (idx % 5 == 0 or idx == total or total <= 5):
                print(f"  [{idx}/{total}] Processing question {q.get('question_no', '?')}...")

            try:
                insert_question(q, source=source, force=args.bypass_duplicate)
                count += 1
            except DuplicateQuestionError as e:
                if args.verbose:
                    print(f"    {C.YELLOW}⏭️  Skipped duplicate: {e}{C.RESET}")
                skipped += 1
            except Exception as e:
                errors.append(str(e))
                if args.verbose:
                    print(f"    {C.RED}❌ Error: {e}{C.RESET}")

    elapsed = time.time() - start_time

    # ---- Summary ----
    print("\n" + "═" * 60)
    print_colored("  📋 IMPORT SUMMARY", COLORS.CYAN, bold=True)
    print("═" * 60)
    print(f"  {COLORS.GREEN}✅ Inserted   : {count}{COLORS.RESET}")
    print(f"  {COLORS.YELLOW}⏭️  Skipped    : {skipped}{COLORS.RESET}")
    if errors:
        print(f"  {COLORS.RED}❌ Errors     : {len(errors)}{COLORS.RESET}")
    else:
        print(f"  {COLORS.GREEN}❌ Errors     : 0{COLORS.RESET}")
    print(f"  ⏱️  Time       : {elapsed:.2f}s")
    print(f"  📊 Success rate: {count/total*100:.1f}%" if total else "  📊 Success rate: N/A")
    print("═" * 60)

    if args.verbose and errors:
        print_colored(f"\n  First 5 errors:", COLORS.YELLOW)
        for e in errors[:5]:
            print(f"    {e}")
        if len(errors) > 5:
            print(f"    ... and {len(errors)-5} more")

    return count, errors

def export_to_file(questions, output_file, format, args=None):
    if args is None:
        args = type('Args', (), {'verbose': False})()
    import time
    start_time = time.time()
    log(f"📤 Exporting {len(questions)} questions to {output_file} (format: {format})", "INFO", args.verbose)

    total = len(questions)
    # Count types
    from collections import Counter
    type_counts = Counter(q.get('type', 'essay') for q in questions)
    if args.verbose:
        print_colored(f"   Types: {', '.join(f'{k}: {v}' for k, v in type_counts.items())}", COLORS.BLUE)

    # Perform export
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

    elapsed = time.time() - start_time
    # ---- Summary (unchanged) ----
    print("\n" + "═" * 60)
    print_colored("  📤 EXPORT SUMMARY", COLORS.CYAN, bold=True)
    print("═" * 60)
    print(f"  📁 Output file: {output_file}")
    print(f"  📊 Questions  : {len(questions)}")
    print(f"  🏷️  Format     : {format}")
    print(f"  ⏱️  Time       : {elapsed:.2f}s")
    print("═" * 60)
