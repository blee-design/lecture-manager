import sys
import re
from .utils import (
    log, normalize_text, is_correct_option,
    filter_questions, find_line_in_file, format_passage_in_question
)
from .constants import C
from .exceptions import (
    ConverterError, ParseError, ValidationError, IOError,
    DuplicateQuestionError, MissingCorrectOptionError,
    MultipleCorrectOptionsError, InsufficientOptionsError,
    MatchingPairError, UnknownQuestionTypeError, UndefinedPassageError,
    InvalidFilterError
)

DEFAULT_QUESTION_TYPE = "essay"

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
    'nepali', 'english', 'marks', 'chapter', 'source',
    'id',
    # Metadata fields (for inline context)
    'date', 'institution', 'level', 'paper', 'group', 'subject', 'notes',
    'question_number', 'question number',
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
    elif field_name in ('question_number', 'question number'):
        question['question_number'] = field_content
        log(f"  Question {question.get('question_no', '?')}: Set question number to {field_content}", "INFO", True)
    elif field_name == 'id':
        # Ignore ID on import – just a reference for export
        pass
    elif field_name == 'date':
        question['question_date'] = field_content
    elif field_name == 'institution':
        question['institution'] = field_content
    elif field_name == 'level':
        question['level'] = field_content
    elif field_name == 'paper':
        question['paper'] = field_content
    elif field_name == 'group':
        question['group'] = field_content
    elif field_name == 'subject':
        question['subject'] = field_content
    elif field_name == 'notes':
        question['notes'] = field_content

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
    """Parse text file with flexible block detection – supports metadata before question line."""
    questions = []
    seen_questions = set()
    bypass_used = {"duplicate": [], "option": []}
    skipped_lines = 0
    global_context = {}

    with open(file_path, 'r', encoding='utf-8-sig') as f:
        content = f.read().replace('\ufeff', '')

    passages, remaining_content = extract_passages(content, args.verbose)
    if args.verbose and passages:
        log(f"Extracted {len(passages)} passage(s): {list(passages.keys())}", "INFO", True)

    raw_blocks = re.split(r'\n---+\s*\n', remaining_content)
    raw_blocks = [b.strip() for b in raw_blocks if b.strip()]

    question_no = 0

    for block in raw_blocks:
        lines = [line.strip() for line in block.split('\n') if line.strip()]
        if not lines:
            skipped_lines += 1
            continue

        # Find the question line (anywhere in the block)
        question_line_idx = None
        for idx, line in enumerate(lines):
            if re.match(r'^(Question\s+(No\.?\s*|Number\s*)?\d*)|(Question:)', line, re.IGNORECASE):
                question_line_idx = idx
                break

        if question_line_idx is None:
            # Global context block
            for line in lines:
                if ':' in line:
                    key, val = line.split(':', 1)
                    global_context[key.strip().lower()] = val.strip()
            skipped_lines += len(lines)
            continue

        # --- This block is a question ---
        question_no += 1
        q_line = lines[question_line_idx]

        # Extract question number and text
        q_text = ""
        q_no = question_no
        match = re.match(r'^Question\s+(No\.?\s*|Number\s*)?(\d+)\s*:\s*(.*)', q_line, re.IGNORECASE)
        if match:
            q_no = int(match.group(2))
            q_text = match.group(3).strip()
        else:
            if q_line.lower().startswith('question:'):
                q_text = q_line.split(':', 1)[1].strip()
            else:
                q_text = re.sub(r'^Question\s+', '', q_line, flags=re.IGNORECASE).strip()

        # Collect all field lines (before and after the question line)
        field_lines = lines[:question_line_idx] + lines[question_line_idx+1:]

        # Initialise question dict with DEFAULT_QUESTION_TYPE
        question_dict = {
            "text": q_text,
            "type": DEFAULT_QUESTION_TYPE,
            "options": [],
            "general_feedback": "",
            "grader_info": "",
            "fraction_correct": 100,
            "fraction_wrong": -20,
            "penalty": 0,
            "grade": 1,
            "lines": 15,
            "question_no": q_no,
            "original_question_no": q_no,
            "attachments": 0,
            "filetypes": ".doc,.docx,.pdf,.png,.jpg,.jpeg",
            "maxbytes": 2*1024*1024,
            "group": "",
            "question_date": "",
            "institution": "",
            "level": "",
            "paper": "",
            "subject": "",
            "chapter": "",
            "marks": None,
            "notes": "",
            "source": "",
            "nepali_transcription": "",
            "english_transcription": "",
            "correct_answer": None,
            "feedback_true": "",
            "feedback_false": "",
            "shuffle_answers": True,
            "show_num_correct": False,
            "correct_feedback": "Your answer is correct.",
            "partially_correct_feedback": "Your answer is partially correct.",
            "incorrect_feedback": "Your answer is incorrect.",
            "hints": [],
            "pairs": [],
        }

        # Ensure question_number is set from the line number if not provided later
        if not question_dict.get('question_number'):
            question_dict['question_number'] = str(q_no).zfill(2)

        # Apply global context with key mapping
        KEY_MAP = {
            'date': 'question_date',
            'institution': 'institution',
            'level': 'level',
            'paper': 'paper',
            'group': 'group',
            'subject': 'subject',
            'notes': 'notes',
            'source': 'source',
            'marks': 'marks',
            'chapter': 'chapter',
        }
        mapped_context = {}
        for key, val in global_context.items():
            mapped_key = KEY_MAP.get(key, key)
            mapped_context[mapped_key] = val
        question_dict.update(mapped_context)

        # Process field lines using save_field_to_question
        current_field = None
        field_content = []
        for line in field_lines:
            if ':' in line and not line[0].isspace():
                if current_field:
                    save_field_to_question(question_dict, current_field, '\n'.join(field_content), 0)
                parts = line.split(':', 1)
                current_field = parts[0].strip().lower()
                field_content = [parts[1].strip()] if parts[1].strip() else []
            else:
                if current_field:
                    field_content.append(line.strip())
        if current_field:
            save_field_to_question(question_dict, current_field, '\n'.join(field_content), 0)

        # --- Auto-detect question type from fields ---
        if question_dict.get('options') and question_dict['type'] not in ('truefalse', 'matching'):
            question_dict['type'] = 'multichoice'
        elif question_dict.get('pairs') and question_dict['type'] != 'matching':
            question_dict['type'] = 'matching'
        elif question_dict.get('correct_answer') is not None and question_dict['type'] != 'truefalse':
            question_dict['type'] = 'truefalse'
        if question_dict['type'] == 'multichoice' and not question_dict.get('options'):
            question_dict['type'] = DEFAULT_QUESTION_TYPE

        # --- Build composite key for duplicate detection ---
        # Use the same fields as the database uniqueness constraint
        dup_key = (
            question_dict.get('question_date', ''),
            question_dict.get('institution', ''),
            question_dict.get('level', ''),
            question_dict.get('paper', ''),
            question_dict.get('group', ''),
            question_dict.get('question_number', '')
        )
        # Only fall back to text if ALL fields are empty (should rarely happen)
        if all(not v for v in dup_key):
            dup_key = normalize_text(q_text)

        if dup_key in seen_questions:
            if args.bypass_duplicate:
                bypass_used["duplicate"].append(q_no)
                log(f"Duplicate question {q_no} bypassed", "WARN", args.verbose)
            else:
                raise DuplicateQuestionError(f"Duplicate question at question {q_no}")
        seen_questions.add(dup_key)
        questions.append(question_dict)

    # ---- Post‑processing validation (outside the loop) ----
    for q in questions:
        q_type = q.get("type", DEFAULT_QUESTION_TYPE)

        if q_type == "multichoice":
            correct_count = sum(1 for o in q.get("options", []) if o.get("correct", False))
            if correct_count == 0:
                raise MissingCorrectOptionError(f"Question {q['question_no']} has no correct option marked.")
            if correct_count > 1:
                raise MultipleCorrectOptionsError(f"Question {q['question_no']} has {correct_count} correct options.")
            if len(q.get("options", [])) < 4:
                if args.bypass_option:
                    while len(q["options"]) < 4:
                        q["options"].append({"text": f"Option {len(q['options'])+1}", "correct": False})
                    bypass_used["option"].append(q['question_no'])
                else:
                    raise InsufficientOptionsError(f"Question {q['question_no']} has {len(q['options'])} options (need 4).")

        elif q_type == "truefalse":
            if "options" not in q or len(q.get("options", [])) != 2:
                if "correct_answer" not in q:
                    q["correct_answer"] = True
                setup_truefalse_options(q)

        elif q_type == "matching":
            if "pairs" not in q or len(q.get("pairs", [])) < 2:
                raise MatchingPairError(f"Matching question {q['question_no']} has only {len(q.get('pairs', []))} pairs (need at least 2).")
            subquestions = [p["subquestion"] for p in q.get("pairs", [])]
            duplicates = set([sq for sq in subquestions if subquestions.count(sq) > 1])
            if duplicates:
                raise DuplicateQuestionError(f"Duplicate subquestions in matching question {q['question_no']}: {', '.join(duplicates)}")
            for i, pair in enumerate(q.get("pairs", []), 1):
                if not pair.get("subquestion") or not pair.get("answer"):
                    raise MatchingPairError(f"Incomplete pair {i} in matching question {q['question_no']}")

    # ---- Log parsed question details ----
    if args.verbose:
        for q in questions:
            q_type = q.get('type', DEFAULT_QUESTION_TYPE)
            q_no = q.get('question_no', '?')
            text_preview = q.get('text', '')[:40] + "..." if len(q.get('text', '')) > 40 else q.get('text', '')
            log(f"  ✅ Parsed Q{q_no}: {q_type} – {text_preview}", "OK", True)
            if q_type == 'multichoice':
                log(f"     Options: {len(q.get('options', []))}, Correct: {sum(1 for o in q.get('options', []) if o.get('correct', False))}", "INFO", True)
            elif q_type == 'matching':
                log(f"     Pairs: {len(q.get('pairs', []))}", "INFO", True)

    if args.verbose:
        log(f"Parsed {len(questions)} questions, skipped {skipped_lines} lines", "SUMMARY", True)

    return questions, bypass_used, skipped_lines
