# File xml_handler.py

from xml.dom.minidom import Document, parse
import sys
import re
from .constants import C
from .utils import log

# List VALID_QUESTION_TYPES
VALID_QUESTION_TYPES = ["multichoice", "essay", "truefalse", "matching"]

# -------------------- HELPER FUNCTIONS (defined first) --------------------
def create_name_element(doc, index):
    el = doc.createElement("name")
    text_name = doc.createElement("text")
    text_name.appendChild(doc.createTextNode(f"Question No. {index:03d}"))
    el.appendChild(text_name)
    return el

def create_text_element(doc, tag, text):
    el = doc.createElement(tag)
    el.appendChild(doc.createTextNode(text))
    return el

def create_text_element_cdata(doc, tag, text):
    """Create XML element with CDATA section, preserving newlines"""
    el = doc.createElement(tag)
    text_node = doc.createElement("text")

    # Ensure text is properly formatted for XML
    if text:
        # Convert newlines to HTML breaks for proper display in Moodle
        formatted_text = text.replace('\n', '<br>')
        cdata = doc.createCDATASection(formatted_text)
        text_node.appendChild(cdata)
    else:
        # Empty text node
        text_node.appendChild(doc.createTextNode(""))

    el.appendChild(text_node)
    return el

def create_matching_question(doc, q, index):
    """Create XML for matching question type"""
    question_elem = doc.createElement("question")
    question_elem.setAttribute("type", "matching")
    
    # Name
    question_elem.appendChild(create_name_element(doc, index))
    
    # Question text
    question_elem.appendChild(create_text_element_cdata(doc, "questiontext", q['text']))
    
    # General feedback
    question_elem.appendChild(create_text_element_cdata(doc, "generalfeedback", q.get("general_feedback", "")))
    
    # Default grade and penalty
    question_elem.appendChild(create_text_element(doc, "defaultgrade", str(q.get("grade", 1))))
    penalty_value = q.get("penalty", 0)
    question_elem.appendChild(create_text_element(doc, "penalty", str(penalty_value)))
    
    # Hidden and idnumber (defaults)
    question_elem.appendChild(create_text_element(doc, "hidden", "0"))
    question_elem.appendChild(create_text_element(doc, "idnumber", ""))
    
    # Shuffle answers
    shuffle_value = "true" if q.get("shuffle_answers", True) else "false"
    question_elem.appendChild(create_text_element(doc, "shuffleanswers", shuffle_value))
    
    # Correct feedbacks
    question_elem.appendChild(create_text_element_cdata(doc, "correctfeedback", 
        q.get("correct_feedback", "Your answer is correct.")))
    question_elem.appendChild(create_text_element_cdata(doc, "partiallycorrectfeedback", 
        q.get("partially_correct_feedback", "Your answer is partially correct.")))
    question_elem.appendChild(create_text_element_cdata(doc, "incorrectfeedback", 
        q.get("incorrect_feedback", "Your answer is incorrect.")))
    
    # Show number correct
    if q.get("show_num_correct", False):
        question_elem.appendChild(doc.createElement("shownumcorrect"))
    
    # Add subquestions
    for pair in q.get("pairs", []):
        subquestion_elem = doc.createElement("subquestion")
        subquestion_elem.setAttribute("format", "html")
        
        # Subquestion text
        text_elem = doc.createElement("text")
        # Format the subquestion text properly
        subq_text = pair.get("subquestion", "")
        # If it's a simple text, wrap it in CDATA
        if not subq_text.startswith("<![CDATA["):
            subq_text = f"<![CDATA[<p>{subq_text}</p>]]>"
        
        # Parse the CDATA properly
        text_node = doc.createElement("text")
        if subq_text.startswith("<![CDATA["):
            # Extract CDATA content
            cdata_content = subq_text[9:-3]  # Remove <![CDATA[ and ]]>
            cdata = doc.createCDATASection(cdata_content)
            text_node.appendChild(cdata)
        else:
            text_node.appendChild(doc.createTextNode(subq_text))
        
        subquestion_elem.appendChild(text_node)
        
        # Answer
        answer_elem = doc.createElement("answer")
        answer_text = doc.createElement("text")
        answer_text.appendChild(doc.createTextNode(pair.get("answer", "")))
        answer_elem.appendChild(answer_text)
        subquestion_elem.appendChild(answer_elem)
        
        question_elem.appendChild(subquestion_elem)
    
    # Add hints if any
    for hint_idx, hint in enumerate(q.get("hints", []), 1):
        hint_elem = doc.createElement("hint")
        hint_elem.setAttribute("format", "html")
        
        # Add hint attributes
        if hint.get("clear_incorrect", False):
            hint_elem.setAttribute("clearincorrectresponses", "true")
        if hint.get("show_num_correct", False):
            hint_elem.setAttribute("shownumpartscorrect", "true")
        
        # Hint text
        text_elem = doc.createElement("text")
        hint_text = hint.get("text", f"Hint {hint_idx}")
        if not hint_text.startswith("<![CDATA["):
            hint_text = f"<![CDATA[<p>{hint_text}</p>]]>"
        
        if hint_text.startswith("<![CDATA["):
            cdata_content = hint_text[9:-3]
            cdata = doc.createCDATASection(cdata_content)
            text_elem.appendChild(cdata)
        else:
            text_elem.appendChild(doc.createTextNode(hint_text))
        
        hint_elem.appendChild(text_elem)
        question_elem.appendChild(hint_elem)
    
    return question_elem

def create_mcq_question(doc, q, index):
    question_elem = doc.createElement("question")
    question_elem.setAttribute("type","multichoice")
    question_elem.appendChild(create_name_element(doc,index))

    # Question text with CDATA
    qtext = doc.createElement("questiontext")
    qtext.setAttribute("format","html")
    qtext.appendChild(create_text_element_cdata(doc,"text",q['text']).childNodes[0])
    question_elem.appendChild(qtext)

    # General feedback with CDATA (preserves newlines as <br>)
    question_elem.appendChild(create_text_element_cdata(doc,"generalfeedback",q.get("general_feedback","")))

    # Get grade from question dictionary (defaults to 1)
    grade_value = q.get("grade", 1)  # This reads what was set in text_parser.py
    question_elem.appendChild(create_text_element(doc, "defaultgrade", str(grade_value)))


    # Other elements
    question_elem.appendChild(create_text_element(doc,"penalty",str(q.get("penalty",0))))
    question_elem.appendChild(create_text_element(doc,"shuffleanswers","true"))
    question_elem.appendChild(create_text_element(doc,"single","true"))
    question_elem.appendChild(create_text_element(doc,"answernumbering","abc"))

    # Options
    for opt in q["options"]:
        fraction = str(q.get("fraction_correct",100) if opt["correct"] else q.get("fraction_wrong",-20))
        answer = doc.createElement("answer")
        answer.setAttribute("fraction",fraction)
        answer.setAttribute("format","html")
        answer.appendChild(create_text_element_cdata(doc,"text",opt["text"]).childNodes[0])

        feedback = doc.createElement("feedback")
        feedback.setAttribute("format","html")
        feedback.appendChild(create_text_element_cdata(doc,"text","Correct" if opt["correct"] else "Incorrect").childNodes[0])
        answer.appendChild(feedback)
        question_elem.appendChild(answer)

    return question_elem

def create_essay_question(doc, q, index):
    question_elem = doc.createElement("question")
    question_elem.setAttribute("type","essay")
    question_elem.appendChild(create_name_element(doc,index))

    # Question text
    question_elem.appendChild(create_text_element_cdata(doc,"questiontext",q['text']))

    # General feedback (preserves newlines)
    question_elem.appendChild(create_text_element_cdata(doc,"generalfeedback",q.get("general_feedback","")))

    # Get grade from question dictionary (defaults to 1) - ONLY ONCE!
    grade_value = q.get("grade", 1)
    question_elem.appendChild(create_text_element(doc,"defaultgrade",str(grade_value)))

    # Other elements - REMOVE THE DUPLICATE defaultgrade line from here
    question_elem.appendChild(create_text_element(doc,"penalty","0"))

    response_format = "editorfilepicker" if q.get("attachments",0)>0 else "editor"
    question_elem.appendChild(create_text_element(doc,"responseformat",response_format))
    question_elem.appendChild(create_text_element(doc,"responserequired","1"))
    question_elem.appendChild(create_text_element(doc,"responsefieldlines",str(q.get("lines",15))))

    if q.get('attachments',0)>0:
        question_elem.appendChild(create_text_element(doc,"attachments",str(q.get("attachments",1))))
        question_elem.appendChild(create_text_element(doc,"attachmentsrequired","0"))
        question_elem.appendChild(create_text_element(doc,"maxbytes",str(q.get("maxbytes",2*1024*1024))))
        question_elem.appendChild(create_text_element(doc,"filetypeslist",q.get("filetypes",".doc,.docx,.pdf,.png,.jpg,.jpeg")))

    # Grader info (preserves newlines)
    if q.get("grader_info"):
        question_elem.appendChild(create_text_element_cdata(doc,"graderinfo",q["grader_info"]))

    question_elem.appendChild(create_text_element_cdata(doc,"responsetemplate",""))
    return question_elem

# Creates a simpler helper function for feedback
def create_feedback_element(doc, text):
    """Create a feedback element with CDATA text"""
    feedback = doc.createElement("feedback")
    feedback.setAttribute("format", "html")
    
    text_elem = doc.createElement("text")
    if text:
        formatted_text = text.replace('\n', '<br>')
        cdata = doc.createCDATASection(formatted_text)
        text_elem.appendChild(cdata)
    else:
        text_elem.appendChild(doc.createTextNode(""))
    
    feedback.appendChild(text_elem)
    return feedback

# Add this function to create True/False XML
def create_truefalse_question(doc, q, index):
    """Create XML for True/False question type"""
    question_elem = doc.createElement("question")
    question_elem.setAttribute("type", "truefalse")
    
    # Name
    question_elem.appendChild(create_name_element(doc, index))
    
    # Question text
    question_elem.appendChild(create_text_element_cdata(doc, "questiontext", q['text']))
    
    # General feedback
    question_elem.appendChild(create_text_element_cdata(doc, "generalfeedback", q.get("general_feedback", "")))
    
    # Default grade and penalty
    question_elem.appendChild(create_text_element(doc, "defaultgrade", str(q.get("grade", 1))))
    penalty_value = q.get("penalty", 0)
    question_elem.appendChild(create_text_element(doc, "penalty", str(penalty_value)))
    
    # Hidden and idnumber (defaults)
    question_elem.appendChild(create_text_element(doc, "hidden", "0"))
    question_elem.appendChild(create_text_element(doc, "idnumber", ""))
    
    # Answers: first true, then false
    # Find which is correct
    correct_answer = None
    for opt in q.get("options", []):
        if opt.get("correct", False):
            correct_answer = opt.get("text", "").lower()
            break
    
    # Get fraction values from question (default to 100/-20)
    fraction_correct = q.get("fraction_correct", 100)
    fraction_wrong = q.get("fraction_wrong", -20)
    
    log(f"Question {index}: True/False fractions - Correct: {fraction_correct}%, Wrong: {fraction_wrong}%", "INFO", True)
    
    # Answer for "true"
    true_fraction = str(fraction_correct) if correct_answer == "true" else str(fraction_wrong)
    true_answer = doc.createElement("answer")
    true_answer.setAttribute("fraction", true_fraction)
    true_answer.setAttribute("format", "moodle_auto_format")
    true_answer.appendChild(create_text_element(doc, "text", "true"))
    
    # Feedback for true answer
    true_feedback_text = q.get("feedback_true", "This feedback for the response True.")
    true_feedback = create_feedback_element(doc, true_feedback_text)
    true_answer.appendChild(true_feedback)
    question_elem.appendChild(true_answer)
    
    # Answer for "false"
    false_fraction = str(fraction_correct) if correct_answer == "false" else str(fraction_wrong)
    false_answer = doc.createElement("answer")
    false_answer.setAttribute("fraction", false_fraction)
    false_answer.setAttribute("format", "moodle_auto_format")
    false_answer.appendChild(create_text_element(doc, "text", "false"))
    
    # Feedback for false answer
    false_feedback_text = q.get("feedback_false", "This feedback for the response False.")
    false_feedback = create_feedback_element(doc, false_feedback_text)
    false_answer.appendChild(false_feedback)
    question_elem.appendChild(false_answer)
    
    return question_elem

# -------------------- XML PARSING --------------------
def xml_to_questions(input_file, verbose=False):
    """Parse Moodle XML file and extract questions"""
    try:
        dom = parse(input_file)
    except Exception as e:
        print(f"{C.RED}[ERROR] Failed to parse XML: {e}{C.RESET}")
        sys.exit(1)

    questions = []
    question_elements = dom.getElementsByTagName("question")

    log(f"Found {len(question_elements)} question elements in XML", "INFO", verbose)

    for idx, q_elem in enumerate(question_elements, 1):
        q_type = q_elem.getAttribute("type")

        # Skip if not multichoice, essay, or truefalse
        if q_type not in VALID_QUESTION_TYPES:
            # Log error and skip
            print(f"{C.YELLOW}[WARNING] Skipping question {idx} (unknown type: '{q_type}'){C.RESET}")
            print(f"          Available types: {', '.join(VALID_QUESTION_TYPES)}")
            continue
        
        # Initialize question
        question = {
            "type": q_type,
            "question_no": idx,  # Default to enumeration index
            "original_question_no": idx,  # Store original
            "text": "",
            "general_feedback": "",
            "grader_info": "",  # Initialize as empty string
            "grade": 1,
            "penalty": 0,
            "lines": 15,
        }
        
        # Extract question number from name element
        name_elem = q_elem.getElementsByTagName("name")
        if name_elem:
            text_elem = name_elem[0].getElementsByTagName("text")
            if text_elem and text_elem[0].firstChild:
                name_text = text_elem[0].firstChild.data
                # Try to extract number from "Question No. 001" format
                match = re.search(r'Question No\.?\s*(\d+)', name_text, re.IGNORECASE)
                if match:
                    try:
                        question["question_no"] = int(match.group(1))
                        question["original_question_no"] = int(match.group(1))  # Store original
                        log(f"Question {idx}: Found question number {question['question_no']} in name", "INFO", verbose)
                    except:
                        pass  # Keep the default idx

        # Extract text
        text_elem = q_elem.getElementsByTagName("questiontext")
        if text_elem:
            text_node = text_elem[0].getElementsByTagName("text")
            if text_node:
                question["text"] = text_node[0].firstChild.data if text_node[0].firstChild else ""
                # Truncate for logging
                text_preview = question["text"][:50] + "..." if len(question["text"]) > 50 else question["text"]
                log(f"Question {idx}: {text_preview}", "INFO", verbose)

        # Extract general feedback - preserve newlines
        fb_elem = q_elem.getElementsByTagName("generalfeedback")
        if fb_elem:
            fb_node = fb_elem[0].getElementsByTagName("text")
            if fb_node and fb_node[0].firstChild:
                feedback_text = fb_node[0].firstChild.data
                # Convert HTML <br> back to newlines for consistent handling
                if feedback_text:
                    feedback_text = feedback_text.replace('<br>', '\n').replace('<br/>', '\n')
                    question["general_feedback"] = feedback_text
                    log(f"Question {idx}: Found general feedback", "INFO", verbose)

        # Extract grade
        grade_elem = q_elem.getElementsByTagName("defaultgrade")
        if grade_elem and grade_elem[0].firstChild:
            try:
                question["grade"] = float(grade_elem[0].firstChild.data)
                log(f"Question {idx}: Grade set to {question['grade']}", "INFO", verbose)
            except:
                pass

        # Extract penalty
        penalty_elem = q_elem.getElementsByTagName("penalty")
        if penalty_elem and penalty_elem[0].firstChild:
            try:
                question["penalty"] = float(penalty_elem[0].firstChild.data)
                log(f"Question {idx}: Penalty set to {question['penalty']}", "INFO", verbose)
            except:
                pass
            
        if q_type == "matching":
            # Parse shuffle answers
            shuffle_elem = q_elem.getElementsByTagName("shuffleanswers")
            if shuffle_elem and shuffle_elem[0].firstChild:
                question["shuffle_answers"] = shuffle_elem[0].firstChild.data.lower() == "true"
            
            # Parse show number correct
            shownum_elem = q_elem.getElementsByTagName("shownumcorrect")
            question["show_num_correct"] = len(shownum_elem) > 0
            
            # Parse feedbacks
            for fb_type in ["correctfeedback", "partiallycorrectfeedback", "incorrectfeedback"]:
                fb_elem = q_elem.getElementsByTagName(fb_type)
                if fb_elem:
                    fb_node = fb_elem[0].getElementsByTagName("text")
                    if fb_node and fb_node[0].firstChild:
                        fb_text = fb_node[0].firstChild.data
                        if fb_text:
                            fb_text = fb_text.replace('<br>', '\n').replace('<br/>', '\n')
                            key = fb_type.replace("feedback", "_feedback")
                            question[key] = fb_text
            
            # Parse subquestions
            question["pairs"] = []
            subq_elements = q_elem.getElementsByTagName("subquestion")
            for subq_elem in subq_elements:
                # Get subquestion text
                subq_text = ""
                text_nodes = subq_elem.getElementsByTagName("text")
                if text_nodes and text_nodes[0].firstChild:
                    subq_text = text_nodes[0].firstChild.data
                    # Clean up HTML
                    subq_text = re.sub(r'<[^>]+>', '', subq_text)
                
                # Get answer
                answer_text = ""
                answer_nodes = subq_elem.getElementsByTagName("answer")
                if answer_nodes:
                    ans_text_nodes = answer_nodes[0].getElementsByTagName("text")
                    if ans_text_nodes and ans_text_nodes[0].firstChild:
                        answer_text = ans_text_nodes[0].firstChild.data
                
                if subq_text and answer_text:
                    question["pairs"].append({
                        "subquestion": subq_text,
                        "answer": answer_text
                    })
            
            # Parse hints
            question["hints"] = []
            hint_elements = q_elem.getElementsByTagName("hint")
            for hint_elem in hint_elements:
                hint = {
                    "text": "",
                    "clear_incorrect": False,
                    "show_num_correct": False
                }
                
                # Get hint attributes
                if hint_elem.hasAttribute("clearincorrectresponses"):
                    hint["clear_incorrect"] = hint_elem.getAttribute("clearincorrectresponses").lower() == "true"
                if hint_elem.hasAttribute("shownumpartscorrect"):
                    hint["show_num_correct"] = hint_elem.getAttribute("shownumpartscorrect").lower() == "true"
                
                # Get hint text
                text_nodes = hint_elem.getElementsByTagName("text")
                if text_nodes and text_nodes[0].firstChild:
                    hint_text = text_nodes[0].firstChild.data
                    if hint_text:
                        hint_text = hint_text.replace('<br>', '\n').replace('<br/>', '\n')
                        hint["text"] = hint_text
                
                question["hints"].append(hint)
            
            log(f"Question {idx}: Matching with {len(question['pairs'])} pairs", "INFO", verbose)

        if q_type == "truefalse":
            question["type"] = "truefalse"
            question["options"] = []
            
            # Get answers
            answer_elements = q_elem.getElementsByTagName("answer")
            for ans_idx, ans_elem in enumerate(answer_elements, 1):
                # Get fraction to determine correctness
                fraction = ans_elem.getAttribute("fraction")
                try:
                    fraction_val = float(fraction)
                    correct = (fraction_val == 100)
                except:
                    correct = False
                
                # Get answer text
                ans_text = ""
                text_node = ans_elem.getElementsByTagName("text")
                if text_node and text_node[0].firstChild:
                    ans_text = text_node[0].firstChild.data
                    # Ensure proper case
                    ans_text = ans_text.capitalize()
                
                # Get feedback
                feedback_text = ""
                feedback_nodes = ans_elem.getElementsByTagName("feedback")
                if feedback_nodes and feedback_nodes[0]:
                    text_nodes = feedback_nodes[0].getElementsByTagName("text")
                    if text_nodes and text_nodes[0] and text_nodes[0].firstChild:
                        feedback_text = text_nodes[0].firstChild.data
                        # Convert HTML breaks to newlines
                        feedback_text = feedback_text.replace('<br>', '\n').replace('<br/>', '\n')
                
                # Store the option
                question["options"].append({
                    "text": ans_text,
                    "correct": correct
                })
                
                # Store feedback in the question
                if ans_text.lower() == "true":
                    question["feedback_true"] = feedback_text
                elif ans_text.lower() == "false":
                    question["feedback_false"] = feedback_text
                
                log(f"Question {idx}, Answer {ans_idx}: {ans_text} (correct: {correct})", "INFO", verbose)
            
            log(f"Question {idx}: True/False question parsed", "INFO", verbose)
        
        elif q_type == "multichoice":
            question["options"] = []
            answer_elements = q_elem.getElementsByTagName("answer")
            log(f"Question {idx}: Found {len(answer_elements)} options", "INFO", verbose)

            for ans_idx, ans_elem in enumerate(answer_elements, 1):
                # Get fraction
                fraction = ans_elem.getAttribute("fraction")
                try:
                    fraction_val = float(fraction)
                    correct = fraction_val > 0
                except:
                    correct = False

                # Get answer text
                ans_text = ""
                text_node = ans_elem.getElementsByTagName("text")
                if text_node and text_node[0].firstChild:
                    ans_text = text_node[0].firstChild.data

                question["options"].append({
                    "text": ans_text,
                    "correct": correct
                })

                # Log option details
                ans_preview = ans_text[:30] + "..." if len(ans_text) > 30 else ans_text
                log(f"Question {idx}, Option {ans_idx}: {ans_preview} (correct: {correct})", "INFO", verbose)

            # Set default fractions
            question["fraction_correct"] = 100
            question["fraction_wrong"] = -20

        else:  # essay
            # Extract lines
            lines_elem = q_elem.getElementsByTagName("responsefieldlines")
            if lines_elem and lines_elem[0].firstChild:
                try:
                    question["lines"] = int(lines_elem[0].firstChild.data)
                    log(f"Question {idx}: Response lines set to {question['lines']}", "INFO", verbose)
                except:
                    pass

            # Extract attachments
            att_elem = q_elem.getElementsByTagName("attachments")
            if att_elem and att_elem[0].firstChild:
                try:
                    question["attachments"] = int(att_elem[0].firstChild.data)
                    log(f"Question {idx}: Attachments set to {question['attachments']}", "INFO", verbose)
                except:
                    pass
            else:
                question["attachments"] = 0

            # Extract filetypes
            filetypes_elem = q_elem.getElementsByTagName("filetypeslist")
            if filetypes_elem and filetypes_elem[0].firstChild:
                question["filetypes"] = filetypes_elem[0].firstChild.data
            else:
                question["filetypes"] = ".doc,.docx,.pdf,.png,.jpg,.jpeg"

            # Extract maxbytes
            maxbytes_elem = q_elem.getElementsByTagName("maxbytes")
            if maxbytes_elem and maxbytes_elem[0].firstChild:
                try:
                    question["maxbytes"] = int(maxbytes_elem[0].firstChild.data)
                except:
                    question["maxbytes"] = 2 * 1024 * 1024
            else:
                question["maxbytes"] = 2 * 1024 * 1024

            # Extract grader info - FIXED: Was missing!
            grader_elem = q_elem.getElementsByTagName("graderinfo")
            if grader_elem:
                grader_node = grader_elem[0].getElementsByTagName("text")
                if grader_node and grader_node[0].firstChild:
                    grader_text = grader_node[0].firstChild.data
                    # Convert HTML <br> back to newlines for consistent handling
                    if grader_text:
                        grader_text = grader_text.replace('<br>', '\n').replace('<br/>', '\n')
                        question["grader_info"] = grader_text
                        log(f"Question {idx}: Found grader info", "INFO", verbose)

        questions.append(question)
        log(f"Question {idx}: Successfully parsed ({q_type}, Grade: {question['grade']})", "OK", verbose)

    log(f"Total questions parsed: {len(questions)}", "SUMMARY", verbose)
    return questions

# -------------------- XML OUTPUT --------------------
def create_moodle_xml(questions, output_file, verbose=False):
    doc = Document()
    quiz = doc.createElement("quiz")
    doc.appendChild(quiz)

    log(f"Creating XML with {len(questions)} questions", "INFO", verbose)

    for i, q in enumerate(questions, 1):
        # Log question being processed
        text_preview = q.get('text', '')[:50] + "..." if len(q.get('text', '')) > 50 else q.get('text', '')
        log(f"Processing Question {i}: {text_preview}", "INFO", verbose)

        # Question comment block
        quiz.appendChild(doc.createComment(" ================================================= "))
        quiz.appendChild(doc.createComment(f" Question No. {i} "))
        quiz.appendChild(doc.createComment(" ================================================= "))

        # Question element
        if q["type"] == "multichoice":
            question_elem = create_mcq_question(doc, q, i)
            log(f"Question {i}: Created MCQ element", "INFO", verbose)
        elif q["type"] == "truefalse":
            question_elem = create_truefalse_question(doc, q, i)
            log(f"Question {i}: Created True/False element", "INFO", verbose)
        elif q["type"] == "matching":
            question_elem = create_matching_question(doc, q, i)
            log(f"Question {i}: Created matching element", "INFO", verbose)
        else:
            question_elem = create_essay_question(doc, q, i)
            log(f"Question {i}: Created essay element", "INFO", verbose)

        quiz.appendChild(question_elem)

        # Add ONE-LINE GAP after each question for readability
        quiz.appendChild(doc.createTextNode("\n"))
        log(f"Question {i}: Added to XML document", "OK", verbose)
        
    with open(output_file, "wb") as f:
        f.write(doc.toprettyxml(indent="  ", encoding="utf-8"))

    log(f"XML file created: {output_file}", "SUCCESS", verbose)