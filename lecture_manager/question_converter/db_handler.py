import sys
import re
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
    raw = paper_str.strip().lower()

    from ..syllabus_config import get_papers
    for p in get_papers(active_only=False):
        key    = (p.get('paper_key') or '').lower()
        name   = (p.get('display_name') or '').lower()
        folder = (p.get('folder_name') or '').lower()
        if raw in (key, name, folder):
            return p['paper_key']

    # Legacy aliases for very old files
    legacy = {
        'pretest officer': 'pretest',
        'first paper': 'paper_i',
        'first paper: economics': 'paper_i',
        'second paper': 'paper_ii',
        'second paper: management': 'paper_ii',
        'third paper': 'paper_iii',
        'third paper: research methodologies, ict and banking laws & regulation': 'paper_iii',
    }
    return legacy.get(raw)

def _compute_marks(q_dict):
    """
    Determine the marks value for a question from various sources.

    Priority:
      1. Explicit 'marks' value (from TXT 'Marks:' line, or CSV column)
      2. 'grade' value (Moodle <defaultgrade>, or JSON 'grade')
      3. Detect "5+5" style pattern in notes and sum the parts
      4. None
    """
    marks = q_dict.get('marks')
    if marks is not None:
        try:
            return int(marks)
        except (ValueError, TypeError):
            pass

    grade = q_dict.get('grade')
    if grade is not None:
        try:
            return int(float(grade))
        except (ValueError, TypeError):
            pass

    notes = (q_dict.get('notes') or '')
    if isinstance(notes, str):
        match = re.search(r'(\d+(?:\s*\+\s*\d+)+)', notes)
        if match:
            parts = re.split(r'\s*\+\s*', match.group(1))
            try:
                return sum(int(p) for p in parts)
            except ValueError:
                pass

    return None


def _split_text_into_transcriptions(q_dict):
    """
    Return (nepali_value, english_value) for the given question dict.

    Rules:
      - If both 'nepali_transcription' and 'english_transcription' are explicitly
        provided, use them as-is.
      - Otherwise, examine 'text' (the combined field the parsers set).
        - If 'text' contains Devanagari characters, put it in Nepali.
        - Otherwise, put it in English.
      - Never duplicate the same value into both columns.
    """
    nep = q_dict.get('nepali_transcription')
    eng = q_dict.get('english_transcription')

    # If both explicitly provided, trust them.
    if nep is not None or eng is not None:
        return (nep or ''), (eng or '')

    text = q_dict.get('text') or ''
    if not text:
        return '', ''

    has_devanagari = bool(re.search(r'[\u0900-\u097F]', text))
    if has_devanagari:
        return text, ''
    return '', text

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
    from ..question_bank import add_question, check_duplicate, update_question

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
    from ..syllabus_config import get_papers
    if q_dict.get('paper') and not paper:
        valid = [p['paper_key'] for p in get_papers(active_only=False)]
        raise ValidationError(
            f"Unknown paper value: {q_dict['paper']!r}. "
            f"Valid keys: {valid}. Fix the source file or add the paper via Syllabus Setup."
        )
    group = clean_value(q_dict.get('group'))

    qno = q_dict.get('question_no')
    if qno is not None and str(qno).strip():
        question_number = str(qno).strip().zfill(2)
    else:
        question_number = None

    # Check duplicate
    dup_id = check_duplicate(date, institution, level, paper, group, question_number)
    if dup_id:
        if force:
            # Build keyword arguments for update
            nep_val, eng_val = _split_text_into_transcriptions(q_dict)
            update_kwargs = {
                'subject': q_dict.get('subject', ''),
                'paper': paper,
                'group': group,
                'marks': _compute_marks(q_dict),
                'penalty': q_dict.get('penalty', 0),
                'chapter': q_dict.get('chapter', ''),
                'question_number': question_number,
                'nepali_transcription': nep_val,
                'english_transcription': eng_val,
                'level': level,
                'notes': q_dict.get('notes'),
                'options': q_dict.get('options'),
                'pairs': q_dict.get('pairs'),
                'hints': q_dict.get('hints'),
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
                'syllabus_code': q_dict.get('syllabus_code'),
                'type': q_dict.get('type', 'essay'),
                'feedback_true': q_dict.get('feedback_true'),
                'feedback_false': q_dict.get('feedback_false'),
                'exam_type': q_dict.get('exam_type', 'open'),
                'alias': (q_dict.get('alias') or None),
            }
            # Remove None values so defaults are used
            update_kwargs = {k: v for k, v in update_kwargs.items() if v is not None}
            result = update_question(dup_id, **update_kwargs)
            if result == 'updated':
                return 'updated', dup_id
            elif result == 'no_change':
                return 'unchanged', dup_id   # <-- NEW: treat no_change as success
            else:
                # Only raise for actual errors (e.g., 'error: something')
                raise Exception(f"Update failed: {result}")
        else:
            raise DuplicateQuestionError(
                f"Question already exists with ID {dup_id} for {date} {institution} {level} {paper} {group} Q{question_number}"
            )

    # No duplicate – insert new
    nep_val, eng_val = _split_text_into_transcriptions(q_dict)
    qid = add_question(
        exam_type=q_dict.get('exam_type', 'open'),
        alias=(q_dict.get('alias') or None),
        date=date,
        institution=institution,
        subject=q_dict.get('subject', ''),
        paper=paper,
        group=group,
        marks=_compute_marks(q_dict),
        penalty=q_dict.get('penalty', 0),
        chapter=q_dict.get('chapter', ''),
        question_number=question_number,
        nepali=nep_val,
        english=eng_val,
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
        q_type=q_dict.get('type', 'essay'),
        feedback_true=q_dict.get('feedback_true'),
        feedback_false=q_dict.get('feedback_false'),
    )
    return 'inserted', qid

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
            'alias': row.get('alias'),
            'paper': row.get('paper') or '',
            'subject': row.get('subject') or '',
            'date': row.get('question_date') or '',
            'chapter': row.get('chapter') or '',
            'marks': row.get('marks'),
            'notes': row.get('notes') or '',
            'source': row.get('source') or '',
            'exam_type': row.get('exam_type') or 'open',
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

    count = 0      # inserted
    updated = 0
    unchanged = 0
    skipped = 0
    errors = []

    for idx, q in enumerate(questions, 1):
        q_no = q.get('question_no', '?')

        # ---- Verbose duplicate check info (restored) ----
        if args.verbose:
            dup_info = (
                f"date={q.get('question_date')}, "
                f"institution={q.get('institution')}, "
                f"level={q.get('level')}, "
                f"paper={q.get('paper')}, "
                f"group={q.get('group')}, "
                f"qno={q_no}"
            )
            print(f"[DEBUG] Checking duplicate: {dup_info}")

        try:
            status, qid = insert_question(q, source=source, force=args.bypass_duplicate)
            if status == 'inserted':
                count += 1
                if args.verbose:
                    print(f"    {C.GREEN}✅ Inserted (ID: {qid}){C.RESET}")
            elif status == 'updated':
                updated += 1
                if args.verbose:
                    print(f"    {C.BLUE}🔄 Updated (ID: {qid}){C.RESET}")
            elif status == 'unchanged':
                unchanged += 1
                if args.verbose:
                    print(f"    {C.CYAN}🔁 Unchanged (ID: {qid}){C.RESET}")
        except DuplicateQuestionError as e:
            skipped += 1
            if args.verbose:
                print(f"    {C.YELLOW}⏭️  Skipped duplicate: {e}{C.RESET}")
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
    print(f"  {COLORS.BLUE}🔄 Updated    : {updated}{COLORS.RESET}")
    print(f"  {COLORS.CYAN}🔁 Unchanged  : {unchanged}{COLORS.RESET}")   # <-- new
    print(f"  {COLORS.YELLOW}⏭️  Skipped    : {skipped}{COLORS.RESET}")
    if errors:
        print(f"  {COLORS.RED}❌ Errors     : {len(errors)}{COLORS.RESET}")
    else:
        print(f"  {COLORS.GREEN}❌ Errors     : 0{COLORS.RESET}")
    print(f"  ⏱️  Time       : {elapsed:.2f}s")
    total_processed = count + updated + unchanged + skipped
    if total_processed > 0:
        success_rate = (count + updated + unchanged) / total_processed * 100
        print(f"  📊 Success rate: {success_rate:.1f}%")
    else:
        print("  📊 Success rate: N/A")
    print("═" * 60)

    # ---- Final user-friendly message ----
    if count == 0 and updated == 0 and unchanged == 0 and skipped == 0 and not errors:
        print_colored("[i] No questions were processed.", COLORS.YELLOW)
    elif count == 0 and updated == 0 and skipped == 0 and errors == 0 and unchanged > 0:
        print_colored("[i] All questions are already up‑to‑date. Nothing new to insert or update.", COLORS.BLUE)
    elif count == 0 and updated == 0 and skipped == 0 and errors == 0:
        print_colored("[i] No changes were made.", COLORS.YELLOW)
    else:
        if count > 0:
            print_colored(f"[✓] Inserted {count} new question{'s' if count != 1 else ''}.", COLORS.GREEN)
        if updated > 0:
            print_colored(f"[✓] Updated {updated} existing question{'s' if updated != 1 else ''}.", COLORS.BLUE)
        if unchanged > 0:
            print_colored(f"[i] {unchanged} question{'s' if unchanged != 1 else ''} were unchanged.", COLORS.CYAN)
        if skipped > 0:
            print_colored(f"[!] Skipped {skipped} duplicate question{'s' if skipped != 1 else ''}.", COLORS.YELLOW)
        if errors:
            print_colored(f"[!] {len(errors)} error{'s' if len(errors) != 1 else ''} occurred.", COLORS.RED)

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
