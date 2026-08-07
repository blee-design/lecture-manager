# core/html_output.py

from html import escape
from .utils import log

# Optional: try to import bleach
try:
    import bleach
    BLEACH_AVAILABLE = True
    ALLOWED_TAGS = [
    'b', 'i', 'em', 'p', 'br', 'strong', 'ul', 'ol', 'li',
    'table', 'tr', 'td', 'th', 'thead', 'tbody', 'div', 'span',
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'hr', 'blockquote',
    'pre', 'code', 'sub', 'sup', 'u', 's',
    # SVG elements
    'svg', 'line', 'rect', 'circle', 'text', 'g', 'path', 'polygon', 'ellipse',
    'defs', 'filter', 'feDropShadow', 'feOffset', 'feGaussianBlur',
    'polyline', 'image', 'use', 'linearGradient', 'stop', 'radialGradient',
    'tspan', 'marker', 'title', 'desc'
    ]
except ImportError:
    BLEACH_AVAILABLE = False
    ALLOWED_TAGS = []

def create_html_output(questions, output_file, verbose=False, shuffle_applied=False):
    """Convert questions list to modern, attractive HTML format with search, filter,
       collapsible groups, per‑question correct answer toggles, global toggle,
       LaTeX support and pagination."""
    log(f"Creating HTML output with {len(questions)} questions", "INFO", verbose)

    if not BLEACH_AVAILABLE and verbose:
        log("Bleach not installed – HTML will not be sanitized. Install with: pip install bleach", "WARN", True)

    def sanitize(text):
        # If the text contains an SVG tag, return it as-is (trusted content)
        if text and '<svg' in text:
            return text
    
        if BLEACH_AVAILABLE and text:
            allowed_attrs = bleach.sanitizer.ALLOWED_ATTRIBUTES.copy()
            # Allow style/class/id on all tags
            allowed_attrs['*'] = ['style', 'class', 'id']
            
            # SVG-specific attributes
            svg_attrs = {
                'svg': ['xmlns', 'width', 'height', 'viewBox', 'version'],
                'line': ['x1', 'y1', 'x2', 'y2', 'stroke', 'stroke-width', 'stroke-linecap', 'stroke-linejoin'],
                'rect': ['x', 'y', 'width', 'height', 'fill', 'stroke', 'rx', 'ry'],
                'circle': ['cx', 'cy', 'r', 'fill', 'stroke'],
                'text': ['x', 'y', 'font-size', 'text-anchor', 'fill', 'font-weight', 'font-family', 'dy', 'dx', 'transform'],
                'g': ['fill', 'stroke', 'transform', 'filter'],
                'path': ['d', 'fill', 'stroke', 'stroke-width', 'stroke-linecap', 'stroke-linejoin', 'filter'],
                'polygon': ['points', 'fill', 'stroke', 'filter'],
                'ellipse': ['cx', 'cy', 'rx', 'ry', 'fill', 'stroke'],
                'defs': [],
                'filter': ['id', 'x', 'y', 'width', 'height', 'filterUnits'],
                'feDropShadow': ['dx', 'dy', 'stdDeviation', 'flood-color', 'flood-opacity'],
                'feOffset': ['dx', 'dy'],
                'feGaussianBlur': ['stdDeviation'],
                'polyline': ['points', 'fill', 'stroke'],
                'image': ['x', 'y', 'width', 'height', 'href', 'preserveAspectRatio'],
                'linearGradient': ['id', 'x1', 'y1', 'x2', 'y2'],
                'stop': ['offset', 'stop-color', 'stop-opacity'],
                'radialGradient': ['id', 'cx', 'cy', 'r', 'fx', 'fy'],
                'tspan': ['x', 'y', 'dy', 'font-family'],
                'marker': ['id', 'viewBox', 'refX', 'refY', 'markerWidth', 'markerHeight', 'orient'],
                'title': [],
                'desc': []
            }
            allowed_attrs.update(svg_attrs)
            
            # No 'styles' argument – style attribute is already allowed via allowed_attrs['*']
            return bleach.clean(text, tags=ALLOWED_TAGS, attributes=allowed_attrs, strip=True)
        
        return text

    # Build filter buttons based on actual question types present
    all_types = set(q.get("type", "multichoice") for q in questions)
    type_count = {t: sum(1 for q in questions if q.get("type") == t) for t in all_types}
    type_display = {
        "multichoice": "MCQ",
        "essay": "Essay",
        "truefalse": "True/False",
        "matching": "Matching"
    }
    filter_buttons_html = '<div class="filter-buttons" id="typeFilterButtons">'
    filter_buttons_html += '<button class="filter-btn active" data-type="all">All</button>'
    for t in sorted(all_types):
        display = type_display.get(t, t.capitalize())
        filter_buttons_html += f'<button class="filter-btn" data-type="{t}">{display} ({type_count[t]})</button>'
    filter_buttons_html += '</div>'

    # Build full questions HTML (with groups and collapsible structure)
    full_questions_html = ""
    last_group = None
    group_opened = False
    group_id_counter = 0

    for i, q in enumerate(questions, 1):
        q_text = sanitize(q.get("text", ""))
        q_type = q.get("type", "multichoice")
        q_no = q.get("question_no", i)

        group = q.get("group", "")
        if not shuffle_applied:
            if group != last_group:
                if group_opened:
                    full_questions_html += '</div></div>'
                if group:
                    group_id_counter += 1
                    full_questions_html += f'''
                    <div class="group" data-group-id="{group_id_counter}">
                        <div class="group-title" data-group-toggle="{group_id_counter}">
                            <span class="group-icon">📁</span> {escape(group)}
                            <span class="group-toggle-icon">▼</span>
                        </div>
                        <div class="group-questions" data-group-questions="{group_id_counter}">'''
                    group_opened = True
                else:
                    full_questions_html += '<div class="group"><div class="group-questions">'
                    group_opened = True
                last_group = group
        else:
            if not group_opened:
                full_questions_html += '<div class="group"><div class="group-questions">'
                group_opened = True

        # Question card
        full_questions_html += f'''
        <div class="question-card" data-question-id="{i}" data-question-type="{q_type}">
            <div class="question-header">
                <div class="q-number">Question {q_no}</div>
                <div class="q-type {q_type}">{q_type.upper()}</div>
            </div>
            <div class="q-text">{q_text}</div>
        '''

        # General feedback
        if q.get("general_feedback"):
            fb_text = sanitize(q.get("general_feedback", "").replace('<br>', '\n'))
            full_questions_html += f'<div class="feedback" data-feedback="true"><strong>💡 Feedback:</strong><br>{fb_text}</div>'

        # Options
        if q_type == "multichoice":
            options = q.get("options", [])
            if options:
                full_questions_html += '<div class="options">'
                for opt in options:
                    correct = opt.get("correct", False)
                    opt_text = sanitize(opt.get("text", ""))
                    correct_badge = '<span class="correct-badge">✓ Correct</span>' if correct else ''
                    full_questions_html += f'''
                    <div class="option {'correct' if correct else ''}" data-correct="{str(correct).lower()}">
                        <div class="option-content">{correct_badge}{opt_text}</div>
                    </div>'''
                full_questions_html += '</div>'

        elif q_type == "truefalse":
            options = q.get("options", [])
            full_questions_html += '<div class="options truefalse-options">'
            for opt in options:
                correct = opt.get("correct", False)
                opt_text = sanitize(opt.get("text", ""))
                correct_badge = '<span class="correct-badge">✓ Correct</span>' if correct else ''
                feedback_html = ""
                if opt_text == "True" and q.get("feedback_true"):
                    feedback_html = f'<div class="option-feedback"><em>Feedback if True:</em> {sanitize(q["feedback_true"])}</div>'
                elif opt_text == "False" and q.get("feedback_false"):
                    feedback_html = f'<div class="option-feedback"><em>Feedback if False:</em> {sanitize(q["feedback_false"])}</div>'
                full_questions_html += f'''
                <div class="option {'correct' if correct else ''}" data-correct="{str(correct).lower()}">
                    <div class="option-content">{correct_badge}{opt_text}</div>
                    {feedback_html}
                </div>'''
            full_questions_html += '</div>'

        elif q_type == "matching":
            pairs = q.get("pairs", [])
            if pairs:
                full_questions_html += '''
                <div class="matching-pairs">
                    <h4>🔗 Matching Pairs</h4>
                    <table class="matching-table">
                        <thead><tr><th>Subquestion</th><th>Answer</th></tr></thead>
                        <tbody>'''
                for pair in pairs:
                    subq = sanitize(pair.get("subquestion", ""))
                    ans = sanitize(pair.get("answer", ""))
                    full_questions_html += f'<tr><br>{subq}</td><br>{ans}</td></tr>'
                full_questions_html += '''
                        </tbody>
                    </table>
                </div>'''
                shuffle_text = "Yes" if q.get("shuffle_answers", True) else "No"
                show_num_text = "Yes" if q.get("show_num_correct", False) else "No"
                full_questions_html += f'''
                <div class="matching-settings">
                    <span><strong>Shuffle Answers:</strong> {shuffle_text}</span>
                    <span><strong>Show Number Correct:</strong> {show_num_text}</span>
                </div>'''

            hints = q.get("hints", [])
            if hints:
                full_questions_html += '<div class="hints"><h4>💡 Hints</h4>'
                for idx, hint in enumerate(hints, 1):
                    hint_text = sanitize(hint.get("text", ""))
                    clear = hint.get("clear_incorrect", False)
                    show_num = hint.get("show_num_correct", False)
                    extra = ""
                    if clear or show_num:
                        extra = '<div class="hint-options">'
                        if clear: extra += '<span class="hint-option">Clears incorrect responses</span>'
                        if show_num: extra += '<span class="hint-option">Shows number correct</span>'
                        extra += '</div>'
                    full_questions_html += f'<div class="hint"><strong>Hint {idx}:</strong> {hint_text}{extra}</div>'
                full_questions_html += '</div>'

        # Add the per‑question answer toggle button (eye icon) near the metadata toggle
        full_questions_html += f'''
            <div class="action-bar" style="display: flex; gap: 0.5rem; margin-top: 0.5rem;">
                <button class="question-answer-toggle" data-qid="{i}" onclick="toggleSingleQuestionAnswer({i})">👁️ Show Answer</button>
                <button class="metadata-toggle" onclick="toggleMetadata(this, {i})" data-question-id="{i}">
                    <span class="toggle-icon">▶</span>
                    <span class="toggle-text">Show Details</span>
                </button>
            </div>
            <div class="metadata" id="metadata-{i}">
                <h4>📋 Question Details</h4>
                <div class="metadata-grid">'''

        # Metadata fields
        if q_type == "multichoice":
            full_questions_html += f'''
                <div class="metadata-item"><span class="metadata-label">Grade:</span><span class="metadata-value">{q.get("grade", 1)}</span></div>
                <div class="metadata-item"><span class="metadata-label">Penalty:</span><span class="metadata-value">{q.get("penalty", 0)}</span></div>
                <div class="metadata-item"><span class="metadata-label">Correct Fraction:</span><span class="metadata-value">{q.get("fraction_correct", 100)}%</span></div>
                <div class="metadata-item"><span class="metadata-label">Wrong Fraction:</span><span class="metadata-value">{q.get("fraction_wrong", -20)}%</span></div>
                <div class="metadata-item"><span class="metadata-label">Options Count:</span><span class="metadata-value">{len(q.get("options", []))}</span></div>'''
        elif q_type == "truefalse":
            full_questions_html += f'''
                <div class="metadata-item"><span class="metadata-label">Grade:</span><span class="metadata-value">{q.get("grade", 1)}</span></div>
                <div class="metadata-item"><span class="metadata-label">Penalty:</span><span class="metadata-value">{q.get("penalty", 0)}</span></div>
                <div class="metadata-item"><span class="metadata-label">Correct Fraction:</span><span class="metadata-value">{q.get("fraction_correct", 100)}%</span></div>
                <div class="metadata-item"><span class="metadata-label">Wrong Fraction:</span><span class="metadata-value">{q.get("fraction_wrong", -20)}%</span></div>'''
            if q.get("feedback_true"):
                full_questions_html += f'<div class="metadata-item"><span class="metadata-label">Feedback True:</span><span class="metadata-value">{q["feedback_true"][:50]}...</span></div>'
            if q.get("feedback_false"):
                full_questions_html += f'<div class="metadata-item"><span class="metadata-label">Feedback False:</span><span class="metadata-value">{q["feedback_false"][:50]}...</span></div>'
        elif q_type == "essay":
            full_questions_html += f'''
                <div class="metadata-item"><span class="metadata-label">Grade:</span><span class="metadata-value">{q.get("grade", 1)}</span></div>
                <div class="metadata-item"><span class="metadata-label">Response Lines:</span><span class="metadata-value">{q.get("lines", 15)}</span></div>
                <div class="metadata-item"><span class="metadata-label">Attachments:</span><span class="metadata-value">{q.get("attachments", 0)}</span></div>'''
            if q.get("attachments", 0) > 0:
                max_mb = q.get("maxbytes", 2*1024*1024) // (1024*1024)
                full_questions_html += f'<div class="metadata-item"><span class="metadata-label">Max File Size:</span><span class="metadata-value">{max_mb} MB</span></div>'
            if q.get("grader_info"):
                full_questions_html += f'<div class="metadata-item"><span class="metadata-label">Grader Info:</span><span class="metadata-value">{q["grader_info"][:50]}...</span></div>'
        elif q_type == "matching":
            shuffle_text = "Yes" if q.get("shuffle_answers", True) else "No"
            show_num_text = "Yes" if q.get("show_num_correct", False) else "No"
            full_questions_html += f'''
                <div class="metadata-item"><span class="metadata-label">Grade:</span><span class="metadata-value">{q.get("grade", 1)}</span></div>
                <div class="metadata-item"><span class="metadata-label">Penalty:</span><span class="metadata-value">{q.get("penalty", 0)}</span></div>
                <div class="metadata-item"><span class="metadata-label">Shuffle Answers:</span><span class="metadata-value">{shuffle_text}</span></div>
                <div class="metadata-item"><span class="metadata-label">Show Number Correct:</span><span class="metadata-value">{show_num_text}</span></div>
                <div class="metadata-item"><span class="metadata-label">Pairs Count:</span><span class="metadata-value">{len(q.get("pairs", []))}</span></div>'''
            if q.get("hints"):
                full_questions_html += f'<div class="metadata-item"><span class="metadata-label">Hints Count:</span><span class="metadata-value">{len(q.get("hints", []))}</span></div>'

        original_no = q.get("original_question_no", q_no)
        if "original_question_no" in q and original_no != q_no:
            full_questions_html += f'<div class="metadata-item"><span class="metadata-label">Original Position:</span><span class="metadata-value">{original_no} (shuffled to {q_no})</span></div>'
        else:
            full_questions_html += f'<div class="metadata-item"><span class="metadata-label">Question No:</span><span class="metadata-value">{original_no}</span></div>'

        if shuffle_applied and q.get("group"):
            full_questions_html += f'<div class="metadata-item"><span class="metadata-label">Original Group:</span><span class="metadata-value">{q["group"]}</span></div>'

        full_questions_html += '</div></div></div>'

    if group_opened:
        full_questions_html += '</div></div>'

    # HTML template with all fixes and per‑question toggles
    html_template = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
    <title>Question Bank – Modern Export</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:ital,wght@0,300;0,400;0,500;0,600;0,700;1,400&display=swap" rel="stylesheet">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', Roboto, Helvetica, sans-serif;
            background: var(--bg-body);
            color: var(--text-primary);
            transition: background 0.3s ease, color 0.2s ease;
            padding: 2rem 1rem;
        }}
        :root {{
            --bg-body: #f4f7fc;
            --bg-container: #ffffff;
            --card-bg: #ffffff;
            --text-primary: #1e293b;
            --text-secondary: #475569;
            --border-light: #e2e8f0;
            --shadow-sm: 0 10px 25px -5px rgba(0, 0, 0, 0.05), 0 8px 10px -6px rgba(0, 0, 0, 0.02);
            --shadow-md: 0 20px 25px -5px rgba(0, 0, 0, 0.08), 0 10px 10px -5px rgba(0, 0, 0, 0.01);
            --grad-group: linear-gradient(135deg, #2c3e50, #3498db);
            --q-header-bg: #f8fafc;
            --correct-bg: #f0fdf4;
            --correct-border: #22c55e;
            --toggle-bg: #eef2ff;
            --toggle-hover: #e0e7ff;
        }}
        body.dark {{
            --bg-body: #0f172a;
            --bg-container: #1e293b;
            --card-bg: #334155;
            --text-primary: #f1f5f9;
            --text-secondary: #cbd5e1;
            --border-light: #475569;
            --shadow-sm: 0 10px 25px -5px rgba(0, 0, 0, 0.3);
            --shadow-md: 0 20px 25px -5px rgba(0, 0, 0, 0.4);
            --grad-group: linear-gradient(135deg, #1e293b, #3b82f6);
            --q-header-bg: #0f172a;
            --correct-bg: #064e3b;
            --correct-border: #10b981;
            --toggle-bg: #1e293b;
            --toggle-hover: #334155;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: var(--bg-container);
            border-radius: 2rem;
            box-shadow: var(--shadow-md);
            overflow: hidden;
            padding: 2rem 1.5rem;
        }}
        .header {{
            text-align: center;
            margin-bottom: 2rem;
            border-bottom: 2px solid var(--border-light);
            padding-bottom: 1.5rem;
        }}
        .header h1 {{
            font-size: 2.5rem;
            background: linear-gradient(120deg, #3b82f6, #8b5cf6);
            background-clip: text;
            -webkit-background-clip: text;
            color: transparent;
            margin-bottom: 0.5rem;
        }}
        .header h3 {{
            font-weight: 500;
            color: var(--text-secondary);
        }}
        .author {{
            margin-top: 0.5rem;
            font-size: 0.9rem;
            color: var(--text-secondary);
        }}
        .controls-bar {{
            display: flex;
            flex-wrap: wrap;
            justify-content: space-between;
            align-items: center;
            gap: 1rem;
            margin-bottom: 1.5rem;
            padding: 1rem;
            background: var(--q-header-bg);
            border-radius: 1.5rem;
        }}
        .search-filter {{
            display: flex;
            flex-wrap: wrap;
            gap: 0.5rem;
            align-items: center;
        }}
        .search-filter input {{
            padding: 0.5rem 1rem;
            border-radius: 2rem;
            border: 1px solid var(--border-light);
            background: var(--bg-container);
            color: var(--text-primary);
            font-size: 0.9rem;
            min-width: 200px;
        }}
        .filter-buttons {{
            display: flex;
            flex-wrap: wrap;
            gap: 0.5rem;
        }}
        .filter-btn, .action-btn {{
            background: var(--toggle-bg);
            border: none;
            padding: 0.4rem 1rem;
            border-radius: 2rem;
            cursor: pointer;
            font-size: 0.8rem;
            transition: all 0.2s;
            color: var(--text-primary);
        }}
        .filter-btn.active {{
            background: var(--primary);
            color: white;
        }}
        .filter-btn:hover, .action-btn:hover {{
            background: var(--toggle-hover);
            transform: translateY(-1px);
        }}
        .pagination {{
            display: flex;
            flex-wrap: wrap;
            justify-content: center;
            align-items: center;
            gap: 0.5rem;
            margin: 1rem 0;
        }}
        .page-btn {{
            background: var(--toggle-bg);
            border: none;
            padding: 0.3rem 0.8rem;
            border-radius: 2rem;
            cursor: pointer;
            font-size: 0.8rem;
        }}
        .page-btn.active {{
            background: var(--primary);
            color: white;
        }}
        .group {{
            margin-bottom: 2rem;
        }}
        .group-title {{
            background: var(--grad-group);
            color: white;
            padding: 0.8rem 1.5rem;
            border-radius: 3rem;
            display: flex;
            align-items: center;
            gap: 0.8rem;
            font-size: 1.4rem;
            font-weight: 600;
            margin-bottom: 1rem;
            box-shadow: var(--shadow-sm);
            cursor: pointer;
            transition: opacity 0.2s;
        }}
        .group-title:hover {{
            opacity: 0.9;
        }}
        .group-toggle-icon {{
            margin-left: auto;
            font-size: 1.2rem;
            transition: transform 0.2s;
        }}
        .group-questions.collapsed {{
            display: none;
        }}
        .question-card {{
            background: var(--card-bg);
            border-radius: 1.5rem;
            padding: 1.5rem;
            margin-bottom: 1.8rem;
            box-shadow: var(--shadow-sm);
            transition: transform 0.2s, box-shadow 0.2s;
            border: 1px solid var(--border-light);
        }}
        .question-card:hover {{
            transform: translateY(-2px);
            box-shadow: var(--shadow-md);
        }}
        .question-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 1rem;
            flex-wrap: wrap;
            gap: 0.5rem;
        }}
        .q-number {{
            background: #3b82f6;
            color: white;
            padding: 0.3rem 1rem;
            border-radius: 2rem;
            font-weight: 600;
            font-size: 0.9rem;
        }}
        .q-type {{
            background: #8b5cf6;
            color: white;
            padding: 0.3rem 1rem;
            border-radius: 2rem;
            font-weight: 600;
            font-size: 0.8rem;
            letter-spacing: 0.5px;
        }}
        .q-type.essay {{ background: #f59e0b; }}
        .q-type.truefalse {{ background: #10b981; }}
        .q-type.matching {{ background: #ec489a; }}
        .q-text {{
            font-size: 1.1rem;
            line-height: 1.5;
            margin: 1rem 0;
            white-space: pre-wrap;
        }}
        .feedback {{
            background: var(--toggle-bg);
            padding: 0.8rem;
            border-radius: 1rem;
            margin: 1rem 0;
            border-left: 4px solid #3b82f6;
            font-size: 0.9rem;
            transition: opacity 0.2s;
        }}
        .options {{
            margin: 1rem 0 0 0;
        }}
        .option {{
            background: var(--q-header-bg);
            margin: 0.6rem 0;
            padding: 0.7rem 1rem;
            border-radius: 1rem;
            border: 1px solid var(--border-light);
        }}
        .option.correct {{
            background: var(--correct-bg);
            border-left: 4px solid var(--correct-border);
        }}
        .option-content {{
            display: flex;
            align-items: center;
            gap: 0.8rem;
            flex-wrap: wrap;
        }}
        .correct-badge {{
            background: #22c55e;
            color: white;
            font-size: 0.7rem;
            padding: 0.2rem 0.6rem;
            border-radius: 1rem;
        }}
        .option-feedback {{
            margin-top: 0.5rem;
            font-size: 0.8rem;
            opacity: 0.8;
        }}
        .matching-pairs {{
            margin: 1rem 0;
        }}
        .matching-table {{
            width: 100%;
            border-collapse: collapse;
            background: var(--q-header-bg);
            border-radius: 1rem;
            overflow: hidden;
        }}
        .matching-table th, .matching-table td {{
            border: 1px solid var(--border-light);
            padding: 0.7rem;
            text-align: left;
        }}
        .matching-table th {{
            background: var(--toggle-bg);
        }}
        .matching-settings {{
            display: flex;
            gap: 1rem;
            margin: 1rem 0;
            font-size: 0.85rem;
            background: var(--toggle-bg);
            padding: 0.5rem 1rem;
            border-radius: 2rem;
        }}
        .hints {{
            background: #fef9c3;
            border-radius: 1rem;
            padding: 1rem;
            margin-top: 1rem;
        }}
        body.dark .hints {{
            background: #422006;
        }}
        .hint {{
            padding: 0.5rem;
            border-bottom: 1px dashed var(--border-light);
        }}
        .hint-options {{
            margin-top: 0.3rem;
            display: flex;
            gap: 0.5rem;
            font-size: 0.7rem;
        }}
        .hint-option {{
            background: #e2e8f0;
            padding: 0.2rem 0.5rem;
            border-radius: 1rem;
        }}
        .action-bar {{
            display: flex;
            gap: 0.5rem;
            margin-top: 0.5rem;
        }}
        .question-answer-toggle, .metadata-toggle {{
            background: none;
            border: 1px solid var(--border-light);
            padding: 0.4rem 1rem;
            border-radius: 2rem;
            cursor: pointer;
            font-size: 0.8rem;
            transition: all 0.2s;
            color: var(--text-primary);
        }}
        .question-answer-toggle:hover, .metadata-toggle:hover {{
            background: var(--toggle-bg);
        }}
        .metadata {{
            display: none;
            margin-top: 1rem;
            background: var(--q-header-bg);
            border-radius: 1rem;
            padding: 1rem;
            border-top: 2px solid #3b82f6;
        }}
        .metadata.expanded {{
            display: block;
        }}
        .metadata-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
            gap: 0.8rem;
        }}
        .metadata-label {{
            font-weight: 600;
            display: block;
            font-size: 0.7rem;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            color: var(--text-secondary);
        }}
        .show-correct-btn {{
            background: #10b981;
            color: white;
            border: none;
        }}
        .show-correct-btn.active {{
            background: #059669;
        }}
        footer {{
            text-align: center;
            margin-top: 2.5rem;
            padding-top: 1rem;
            border-top: 1px solid var(--border-light);
            color: var(--text-secondary);
            font-size: 0.8rem;
        }}
        @media (max-width: 640px) {{
            .container {{ padding: 1rem; }}
            .question-card {{ padding: 1rem; }}
            .controls-bar {{ flex-direction: column; align-items: stretch; }}
            .search-filter {{ justify-content: space-between; }}
            .action-bar {{ flex-wrap: wrap; }}
        }}
    </style>
    <script src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-chtml.js"></script>
</head>
<body>
<div class="container">
    <div class="header">
        <h1>📚 Question Bank</h1>
        <h3>Professional Assessment Export</h3>
        <div class="author">Generated by Udaya Raj Joshi — Multi-Format Converter v2.0</div>
    </div>

    <div class="controls-bar">
        <div class="search-filter">
            <input type="text" id="searchInput" placeholder="🔍 Search questions...">
            {filter_buttons_html}
        </div>
        <div class="action-buttons">
            <button class="action-btn show-correct-btn" id="globalToggleBtn">✅ Show All Answers</button>
            <button class="action-btn" id="refreshLatexBtn">⟳ Refresh LaTeX</button>
            <button class="action-btn" id="darkModeToggleBtn">🌓 Dark/Light</button>
        </div>
    </div>

    <div class="pagination" id="paginationTop"></div>
    <div id="questions-container"></div>
    <div class="pagination" id="paginationBottom"></div>

    <footer>
        <p>Converter Tool v2.0 | Designed for clarity & accessibility | LaTeX powered by MathJax</p>
    </footer>
</div>

<script>
    const fullQuestionsHTML = `{full_questions_html}`;
    let questionsPerPage = 25;
    let currentPage = 1;
    let currentFilterType = "all";
    let currentSearchTerm = "";
    let questionAnswerShown = {{}}; // tracks per‑question answer visibility

    function getAllQuestionCards() {{
        const container = document.createElement('div');
        container.innerHTML = fullQuestionsHTML;
        return Array.from(container.querySelectorAll('.question-card'));
    }}

    function filterQuestions() {{
        let allCards = getAllQuestionCards();
        let filtered = allCards;
        if (currentFilterType !== "all") {{
            filtered = filtered.filter(card => card.dataset.questionType === currentFilterType);
        }}
        if (currentSearchTerm.trim() !== "") {{
            const term = currentSearchTerm.trim().toLowerCase();
            filtered = filtered.filter(card => {{
                const text = card.querySelector('.q-text')?.innerText.toLowerCase() || "";
                return text.includes(term);
            }});
        }}
        return filtered;
    }}

    function renderPagination(filteredCount, showAll) {{
        const paginationTop = document.getElementById('paginationTop');
        const paginationBottom = document.getElementById('paginationBottom');
        const renderNav = (container) => {{
            container.innerHTML = '';
            const allBtn = document.createElement('button');
            allBtn.innerText = 'All';
            allBtn.classList.add('page-btn');
            if (showAll) allBtn.classList.add('active');
            allBtn.addEventListener('click', () => {{
                questionsPerPage = filteredCount;
                currentPage = 1;
                updateDisplay();
            }});
            container.appendChild(allBtn);
            const paginateBtn = document.createElement('button');
            paginateBtn.innerText = 'Paginate (25)';
            paginateBtn.classList.add('page-btn');
            if (!showAll && filteredCount > 25) paginateBtn.classList.add('active');
            paginateBtn.addEventListener('click', () => {{
                questionsPerPage = 25;
                currentPage = 1;
                updateDisplay();
            }});
            container.appendChild(paginateBtn);
            if (showAll || filteredCount <= questionsPerPage) return;
            const totalPages = Math.ceil(filteredCount / questionsPerPage);
            for (let i = 1; i <= totalPages; i++) {{
                const btn = document.createElement('button');
                btn.innerText = i;
                btn.classList.add('page-btn');
                if (i === currentPage) btn.classList.add('active');
                btn.addEventListener('click', () => {{
                    currentPage = i;
                    updateDisplay();
                }});
                container.appendChild(btn);
            }}
        }};
        renderNav(paginationTop);
        renderNav(paginationBottom);
    }}

    function applyQuestionAnswerStyles(qid, show) {{
        const card = document.querySelector(`.question-card[data-question-id="${{qid}}"]`);
        if (!card) return;
        const options = card.querySelectorAll('.option');
        const feedbackDiv = card.querySelector('.feedback');
        options.forEach(opt => {{
            const isCorrect = opt.getAttribute('data-correct') === 'true';
            if (show) {{
                if (isCorrect) {{
                    opt.classList.add('correct');
                    if (!opt.querySelector('.correct-badge')) {{
                        const badgeSpan = document.createElement('span');
                        badgeSpan.className = 'correct-badge';
                        badgeSpan.innerText = '✓ Correct';
                        const contentDiv = opt.querySelector('.option-content');
                        if (contentDiv) contentDiv.prepend(badgeSpan);
                    }}
                }}
            }} else {{
                opt.classList.remove('correct');
                const badge = opt.querySelector('.correct-badge');
                if (badge) badge.remove();
            }}
        }});
        if (feedbackDiv) {{
            feedbackDiv.style.display = show ? '' : 'none';
        }}
        // Update the button text
        const toggleBtn = card.querySelector('.question-answer-toggle');
        if (toggleBtn) {{
            toggleBtn.innerHTML = show ? '🙈 Hide Answer' : '👁️ Show Answer';
        }}
    }}

    function toggleSingleQuestionAnswer(qid) {{
        const current = questionAnswerShown[qid] || false;
        const newState = !current;
        questionAnswerShown[qid] = newState;
        applyQuestionAnswerStyles(qid, newState);
        // Update global button text based on whether all are hidden or any shown
        updateGlobalButtonText();
        // Also sync with global state? We don't override global, but we reflect.
    }}

    function setAllAnswers(show) {{
        const allQuestionCards = document.querySelectorAll('.question-card');
        allQuestionCards.forEach(card => {{
            const qid = parseInt(card.dataset.questionId);
            questionAnswerShown[qid] = show;
            applyQuestionAnswerStyles(qid, show);
        }});
        updateGlobalButtonText();
    }}

    function updateGlobalButtonText() {{
        const anyShown = Object.values(questionAnswerShown).some(v => v === true);
        const globalBtn = document.getElementById('globalToggleBtn');
        if (globalBtn) {{
            globalBtn.innerHTML = anyShown ? '🙈 Hide All Answers' : '✅ Show All Answers';
        }}
    }}

    function applyAllSavedStyles() {{
        for (const qid in questionAnswerShown) {{
            if (questionAnswerShown.hasOwnProperty(qid)) {{
                applyQuestionAnswerStyles(parseInt(qid), questionAnswerShown[qid]);
            }}
        }}
        updateGlobalButtonText();
    }}

    function updateDisplay() {{
        const filteredCards = filterQuestions();
        const totalFiltered = filteredCards.length;
        const showAll = (questionsPerPage >= totalFiltered);
        let startIdx = 0, endIdx = totalFiltered;
        if (!showAll) {{
            const totalPages = Math.ceil(totalFiltered / questionsPerPage);
            if (currentPage < 1) currentPage = 1;
            if (currentPage > totalPages && totalPages > 0) currentPage = totalPages;
            startIdx = (currentPage - 1) * questionsPerPage;
            endIdx = startIdx + questionsPerPage;
        }}
        const pageCards = filteredCards.slice(startIdx, endIdx);

        const tempDiv = document.createElement('div');
        tempDiv.innerHTML = fullQuestionsHTML;
        const allCards = tempDiv.querySelectorAll('.question-card');
        allCards.forEach(card => card.style.display = 'none');
        pageCards.forEach(card => {{
            const qid = card.dataset.questionId;
            const matchingCard = tempDiv.querySelector(`.question-card[data-question-id="${{qid}}"]`);
            if (matchingCard) matchingCard.style.display = '';
        }});
        const groups = tempDiv.querySelectorAll('.group');
        groups.forEach(group => {{
            const visibleQuestions = group.querySelectorAll('.question-card[style="display: block;"], .question-card:not([style*="display: none"])');
            if (visibleQuestions.length === 0) {{
                group.style.display = 'none';
            }} else {{
                group.style.display = '';
            }}
        }});
        const container = document.getElementById('questions-container');
        container.innerHTML = '';
        while (tempDiv.firstChild) container.appendChild(tempDiv.firstChild);

        // Re‑apply saved per‑question answer states
        applyAllSavedStyles();
        attachGroupCollapsible();

        renderPagination(totalFiltered, showAll);
        if (window.MathJax) MathJax.typesetPromise();
    }}

    function attachGroupCollapsible() {{
        document.querySelectorAll('.group-title').forEach(title => {{
            title.removeEventListener('click', toggleGroup);
            title.addEventListener('click', toggleGroup);
        }});
    }}
    function toggleGroup(e) {{
        const groupDiv = e.currentTarget.closest('.group');
        const questionsDiv = groupDiv.querySelector('.group-questions');
        const iconSpan = e.currentTarget.querySelector('.group-toggle-icon');
        if (questionsDiv) {{
            questionsDiv.classList.toggle('collapsed');
            if (iconSpan) iconSpan.innerHTML = questionsDiv.classList.contains('collapsed') ? '▶' : '▼';
        }}
    }}

    window.toggleMetadata = function(btn, qid) {{
        const meta = document.getElementById('metadata-'+qid);
        const icon = btn.querySelector('.toggle-icon');
        const textSpan = btn.querySelector('.toggle-text');
        if (meta.classList.contains('expanded')) {{
            meta.classList.remove('expanded');
            icon.innerText = '▶';
            textSpan.innerText = 'Show Details';
        }} else {{
            meta.classList.add('expanded');
            icon.innerText = '▼';
            textSpan.innerText = 'Hide Details';
        }}
    }};

    function resetPaginationAndFilter() {{
        questionsPerPage = 25;
        currentPage = 1;
        updateDisplay();
    }}

    document.getElementById('searchInput').addEventListener('input', (e) => {{
        currentSearchTerm = e.target.value;
        resetPaginationAndFilter();
    }});
    document.querySelectorAll('.filter-btn').forEach(btn => {{
        btn.addEventListener('click', () => {{
            document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            currentFilterType = btn.dataset.type;
            resetPaginationAndFilter();
        }});
    }});
    document.getElementById('globalToggleBtn').addEventListener('click', () => {{
        const anyShown = Object.values(questionAnswerShown).some(v => v === true);
        setAllAnswers(!anyShown);
    }});
    document.getElementById('refreshLatexBtn').addEventListener('click', () => {{
        if (window.MathJax) MathJax.typesetPromise();
    }});
    document.getElementById('darkModeToggleBtn').addEventListener('click', () => {{
        document.body.classList.toggle('dark');
        localStorage.setItem('darkMode', document.body.classList.contains('dark'));
    }});
    if (localStorage.getItem('darkMode') === 'true') {{
        document.body.classList.add('dark');
    }}

    // Initialize per‑question states (all hidden)
    const allQuestionsCount = {len(questions)};
    for (let i = 1; i <= allQuestionsCount; i++) {{
        questionAnswerShown[i] = false;
    }}
    updateDisplay();
</script>
</body>
</html>"""

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html_template)

    log(f"Enhanced HTML file created: {output_file}", "SUCCESS", verbose)
