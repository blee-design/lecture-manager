import json
from decimal import Decimal
from .utils import log
from ..utils import sanitize_for_json
from .exceptions import UnknownQuestionTypeError

VALID_QUESTION_TYPES = ["multichoice", "essay", "truefalse", "matching"]



# -------------------- JSON PARSING --------------------
def json_to_questions(input_file, verbose=False):  # Add verbose parameter
    """Load questions from JSON file"""
    with open(input_file, 'r', encoding='utf-8') as f:
        json_data = json.load(f)

    log(f"Loaded JSON file with {len(json_data)} questions", "INFO", verbose)

    questions = []
    for i, item in enumerate(json_data, 1):
        q_type = item.get("type", "multichoice")
        nep = item.get("nepali_transcription", "") or ""
        eng = item.get("english_transcription", "") or ""
        combined = f"{nep} ({eng})" if nep and eng else (nep or eng)

        # Validate question type
        if q_type not in VALID_QUESTION_TYPES:
            raise UnknownQuestionTypeError(f"Unknown question type: '{q_type}' in JSON question {i}")

        # Validate question type
        if q_type not in VALID_QUESTION_TYPES:
            raise UnknownQuestionTypeError(f"Unknown question type: '{q_type}' in JSON question {i}")
            print(f"        Question No.: {i}")
            print(f"        Question: {item.get('text', '')[:80]}...")
            print(f"{C.YELLOW}        Available question types:")
            print(f"        • multichoice - Multiple choice questions (MCQ)")
            print(f"        • essay - Essay questions (long answer)")
            print(f"        • truefalse - True/False questions{C.RESET}")

        question = {
            "text": combined,
            "nepali_transcription": nep,
            "english_transcription": eng,
            "type": q_type,
            "type": q_type,
            "general_feedback": item.get("general_feedback", ""),
            "grader_info": item.get("grader_info", ""),
            "grade": item.get("grade", 1),
            "lines": item.get("lines", 15),
            "penalty": item.get("penalty", 0),
            "question_no": item.get("question_no", i),
            "original_question_no": item.get("question_no", i),  # Store original
        }

        # Log question details
        text_preview = question["text"][:50] + "..." if len(question["text"]) > 50 else question["text"]
        log(f"Question {i}: {text_preview}", "INFO", verbose)
        log(f"Question {i}: Type: {question['type']}, Grade: {question['grade']}", "INFO", verbose)

        if item.get("type") == "multichoice":
            question["fraction_correct"] = item.get("fraction_correct", 100)
            question["fraction_wrong"] = item.get("fraction_wrong", -20)
            question["options"] = item.get("options", [])
            log(f"Question {i}: Found {len(question['options'])} options", "INFO", verbose)

            # Log correct option
            for opt_idx, opt in enumerate(question["options"], 1):
                if opt.get("correct", False):
                    opt_preview = opt.get("text", "")[:30] + "..." if len(opt.get("text", "")) > 30 else opt.get("text", "")
                    log(f"Question {i}: Correct option {opt_idx}: {opt_preview}", "INFO", verbose)
                    break

        # Handle matching questions
        elif item.get("type") == "matching":
            question["shuffle_answers"] = item.get("shuffle_answers", True)
            question["show_num_correct"] = item.get("show_num_correct", False)
            question["correct_feedback"] = item.get("correct_feedback", "Your answer is correct.")
            question["partially_correct_feedback"] = item.get("partially_correct_feedback", "Your answer is partially correct.")
            question["incorrect_feedback"] = item.get("incorrect_feedback", "Your answer is incorrect.")
            question["pairs"] = item.get("pairs", [])
            question["hints"] = item.get("hints", [])

            # Ensure hint defaults are secure
            for hint in question["hints"]:
                hint.setdefault("clear_incorrect", False)
                hint.setdefault("show_num_correct", False)

            log(f"Question {i}: Matching with {len(question['pairs'])} pairs", "INFO", verbose)

        # True/False handling
        elif item.get("type") == "truefalse":
            question["type"] = "truefalse"
            question["options"] = [
                {"text": "True", "correct": item.get("correct_answer", True) == True},
                {"text": "False", "correct": item.get("correct_answer", True) == False}
            ]
            question["feedback_true"] = item.get("feedback_true", "")
            question["feedback_false"] = item.get("feedback_false", "")
            question["fraction_correct"] = item.get("fraction_correct", 100) # Default 100%
            question["fraction_wrong"] = item.get("fraction_wrong", -20) # Default -20%
            log(f"Question {i}: True/False, correct: {item.get('correct_answer', True)}", "INFO", verbose)
        else:
            question["attachments"] = item.get("attachments", 0)
            question["filetypes"] = item.get("filetypes", ".doc,.docx,.pdf,.png,.jpg,.jpeg")
            question["maxbytes"] = item.get("maxbytes", 2*1024*1024)
            if question["attachments"] > 0:
                log(f"Question {i}: Essay with {question['attachments']} attachments", "INFO", verbose)

        questions.append(question)
        log(f"Question {i}: Successfully parsed", "OK", verbose)

    log(f"Total questions loaded: {len(questions)}", "SUMMARY", verbose)
    return questions

def convert_decimals(obj):
    """Recursively convert Decimal to float/int in a dict/list."""
    if isinstance(obj, Decimal):
        return int(obj) if obj % 1 == 0 else float(obj)
    elif isinstance(obj, dict):
        return {k: convert_decimals(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_decimals(v) for v in obj]
    else:
        return obj

# -------------------- JSON OUTPUT --------------------
def create_json_output(questions, output_file, verbose=False):
    """Convert questions list to JSON format"""
    log(f"Creating JSON output with {len(questions)} questions", "INFO", verbose)

    json_data = []
    for i, q in enumerate(questions, 1):
        # Build JSON-friendly structure
        json_q = {
            "question_no": q.get("question_no", i),
            "type": q.get("type", "multichoice"),
            "text": q.get("text", ""),
            "nepali_transcription": q.get("nepali_transcription", ""),
            "english_transcription": q.get("english_transcription", ""),
            "general_feedback": q.get("general_feedback", ""),
            "grader_info": q.get("grader_info", ""),
            "grade": q.get("grade", 1),
            "lines": q.get("lines", 15),
            "penalty": q.get("penalty", 0),
            "group": q.get("group", ""),
            "institution": q.get("institution", ""),
            "level": q.get("level", ""),
            "paper": q.get("paper", ""),
            "subject": q.get("subject", ""),
            "chapter": q.get("chapter", ""),
            "marks": q.get("marks"),
            "notes": q.get("notes", ""),
        }

        if q.get("type") == "multichoice":
            json_q["fraction_correct"] = q.get("fraction_correct", 100)
            json_q["fraction_wrong"] = q.get("fraction_wrong", -20)
            json_q["options"] = q.get("options", [])
            log(f"Writing Question {i}: MCQ with {len(json_q['options'])} options", "INFO", verbose)

        elif q.get("type") == "matching":
            json_q["shuffle_answers"] = q.get("shuffle_answers", True)
            json_q["show_num_correct"] = q.get("show_num_correct", False)
            json_q["correct_feedback"] = q.get("correct_feedback", "Your answer is correct.")
            json_q["partially_correct_feedback"] = q.get("partially_correct_feedback", "Your answer is partially correct.")
            json_q["incorrect_feedback"] = q.get("incorrect_feedback", "Your answer is incorrect.")
            json_q["pairs"] = q.get("pairs", [])
            json_q["hints"] = q.get("hints", [])
            log(f"Writing Question {i}: Matching with {len(json_q['pairs'])} pairs", "INFO", verbose)

        elif q.get("type") == "truefalse":
            correct_answer = True
            for opt in q.get("options", []):
                if opt.get("correct", False):
                    correct_answer = (opt.get("text", "").lower() == "true")
                    break
            json_q["correct_answer"] = correct_answer
            json_q["feedback_true"] = q.get("feedback_true", "")
            json_q["feedback_false"] = q.get("feedback_false", "")
            json_q["fraction_correct"] = q.get("fraction_correct", 100)
            json_q["fraction_wrong"] = q.get("fraction_wrong", -20)
            log(f"Writing Question {i}: True/False (Correct: {correct_answer})", "INFO", verbose)

        else:  # essay
            json_q["attachments"] = q.get("attachments", 0)
            json_q["filetypes"] = q.get("filetypes", ".doc,.docx,.pdf,.png,.jpg,.jpeg")
            json_q["maxbytes"] = q.get("maxbytes", 2*1024*1024)
            log(f"Writing Question {i}: Essay (Grade: {json_q['grade']})", "INFO", verbose)

        json_data.append(json_q)

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(json_data, f, indent=2, ensure_ascii=False)

    log(f"JSON file created: {output_file}", "SUCCESS", verbose)
