# File text_parser.py

import sys
import re
from .utils import (
    log, normalize_text, is_correct_option,
    filter_questions, find_line_in_file, format_passage_in_question
)
from .constants import C
from .exceptions import ConverterError, ParseError, ValidationError, IOError

# Define valid question types
VALID_QUESTION_TYPES = ["multichoice", "essay", "truefalse", "matching"]

# Define valid field names for questions
VALID_FIELD_NAMES = {
    'type', 'option', 'correct', 'correct answer',
    'feedback true', 'feedback_true', 'feedback false', 'feedback_false',
    'general feedback', 'grader information', 'fraction', 'penalty',
    'grade', 'lines', 'attachments', 'filetypes', 'maxfilesizemb',
    # Matching question fields
    'subquestion', 'answer', 'shuffle answers', 'show number correct',
    'correct feedback', 'partially correct feedback', 'incorrect feedback',
    'hint', 'hint clear incorrect', 'hint show number correct',
    # Bank TXT fields
    'nepali', 'english', 'marks', 'chapter', 'source'
}

# ----- PASSAGE FEATURE: extract passages from content -----
def extract_passages(content, verbose=False):
    passages = {}
    lines = content.splitlines(keepends=True)
    output_lines = []
    i = 0
    total = len(lines)

    while i < total:
        line = lines[i].strip()
        match = re.match(r'^\[passage\s*:\s*([^\]]+)\]$', line, re.IGNORECASE)
        if match:
            identifier = match.group(1).strip()
            log(f"Found passage definition: {identifier}", "INFO", verbose)
            passage_lines = []
            i += 1
            while i < total:
                next_line_raw = lines[i]
                next_line_stripped = next_line_raw.strip()
                # Stop at next passage marker
                if re.match(r'^\[passage\s*:\s*[^\]]+\]$', next_line_stripped, re.IGNORECASE):
                    break
                # Stop at a line that starts a question
                if next_line_stripped and re.match(r'^Question(\s+No\.?)?\s*\d*', next_line_stripped, re.IGNORECASE):
                    break
                # Stop at a line that starts a group marker
                if next_line_stripped and re.match(r'^\[group', next_line_stripped, re.IGNORECASE):
                    break
                # ----- ADD THIS: stop at a line that starts a comment -----
                if next_line_stripped and re.match(r'^(#|//|/\*|---|\*\*\*)', next_line_stripped):
                    break
                # ----------------------------------------------------------
                passage_lines.append(lines[i])
                i += 1
            passage_text = ''.join(passage_lines).rstrip('\n')
            passages[identifier] = passage_text
        else:
            output_lines.append(lines[i])
            i += 1

    return passages, ''.join(output_lines)

def remove_passage_marker(line, passages, verbose=False):
    """Remove (passage:identifier) from the line and return the cleaned line and the identifier.
    Raises SystemExit if the referenced passage is not defined."""
    pattern = re.compile(r'\(\s*passage\s*[:]?\s*([\w\s\-]+?)\s*\)', re.IGNORECASE)
    match = pattern.search(line)
    if not match:
        return line, None
    identifier = match.group(1).strip()
    if identifier not in passages:
        # Find the position of the marker for a better error message
        marker_start = match.start()
        start = max(0, marker_start - 30)
        end = min(len(line), marker_start + 50)
        snippet = line[start:end]
        raise UndefinedPassageError(f"Passage reference to undefined passage: '{identifier}' (available: {list(passages.keys())})")
        print(f"{C.YELLOW}Line snippet: ...{snippet}...{C.RESET}")
    cleaned = pattern.sub('', line).strip()
    return cleaned, identifier
# ----- END PASSAGE FEATURE -----

def validate_question_type(q_type, question_no, line_no, question_text):
    """Validate question type and provide helpful error message"""
    if q_type not in VALID_QUESTION_TYPES:
        raise UnknownQuestionTypeError(f"Unknown question type: '{q_type}' in question {question_no} (line {line_no})")
        return False
    return True

def setup_truefalse_options(question):
    """Set up True/False options for a question"""
    if "correct_answer" not in question:
        # Default to True if not specified
        question["correct_answer"] = True
        log(f"  Question {question.get('question_no', '?')}: No correct answer specified, defaulting to True", "WARN", True)

    # Set up True/False options
    correct = question.pop("correct_answer", True)
    question["options"] = [
        {"text": "True", "correct": correct == True},
        {"text": "False", "correct": correct == False}
    ]
    question["fraction_correct"] = 100  # Correct answer gets 100%
    question["fraction_wrong"] = -20    # Wrong answer gets -20%
    log(f"  Question {question.get('question_no', '?')}: Set up True/False options (Correct: {correct}) with fractions 100%/-20%", "INFO", True)

def needs_latex_processing(text):
    """Check if text contains LaTeX math blocks that need special handling"""
    if not text:
        return False

    # LaTeX patterns to look for
    latex_patterns = [
        r'\$\$.*?\$\$',        # Display math: $$...$$
        r'\$.*?\$',            # Inline math: $...$
        r'\\\(.*?\\\)',        # Inline math: \(...\)
        r'\\\[.*?\\\]'         # Display math: \[...\]
    ]

    for pattern in latex_patterns:
        if re.search(pattern, text):
            return True

    return False

def save_field_to_question(question, field_name, field_content, line_no=None):
    """Save a field to the question dictionary with proper processing"""
    # Get the question text for error reporting
    question_text = question.get("text", "")
    question_no = question.get("question_no", "?")

    # ===== HANDLE HINT FIELDS FIRST (before validation) =====
    # Special handling for hint fields (Hint 1, Hint 1 Clear Incorrect, etc.)
    # Check if it starts with "hint" (case-insensitive)
    if field_name.lower().startswith('hint'):
        # Parse hint number and type
        parts = field_name.lower().split()
        hint_num = 1
        hint_type = 'text'

        if len(parts) > 1:
            # Try to parse hint number
            try:
                hint_num = int(parts[1])
            except:
                hint_num = 1

            # Check for hint options
            if len(parts) > 2:
                if 'clear' in parts[2]:
                    hint_type = 'clear_incorrect'
                elif 'show' in parts[2]:
                    hint_type = 'show_num_correct'
                elif 'incorrect' in parts[2]:
                    hint_type = 'clear_incorrect'
                elif 'number' in parts[2] or 'correct' in parts[2]:
                    hint_type = 'show_num_correct'

        # Initialize hints array if needed
        if "hints" not in question:
            question["hints"] = []

        # Ensure we have enough hint entries
        while len(question["hints"]) < hint_num:
            question["hints"].append({
                "text": "",
                "clear_incorrect": False,
                "show_num_correct": False
            })

        hint_idx = hint_num - 1

        if hint_type == 'text':
            question["hints"][hint_idx]["text"] = field_content.replace('\n', '<br>')
            log(f"  Question {question.get('question_no', '?')}: Added hint {hint_num} text", "INFO", True)
        elif hint_type == 'clear_incorrect':
            if field_content.lower() in ['true', 'false']:
                question["hints"][hint_idx]["clear_incorrect"] = field_content.lower() == 'true'
                log(f"  Question {question.get('question_no', '?')}: Set hint {hint_num} clear incorrect to {question['hints'][hint_idx]['clear_incorrect']}", "INFO", True)
            else:
                print(f"{C.RED}[ERROR] Invalid value for 'Hint {hint_num} Clear Incorrect': '{field_content}'{C.RESET}")
                sys.exit(1)
        elif hint_type == 'show_num_correct':
            if field_content.lower() in ['true', 'false']:
                question["hints"][hint_idx]["show_num_correct"] = field_content.lower() == 'true'
                log(f"  Question {question.get('question_no', '?')}: Set hint {hint_num} show number correct to {question['hints'][hint_idx]['show_num_correct']}", "INFO", True)
            else:
                print(f"{C.RED}[ERROR] Invalid value for 'Hint {hint_num} Show Number Correct': '{field_content}'{C.RESET}")
                sys.exit(1)

        return  # Skip further validation for hint fields
    # ===== END HINT HANDLING =====

    # ===== VALIDATE NON-HINT FIELDS =====
    # Validate field name
    if field_name not in VALID_FIELD_NAMES:
        raise ParseError(f"Unknown field: '{field_name}' in question {question_no} (line {line_no})")
        if line_no and line_no > 0:
            print(f"        Line No.: {line_no}")
        print(f"        Question: {question_text[:80]}...")
        print(f"{C.YELLOW}        Allowed field names:")
        print(f"        • Type: [multichoice|essay|truefalse|matching]")
        print(f"        • Option: [text] [* or [Correct]]")
        print(f"        • Correct: [true|false] (for True/False)")
        print(f"        • Grade: [number]")
        print(f"        • Penalty: [number]")
        print(f"        • General Feedback: [text]")
        print(f"        • Feedback True: [text] (for True/False)")
        print(f"        • Feedback False: [text] (for True/False)")
        print(f"        • Lines: [number] (for essay)")
        print(f"        • Attachments: [number] (for essay)")
        print(f"        • FileTypes: [extensions] (for essay)")
        print(f"        • MaxFileSizeMB: [number] (for essay)")
        print(f"        • Grader Information: [text] (for essay)")
        print(f"        • Fraction: [correct% wrong%] (for MCQ)")
        print(f"        • Subquestion: [text] (for matching)")
        print(f"        • Answer: [text] (for matching)")
        print(f"        • Shuffle Answers: [true|false] (for matching)")
        print(f"        • Show Number Correct: [true|false] (for matching)")
        print(f"        • Correct Feedback: [text] (for matching)")
        print(f"        • Partially Correct Feedback: [text] (for matching)")
        print(f"        • Incorrect Feedback: [text] (for matching)")
        print(f"        • Hint [number]: [text] (e.g., Hint 1: Some hint)")
        print(f"        • Hint [number] Clear Incorrect: [true|false] (e.g., Hint 1 Clear Incorrect: true)")
        print(f"        • Hint [number] Show Number Correct: [true|false] (e.g., Hint 1 Show Number Correct: true)")
        print(f"")
        print(f"        Check for typos in field names and ensure they start with a capital letter.")
        print(f"        Example: 'Type: multichoice', not 'type: multichoice'{C.RESET}")

    # ===== HANDLE SPECIFIC FIELD TYPES =====
    if field_name == 'type':
        q_type = field_content.lower()

        # Validate question type
        if not validate_question_type(q_type, question_no, line_no, question_text):
            raise ValidationError("Detailed error message")

        question["type"] = q_type
        log(f"  Question {question_no}: Set type to '{q_type}'", "INFO", True)

        # If type is truefalse, set default fractions
        if q_type == "truefalse":
            question.setdefault("fraction_correct", 100)
            question.setdefault("fraction_wrong", -20)
            # If we already have a correct_answer, set up options
            if "correct_answer" in question:
                setup_truefalse_options(question)

    elif field_name == 'option':
        raw = field_content

        # Check if the question text contains LaTeX math blocks
        question_text = question.get("text", "")
        has_latex_in_question = needs_latex_processing(question_text)

        # Use context-aware LaTeX processing
        if has_latex_in_question:
            log(f"  Question {question.get('question_no', '?')}: Question contains LaTeX, using LaTeX-aware option parsing", "INFO", True)

        correct, clean = is_correct_option(raw, has_latex_in_question=has_latex_in_question)

        question["options"].append({"text": clean, "correct": correct})

        if correct:
            log(f"  Question {question.get('question_no', '?')}: Added CORRECT option: {clean[:50]}...", "INFO", True)
        else:
            log(f"  Question {question.get('question_no', '?')}: Added option: {clean[:50]}...", "INFO", True)

    elif field_name == 'correct' or field_name == 'correct answer':  # Handle both formats
        if field_content.lower() in ['true', 'false']:
            question["correct_answer"] = field_content.lower() == 'true'
            log(f"  Question {question.get('question_no', '?')}: Set correct answer to {field_content}", "INFO", True)

            # Set default fractions for True/False
            question.setdefault("fraction_correct", 100)
            question.setdefault("fraction_wrong", -20)

            # If question type is already truefalse, set up options immediately
            if question.get("type") == "truefalse":
                setup_truefalse_options(question)
        else:
            print(f"{C.RED}[ERROR] Invalid value for 'Correct' field: '{field_content}'{C.RESET}")
            print(f"        Question No.: {question_no}")
            if line_no and line_no > 0:
                print(f"        Line No.: {line_no}")
            print(f"        Question: {question_text[:80]}...")
            raise ValidationError(f"Invalid value for 'Correct' field: '{field_content}'. Must be 'true' or 'false'.")

    elif field_name == 'feedback true' or field_name == 'feedback_true':
        question["feedback_true"] = field_content.replace('\n', '<br>')
        log(f"  Question {question.get('question_no', '?')}: Added feedback for True", "INFO", True)

    elif field_name == 'feedback false' or field_name == 'feedback_false':
        question["feedback_false"] = field_content.replace('\n', '<br>')
        log(f"  Question {question.get('question_no', '?')}: Added feedback for False", "INFO", True)

    elif field_name == 'general feedback':
        # Preserve newlines by converting them to <br> for HTML display
        question["general_feedback"] = field_content.replace('\n', '<br>')
        log(f"  Question {question.get('question_no', '?')}: Added general feedback", "INFO", True)

    elif field_name == 'grader information':
        question["grader_info"] = field_content.replace('\n', '<br>')
        log(f"  Question {question.get('question_no', '?')}: Added grader information", "INFO", True)

    elif field_name == 'fraction':
        parts = field_content.split()
        if len(parts) == 2:
            question["fraction_correct"] = float(parts[0])
            question["fraction_wrong"] = float(parts[1])
            log(f"  Question {question.get('question_no', '?')}: Set fractions - Correct: {parts[0]}%, Wrong: {parts[1]}%", "INFO", True)
        else:
            print(f"{C.RED}[ERROR] Invalid fraction format: '{field_content}'{C.RESET}")
            print(f"        Question No.: {question_no}")
            if line_no and line_no > 0:
                print(f"        Line No.: {line_no}")
            print(f"        Question: {question_text[:80]}...")
            print(f"        Example: '100 -20'{C.RESET}")
            raise ValidationError(f"Invalid fraction format: '{field_content}'. Use 'correct% wrong%'.")

    elif field_name == 'penalty':
        try:
            question["penalty"] = float(field_content)
            log(f"  Question {question.get('question_no', '?')}: Set penalty to {field_content}", "INFO", True)
        except ValueError:
            print(f"{C.RED}[ERROR] Invalid penalty value: '{field_content}'{C.RESET}")
            print(f"        Question No.: {question_no}")
            if line_no and line_no > 0:
                print(f"        Line No.: {line_no}")
            print(f"        Question: {question_text[:80]}...")
            print(f"{C.YELLOW}        Penalty must be a number (e.g., 0.33, 0.5){C.RESET}")
            sys.exit(1)

    elif field_name == 'grade':
        try:
            question["grade"] = float(field_content)
            log(f"  Question {question.get('question_no', '?')}: Set grade to {field_content}", "INFO", True)
        except ValueError:
            print(f"{C.RED}[ERROR] Invalid grade value: '{field_content}'{C.RESET}")
            print(f"        Question No.: {question_no}")
            if line_no and line_no > 0:
                print(f"        Line No.: {line_no}")
            print(f"        Question: {question_text[:80]}...")
            print(f"{C.YELLOW}        Grade must be a number (e.g., 1, 2, 10){C.RESET}")
            sys.exit(1)

    elif field_name == 'lines':
        try:
            question["lines"] = int(field_content)
            log(f"  Question {question.get('question_no', '?')}: Set response lines to {field_content}", "INFO", True)
        except ValueError:
            print(f"{C.RED}[ERROR] Invalid lines value: '{field_content}'{C.RESET}")
            print(f"        Question No.: {question_no}")
            if line_no and line_no > 0:
                print(f"        Line No.: {line_no}")
            print(f"        Question: {question_text[:80]}...")
            print(f"{C.YELLOW}        Lines must be an integer number (e.g., 10, 15, 20){C.RESET}")
            sys.exit(1)

    elif field_name == 'attachments':
        try:
            question["attachments"] = int(field_content)
            log(f"  Question {question.get('question_no', '?')}: Set attachments to {field_content}", "INFO", True)
        except ValueError:
            print(f"{C.RED}[ERROR] Invalid attachments value: '{field_content}'{C.RESET}")
            print(f"        Question No.: {question_no}")
            if line_no and line_no > 0:
                print(f"        Line No.: {line_no}")
            print(f"        Question: {question_text[:80]}...")
            print(f"{C.YELLOW}        Attachments must be an integer number (e.g., 0, 1, 2){C.RESET}")
            sys.exit(1)

    elif field_name == 'filetypes':
        question["filetypes"] = field_content
        log(f"  Question {question.get('question_no', '?')}: Set filetypes to {field_content}", "INFO", True)

    elif field_name == 'maxfilesizemb':
        try:
            question["maxbytes"] = int(float(field_content) * 1024 * 1024)
            log(f"  Question {question.get('question_no', '?')}: Set max file size to {field_content} MB", "INFO", True)
        except ValueError:
            print(f"{C.RED}[ERROR] Invalid max file size: '{field_content}'{C.RESET}")
            print(f"        Question No.: {question_no}")
            if line_no and line_no > 0:
                print(f"        Line No.: {line_no}")
            print(f"        Question: {question_text[:80]}...")
            print(f"{C.YELLOW}        MaxFileSizeMB must be a number (e.g., 2, 5, 10){C.RESET}")
            sys.exit(1)

    # Add handling for matching question fields
    elif field_name == 'shuffle answers':
        if field_content.lower() in ['true', 'false']:
            question["shuffle_answers"] = field_content.lower() == 'true'
            log(f"  Question {question.get('question_no', '?')}: Set shuffle answers to {question['shuffle_answers']}", "INFO", True)
        else:
            print(f"{C.RED}[ERROR] Invalid value for 'Shuffle Answers': '{field_content}'{C.RESET}")
            print(f"        Must be 'true' or 'false'{C.RESET}")
            sys.exit(1)

    elif field_name == 'show number correct':
        if field_content.lower() in ['true', 'false']:
            question["show_num_correct"] = field_content.lower() == 'true'
            log(f"  Question {question.get('question_no', '?')}: Set show number correct to {question['show_num_correct']}", "INFO", True)
        else:
            print(f"{C.RED}[ERROR] Invalid value for 'Show Number Correct': '{field_content}'{C.RESET}")
            print(f"        Must be 'true' or 'false'{C.RESET}")
            sys.exit(1)

    elif field_name == 'subquestion':
        if "pairs" not in question:
            question["pairs"] = []
        question["pairs"].append({"subquestion": field_content, "answer": ""})
        log(f"  Question {question.get('question_no', '?')}: Added subquestion: {field_content[:50]}...", "INFO", True)

    elif field_name == 'answer':
        if "pairs" not in question:
            print(f"{C.RED}[ERROR] Answer without preceding subquestion{C.RESET}")
            sys.exit(1)
        if not question["pairs"]:
            print(f"{C.RED}[ERROR] Answer without subquestion{C.RESET}")
            sys.exit(1)
        # Add answer to the last subquestion
        question["pairs"][-1]["answer"] = field_content
        log(f"  Question {question.get('question_no', '?')}: Added answer: {field_content[:50]}...", "INFO", True)

    elif field_name == 'correct feedback':
        question["correct_feedback"] = field_content.replace('\n', '<br>')
        log(f"  Question {question.get('question_no', '?')}: Added correct feedback", "INFO", True)

    elif field_name == 'partially correct feedback':
        question["partially_correct_feedback"] = field_content.replace('\n', '<br>')
        log(f"  Question {question.get('question_no', '?')}: Added partially correct feedback", "INFO", True)

    elif field_name == 'incorrect feedback':
        question["incorrect_feedback"] = field_content.replace('\n', '<br>')
        log(f"  Question {question.get('question_no', '?')}: Added incorrect feedback", "INFO", True)

    # ---- NEW: Bank TXT fields ----
    elif field_name == 'nepali':
        question['nepali_transcription'] = field_content
        log(f"  Question {question.get('question_no', '?')}: Added Nepali transcription", "INFO", True)
    elif field_name == 'english':
        question['english_transcription'] = field_content
        log(f"  Question {question.get('question_no', '?')}: Added English transcription", "INFO", True)
    elif field_name == 'marks':
        try:
            question['marks'] = int(field_content)
            log(f"  Question {question.get('question_no', '?')}: Set marks to {field_content}", "INFO", True)
        except ValueError:
            question['marks'] = None
            log(f"  Question {question.get('question_no', '?')}: Invalid marks value, set to NULL", "WARN", True)
    elif field_name == 'chapter':
        question['chapter'] = field_content
        log(f"  Question {question.get('question_no', '?')}: Set chapter to {field_content}", "INFO", True)
    elif field_name == 'source':
        question['source'] = field_content
        log(f"  Question {question.get('question_no', '?')}: Set source to {field_content}", "INFO", True)

def process_question_lines(question, lines, line_number_start, file_path):
    """Process lines for a question, handling multi-line fields"""
    current_field = None
    field_content = []
    current_line_no = line_number_start

    for i, line in enumerate(lines):
        # Calculate actual line number
        current_line_no = line_number_start + i

        # Check if line starts a new field (has a colon)
        # A new field starts only if the line does NOT begin with whitespace
        if line and not line[0].isspace() and ':' in line:
            # Save previous field if exists
            if current_field:
                save_field_to_question(question, current_field, '\n'.join(field_content), current_line_no - len(field_content))

            # Start new field
            parts = line.split(':', 1)
            current_field = parts[0].strip().lower()
            field_content = [parts[1].strip()] if parts[1].strip() else []
        else:
            # Continuation of current field
            if current_field:
                field_content.append(line.strip())
            else:
                # This line doesn't have a field and is not a continuation - it's malformed
                actual_line = find_line_in_file(file_path, line)
                print(f"{C.RED}[ERROR] Malformed line detected - not a valid question field{C.RESET}")
                print(f"        Question No.: {question.get('question_no', '?')}")
                print(f"        Line No.: {actual_line}")
                print(f"        Line: '{line[:80]}...'")
                print(f"{C.YELLOW}        Expected a field with a colon (e.g., 'Type: multichoice', 'Option: text *')")
                print(f"        This line appears to be extra text not part of the question format.")
                print(f"")
                print(f"        Common causes:")
                print(f"        1. Missing colon after field name")
                print(f"        2. Extra text between questions without proper formatting")
                print(f"        3. Comment line without comment marker (#, //, etc.)")
                print(f"")
                print(f"        Fix: Remove this line or format it properly.")
                print(f"        Example of proper format:")
                print(f"        Question No. 1: Your question here")
                print(f"        Type: multichoice")
                print(f"        Option: Option 1 *")
                print(f"        Option: Option 2")
                print(f"        Option: Option 3")
                print(f"        Option: Option 4")
                print(f"")
                print(f"        # This is a proper comment (starts with #)")
                print(f"        // This is also a comment (starts with //){C.RESET}")
                raise ParseError(f"Malformed line at line {actual_line}: '{line[:80]}...'. Expected a field with a colon.")

    # Save the last field
    if current_field:
        save_field_to_question(question, current_field, '\n'.join(field_content), current_line_no - len(field_content) + 1)

# The parse_text_file function to better track skipped lines
def parse_text_file(file_path, args):
    """Parse text file with support for multi-line fields - STRICTER VERSION"""
    questions = []
    seen_questions = set()
    bypass_used = {"duplicate": [], "option": []}

    # Track skipped sections for logging
    skipped_sections = []
    skipped_lines = 0  # Initialize skipped_lines variable

    # Read entire file and handle BOM
    with open(file_path, 'r', encoding='utf-8-sig') as f:  # Changed to utf-8-sig to handle BOM
        content = f.read()

    # Remove any remaining BOM characters throughout the content
    content = content.replace('\ufeff', '')

    # ----- PASSAGE FEATURE: extract passages before splitting sections -----
    passages, remaining_content = extract_passages(content, args.verbose)
    if args.verbose and passages:
        log(f"Extracted {len(passages)} passage(s): {list(passages.keys())}", "INFO", True)
    # ---------------------------------------------------------------------

    log("Initializing parser", "INIT", args.verbose)
    log(f"Input file: {file_path}", "INFO", args.verbose)
    log("Strict validation enabled", "INFO", args.verbose)

    # Count total lines in the file for statistics
    total_lines = len(remaining_content.split('\n'))
    log(f"Input file has {total_lines} total lines (after removing passage definitions)", "INFO", args.verbose)

    # Split content by blank lines (simpler approach)
    raw_sections = remaining_content.strip().split('\n\n')

    question_no = 0
    current_question = None
    current_group = ""  # ----- GROUP FEATURE -----

    for section_idx, section in enumerate(raw_sections):
        # Skip empty sections
        if not section.strip():
            skipped_sections.append(f"Section {section_idx+1}: Empty section")
            # Count lines in empty section (at least 1)
            section_lines = max(1, len(section.split('\n')))
            skipped_lines += section_lines
            continue

        # Keep original lines (including leading spaces), skip empty lines
        raw_lines = section.split('\n')
        lines = []
        for line in raw_lines:
            if line.strip() == '':
                continue
            lines.append(line)          # keep the line as is (preserve leading spaces)

        if not lines:
            skipped_sections.append(f"Section {section_idx+1}: No content after stripping")
            # Count lines in section
            section_lines = max(1, len(section.split('\n')))
            skipped_lines += section_lines
            continue

        # Look for "Question:" pattern even in comment lines
        first_line = lines[0]
        first_line_clean = first_line.strip()

        # ----- GROUP FEATURE: detect group markers -----
        if re.match(r'^\[group\s*[:]?\s*(.*?)\]$', first_line_clean, re.IGNORECASE):
            # Extract group name: match after 'group' and optional colon, up to the closing bracket
            match = re.match(r'^\[group\s*[:]?\s*(.*?)\]$', first_line_clean, re.IGNORECASE)
            if match:
                current_group = match.group(1).strip()
                log(f"Group detected: {current_group}", "INFO", args.verbose)
                # This is a valid structural element, not a skipped line.
                # Just skip processing it as a question.
                continue

        # --------------------------------------------

        # Check for various comment formats
        is_comment = False
        comment_patterns = ['#', '###', '---', '***', '//', '/*']

        # Check if line starts with a comment pattern
        for pattern in comment_patterns:
            if first_line_clean.startswith(pattern):
                is_comment = True
                break

        # Check if this comment line contains a question pattern
        question_in_comment = False
        question_patterns = [
            r'Question\s+No\.?\s*\d+\s*:',  # Question No. X:
            r'Question\s*:',                 # Question:
            r'Question\s+',                  # Question (without colon)
        ]

        for q_pattern in question_patterns:
            if re.search(q_pattern, first_line_clean, re.IGNORECASE):
                question_in_comment = True
                break

        # If it starts with a comment but contains a question pattern, try to parse it
        if is_comment and question_in_comment:
            # Try to extract the question from comment line
            temp_line = first_line_clean

            # Remove comment prefixes one by one
            for pattern in comment_patterns:
                if temp_line.startswith(pattern):
                    # Remove the comment prefix and any following spaces or backticks
                    temp_line = re.sub(r'^' + re.escape(pattern) + r'[\s`]*', '', temp_line)

            # Check if the cleaned line is a valid question
            temp_line_stripped = temp_line.strip()
            is_valid_question = False

            # Pattern 1: "Question No. X: text" or "Question No.X: text"
            if re.match(r'^Question\s+No\.?\s*\d+\s*:', temp_line_stripped, re.IGNORECASE):
                is_valid_question = True
            # Pattern 2: "Question: text"
            elif temp_line_stripped.lower().startswith('question:'):
                is_valid_question = True
            # Pattern 3: "Question text" (without colon, but starting with Question)
            elif temp_line_stripped.lower().startswith('question '):
                # Try to extract if it has a colon somewhere
                if ':' in temp_line_stripped:
                    parts = temp_line_stripped.split(':', 1)
                    if parts[0].lower().startswith('question'):
                        is_valid_question = True
                else:
                    # Just "Question" followed by text
                    is_valid_question = True

            if is_valid_question:
                log(f"Found question in comment line, attempting to parse: {first_line_clean[:50]}...", "INFO", args.verbose)
                first_line = temp_line  # Replace with cleaned line
                first_line_clean = temp_line_stripped
                is_comment = False  # No longer treat as comment
            else:
                log(f"Skipping comment section (no valid question found): {first_line_clean[:50]}...", "INFO", args.verbose)
                skipped_sections.append(f"Section {section_idx+1}: Comment without valid question")
                # Count lines in comment section
                section_lines = max(1, len(section.split('\n')))
                skipped_lines += section_lines
                continue
        elif is_comment and not question_in_comment:
            # It's just a regular comment, skip it
            log(f"Skipping comment section: {first_line_clean[:50]}...", "INFO", args.verbose)
            skipped_sections.append(f"Section {section_idx+1}: Comment section")
            # Count lines in comment section
            section_lines = max(1, len(section.split('\n')))
            skipped_lines += section_lines
            continue

        # Check if this section starts with a Question (multiple patterns)
        first_line_clean = first_line.strip()

        # Check multiple question patterns
        is_question = False
        question_text = ""

        # Pattern 1: "Question No. X: text" or "Question No.X: text"
        if re.match(r'^Question\s+No\.?\s*\d+\s*:', first_line_clean, re.IGNORECASE):
            is_question = True
            # Extract question number and text
            match = re.match(r'^Question\s+No\.?\s*(\d+)\s*:\s*(.*)', first_line_clean, re.IGNORECASE)
            if match:
                q_num = match.group(1)
                question_text = match.group(2)
                log(f"Detected 'Question No. {q_num}:' format", "INFO", args.verbose)
            else:
                # Fallback: just extract everything after the first colon
                parts = first_line_clean.split(':', 1)
                if len(parts) > 1:
                    question_text = parts[1].strip()

        # Pattern 2: "Question: text"
        elif first_line_clean.lower().startswith('question:'):
            is_question = True
            question_text = first_line_clean.split(':', 1)[1].strip()

        # Pattern 3: "Question text" (without colon, but starting with Question)
        elif first_line_clean.lower().startswith('question '):
            # Try to extract if it has a colon somewhere
            if ':' in first_line_clean:
                parts = first_line_clean.split(':', 1)
                if parts[0].lower().startswith('question'):
                    is_question = True
                    question_text = parts[1].strip()
            else:
                # Just "Question" followed by text
                is_question = True
                question_text = first_line_clean[8:].strip()

        if is_question:
            # Save previous question if exists
            if current_question:
                questions.append(current_question)

            question_no += 1

            # ----- PASSAGE FEATURE: remove marker from the whole line first -----
            line_without_marker, passage_id = remove_passage_marker(first_line_clean, passages, args.verbose)

            # Now extract the actual question text from the line without the marker
            extracted_question = ""
            # Pattern 1: "Question No. X: text"
            match = re.match(r'^Question\s+No\.?\s*(\d+)\s*:\s*(.*)', line_without_marker, re.IGNORECASE)
            if match:
                extracted_question = match.group(2).strip()
            # Pattern 2: "Question: text"
            elif line_without_marker.lower().startswith('question:'):
                extracted_question = line_without_marker.split(':', 1)[1].strip()
            # Pattern 3: "Question text" (without colon)
            elif line_without_marker.lower().startswith('question '):
                if ':' in line_without_marker:
                    parts = line_without_marker.split(':', 1)
                    if parts[0].lower().startswith('question'):
                        extracted_question = parts[1].strip()
                else:
                    extracted_question = line_without_marker[8:].strip()

            # If we found a passage identifier, expand it now
            if passage_id:
                passage_content = passages.get(passage_id, "")
                extracted_question = format_passage_in_question(passage_id, passage_content, extracted_question)

            question_text = extracted_question
            # ----------------------------------------------------------------

            # Check for duplicates (using the expanded question text)
            key = normalize_text(question_text)
            if key in seen_questions:
                if args.bypass_duplicate:
                    log(f"Duplicate question detected (bypassed)", "WARN", args.verbose)
                    bypass_used["duplicate"].append(question_no)
                else:
                    # Find actual line number
                    actual_line = find_line_in_file(file_path, question_text)
                    raise DuplicateQuestionError(f"Duplicate question '{question_text}' at question {question_no} (line {actual_line})")
                    raise DuplicateQuestionError(f"Question already exists with ID {dup_id} for {date} {institution} {level} {paper} {group} Q{question_number}")
                    print(f"{C.YELLOW}        Fix: Remove duplicate or use --bypass-duplicate{C.RESET}")
            seen_questions.add(key)

            # Create new question
            current_question = {
                "text": question_text,
                "type": "multichoice",  # Default, can be overridden by Type field
                "options": [],
                "general_feedback": "",
                "grader_info": "",
                "fraction_correct": 100,
                "fraction_wrong": -20,
                "penalty": 0,
                "grade": 1,
                "lines": 15,
                "question_no": question_no,
                "original_question_no": question_no,  # Store original number
                "attachments": 0,
                "filetypes": ".doc,.docx,.pdf,.png,.jpg,.jpeg",
                "maxbytes": 2*1024*1024,
                "group": current_group   # ----- GROUP FEATURE -----
            }

            # Process remaining lines in this section
            if len(lines) > 1:
                process_question_lines(current_question, lines[1:], section_idx * 2 + 2, file_path)

        elif current_question:
            # This is continuation of current question (multi-line fields)
            # But first check if this line is a comment within a question
            line = lines[0].strip()
            if (line.startswith('#') or
                line.startswith('###') or
                line.startswith('---') or
                line.startswith('***') or
                line.startswith('//')):
                log(f"Skipping comment within question: {line[:50]}...", "INFO", args.verbose)
                # Count this comment line as skipped
                skipped_lines += 1
                # Skip this line but continue processing the question
                if len(lines) > 1:
                    process_question_lines(current_question, lines[1:], section_idx * 2 + 2, file_path)
            else:
                process_question_lines(current_question, lines, section_idx * 2 + 1, file_path)
        else:
            # This section doesn't start with a recognizable question format
            # Check if it's just a comment/section header we missed
            line = first_line_clean
            if (line.startswith('#') or
                line.startswith('###') or
                line.startswith('---') or
                line.startswith('***')):
                log(f"Skipping comment/header: {first_line_clean[:50]}...", "INFO", args.verbose)
                skipped_sections.append(f"Section {section_idx+1}: Header/comment")
                # Count lines in header section
                section_lines = max(1, len(section.split('\n')))
                skipped_lines += section_lines
                continue
            else:
                # Not a comment and not a question - this is malformed!
                actual_line = find_line_in_file(file_path, line)
                raise ParseError(f"Malformed section at line {actual_line}: '{line[:80]}...' (does not start with 'Question')")
                print(f"        Line No.: {actual_line}")
                print(f"        Line: '{line[:80]}...'")
                print(f"{C.YELLOW}        Expected: 'Question: <text>' or 'Question No. X: <text>'")
                print(f"        Also accepted: Comment lines starting with #, ###, ---, or ***")

    # Add the last question
    if current_question:
        questions.append(current_question)

    # Log skipped sections if verbose
    if args.verbose and skipped_sections:
        log(f"Skipped {len(skipped_sections)} sections ({skipped_lines} lines):", "INFO", True)
        for section in skipped_sections[:5]:  # Show first 5
            log(f"  - {section}", "INFO", True)
        if len(skipped_sections) > 5:
            log(f"  ... and {len(skipped_sections) - 5} more sections", "INFO", True)

    # Validate all questions have valid types
    for q in questions:
        if not validate_question_type(q["type"], q["question_no"], 0, q["text"]):
            sys.exit(1)

    # Validate MCQs and provide helpful error messages
    for q in questions:
        if q["type"] == "multichoice":
            correct_count = sum(1 for o in q["options"] if o["correct"])

            if correct_count == 0:
                # No correct option found
                actual_line = find_line_in_file(file_path, q["text"])
                raise MissingCorrectOptionError(f"Question {q['question_no']} has no correct option marked.")
                print(f"        Line No.: ~{actual_line}")
                print(f"        Question: {q['text'][:80]}...")
                print(f"{C.YELLOW}        Fix: Mark exactly ONE option as correct using:")
                print(f"        • Asterisk (*) at end: 'Option: Kathmandu *'")
                print(f"        • [Correct] marker: 'Option: Kathmandu [Correct]'")
                print(f"        • [OK] marker: 'Option: Kathmandu [OK]'")
                print(f"        • [Right] marker: 'Option: Kathmandu [Right]'")
                print(f"        Note: Markers must be OUTSIDE LaTeX math blocks")
                print(f"        Example: 'Option: Solve \\(x^2 = 4\\) to get *' (correct)")
                print(f"        Example: 'Option: Solve \\(x^2 = 4 *\\)' (WRONG - inside LaTeX){C.RESET}")

            elif correct_count > 1:
                actual_line = find_line_in_file(file_path, q["text"])
                raise MultipleCorrectOptionsError(f"Question {q['question_no']} has {correct_count} correct options.")
                print(f"        Line No.: ~{actual_line}")
                print(f"        Question: {q['text'][:80]}...")
                print(f"{C.YELLOW}        Fix: Remove extra correct markers, keep only ONE")
                print(f"        Check all options and remove *, [Correct], [OK], [Right] from extras{C.RESET}")

            if len(q["options"]) < 4:
                if args.bypass_option:
                    while len(q["options"]) < 4:
                        q["options"].append({"text": f"Option {len(q['options'])+1}", "correct": False})
                    log(f"Question {q['question_no']} auto-filled missing options due to --bypass-option", "WARN", args.verbose)
                    bypass_used["option"].append(q['question_no'])
                else:
                    actual_line = find_line_in_file(file_path, q["text"])
                    raise InsufficientOptionsError(f"Question {q['question_no']} has {len(q['options'])} options (need 4).")
                    print(f"        Line No.: ~{actual_line}")
                    print(f"        Question: {q['text'][:80]}...")
                    print(f"        OR use --bypass-option to auto-fill missing options{C.RESET}")
                    sys.exit(1)

            elif len(q["options"]) > 4:
                log(f"Question {q['question_no']} has {len(q['options'])} options (more than 4)", "WARN", args.verbose)

        # Validate and set up True/False questions
        elif q["type"] == "truefalse":
            # Ensure fractions are set
            q.setdefault("fraction_correct", 100)
            q.setdefault("fraction_wrong", -20)

            # If options not set up yet, set them up now
            if "options" not in q or len(q.get("options", [])) != 2:
                if "correct_answer" not in q:
                    # Default to True if not specified
                    q["correct_answer"] = True
                    log(f"Question {q.get('question_no', '?')}: No correct answer specified for True/False, defaulting to True", "WARN", args.verbose)
                setup_truefalse_options(q)
            else:
                # Ensure correct_answer exists based on options
                true_option = next((opt for opt in q["options"] if opt.get("text", "").lower() == "true"), None)
                if true_option and "correct_answer" not in q:
                    q["correct_answer"] = true_option.get("correct", True)

    # Add validation for matching questions
    for q in questions:
        if q["type"] == "matching":
            # Check if we have pairs
            if "pairs" not in q or len(q.get("pairs", [])) < 2:
                actual_line = find_line_in_file(file_path, q["text"])
                raise MatchingPairError(f"Matching question {q['question_no']} has only {len(q.get('pairs', []))} pairs (need at least 2).")
                print(f"        Line No.: ~{actual_line}")
                print(f"        Question: {q['text'][:80]}...")
                print(f"{C.YELLOW}        Fix: Add at least 2 subquestion/answer pairs")
                print(f"        Example:")
                print(f"        Subquestion: France")
                print(f"        Answer: Paris")
                print(f"        Subquestion: Germany")
                print(f"        Answer: Berlin{C.RESET}")
                sys.exit(1)

            # Check for unique subquestions
            subquestions = [p["subquestion"] for p in q.get("pairs", [])]
            duplicates = set([sq for sq in subquestions if subquestions.count(sq) > 1])
            if duplicates:
                actual_line = find_line_in_file(file_path, q["text"])
                print(f"{C.RED}[ERROR] Duplicate subquestions in matching question{C.RESET}")
                print(f"        Question No.: {q['question_no']}")
                print(f"        Line No.: ~{actual_line}")
                print(f"        Question: {q['text'][:80]}...")
                print(f"        Duplicates: {', '.join(duplicates)}")
                print(f"{C.YELLOW}        Fix: Each subquestion must be unique{C.RESET}")
                raise DuplicateQuestionError(f"Duplicate question '{question_text}' at question {question_no} (line {actual_line})")

            # Check all pairs have both subquestion and answer
            incomplete_pairs = []
            for i, pair in enumerate(q.get("pairs", []), 1):
                if not pair.get("subquestion") or not pair.get("answer"):
                    incomplete_pairs.append(i)

            if incomplete_pairs:
                actual_line = find_line_in_file(file_path, q["text"])
                print(f"{C.RED}[ERROR] Incomplete pairs in matching question{C.RESET}")
                print(f"        Question No.: {q['question_no']}")
                print(f"        Line No.: ~{actual_line}")
                print(f"        Question: {q['text'][:80]}...")
                print(f"        Incomplete pairs: {incomplete_pairs}")
                print(f"{C.YELLOW}        Fix: Each pair must have both subquestion and answer{C.RESET}")
                raise MissingCorrectOptionError(f"Question {q['question_no']} has no correct option marked.")

            # Set defaults if not specified
            q.setdefault("shuffle_answers", True) # True (this doesn't reveal answers)
            q.setdefault("show_num_correct", False)
            q.setdefault("correct_feedback", "Your answer is correct.")
            q.setdefault("partially_correct_feedback", "Your answer is partially correct.")
            q.setdefault("incorrect_feedback", "Your answer is incorrect.")

            log(f"Question {q['question_no']}: Validated matching question with {len(q['pairs'])} pairs", "INFO", args.verbose)

    # Log with detailed information about marks/grade - ONLY ONCE, after all validation
    # This is the main verbose output section that shows question details
    if args.verbose:
        log(f"--- Question Details ({len(questions)} questions) ---", "INFO", True)
        for q in questions:
            if q["type"] == "multichoice":
                correct_opt = next((opt for opt in q["options"] if opt["correct"]), None)
                log(f"Question {q['question_no']}: {q['text'][:50]}... (MCQ, Grade: {q.get('grade', 1)}, Correct: '{correct_opt['text'][:30] if correct_opt else 'N/A'}...')", "OK", True)
            elif q["type"] == "truefalse":
                correct_opt = next((opt for opt in q["options"] if opt.get("correct", False)), None)
                log(f"Question {q['question_no']}: {q['text'][:50]}... (True/False, Grade: {q.get('grade', 1)}, Correct: {correct_opt.get('text', 'N/A') if correct_opt else 'N/A'})", "OK", True)
            else:
                log(f"Question {q['question_no']}: {q['text'][:50]}... (Essay, Grade: {q.get('grade', 1)}, Lines: {q.get('lines', 15)})", "OK", True)

    # Calculate skipped lines statistics
    total_processed_lines = 0
    for q in questions:
        # Estimate lines per question (question text + options + metadata)
        lines_per_q = 3  # Base for question text and type
        if q["type"] == "multichoice":
            lines_per_q += len(q.get("options", []))
        lines_per_q += 1 if q.get("general_feedback") else 0
        total_processed_lines += lines_per_q

    # If we have filtering, adjust skipped lines
    if args.questions:
        original_question_count = len(questions) + skipped_lines // 5  # Rough estimate
        log(f"Estimated {original_question_count} original questions before filtering", "INFO", args.verbose)

    log(f"Statistics: Processed {len(questions)} questions, skipped {skipped_lines} lines", "SUMMARY", args.verbose)

    return questions, bypass_used, skipped_lines
