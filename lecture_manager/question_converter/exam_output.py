# File exam_output.py

from html import escape
from .utils import log
import json
import hashlib
import time
import random
import re

def parse_time_argument(time_str):
    if isinstance(time_str, int):
        return time_str
    time_str = str(time_str).strip().lower()
    if time_str.endswith('m'):
        try:
            return int(time_str[:-1])
        except:
            return 90
    elif time_str.endswith('h'):
        try:
            return int(time_str[:-1]) * 60
        except:
            return 90
    elif time_str.endswith('s'):
        try:
            return int(time_str[:-1]) // 60
        except:
            return 90
    else:
        try:
            return int(time_str)
        except:
            return 90

def safe_html(text):
    if not text:
        return ""
    escaped = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    allowed_tags = re.compile(r'&lt;(/?(?:br|p|strong|em|u|ol|ul|li|span|div|h[1-6]))&gt;', re.IGNORECASE)
    return allowed_tags.sub(r'<\1>', escaped)

def create_exam_html(questions, output_file, verbose=False, time_minutes=90, pass_marks=45):
    log(f"Creating exam HTML with {len(questions)} questions, time limit {time_minutes} min, pass mark {pass_marks}%", "INFO", verbose)

    exam_questions = []
    total_max_raw = 0
    for i, q in enumerate(questions, 1):
        q_type = q.get("type", "multichoice")
        grade = float(q.get("grade", 1))
        total_max_raw += grade

        q_data = {
            "id": i,
            "text": q.get("text", ""),
            "type": q_type,
            "grade": grade,
            "fraction_correct": float(q.get("fraction_correct", 100)),
            "fraction_wrong": float(q.get("fraction_wrong", -20)),
            "options": [],
            "pairs": [],
            "essay_lines": q.get("lines", 15)
        }
        if q_type in ("multichoice", "truefalse"):
            for opt in q.get("options", []):
                q_data["options"].append({
                    "text": safe_html(opt.get("text", "")),
                    "correct": opt.get("correct", False)
                })
        elif q_type == "matching":
            for pair in q.get("pairs", []):
                q_data["pairs"].append({
                    "sub": safe_html(pair.get("subquestion", "")),
                    "ans": safe_html(pair.get("answer", ""))
                })
        exam_questions.append(q_data)

    questions_json = json.dumps(exam_questions, ensure_ascii=False)

    timestamp = int(time.time() * 1000)
    random_salt = random.randint(0, 999999)
    content_version = hashlib.sha256(f"{timestamp}_{random_salt}_{time_minutes}_{questions_json}".encode()).hexdigest()[:16]

    html_template = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=yes, viewport-fit=cover">
    <title>Interactive Exam – Secure Mode</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:ital,wght@0,300;0,400;0,500;0,600;0,700;1,400&display=swap" rel="stylesheet">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Inter', sans-serif;
            background: var(--bg-body);
            color: var(--text-primary);
            transition: background 0.3s, color 0.2s;
            padding: 1rem;
            touch-action: pan-y pinch-zoom; /* Improve touch scrolling */
        }}
        :root {{
            --bg-body: #f4f7fc;
            --bg-container: #ffffff;
            --card-bg: #ffffff;
            --text-primary: #1e293b;
            --text-secondary: #475569;
            --border-light: #e2e8f0;
            --shadow: 0 10px 25px -5px rgba(0,0,0,0.05);
            --primary: #3b82f6;
            --correct: #10b981;
            --wrong: #ef4444;
        }}
        body.dark {{
            --bg-body: #0f172a;
            --bg-container: #1e293b;
            --card-bg: #334155;
            --text-primary: #f1f5f9;
            --text-secondary: #cbd5e1;
            --border-light: #475569;
            --shadow: 0 10px 25px -5px rgba(0,0,0,0.3);
        }}
        .exam-container {{
            max-width: 900px;
            margin: 0 auto;
            background: var(--bg-container);
            border-radius: 1.5rem;
            box-shadow: var(--shadow);
            padding: 1.5rem;
        }}
        .header {{
            display: flex;
            flex-wrap: wrap;
            justify-content: space-between;
            align-items: center;
            gap: 1rem;
            margin-bottom: 1.5rem;
            padding-bottom: 1rem;
            border-bottom: 2px solid var(--border-light);
        }}
        .timer {{
            background: var(--primary);
            color: white;
            padding: 0.5rem 1rem;
            border-radius: 3rem;
            font-weight: bold;
            font-size: 1.2rem;
        }}
        .progress {{
            background: var(--bg-body);
            border-radius: 2rem;
            padding: 0.3rem 0.8rem;
            font-size: 0.9rem;
            font-weight: 500;
        }}
        .controls {{
            display: flex;
            gap: 0.5rem;
        }}
        .controls button {{
            background: var(--card-bg);
            border: 1px solid var(--border-light);
            padding: 0.5rem 1rem;
            border-radius: 2rem;
            cursor: pointer;
            transition: all 0.2s;
            font-size: 0.9rem;
        }}
        .controls button:hover {{
            background: var(--primary);
            color: white;
            border-color: var(--primary);
        }}
        .question-card {{
            background: var(--card-bg);
            border-radius: 1.5rem;
            padding: 1.5rem;
            margin: 1rem 0;
            border: 1px solid var(--border-light);
            position: relative;
        }}
        .q-text {{
            font-size: 1.2rem;
            margin-bottom: 1.5rem;
            line-height: 1.4;
            user-select: text;
        }}
        .option {{
            margin: 0.8rem 0;
            padding: 0.9rem 0.7rem;  /* bigger tap area */
            background: var(--bg-body);
            border-radius: 1rem;
            border: 1px solid var(--border-light);
            cursor: pointer;
            transition: all 0.2s;
            display: flex;
            align-items: center;
            justify-content: space-between;
            font-size: 1rem;
            touch-action: manipulation;
        }}
        .option:hover {{
            background: var(--primary);
            color: white;
        }}
        .option input {{
            margin-right: 0.8rem;
            width: 1.2rem;
            height: 1.2rem;
            cursor: pointer;
        }}
        .option.disabled {{
            opacity: 0.7;
            cursor: not-allowed;
        }}
        .option.correct {{
            border-left: 6px solid var(--correct);
            background: #e0f2e9;
        }}
        .option.wrong {{
            border-left: 6px solid var(--wrong);
            background: #ffe0e0;
        }}
        body.dark .option.correct {{
            background: #064e3b;
        }}
        body.dark .option.wrong {{
            background: #7f1a1a;
        }}
        .status-icon {{
            font-size: 1.1rem;
            font-weight: 500;
            margin-left: 1rem;
        }}
        .textarea-essay {{
            width: 100%;
            padding: 0.8rem;
            border-radius: 1rem;
            border: 1px solid var(--border-light);
            background: var(--bg-body);
            color: var(--text-primary);
            font-family: inherit;
            font-size: 1rem;
            user-select: text;
            touch-action: manipulation;
        }}
        .matching-row {{
            margin: 1rem 0;
            display: flex;
            gap: 1rem;
            align-items: center;
            flex-wrap: wrap;
        }}
        .matching-sub {{
            flex: 1;
            font-weight: 500;
        }}
        .matching-select {{
            flex: 1;
            padding: 0.7rem;
            border-radius: 0.8rem;
            background: var(--bg-body);
            color: var(--text-primary);
            border: 1px solid var(--border-light);
            font-size: 1rem;
        }}
        .nav-buttons {{
            display: flex;
            justify-content: space-between;
            margin-top: 2rem;
        }}
        .nav-buttons button {{
            background: var(--primary);
            color: white;
            padding: 0.7rem 1.5rem;
            border: none;
            border-radius: 2rem;
            cursor: pointer;
            font-weight: 600;
            font-size: 1rem;
            touch-action: manipulation;
        }}
        .nav-buttons button:disabled {{
            opacity: 0.5;
            cursor: not-allowed;
        }}
        /* Certificate styling (unchanged, but added version ID) */
        .certificate {{
            background: linear-gradient(135deg, #fff8e7, #fff0d4);
            border: 12px double #d4af37;
            border-radius: 2rem;
            padding: 2rem;
            text-align: center;
            font-family: 'Georgia', 'Times New Roman', serif;
            box-shadow: 0 20px 35px rgba(0,0,0,0.2);
            position: relative;
            margin-top: 1rem;
        }}
        body.dark .certificate {{
            background: linear-gradient(135deg, #2a2418, #1e1a10);
            border-color: #f0b90b;
        }}
        .certificate h2 {{
            font-size: 2.5rem;
            color: #b8860b;
            text-transform: uppercase;
            letter-spacing: 4px;
            margin-bottom: 1rem;
        }}
        .certificate .score {{
            font-size: 3rem;
            font-weight: bold;
            color: #d4af37;
            margin: 1rem 0;
        }}
        .certificate .details-table {{
            margin: 1.5rem auto;
            max-width: 400px;
            text-align: left;
            border-collapse: collapse;
            background: rgba(0,0,0,0.05);
            border-radius: 1rem;
            overflow: hidden;
        }}
        .certificate .details-table td {{
            padding: 0.5rem 1rem;
            border-bottom: 1px dashed #d4af37;
        }}
        .certificate .signature {{
            margin-top: 2rem;
            display: flex;
            justify-content: space-between;
            flex-wrap: wrap;
            gap: 1rem;
            border-top: 1px solid #d4af37;
            padding-top: 1rem;
        }}
        .certificate .signature-line {{
            flex: 1;
            text-align: center;
        }}
        .certificate .signature-line .line {{
            width: 80%;
            border-bottom: 1px solid #333;
            margin: 0 auto 0.5rem;
        }}
        .certificate .awarded-by {{
            font-size: 0.9rem;
            margin-top: 1rem;
            font-style: italic;
        }}
        .certificate button {{
            background: #d4af37;
            color: #2c3e50;
            border: none;
            padding: 0.5rem 1.5rem;
            border-radius: 2rem;
            margin-top: 1rem;
            cursor: pointer;
            font-weight: bold;
        }}
        .certificate button:hover {{
            background: #b8860b;
            color: white;
        }}
        .hidden {{
            display: none;
        }}
        footer {{
            text-align: center;
            margin-top: 2rem;
            font-size: 0.8rem;
            color: var(--text-secondary);
        }}
        /* Responsive touch improvements */
        @media (max-width: 640px) {{
            .exam-container {{ padding: 1rem; }}
            .question-card {{ padding: 1rem; }}
            .option {{ padding: 0.9rem 0.5rem; }}
            .option input {{ width: 1.4rem; height: 1.4rem; }}
            .nav-buttons button {{ padding: 0.8rem 1.2rem; }}
        }}
    </style>
    <script src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-chtml.js"></script>
</head>
<body>
<div class="exam-container" id="examContainer">
    <div class="header">
        <h2>📝 Online Examination</h2>
        <div class="timer" id="timerDisplay">90:00</div>
        <div class="progress" id="progressDisplay">0/0 answered</div>
        <div class="controls">
            <button id="darkModeToggle">🌓</button>
            <button id="submitExamBtn" style="background:#ef4444; color:white;">Submit</button>
        </div>
    </div>

    <div id="questionArea"></div>
    <div class="nav-buttons" id="navButtons">
        <button id="prevBtn" disabled>← Prev</button>
        <span id="questionCounter">Question 1 of {len(questions)}</span>
        <button id="nextBtn">Next →</button>
    </div>
    <footer>
        ⚠️ Secure mode. Progress saved automatically. Tap to select answer.
    </footer>
</div>

<script>
    // ---------- Security Features (unchanged) ----------
    (function() {{
        document.addEventListener('contextmenu', function(e) {{ e.preventDefault(); return false; }});
        document.addEventListener('copy', function(e) {{ e.preventDefault(); return false; }});
        document.addEventListener('cut', function(e) {{ e.preventDefault(); return false; }});
        document.addEventListener('paste', function(e) {{ e.preventDefault(); return false; }});
        document.addEventListener('dragstart', function(e) {{ e.preventDefault(); return false; }});
        function blockShortcuts(e) {{
            if (e.key === 'F12') {{ e.preventDefault(); alert('Developer tools are disabled.'); return false; }}
            if (e.ctrlKey && e.shiftKey && (e.key === 'I' || e.key === 'J' || e.key === 'C')) {{ e.preventDefault(); alert('Developer tools are disabled.'); return false; }}
            if (e.ctrlKey && e.key === 'u') {{ e.preventDefault(); alert('View source is disabled.'); return false; }}
            if (e.ctrlKey && e.key === 's') {{ e.preventDefault(); alert('Saving is not allowed.'); return false; }}
            if (e.ctrlKey && e.key === 'p') {{ e.preventDefault(); alert('Printing is not allowed.'); return false; }}
            if (e.key === 'PrintScreen') {{ e.preventDefault(); alert('Screenshots are not allowed.'); return false; }}
        }}
        document.addEventListener('keydown', blockShortcuts);
        let devtoolsOpen = false;
        function detectDevTools() {{
            const threshold = 160;
            const start = performance.now();
            debugger;
            const end = performance.now();
            if (end - start > threshold && !devtoolsOpen) {{
                devtoolsOpen = true;
                alert('Developer tools detected. Please close them to continue.');
            }} else {{ devtoolsOpen = false; }}
        }}
        setInterval(detectDevTools, 1000);
        let blurWarningShown = false;
        window.addEventListener('blur', function() {{
            if (!blurWarningShown && !examSubmitted) {{
                blurWarningShown = true;
                alert('Tab switching is not allowed. Your action has been recorded.');
                setTimeout(() => {{ blurWarningShown = false; }}, 5000);
            }}
        }});
        const oldEval = window.eval;
        window.eval = function(str) {{ alert('Eval is not allowed.'); return null; }};
    }})();

    // ---------- Exam Data ----------
    const questionsData = {questions_json};
    const totalQuestions = questionsData.length;
    const timeLimitMinutes = {time_minutes};
    const passMarks = {pass_marks};
    const contentVersion = "{content_version}";
    const totalMaxRaw = {total_max_raw};

    function getStorageKey(prefix) {{ return prefix + '_' + contentVersion; }}
    function getAnswersKey() {{ return getStorageKey('answers'); }}
    function getProgressKey() {{ return getStorageKey('progress'); }}
    function getCompletionKey() {{ return getStorageKey('completed'); }}
    function getEndTimeKey() {{ return getStorageKey('endTime'); }}

    let currentIndex = 0;
    let userAnswers = {{}};
    let examSubmitted = false;
    let timerSeconds = timeLimitMinutes * 60;
    let timerInterval = null;
    let examStartTime = null;
    let examEndTime = null;

    // Helper: update progress bar & answered count
    function updateProgress() {{
        const answered = Object.keys(userAnswers).length;
        document.getElementById('progressDisplay').innerText = `${{answered}}/${{totalQuestions}} answered`;
        // Also update the question counter (already done in render)
    }}

    // Load/save state (unchanged except added updateProgress)
    function loadState() {{
        const completed = localStorage.getItem(getCompletionKey());
        if (completed === 'true') {{
            examSubmitted = true;
            const savedAnswers = localStorage.getItem(getAnswersKey());
            if (savedAnswers) userAnswers = JSON.parse(savedAnswers);
            const progress = localStorage.getItem(getProgressKey());
            if (progress) {{
                const data = JSON.parse(progress);
                examStartTime = data.startTime;
                timerSeconds = data.remainingSeconds;
                currentIndex = data.currentIndex;
            }}
            const endTimeStr = localStorage.getItem(getEndTimeKey());
            if (endTimeStr) examEndTime = parseInt(endTimeStr);
            showCertificateFromStorage();
            return;
        }}
        const progress = localStorage.getItem(getProgressKey());
        if (progress) {{
            const data = JSON.parse(progress);
            currentIndex = data.currentIndex || 0;
            timerSeconds = data.remainingSeconds || (timeLimitMinutes * 60);
            examStartTime = data.startTime;
        }}
        const savedAnswers = localStorage.getItem(getAnswersKey());
        if (savedAnswers) userAnswers = JSON.parse(savedAnswers);
        examSubmitted = false;
        updateProgress();
    }}

    function saveProgress() {{
        if (examSubmitted) return;
        const progressData = {{
            currentIndex: currentIndex,
            remainingSeconds: timerSeconds,
            startTime: examStartTime
        }};
        localStorage.setItem(getProgressKey(), JSON.stringify(progressData));
        localStorage.setItem(getAnswersKey(), JSON.stringify(userAnswers));
        updateProgress();
    }}

    // (markCompleted, timer, score computation same as before – omitted for brevity, but keep from previous working version)
    // ... (I will keep the existing implementations of markCompleted, timer, computeDetailedScore, etc.)
    // To save space, I'm including only the new parts; assume the rest is unchanged from the last working exam_output.py
    // For the final answer, I'll provide the complete file with all parts. Since the message is long, I'll continue.

    // For brevity, I'm showing only the additions and modifications. The full file is available upon request.
    // But to give you a working version, here is the rest of the script (containing the essential functions unchanged).

    // ----- Everything below is exactly from the last working version, with added: updateProgress calls, MathJax typeset, CSV export, version ID -----
    function markCompleted() {{
        examEndTime = Date.now();
        localStorage.setItem(getCompletionKey(), 'true');
        localStorage.setItem(getEndTimeKey(), examEndTime.toString());
        saveProgress();
        examSubmitted = true;
        if (timerInterval) clearInterval(timerInterval);
    }}

    function updateTimerDisplay() {{
        const mins = Math.floor(timerSeconds / 60);
        const secs = timerSeconds % 60;
        document.getElementById('timerDisplay').innerText = `${{mins.toString().padStart(2,'0')}}:${{secs.toString().padStart(2,'0')}}`;
    }}

    function startTimer() {{
        if (timerInterval) clearInterval(timerInterval);
        timerInterval = setInterval(() => {{
            if (examSubmitted) return;
            if (timerSeconds <= 0) {{
                clearInterval(timerInterval);
                alert("Time's up! Submitting your exam.");
                submitExam();
            }} else {{
                timerSeconds--;
                updateTimerDisplay();
                saveProgress();
            }}
        }}, 1000);
    }}

    function computeDetailedScore() {{
        let rawScore = 0;
        let maxRaw = 0;
        let correctCount = 0;
        let wrongCount = 0;
        let unansweredCount = 0;
        let totalDeduction = 0;

        for (let q of questionsData) {{
            const grade = q.grade;
            maxRaw += grade;
            const answer = userAnswers[q.id];
            if (!answer) {{
                unansweredCount++;
                continue;
            }}
            let points = 0;
            if (q.type === 'multichoice' || q.type === 'truefalse') {{
                const selectedIdx = answer.selected;
                if (selectedIdx !== undefined && q.options[selectedIdx] && q.options[selectedIdx].correct) {{
                    points = grade * (q.fraction_correct / 100);
                    correctCount++;
                }} else {{
                    points = grade * (q.fraction_wrong / 100);
                    wrongCount++;
                    totalDeduction += -points;
                }}
            }}
            else if (q.type === 'essay') {{
                if (answer.text && answer.text.trim() !== "") {{
                    points = grade;
                    correctCount++;
                }} else {{
                    unansweredCount++;
                }}
            }}
            else if (q.type === 'matching') {{
                if (answer.matches) {{
                    let allCorrect = true;
                    for (let i=0; i<q.pairs.length; i++) {{
                        if (answer.matches[i] !== q.pairs[i].ans) {{ allCorrect = false; break; }}
                    }}
                    if (allCorrect) {{
                        points = grade;
                        correctCount++;
                    }} else {{
                        points = grade * (q.fraction_wrong / 100);
                        wrongCount++;
                        totalDeduction += -points;
                    }}
                }} else {{
                    unansweredCount++;
                }}
            }}
            rawScore += points;
        }}
        let displayedRaw = Math.max(0, rawScore);
        let percentScore = (rawScore / maxRaw) * 100;
        percentScore = Math.max(0, Math.min(100, percentScore));
        return {{
            raw: rawScore,
            displayedRaw: displayedRaw,
            maxRaw: maxRaw,
            percent: percentScore,
            correct: correctCount,
            wrong: wrongCount,
            unanswered: unansweredCount,
            totalAttempted: correctCount + wrongCount,
            deduction: totalDeduction
        }};
    }}

    function formatDateTime(timestamp) {{
        if (!timestamp) return 'N/A';
        const d = new Date(timestamp);
        return d.toLocaleString();
    }}

    function getDuration() {{
        if (!examStartTime) return 'N/A';
        const end = examEndTime || Date.now();
        const diffSeconds = Math.floor((end - examStartTime) / 1000);
        const mins = Math.floor(diffSeconds / 60);
        const secs = diffSeconds % 60;
        return `${{mins}} min ${{secs}} sec`;
    }}

    // CSV export function (for essay answers)
    function downloadAnswersCSV() {{
        let csvRows = [["Question ID", "Type", "Question Text", "Student Answer (raw)", "Correct/Score"]];
        for (let q of questionsData) {{
            const answer = userAnswers[q.id];
            let answerText = "";
            let correctness = "Not answered";
            if (answer) {{
                if (q.type === "essay") {{
                    answerText = answer.text || "";
                    correctness = "To be graded";
                }} else if (q.type === "multichoice" || q.type === "truefalse") {{
                    const selectedIdx = answer.selected;
                    if (selectedIdx !== undefined && q.options[selectedIdx]) {{
                        answerText = q.options[selectedIdx].text;
                        correctness = q.options[selectedIdx].correct ? "Correct" : "Wrong";
                    }}
                }} else if (q.type === "matching") {{
                    if (answer.matches) {{
                        answerText = Object.values(answer.matches).join(" | ");
                        let allCorrect = true;
                        for (let i=0; i<q.pairs.length; i++) {{
                            if (answer.matches[i] !== q.pairs[i].ans) allCorrect = false;
                        }}
                        correctness = allCorrect ? "Correct" : "Wrong";
                    }}
                }}
            }}
            csvRows.push([q.id, q.type, q.text.replace(/<[^>]*>/g, ''), answerText, correctness]);
        }}
        const csvContent = csvRows.map(row => row.map(cell => `"${{cell.replace(/"/g, '""')}}"`).join(",")).join("\\n");
        const blob = new Blob([csvContent], {{ type: "text/csv;charset=utf-8;" }});
        const link = document.createElement("a");
        const url = URL.createObjectURL(blob);
        link.href = url;
        link.setAttribute("download", `exam_answers_${{contentVersion}}.csv`);
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
    }}

    function showCertificateFromStorage() {{
        const stats = computeDetailedScore();
        const passed = stats.percent >= passMarks;
        const statusText = passed ? 'PASSED' : 'FAILED';
        const gradeLetter = stats.percent >= 80 ? 'A' : (stats.percent >= 60 ? 'B' : (stats.percent >= 40 ? 'C' : 'F'));
        const startStr = formatDateTime(examStartTime);
        const endStr = formatDateTime(examEndTime);
        const durationStr = getDuration();

        const certificateHTML = `
            <div class="certificate">
                <h2>🎓 Certificate of Achievement</h2>
                <div class="subtitle">Examination Completion</div>
                <div class="student-name">Esteemed Candidate</div>
                <div class="score">${{stats.percent.toFixed(1)}}%</div>
                <table class="details-table">
                    <tr><td>📊 Raw Score</td><td><strong>${{stats.displayedRaw.toFixed(1)}} / ${{stats.maxRaw}}</strong></td></tr>
                    <tr><td>📉 Marks Deducted</td><td>${{stats.deduction.toFixed(1)}}</td></tr>
                    <tr><td>✅ Correct Answers</td><td>${{stats.correct}}</td></tr>
                    <tr><td>❌ Wrong Answers</td><td>${{stats.wrong}}</td></tr>
                    <tr><td>❓ Unanswered</td><td>${{stats.unanswered}}</td></tr>
                    <tr><td>🖊️ Attempted</td><td>${{stats.totalAttempted}}</td></tr>
                    <tr><td>📅 Started</td><td>${{startStr}}</td></tr>
                    <tr><td>⏱️ Completed</td><td>${{endStr}}</td></tr>
                    <tr><td>⌛ Duration</td><td>${{durationStr}}</td></tr>
                    <tr><td>🏅 Grade</td><td>${{gradeLetter}} (${{statusText}})</td></tr>
                    <tr><td>🆔 Exam ID</td><td><small>${{contentVersion}}</small></td></tr>
                </table>
                <div class="signature">
                    <div class="signature-line"><div class="line"></div><div>Student Signature</div></div>
                    <div class="signature-line"><div class="line"></div><div>Examiner's Seal</div></div>
                </div>
                <div class="awarded-by">🏆 Awarded by: Udaya Raj Joshi 🏆</div>
                <button onclick="downloadAnswersCSV()">📥 Download Answers (CSV)</button>
                <button onclick="location.reload()">⟳ Reload</button>
            </div>
        `;
        document.getElementById('questionArea').innerHTML = certificateHTML;
        document.getElementById('navButtons').classList.add('hidden');
        document.getElementById('submitExamBtn').disabled = true;
    }}

    function showCertificate() {{
        markCompleted();
        const stats = computeDetailedScore();
        const passed = stats.percent >= passMarks;
        const statusText = passed ? 'PASSED' : 'FAILED';
        const gradeLetter = stats.percent >= 80 ? 'A' : (stats.percent >= 60 ? 'B' : (stats.percent >= 40 ? 'C' : 'F'));
        const startStr = formatDateTime(examStartTime);
        const endStr = formatDateTime(examEndTime);
        const durationStr = getDuration();

        const certificateHTML = `
            <div class="certificate">
                <h2>🎓 Certificate of Achievement</h2>
                <div class="subtitle">Examination Completion</div>
                <div class="student-name">Esteemed Candidate</div>
                <div class="score">${{stats.percent.toFixed(1)}}%</div>
                <table class="details-table">
                    <tr><td>📊 Raw Score</td><td><strong>${{stats.displayedRaw.toFixed(1)}} / ${{stats.maxRaw}}</strong></td></tr>
                    <tr><td>📉 Marks Deducted</td><td>${{stats.deduction.toFixed(1)}}</td></tr>
                    <tr><td>✅ Correct Answers</td><td>${{stats.correct}}</td></tr>
                    <tr><td>❌ Wrong Answers</td><td>${{stats.wrong}}</td></tr>
                    <tr><td>❓ Unanswered</td><td>${{stats.unanswered}}</td></tr>
                    <tr><td>🖊️ Attempted</td><td>${{stats.totalAttempted}}</td></tr>
                    <tr><td>📅 Started</td><td>${{startStr}}</td></tr>
                    <tr><td>⏱️ Completed</td><td>${{endStr}}</td></tr>
                    <tr><td>⌛ Duration</td><td>${{durationStr}}</td></tr>
                    <tr><td>🏅 Grade</td><td>${{gradeLetter}} (${{statusText}})</td></tr>
                    <tr><td>🆔 Exam ID</td><td><small>${{contentVersion}}</small></td></tr>
                </table>
                <div class="signature">
                    <div class="signature-line"><div class="line"></div><div>Student Signature</div></div>
                    <div class="signature-line"><div class="line"></div><div>Examiner's Seal</div></div>
                </div>
                <div class="awarded-by">🏆 Awarded by: Udaya Raj Joshi 🏆</div>
                <button onclick="downloadAnswersCSV()">📥 Download Answers (CSV)</button>
                <button onclick="location.reload()">⟳ Reload</button>
            </div>
        `;
        document.getElementById('questionArea').innerHTML = certificateHTML;
        document.getElementById('navButtons').classList.add('hidden');
        document.getElementById('submitExamBtn').disabled = true;
    }}

    function submitExam() {{
        if (examSubmitted) return;
        if (timerInterval) clearInterval(timerInterval);
        showCertificate();
    }}

    // Apply visual feedback, renderQuestion (same as before, but add MathJax typeset)
    function applyVisualFeedbackAndLock(q, qid, selectedIdx) {{
        if (q.type === 'multichoice' || q.type === 'truefalse') {{
            const optionsDiv = document.querySelectorAll('.option');
            const correctIdx = q.options.findIndex(opt => opt.correct);
            optionsDiv.forEach((optDiv, idx) => {{
                const radio = optDiv.querySelector('input');
                if (radio) radio.disabled = true;
                optDiv.classList.add('disabled');
                if (idx === selectedIdx) {{
                    const isCorrect = q.options[selectedIdx].correct;
                    optDiv.classList.add(isCorrect ? 'correct' : 'wrong');
                    const iconSpan = document.createElement('span');
                    iconSpan.className = 'status-icon';
                    iconSpan.innerHTML = isCorrect ? '✅ Correct' : '❌ Wrong';
                    const oldIcon = optDiv.querySelector('.status-icon');
                    if (oldIcon) oldIcon.remove();
                    optDiv.appendChild(iconSpan);
                }}
                if (selectedIdx !== correctIdx && idx === correctIdx) {{
                    optDiv.classList.add('correct');
                    if (!optDiv.querySelector('.status-icon')) {{
                        const iconSpan = document.createElement('span');
                        iconSpan.className = 'status-icon';
                        iconSpan.innerHTML = '✅ Correct';
                        optDiv.appendChild(iconSpan);
                    }}
                }}
            }});
        }}
        else if (q.type === 'matching') {{
            document.querySelectorAll('.matching-select').forEach(select => select.disabled = true);
        }}
    }}

    function renderQuestion() {{
        if (examSubmitted) return;
        const q = questionsData[currentIndex];
        const qid = q.id;
        const saved = userAnswers[qid];
        let html = `<div class="question-card"><div class="q-text">${{q.text}}</div>`;

        if (q.type === 'multichoice' || q.type === 'truefalse') {{
            html += `<div class="options">`;
            q.options.forEach((opt, idx) => {{
                const isChecked = (saved && saved.selected === idx) ? 'checked' : '';
                const disabled = (saved !== undefined) ? 'disabled' : '';
                let extraClass = '';
                let iconHtml = '';
                if (saved !== undefined) {{
                    if (idx === saved.selected) {{
                        extraClass = opt.correct ? 'correct' : 'wrong';
                        iconHtml = `<span class="status-icon">${{opt.correct ? '✅ Correct' : '❌ Wrong'}}</span>`;
                    }} else if (saved.selected !== idx && opt.correct) {{
                        extraClass = 'correct';
                        iconHtml = `<span class="status-icon">✅ Correct</span>`;
                    }}
                }}
                html += `
                    <div class="option ${{extraClass}}">
                        <label style="display: flex; width: 100%; align-items: center; gap: 0.5rem;">
                            <input type="radio" name="q${{qid}}" value="${{idx}}" ${{isChecked}} ${{disabled}}>
                            <span>${{opt.text}}</span>
                        </label>
                        ${{iconHtml}}
                    </div>`;
            }});
            html += `</div>`;
        }}
        else if (q.type === 'essay') {{
            const essayText = (saved && saved.text) ? escapeHtml(saved.text) : '';
            html += `<textarea class="textarea-essay" id="essay_${{qid}}" rows="${{q.essay_lines || 5}}" placeholder="Write your answer here...">${{essayText}}</textarea>`;
        }}
        else if (q.type === 'matching') {{
            html += `<div class="matching-rows">`;
            q.pairs.forEach((pair, pairIdx) => {{
                const savedChoice = (saved && saved.matches && saved.matches[pairIdx]) ? saved.matches[pairIdx] : '';
                const disabled = (saved !== undefined) ? 'disabled' : '';
                html += `
                    <div class="matching-row">
                        <div class="matching-sub">${{pair.sub}}</div>
                        <select class="matching-select" data-pair-index="${{pairIdx}}" ${{disabled}}>
                            <option value="">-- Select answer --</option>`;
                const allAnswers = [...new Set(q.pairs.map(p => p.ans))];
                allAnswers.forEach(ans => {{
                    const selected = (savedChoice === ans) ? 'selected' : '';
                    html += `<option value="${{escapeHtml(ans)}}" ${{selected}}>${{ans}}</option>`;
                }});
                html += `</select>
                    </div>`;
            }});
            html += `</div>`;
        }}

        html += `</div>`;
        document.getElementById('questionArea').innerHTML = html;

        // MathJax typeset to render LaTeX inside the new content
        if (window.MathJax) {{
            MathJax.typesetPromise();
        }}

        if (!saved) {{
            if (q.type === 'multichoice' || q.type === 'truefalse') {{
                document.querySelectorAll(`input[name="q${{qid}}"]`).forEach(radio => {{
                    radio.addEventListener('change', (e) => {{
                        const selectedIdx = parseInt(e.target.value);
                        userAnswers[qid] = {{ selected: selectedIdx }};
                        saveProgress();
                        applyVisualFeedbackAndLock(q, qid, selectedIdx);
                        renderQuestion();
                    }});
                }});
            }}
            else if (q.type === 'essay') {{
                const textarea = document.getElementById(`essay_${{qid}}`);
                textarea.addEventListener('input', (e) => {{
                    userAnswers[qid] = {{ text: e.target.value }};
                    saveProgress();
                }});
            }}
            else if (q.type === 'matching') {{
                document.querySelectorAll('.matching-select').forEach(select => {{
                    select.addEventListener('change', (e) => {{
                        const pairIdx = parseInt(select.dataset.pairIndex);
                        if (!userAnswers[qid]) userAnswers[qid] = {{ matches: {{}} }};
                        if (!userAnswers[qid].matches) userAnswers[qid].matches = {{}};
                        userAnswers[qid].matches[pairIdx] = select.value;
                        saveProgress();
                        applyVisualFeedbackAndLock(q, qid);
                        renderQuestion();
                    }});
                }});
            }}
        }}

        document.getElementById('questionCounter').innerText = `Question ${{currentIndex+1}} of ${{totalQuestions}}`;
        document.getElementById('prevBtn').disabled = (currentIndex === 0);
        document.getElementById('nextBtn').innerText = (currentIndex === totalQuestions-1) ? 'Finish' : 'Next →';
    }}

    function nextQuestion() {{
        if (examSubmitted) return;
        if (currentIndex < totalQuestions-1) {{
            currentIndex++;
            saveProgress();
            renderQuestion();
        }} else {{
            submitExam();
        }}
    }}
    function prevQuestion() {{
        if (examSubmitted) return;
        if (currentIndex > 0) {{
            currentIndex--;
            saveProgress();
            renderQuestion();
        }}
    }}

    function escapeHtml(str) {{
        if (!str) return '';
        return str.replace(/[&<>]/g, function(m) {{
            if (m === '&') return '&amp;';
            if (m === '<') return '&lt;';
            if (m === '>') return '&gt;';
            return m;
        }});
    }}

    function initDarkMode() {{
        const dark = localStorage.getItem('examDark') === 'true';
        if (dark) document.body.classList.add('dark');
        document.getElementById('darkModeToggle').addEventListener('click', () => {{
            document.body.classList.toggle('dark');
            localStorage.setItem('examDark', document.body.classList.contains('dark'));
        }});
    }}

    // Initialization
    loadState();
    if (examSubmitted) {{
        showCertificateFromStorage();
    }} else {{
        if (!examStartTime) {{
            examStartTime = Date.now();
            saveProgress();
        }}
        startTimer();
        updateTimerDisplay();
        renderQuestion();
        document.getElementById('prevBtn').addEventListener('click', prevQuestion);
        document.getElementById('nextBtn').addEventListener('click', nextQuestion);
        document.getElementById('submitExamBtn').addEventListener('click', () => {{
            if (confirm('Are you sure you want to submit the exam? You cannot change answers after submission.')) submitExam();
        }});
    }}
    initDarkMode();
</script>
</body>
</html>"""
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html_template)
    log(f"Exam HTML file created: {output_file}", "SUCCESS", verbose)
