# File text_output.py

from .utils import log

# -------------------- TEXT OUTPUT --------------------
def create_text_output(questions, output_file, verbose=False):
    """
    Convert questions list to text format with full metadata (context-aware).
    Each block is separated by '---' and includes all relevant fields.
    """
    log(f"Creating text output with {len(questions)} questions", "INFO", verbose)

    # All possible fields (metadata first, then question content)
    metadata_fields = [
        ('question_date', 'Date'),
        ('institution', 'Institution'),
        ('level', 'Level'),
        ('paper', 'Paper'),
        ('group', 'Group'),
        ('subject', 'Subject'),
        ('chapter', 'Chapter'),
        ('marks', 'Marks'),
        ('notes', 'Notes'),
        ('source', 'Source'),
    ]

    with open(output_file, 'w', encoding='utf-8') as f:
        # Write header
        f.write("# Exported Question Bank (Full Metadata)\n")
        f.write(f"# Total: {len(questions)} questions\n")
        f.write("# Each block is separated by '---'\n\n")

        for idx, q in enumerate(questions, 1):
            if verbose and idx % 5 == 0:
                log(f"Writing question {idx}/{len(questions)}", "INFO", verbose)

            f.write("---\n")

            # Write metadata fields (only if present and non‑empty)
            for field, label in metadata_fields:
                val = q.get(field)
                if val is not None and str(val).strip():
                    f.write(f"{label}: {val}\n")

            # Question number and text
            qno = q.get("question_no")
            text = q.get("text", "")
            f.write(f"Question No. {qno}: {text}\n" if qno else f"Question: {text}\n")

            # Type
            q_type = q.get("type", "multichoice")
            f.write(f"Type: {q_type}\n")

            # Handle specific types
            if q_type == "multichoice":
                for opt in q.get("options", []):
                    correct_marker = " *" if opt.get("correct", False) else ""
                    f.write(f"Option: {opt.get('text', '')}{correct_marker}\n")

                if q.get("grade", 1) != 1:
                    f.write(f"Grade: {q.get('grade', 1)}\n")
                if q.get("penalty", 0) != 0:
                    f.write(f"Penalty: {q.get('penalty', 0)}\n")
                if q.get("general_feedback"):
                    f.write(f"General Feedback: {q.get('general_feedback')}\n")
                if q.get("fraction_correct", 100) != 100 or q.get("fraction_wrong", -20) != -20:
                    f.write(f"Fraction: {q.get('fraction_correct', 100)} {q.get('fraction_wrong', -20)}\n")

            elif q_type == "truefalse":
                # Determine correct answer
                correct_opt = next((opt for opt in q.get("options", []) if opt.get("correct", False)), None)
                if correct_opt:
                    f.write(f"Correct: {correct_opt.get('text', '').lower()}\n")

                if q.get("grade", 1) != 1:
                    f.write(f"Grade: {q.get('grade', 1)}\n")
                if q.get("penalty", 0) != 0:
                    f.write(f"Penalty: {q.get('penalty', 0)}\n")
                if q.get("general_feedback"):
                    f.write(f"General Feedback: {q.get('general_feedback')}\n")
                if q.get("feedback_true"):
                    f.write(f"Feedback True: {q.get('feedback_true')}\n")
                if q.get("feedback_false"):
                    f.write(f"Feedback False: {q.get('feedback_false')}\n")
                if q.get("fraction_correct", 100) != 100 or q.get("fraction_wrong", -20) != -20:
                    f.write(f"Fraction: {q.get('fraction_correct', 100)} {q.get('fraction_wrong', -20)}\n")

            elif q_type == "matching":
                for pair in q.get("pairs", []):
                    f.write(f"Subquestion: {pair.get('subquestion', '')}\n")
                    f.write(f"Answer: {pair.get('answer', '')}\n")

                if q.get("grade", 1) != 1:
                    f.write(f"Grade: {q.get('grade', 1)}\n")
                if q.get("penalty", 0) != 0:
                    f.write(f"Penalty: {q.get('penalty', 0)}\n")
                if q.get("shuffle_answers", True) is False:
                    f.write("Shuffle Answers: false\n")
                if q.get("show_num_correct", False):
                    f.write("Show Number Correct: true\n")
                if q.get("general_feedback"):
                    f.write(f"General Feedback: {q.get('general_feedback')}\n")
                # Feedback for correct/partial/incorrect (if custom)
                default_correct = "Your answer is correct."
                default_partial = "Your answer is partially correct."
                default_incorrect = "Your answer is incorrect."
                if q.get("correct_feedback") and q.get("correct_feedback") != default_correct:
                    f.write(f"Correct Feedback: {q.get('correct_feedback')}\n")
                if q.get("partially_correct_feedback") and q.get("partially_correct_feedback") != default_partial:
                    f.write(f"Partially Correct Feedback: {q.get('partially_correct_feedback')}\n")
                if q.get("incorrect_feedback") and q.get("incorrect_feedback") != default_incorrect:
                    f.write(f"Incorrect Feedback: {q.get('incorrect_feedback')}\n")
                for hint in q.get("hints", []):
                    f.write(f"Hint: {hint.get('text', '')}\n")
                    if hint.get("clear_incorrect", False):
                        f.write("Hint Clear Incorrect: true\n")
                    if hint.get("show_num_correct", False):
                        f.write("Hint Show Number Correct: true\n")

            else:  # essay
                if q.get("grade", 1) != 1:
                    f.write(f"Grade: {q.get('grade', 1)}\n")
                if q.get("lines", 15) != 15:
                    f.write(f"Lines: {q.get('lines', 15)}\n")
                if q.get("attachments", 0) > 0:
                    f.write(f"Attachments: {q.get('attachments')}\n")
                    f.write(f"FileTypes: {q.get('filetypes', '.doc,.docx,.pdf,.png,.jpg,.jpeg')}\n")
                    max_mb = q.get("maxbytes", 2*1024*1024) / (1024*1024)
                    f.write(f"MaxFileSizeMB: {max_mb}\n")
                if q.get("general_feedback"):
                    f.write(f"General Feedback: {q.get('general_feedback')}\n")
                if q.get("grader_info"):
                    f.write(f"Grader Information: {q.get('grader_info')}\n")

            f.write("\n")  # blank line between questions

        f.write("---\n")  # final separator

    log(f"Text file created: {output_file}", "SUCCESS", verbose)
