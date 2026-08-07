# File text_output.py

from .utils import log

# -------------------- TEXT OUTPUT --------------------
def create_text_output(questions, output_file, verbose=False):
    """Convert questions list to text format compatible with converter.py,
    including group markers [group: ...] when groups are present."""
    log(f"Creating text output with {len(questions)} questions", "INFO", verbose)

    with open(output_file, 'w', encoding='utf-8') as f:
        last_group = None
        for i, q in enumerate(questions, 1):
            group = q.get("group", "")

            # Write group marker if group changed and not empty
            if group != last_group:
                if last_group is not None:
                    f.write("\n")  # extra blank line between groups
                if group:
                    f.write(f"[group: {group}]\n\n")
                last_group = group

            # Write question number and text
            question_no = q.get("question_no", i)
            if question_no > 0:
                f.write(f"Question No. {question_no}: {q.get('text', '')}\n")
            else:
                f.write(f"Question: {q.get('text', '')}\n")

            # Log question writing
            text_preview = q.get('text', '')[:50] + "..." if len(q.get('text', '')) > 50 else q.get('text', '')
            log(f"Writing Question {i}: {text_preview}", "INFO", verbose)

            # Write question type
            q_type = q.get('type', 'multichoice')
            f.write(f"Type: {q_type}\n")

            # Handle different question types
            if q_type == "multichoice":
                # Write options
                for opt in q.get("options", []):
                    correct_marker = " *" if opt.get("correct", False) else ""
                    f.write(f"Option: {opt.get('text', '')}{correct_marker}\n")

                # Write grade if not default
                if q.get("grade", 1) != 1:
                    f.write(f"Grade: {q.get('grade', 1)}\n")

                # Write penalty if not default
                if q.get("penalty", 0) != 0:
                    f.write(f"Penalty: {q.get('penalty', 0)}\n")

                # Write general feedback if exists
                if q.get("general_feedback"):
                    feedback_text = q.get('general_feedback', '').replace('<br>', '\n')
                    lines = feedback_text.split('\n')
                    for j, line in enumerate(lines):
                        prefix = "General Feedback: " if j == 0 else "  "
                        f.write(f"{prefix}{line}\n")

                # Write fractions if not default
                if q.get("fraction_correct", 100) != 100 or q.get("fraction_wrong", -20) != -20:
                    f.write(f"Fraction: {q.get('fraction_correct', 100)} {q.get('fraction_wrong', -20)}\n")

            elif q_type == "truefalse":
                # Determine correct answer
                correct_answer = None
                for opt in q.get("options", []):
                    if opt.get("correct", False):
                        correct_answer = opt.get("text", "")
                        break

                if correct_answer:
                    f.write(f"Correct: {correct_answer.lower()}\n")

                # Write grade if not default
                if q.get("grade", 1) != 1:
                    f.write(f"Grade: {q.get('grade', 1)}\n")

                # Write penalty if not default
                if q.get("penalty", 0) != 0:
                    f.write(f"Penalty: {q.get('penalty', 0)}\n")

                # Write general feedback if exists
                if q.get("general_feedback"):
                    feedback_text = q.get('general_feedback', '').replace('<br>', '\n')
                    lines = feedback_text.split('\n')
                    for j, line in enumerate(lines):
                        prefix = "General Feedback: " if j == 0 else "  "
                        f.write(f"{prefix}{line}\n")

                # Write feedback for True if exists
                if q.get("feedback_true"):
                    feedback_text = q.get('feedback_true', '').replace('<br>', '\n')
                    lines = feedback_text.split('\n')
                    for j, line in enumerate(lines):
                        prefix = "Feedback True: " if j == 0 else "  "
                        f.write(f"{prefix}{line}\n")

                # Write feedback for False if exists
                if q.get("feedback_false"):
                    feedback_text = q.get('feedback_false', '').replace('<br>', '\n')
                    lines = feedback_text.split('\n')
                    for j, line in enumerate(lines):
                        prefix = "Feedback False: " if j == 0 else "  "
                        f.write(f"{prefix}{line}\n")

                # Write fractions if not default
                if q.get("fraction_correct", 100) != 100 or q.get("fraction_wrong", -20) != -20:
                    f.write(f"Fraction: {q.get('fraction_correct', 100)} {q.get('fraction_wrong', -20)}\n")

            elif q_type == "matching":
                # Write pairs
                pairs = q.get("pairs", [])
                for pair in pairs:
                    f.write(f"Subquestion: {pair.get('subquestion', '')}\n")
                    f.write(f"Answer: {pair.get('answer', '')}\n")

                # Write grade if not default
                if q.get("grade", 1) != 1:
                    f.write(f"Grade: {q.get('grade', 1)}\n")

                # Write penalty if not default
                if q.get("penalty", 0) != 0:
                    f.write(f"Penalty: {q.get('penalty', 0)}\n")

                # Write shuffle answers if not default (default is true)
                if not q.get("shuffle_answers", True):
                    f.write("Shuffle Answers: false\n")
                elif q.get("shuffle_answers", True) is False:
                    f.write("Shuffle Answers: false\n")

                # Write show number correct if not default (default is false)
                if q.get("show_num_correct", False):
                    f.write("Show Number Correct: true\n")

                # Write general feedback if exists
                if q.get("general_feedback"):
                    feedback_text = q.get('general_feedback', '').replace('<br>', '\n')
                    lines = feedback_text.split('\n')
                    for j, line in enumerate(lines):
                        prefix = "General Feedback: " if j == 0 else "  "
                        f.write(f"{prefix}{line}\n")

                # Write feedbacks if not default
                default_correct = "Your answer is correct."
                default_partial = "Your answer is partially correct."
                default_incorrect = "Your answer is incorrect."

                if q.get("correct_feedback") and q.get("correct_feedback") != default_correct:
                    feedback_text = q.get('correct_feedback', '').replace('<br>', '\n')
                    lines = feedback_text.split('\n')
                    for j, line in enumerate(lines):
                        prefix = "Correct Feedback: " if j == 0 else "  "
                        f.write(f"{prefix}{line}\n")

                if q.get("partially_correct_feedback") and q.get("partially_correct_feedback") != default_partial:
                    feedback_text = q.get('partially_correct_feedback', '').replace('<br>', '\n')
                    lines = feedback_text.split('\n')
                    for j, line in enumerate(lines):
                        prefix = "Partially Correct Feedback: " if j == 0 else "  "
                        f.write(f"{prefix}{line}\n")

                if q.get("incorrect_feedback") and q.get("incorrect_feedback") != default_incorrect:
                    feedback_text = q.get('incorrect_feedback', '').replace('<br>', '\n')
                    lines = feedback_text.split('\n')
                    for j, line in enumerate(lines):
                        prefix = "Incorrect Feedback: " if j == 0 else "  "
                        f.write(f"{prefix}{line}\n")

                # Write hints
                hints = q.get("hints", [])
                for hint_idx, hint in enumerate(hints, 1):
                    if hint.get("text"):
                        hint_text = hint.get("text", "").replace('<br>', '\n')
                        lines = hint_text.split('\n')
                        for j, line in enumerate(lines):
                            prefix = f"Hint {hint_idx}: " if j == 0 else "  "
                            f.write(f"{prefix}{line}\n")

                    # Write hint options if not default (default is false)
                    if hint.get("clear_incorrect", False):
                        f.write(f"Hint {hint_idx} Clear Incorrect: true\n")

                    if hint.get("show_num_correct", False):
                        f.write(f"Hint {hint_idx} Show Number Correct: true\n")

            elif q_type == "essay":
                # Write grade if not default
                if q.get("grade", 1) != 1:
                    f.write(f"Grade: {q.get('grade', 1)}\n")

                # Write lines if not default
                if q.get("lines", 15) != 15:
                    f.write(f"Lines: {q.get('lines', 15)}\n")

                # Write attachments if exists
                if q.get("attachments", 0) > 0:
                    f.write(f"Attachments: {q.get('attachments')}\n")
                    f.write(f"FileTypes: {q.get('filetypes', '.doc,.docx,.pdf,.png,.jpg,.jpeg')}\n")
                    max_mb = q.get("maxbytes", 2*1024*1024) / (1024*1024)
                    f.write(f"MaxFileSizeMB: {max_mb}\n")

                # Write general feedback if exists
                if q.get("general_feedback"):
                    feedback_text = q.get('general_feedback', '').replace('<br>', '\n')
                    lines = feedback_text.split('\n')
                    for j, line in enumerate(lines):
                        prefix = "General Feedback: " if j == 0 else "  "
                        f.write(f"{prefix}{line}\n")

                # Write grader information if exists
                if q.get("grader_info"):
                    grader_text = q.get('grader_info', '').replace('<br>', '\n')
                    lines = grader_text.split('\n')
                    for j, line in enumerate(lines):
                        prefix = "Grader Information: " if j == 0 else "  "
                        f.write(f"{prefix}{line}\n")

            else:
                log(f"Question {i}: Unknown type '{q_type}'", "WARN", verbose)

            # Add blank line between questions
            f.write("\n")
            log(f"Question {i}: Successfully written", "OK", verbose)

    log(f"Text file created: {output_file}", "SUCCESS", verbose)
