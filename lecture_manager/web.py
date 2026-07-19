# web.py

import os
from flask import Flask, render_template, request, redirect, url_for, flash, send_file, jsonify
from .db import get_connection, TABLE_NAME, get_record_by_video_id
from .file_manager import (
    get_target_path,
    organize_video,
    sync_record_files,
    get_tally_data,
    trash_video_by_record,
    collect_facebook_tally_data
)
from .facebook_manager import list_facebook_entries, get_facebook_entry_by_id, delete_facebook_entry, get_facebook_file_path
from .youtube import fetch_youtube_title
from .file_manager import collect_tally_data
from .question_bank import (
    get_all_questions,
    get_question_by_id,
    get_questions_by_criteria,
    add_question,
    update_question,
    delete_question
)

# ===== PLAYBACK CONFIGURATION =====
PLAYBACK_SOURCE = 'mirror_only'   # Change this to your preference
# ==================================

template_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'templates')
app = Flask(__name__, template_folder=template_dir)
app.secret_key = os.urandom(24)

def get_tally_data():
    """Return tally data using hash‑based matching (same as CLI)."""
    from .file_manager import collect_tally_data
    data = collect_tally_data()

    # Convert to the format expected by the web template
    return {
        'total_records': len(data['records']),
        'matched': len(data['correctly_placed']),
        'missing': len(data['missing']),
        'missing_list': data['missing'],
        'orphan': len(data['orphan']),
        'orphan_list': data['orphan'],
        'mismatched': len(data['mismatched']),
        'mismatched_list': [
            {'record': rec, 'files': [fp for fp, v in data['file_to_vid'].items() if v == rec['video_id']]}
            for rec in data['mismatched']
        ],
    }

def get_all_youtube_records():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(f"SELECT * FROM {TABLE_NAME} ORDER BY nepali_date DESC, time DESC")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return rows

@app.route('/lecture/upload/<int:id>', methods=['POST'])
def upload_to_youtube_web(id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(f"SELECT * FROM {TABLE_NAME} WHERE id = %s", (id,))
    record = cursor.fetchone()
    cursor.close()
    conn.close()
    if not record:
        flash('Record not found', 'danger')
        return redirect(url_for('lecture_detail', id=id))

    from .upload import upload_video_to_youtube
    success, msg, vid = upload_video_to_youtube(record)
    if success:
        flash(msg, 'success')
    else:
        flash(msg, 'danger')
    return redirect(url_for('lecture_detail', id=id))

# ---------- YouTube routes ----------
@app.route('/')
def index():
    # Get YouTube tally using hash-based matching
    yt_tally = collect_tally_data()
    total_yt = len(yt_tally['records'])
    missing_yt = len(yt_tally['missing'])
    orphan_yt = len(yt_tally['orphan'])

    # Get Facebook stats
    fb_stats = collect_facebook_tally_data()
    total_fb = fb_stats['total_entries']
    missing_fb = len(fb_stats['missing'])
    orphan_fb = len(fb_stats['orphan'])

    return render_template('index.html',
                           total_yt=total_yt,
                           missing_yt=missing_yt,
                           total_fb=total_fb,
                           missing_fb=missing_fb,
                           orphan_fb=orphan_fb,
                           orphan_yt=orphan_yt,       # pass orphan count
                           tally=yt_tally,            # for backward compatibility with template
                           playback_config=PLAYBACK_SOURCE)

@app.route('/lectures')
def lectures():
    search = request.args.get('search', '')
    sort_by = request.args.get('sort', 'nepali_date')
    order = request.args.get('order', 'desc')
    records = get_all_youtube_records()
    if search:
        search_lower = search.lower()
        records = [r for r in records if
                   search_lower in (r.get('syllabus_id') or '').lower() or
                   search_lower in (r.get('subject') or '').lower() or
                   search_lower in (r.get('chapter') or '').lower() or
                   search_lower in (r.get('lecturer') or '').lower() or
                   search_lower in (r.get('video_id') or '').lower()]
    reverse = (order == 'desc')
    if sort_by == 'syllabus_id':
        records.sort(key=lambda x: x.get('syllabus_id') or '', reverse=reverse)
    elif sort_by == 'subject':
        records.sort(key=lambda x: x.get('subject') or '', reverse=reverse)
    elif sort_by == 'lecturer':
        records.sort(key=lambda x: x.get('lecturer') or '', reverse=reverse)
    elif sort_by == 'nepali_date':
        records.sort(key=lambda x: x.get('nepali_date') or '', reverse=reverse)
    elif sort_by == 'time':
        records.sort(key=lambda x: x.get('time') or '', reverse=reverse)
    else:
        records.sort(key=lambda x: x.get('nepali_date') or '', reverse=True)
    return render_template('lectures.html', records=records, search=search, sort_by=sort_by, order=order)

@app.route('/lecture/<int:id>')
def lecture_detail(id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(f"SELECT * FROM {TABLE_NAME} WHERE id = %s", (id,))
    record = cursor.fetchone()
    cursor.close()
    conn.close()
    if not record:
        flash('Record not found', 'danger')
        return redirect(url_for('lectures'))

    mirror_id = record.get('mirror_video_id')
    original_id = record['video_id']

    using_mirror = False
    embed_vid = None
    config_status = None

    if PLAYBACK_SOURCE == 'mirror_only':
        if mirror_id:
            embed_vid = mirror_id
            using_mirror = True
            config_status = 'ok'
        else:
            embed_vid = None
            config_status = 'missing_mirror'
    elif PLAYBACK_SOURCE == 'original_only':
        embed_vid = original_id
        using_mirror = False
        config_status = 'ok'
    else:  # prefer_mirror
        if mirror_id:
            embed_vid = mirror_id
            using_mirror = True
            config_status = 'ok'
        else:
            embed_vid = original_id
            using_mirror = False
            config_status = 'using_original'

    embed_url = f"https://www.youtube.com/embed/{embed_vid}" if embed_vid else None

    return render_template('detail.html',
                           record=record,
                           embed_url=embed_url,
                           embed_vid=embed_vid,
                           using_mirror=using_mirror,
                           config_status=config_status,
                           playback_config=PLAYBACK_SOURCE)

@app.route('/lecture/add', methods=['GET', 'POST'])
def add_lecture_web():
    if request.method == 'POST':
        video_id = request.form.get('video_id')
        if not video_id:
            flash('Video ID is required', 'danger')
            return redirect(url_for('add_lecture_web'))
        title = fetch_youtube_title(video_id) or ''
        syllabus_id = request.form.get('syllabus_id')
        subject = request.form.get('subject')
        chapter = request.form.get('chapter')
        lecturer = request.form.get('lecturer')
        nepali_date = request.form.get('nepali_date')
        time_str = request.form.get('time')
        mirror_id = request.form.get('mirror_id') or None
        notes = request.form.get('notes') or None

        conn = get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(f"""
                INSERT INTO {TABLE_NAME}
                (video_id, mirror_video_id, video_title, syllabus_id, subject, chapter, lecturer, nepali_date, time, notes)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (video_id, mirror_id, title, syllabus_id, subject, chapter, lecturer, nepali_date, time_str, notes))
            conn.commit()
            flash('Lecture added successfully!', 'success')
        except Exception as e:
            flash(f'Error: {e}', 'danger')
        finally:
            cursor.close()
            conn.close()
        return redirect(url_for('lectures'))
    return render_template('add_edit.html', record=None, title='Add Lecture')

@app.route('/lecture/edit/<int:id>', methods=['GET', 'POST'])
def edit_lecture_web(id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(f"SELECT * FROM {TABLE_NAME} WHERE id = %s", (id,))
    record = cursor.fetchone()
    cursor.close()
    conn.close()
    if not record:
        flash('Record not found', 'danger')
        return redirect(url_for('lectures'))
    if request.method == 'POST':
        video_id = request.form.get('video_id')
        if not video_id:
            flash('Video ID is required', 'danger')
            return redirect(url_for('edit_lecture_web', id=id))
        syllabus_id = request.form.get('syllabus_id')
        subject = request.form.get('subject')
        chapter = request.form.get('chapter')
        lecturer = request.form.get('lecturer')
        nepali_date = request.form.get('nepali_date')
        time_str = request.form.get('time')
        mirror_id = request.form.get('mirror_id') or None
        notes = request.form.get('notes') or None

        if video_id != record['video_id']:
            new_title = fetch_youtube_title(video_id)
        else:
            new_title = record['video_title']

        conn = get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(f"""
                UPDATE {TABLE_NAME}
                SET video_id = %s, mirror_video_id = %s, video_title = %s,
                    syllabus_id = %s, subject = %s, chapter = %s,
                    lecturer = %s, nepali_date = %s, time = %s, notes = %s
                WHERE id = %s
            """, (video_id, mirror_id, new_title, syllabus_id, subject, chapter,
                  lecturer, nepali_date, time_str, notes, id))
            conn.commit()
            flash('Lecture updated successfully!', 'success')
            updated_record = get_record_by_video_id(video_id)
            if updated_record:
                sync_record_files(updated_record, record.get('syllabus_id'), record.get('video_id'), record)
        except Exception as e:
            flash(f'Error: {e}', 'danger')
        finally:
            cursor.close()
            conn.close()
        return redirect(url_for('lecture_detail', id=id))
    return render_template('add_edit.html', record=record, title='Edit Lecture')

@app.route('/lecture/delete/<int:id>', methods=['POST'])
def delete_lecture_web(id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(f"SELECT * FROM {TABLE_NAME} WHERE id = %s", (id,))
    record = cursor.fetchone()
    cursor.close()
    if not record:
        flash('Record not found', 'danger')
        return redirect(url_for('lectures'))
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(f"DELETE FROM {TABLE_NAME} WHERE id = %s", (id,))
        conn.commit()
        flash('Record deleted successfully', 'success')
    except Exception as e:
        flash(f'Error: {e}', 'danger')
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for('lectures'))

@app.route('/organize/<int:id>', methods=['POST'])
def organize_lecture(id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(f"SELECT * FROM {TABLE_NAME} WHERE id = %s", (id,))
    record = cursor.fetchone()
    cursor.close()
    conn.close()
    if not record:
        flash('Record not found', 'danger')
        return redirect(url_for('lectures'))
    result = organize_video(record)
    if result:
        flash(f'Video organized to {result}', 'success')
    else:
        flash('Failed to organize video. Check if file exists.', 'warning')
    return redirect(url_for('lecture_detail', id=id))

@app.route('/trash/<int:id>', methods=['POST'])
def trash_lecture(id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(f"SELECT * FROM {TABLE_NAME} WHERE id = %s", (id,))
    record = cursor.fetchone()
    cursor.close()
    conn.close()
    if not record:
        flash('Record not found', 'danger')
        return redirect(url_for('lectures'))
    result = trash_video_by_record(record)
    if result:
        flash('Video moved to trash', 'success')
    else:
        flash('Failed to move video to trash', 'warning')
    return redirect(url_for('lecture_detail', id=id))

@app.route('/tally')
def tally():
    tally_data = collect_tally_data()
    tally_data = get_tally_data()
    return render_template('tally.html', tally=tally_data)

@app.route('/stream/<int:id>')
def stream_video(id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(f"SELECT * FROM {TABLE_NAME} WHERE id = %s", (id,))
    record = cursor.fetchone()
    cursor.close()
    conn.close()

    if not record:
        flash('Record not found', 'danger')
        return redirect(url_for('index'))

    # Determine which video to use (original or mirror)
    mirror_id = record.get('mirror_video_id')
    original_id = record['video_id']

    # Check if mirror is available and should be used
    use_mirror = False
    video_id_to_play = original_id

    if PLAYBACK_SOURCE == 'mirror_only' and mirror_id:
        video_id_to_play = mirror_id
        use_mirror = True
    elif PLAYBACK_SOURCE == 'prefer_mirror' and mirror_id:
        video_id_to_play = mirror_id
        use_mirror = True
    elif PLAYBACK_SOURCE == 'original_only':
        video_id_to_play = original_id

    # ---- Locate the file using the chosen video ID ----
    # We need to find the file based on the video ID we want to play.
    # Since files are stored by hash, we need to look up the file_hash for that video ID.
    # If we're using the mirror, but the mirror hasn't been downloaded, fallback to original.
    target_dir, filename_base = get_target_path(record, interactive=False)

    # Try to find the file using the record's file_hash (original)
    file_path = None
    file_hash = record.get('file_hash')
    if file_hash and target_dir:
        import glob
        pattern = os.path.join(target_dir, file_hash + '.*')
        matches = glob.glob(pattern)
        if matches:
            file_path = matches[0]

    # If using mirror and file not found, try original
    if use_mirror and not file_path:
        # Try to find the original video
        original_file_hash = record.get('file_hash')  # This is the original's hash
        if original_file_hash and target_dir:
            pattern = os.path.join(target_dir, original_file_hash + '.*')
            matches = glob.glob(pattern)
            if matches:
                file_path = matches[0]
                print(f"[INFO] Mirror file not found, falling back to original for {record['video_id']}")

    # If still not found, search entire ROOT_DIR
    if not file_path:
        from .file_manager import ROOT_DIR
        for root, _, files in os.walk(ROOT_DIR):
            for f in files:
                if f.startswith(file_hash) and f.lower().endswith(('.mp4', '.mkv', '.webm', '.avi', '.mov')):
                    file_path = os.path.join(root, f)
                    break
            if file_path:
                break

    if not file_path or not os.path.exists(file_path):
        flash('Video file not found on disk.', 'warning')
        return redirect(url_for('lecture_detail', id=id))

    return send_file(file_path, as_attachment=False)

@app.route('/stream_facebook_file/<int:id>')
def stream_facebook_file(id):
    """Serve a Facebook file (video or photo) by its entry ID."""
    record = get_facebook_entry_by_id(id)
    if not record:
        flash('Entry not found', 'danger')
        return redirect(url_for('facebook_entries'))
    file_path = get_facebook_file_path(record)
    if not file_path or not os.path.exists(file_path):
        flash('File not found on disk.', 'warning')
        return redirect(url_for('facebook_detail', id=id))
    return send_file(file_path, as_attachment=False)

# ---------- Facebook routes ----------
@app.route('/facebook')
def facebook_entries():
    search = request.args.get('search', '')
    sort_by = request.args.get('sort', 'download_date')
    order = request.args.get('order', 'desc')
    records = list_facebook_entries()
    if search:
        search_lower = search.lower()
        records = [r for r in records if
                   search_lower in (r.get('title') or '').lower() or
                   search_lower in (r.get('uploader') or '').lower() or
                   search_lower in (r.get('facebook_id') or '').lower()]
    reverse = (order == 'desc')
    if sort_by == 'title':
        records.sort(key=lambda x: x.get('title') or '', reverse=reverse)
    elif sort_by == 'uploader':
        records.sort(key=lambda x: x.get('uploader') or '', reverse=reverse)
    elif sort_by == 'type':
        records.sort(key=lambda x: x.get('type') or '', reverse=reverse)
    elif sort_by == 'download_date':
        records.sort(key=lambda x: x.get('download_date') or '', reverse=reverse)
    else:
        records.sort(key=lambda x: x.get('download_date') or '', reverse=True)
    return render_template('facebook_entries.html', records=records, search=search, sort_by=sort_by, order=order)

@app.route('/facebook/<int:id>')
def facebook_detail(id):
    record = get_facebook_entry_by_id(id)
    if not record:
        flash('Entry not found', 'danger')
        return redirect(url_for('facebook_entries'))
    file_path = get_facebook_file_path(record)
    return render_template('facebook_detail.html', record=record, file_path=file_path)

@app.route('/facebook/delete/<int:id>', methods=['POST'])
def facebook_delete(id):
    record = get_facebook_entry_by_id(id)
    if not record:
        flash('Entry not found', 'danger')
        return redirect(url_for('facebook_entries'))
    # Delete file if exists
    file_path = get_facebook_file_path(record)
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
            flash(f'File {os.path.basename(file_path)} deleted', 'success')
        except Exception as e:
            flash(f'Failed to delete file: {e}', 'danger')
    if delete_facebook_entry(id):
        flash('Entry deleted successfully', 'success')
    else:
        flash('Failed to delete entry', 'danger')
    return redirect(url_for('facebook_entries'))

# ---------- Question Bank Routes ----------

@app.route('/questions')
def question_list():
    search = request.args.get('search', '')
    sort_by = request.args.get('sort', 'question_date')
    order = request.args.get('order', 'desc')

    if search:
        rows = get_all_questions(search=search)
    else:
        rows = get_all_questions(sort_by=sort_by, order=order.upper())

    return render_template('questions.html',
                           questions=rows,
                           search=search,
                           sort_by=sort_by,
                           order=order)

@app.route('/question/<int:id>')
def question_detail(id):
    q = get_question_by_id(id)
    if not q:
        flash('Question not found', 'danger')
        return redirect(url_for('question_list'))
    return render_template('question_detail.html', question=q)

@app.route('/question/paper')
def question_paper():
    date = request.args.get('date', '')
    institution = request.args.get('institution', '')
    level = request.args.get('level', '')
    paper = request.args.get('paper', '')

    if not any([date, institution, level, paper]):
        return render_template('paper_form.html')

    results = get_questions_by_criteria(date=date, institution=institution,
                                        level=level, paper=paper)
    if not results:
        flash('No questions found for this paper.', 'warning')
        return render_template('paper_form.html', date=date, institution=institution,
                               level=level, paper=paper)

    from collections import defaultdict
    grouped = defaultdict(lambda: defaultdict(list))
    for q in results:
        grp = q.get('group', 'General')
        subj = q.get('subject', '')
        grouped[grp][subj].append(q)

    return render_template('question_paper.html',
                           grouped=grouped,
                           date=date,
                           institution=institution,
                           level=level,
                           paper=paper)

@app.route('/question/suggestions')
def question_suggestions():
    """Return JSON suggestions for autocomplete, ranked by relevance."""
    query = request.args.get('q', '').strip()
    if len(query) < 2:
        return jsonify([])

    rows = get_all_questions(search=query)
    suggestions_set = set()
    for row in rows:
        if row.get('question_date'):
            suggestions_set.add(str(row['question_date']))
        for field in ['institution', 'subject', 'paper', 'level', 'chapter', 'question_number']:
            val = row.get(field)
            if val:
                suggestions_set.add(str(val))

    query_lower = query.lower()

    # Rank: exact/startswith first, then contains, then others (if any)
    def relevance_score(s):
        s_lower = s.lower()
        if s_lower.startswith(query_lower):
            return (0, s_lower)          # first priority
        elif query_lower in s_lower:
            return (1, s_lower)          # second priority
        else:
            return (2, s_lower)          # last (shouldn't happen often)

    suggestions = sorted(suggestions_set, key=relevance_score)[:10]
    return jsonify(suggestions)

@app.route('/questions/browse')
def browse_chapters():
    """List all chapters with question counts."""
    from .question_bank import get_distinct_chapters, get_questions_by_chapter
    chapters = get_distinct_chapters()
    chapter_data = []
    for ch in chapters:
        qs = get_questions_by_chapter(ch)
        chapter_data.append({
            'name': ch,
            'count': len(qs),
            'subject': qs[0]['subject'] if qs else '',
            'paper': qs[0]['paper'] if qs else '',
            'group': qs[0]['group'] if qs else '',
        })
    return render_template('browse_chapters.html', chapters=chapter_data)

@app.route('/questions/chapter/<path:chapter_code>')
def questions_by_chapter(chapter_code):
    """Show all questions for a specific chapter."""
    from .question_bank import get_questions_by_chapter
    questions = get_questions_by_chapter(chapter_code)
    if not questions:
        flash('No questions found for this chapter.', 'warning')
        return redirect(url_for('browse_chapters'))
    # Group by subject -> group
    grouped = {}
    for q in questions:
        subject = q.get('subject', 'Unknown')
        group = q.get('group', 'General')
        grouped.setdefault(subject, {}).setdefault(group, []).append(q)
    return render_template('questions_by_chapter.html',
                           questions=questions,
                           grouped=grouped,
                           chapter_code=chapter_code)

def run_web_server(host='127.0.0.1', port=5000):
    app.run(host=host, port=port, debug=False, threaded=True)
