# lecture_manager/syllabus_config.py
"""
User-configurable papers and subjects.
All reads happen through get_papers() / get_subjects(), which pull from the DB.
Hardcoded templates in DEFAULT_PAPER_TEMPLATE exist only as optional seeds.
"""
from .db import get_connection
from .utils import print_colored, color_text, COLORS

def _fmt_size(nbytes):
    """Human-readable file size."""
    if nbytes < 1024:
        return f"{nbytes} B"
    if nbytes < 1024 * 1024:
        return f"{nbytes/1024:.1f} KB"
    return f"{nbytes/(1024*1024):.2f} MB"

# ---------- SYLLABI ----------
def get_syllabi(active_only=True):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    sql = "SELECT * FROM syllabi"
    if active_only:
        sql += " WHERE active = 1"
    sql += " ORDER BY display_order, display_name"
    cursor.execute(sql)
    rows = cursor.fetchall()
    cursor.close(); conn.close()
    return rows


def get_syllabus(syllabus_key):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM syllabi WHERE syllabus_key = %s", (syllabus_key,))
    row = cursor.fetchone()
    cursor.close(); conn.close()
    return row


def add_syllabus(syllabus_key, display_name, level=None, description=None):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT COALESCE(MAX(display_order), 0) FROM syllabi")
        next_order = (cursor.fetchone()[0] or 0) + 10
        cursor.execute("""
            INSERT INTO syllabi (syllabus_key, display_name, level, description, display_order)
            VALUES (%s, %s, %s, %s, %s)
        """, (syllabus_key, display_name, level, description, next_order))
        conn.commit()
        return cursor.lastrowid
    except Exception as e:
        print_colored(f"[!] Could not add syllabus: {e}", COLORS.RED)
        return None
    finally:
        cursor.close(); conn.close()


def update_syllabus(syllabus_id, **fields):
    allowed = {'display_name', 'level', 'description', 'active', 'display_order', 'syllabus_key'}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return False
    sets = ", ".join(f"{k} = %s" for k in updates)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(f"UPDATE syllabi SET {sets} WHERE id = %s",
                   (*updates.values(), syllabus_id))
    conn.commit()
    ok = cursor.rowcount > 0
    cursor.close(); conn.close()
    return ok


def delete_syllabus(syllabus_id, cascade_papers=False):
    """Delete a syllabus. If cascade_papers is True, also delete its papers
    and (transitively) their subjects and chapters."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM papers WHERE syllabus_id = %s", (syllabus_id,))
    paper_ids = [r[0] for r in cursor.fetchall()]

    if paper_ids and not cascade_papers:
        cursor.close(); conn.close()
        raise ValueError(
            f"Syllabus has {len(paper_ids)} paper(s). "
            f"Pass cascade_papers=True to delete them too."
        )

    if cascade_papers and paper_ids:
        placeholders = ",".join(["%s"] * len(paper_ids))
        cursor.execute(f"""
            DELETE FROM subjects
            WHERE paper IN (
                SELECT paper_key FROM papers WHERE id IN ({placeholders})
            )
        """, paper_ids)
        cursor.execute(f"DELETE FROM papers WHERE id IN ({placeholders})", paper_ids)

    cursor.execute("DELETE FROM syllabi WHERE id = %s", (syllabus_id,))
    conn.commit()
    ok = cursor.rowcount > 0
    cursor.close(); conn.close()
    return ok

# ---------- READ ----------
def get_papers(active_only=True, syllabus_id=None):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    conditions = []
    params = []
    if active_only:
        conditions.append("active = 1")
    if syllabus_id is not None:
        conditions.append("syllabus_id = %s")
        params.append(syllabus_id)
    sql = "SELECT * FROM papers"
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY display_order, display_name"
    cursor.execute(sql, params)
    rows = cursor.fetchall()
    cursor.close(); conn.close()
    return rows

def get_subjects(paper_key=None, active_only=True):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    sql = "SELECT * FROM subjects WHERE 1=1"
    params = []
    if active_only:
        sql += " AND active = 1"
    if paper_key:
        sql += " AND paper = %s"
        params.append(paper_key)
        # When filtered to one paper, order by code then name
        sql += " ORDER BY chapter, name"
    else:
        # All papers: order by paper, then code, then name
        sql += " ORDER BY paper, chapter, name"
    cursor.execute(sql, params)
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return rows

def is_configured():
    """True if the user has at least one paper and one subject."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM papers")
    p = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM subjects WHERE active = 1")
    s = cursor.fetchone()[0]
    cursor.close()
    conn.close()
    return p > 0 and s > 0

# ---------- CHAPTERS ----------
def get_subject_by_paper_and_code(paper_key, subject_code):
    """Return the subject row for (paper_key, chapter column holding the code)."""
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT * FROM subjects
        WHERE paper = %s AND chapter = %s AND active = 1
        LIMIT 1
    """, (paper_key, str(subject_code).zfill(2)))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return row


def get_chapters(subject_id=None, active_only=True):
    """Return chapters, optionally filtered by subject_id."""
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    sql = "SELECT * FROM chapters WHERE 1=1"
    params = []
    if active_only:
        sql += " AND active = 1"
    if subject_id is not None:
        sql += " AND subject_id = %s"
        params.append(subject_id)
    sql += " ORDER BY display_order, chapter_code"
    cursor.execute(sql, params)
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return rows

# ---------- WRITE ----------
def add_paper(paper_key, display_name, folder_name, keywords="", syllabus_id=None):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    # Warn if another paper already uses this folder name
    cursor.execute(
        "SELECT paper_key, display_name FROM papers WHERE folder_name = %s",
        (folder_name,),
    )
    collisions = cursor.fetchall()
    if collisions:
        print_colored(
            f"[!] Folder name '{folder_name}' is already used by:",
            COLORS.YELLOW,
        )
        for c in collisions:
            print(f"     - [{c['paper_key']}] {c['display_name']}")
        ans = input(color_text("  Continue anyway? (y/n): ", COLORS.MAGENTA)).strip().lower()
        if ans != 'y':
            cursor.close()
            conn.close()
            print_colored("Cancelled.", COLORS.YELLOW)
            return None

    try:
        cursor.execute("SELECT COALESCE(MAX(display_order), 0) AS max_order FROM papers")
        row = cursor.fetchone()
        next_order = ((row or {}).get('max_order') or 0) + 10
        cursor.execute("""
            INSERT INTO papers
                (paper_key, display_name, folder_name, keywords, display_order, syllabus_id)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (paper_key, display_name, folder_name, keywords, next_order, syllabus_id))
        conn.commit()
        return cursor.lastrowid
    except Exception as e:
        print_colored(f"[!] Could not add paper: {e}", COLORS.RED)
        return None
    finally:
        cursor.close()
        conn.close()

def update_paper(paper_id, **fields):
    allowed = {'display_name', 'folder_name', 'keywords', 'active',
               'display_order', 'syllabus_id'}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return False
    sets = ", ".join(f"{k} = %s" for k in updates)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(f"UPDATE papers SET {sets} WHERE id = %s",
                   (*updates.values(), paper_id))
    conn.commit()
    ok = cursor.rowcount > 0
    cursor.close(); conn.close()
    return ok

def clear_syllabus(syllabus_id):
    """Delete all papers (and their subjects/chapters) under one syllabus."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT paper_key FROM papers WHERE syllabus_id = %s",
                   (syllabus_id,))
    keys = [r[0] for r in cursor.fetchall()]
    if keys:
        placeholders = ",".join(["%s"] * len(keys))
        cursor.execute(f"DELETE FROM subjects WHERE paper IN ({placeholders})", keys)
        cursor.execute(f"DELETE FROM papers WHERE paper_key IN ({placeholders})", keys)
    conn.commit()
    cursor.close(); conn.close()

def delete_paper(paper_id, cascade_subjects=False):
    conn = get_connection()
    cursor = conn.cursor()
    if cascade_subjects:
        cursor.execute("DELETE FROM subjects WHERE paper = (SELECT paper_key FROM papers WHERE id = %s)", (paper_id,))
    cursor.execute("DELETE FROM papers WHERE id = %s", (paper_id,))
    conn.commit()
    ok = cursor.rowcount > 0
    cursor.close(); conn.close()
    return ok

def add_chapter(subject_id, chapter_code, name, description=None, display_order=None):
    """Insert a chapter under a subject. Returns chapter id or None."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        if display_order is None:
            cursor.execute("SELECT COALESCE(MAX(display_order), 0) FROM chapters WHERE subject_id = %s",
                           (subject_id,))
            display_order = (cursor.fetchone()[0] or 0) + 10
        code = str(chapter_code).zfill(2)
        cursor.execute("""
            INSERT INTO chapters (subject_id, chapter_code, name, description, display_order)
            VALUES (%s, %s, %s, %s, %s)
        """, (subject_id, code, name, description, display_order))
        conn.commit()
        return cursor.lastrowid
    except Exception as e:
        print_colored(f"[!] Could not add chapter: {e}", COLORS.RED)
        return None
    finally:
        cursor.close(); conn.close()


def update_chapter(chapter_id, **fields):
    allowed = {'name', 'description', 'chapter_code', 'active', 'display_order'}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return False
    if 'chapter_code' in updates:
        updates['chapter_code'] = str(updates['chapter_code']).zfill(2)
    sets = ", ".join(f"{k} = %s" for k in updates)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(f"UPDATE chapters SET {sets} WHERE id = %s",
                   (*updates.values(), chapter_id))
    conn.commit()
    ok = cursor.rowcount > 0
    cursor.close(); conn.close()
    return ok


def delete_chapter(chapter_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM chapters WHERE id = %s", (chapter_id,))
    conn.commit()
    ok = cursor.rowcount > 0
    cursor.close(); conn.close()
    return ok

def add_subject(name, paper_key, chapter=None):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO subjects (name, paper, chapter, active)
            VALUES (%s, %s, %s, 1)
        """, (name, paper_key, chapter))
        conn.commit()
        return cursor.lastrowid
    except Exception as e:
        print_colored(f"[!] Could not add subject: {e}", COLORS.RED)
        return None
    finally:
        cursor.close(); conn.close()


def update_subject(subject_id, **fields):
    allowed = {'name', 'paper', 'chapter', 'active'}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return False
    sets = ", ".join(f"{k} = %s" for k in updates)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(f"UPDATE subjects SET {sets} WHERE id = %s",
                   (*updates.values(), subject_id))
    conn.commit()
    ok = cursor.rowcount > 0
    cursor.close(); conn.close()
    return ok


def delete_subject(subject_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM subjects WHERE id = %s", (subject_id,))
    conn.commit()
    ok = cursor.rowcount > 0
    cursor.close(); conn.close()
    return ok

def clear_all():
    """
    Wipe papers + subjects + chapters.

    chapters has a FK to subjects with ON DELETE CASCADE, so deleting
    subjects alone would work — we delete chapters explicitly anyway
    so the intent is clear and we don't depend on the FK.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM chapters")
    cursor.execute("DELETE FROM subjects")
    cursor.execute("DELETE FROM papers")
    conn.commit()
    cursor.close()
    conn.close()

# ---------- SEED (optional) ----------
# Intentionally empty. New users start with a clean slate.
# To ship a shared syllabus, either edit this dict OR use export/import JSON.
DEFAULT_PAPER_TEMPLATE = {}


def seed_from_default_template():
    """Populate papers+subjects from the bundled template (if any)."""
    if not DEFAULT_PAPER_TEMPLATE:
        print_colored("[i] No bundled template — nothing to load.", COLORS.YELLOW)
        return
    for key, cfg in DEFAULT_PAPER_TEMPLATE.items():
        pid = add_paper(key, cfg["display_name"], cfg["folder_name"], cfg.get("keywords", ""))
        if pid:
            for code, name in cfg["subjects"].items():
                add_subject(name, key, chapter=code)
    print_colored("[✓] Template loaded.", COLORS.GREEN)


# ---------- EXPORT / IMPORT ----------
def export_syllabus(filepath, syllabus_id=None, verbose=True):
    """
    Write papers + subjects + chapters to JSON (v3).
    If `syllabus_id` is given, export just that syllabus. Otherwise all.

    Returns True on success (kept for backwards compatibility).
    """
    import json
    import os
    import time
    from datetime import datetime

    t0 = time.time()

    if syllabus_id is not None:
        syllabi = [s for s in get_syllabi(active_only=False)
                   if s['id'] == syllabus_id]
        scope_label = "Current syllabus"
    else:
        syllabi = get_syllabi(active_only=False)
        scope_label = "All syllabi"

    if not syllabi:
        if verbose:
            print_colored("[i] Nothing to export — no syllabi configured.",
                          COLORS.YELLOW)
        return True

    # ---------- banner ----------
    if verbose:
        print()
        print_colored("═" * 64, COLORS.CYAN)
        print_colored("  📤  EXPORT SYLLABUS", COLORS.CYAN, bold=True)
        print_colored("═" * 64, COLORS.CYAN)
        print()
        print(f"  Scope : {scope_label}")
        print(f"  File  : {filepath}")
        print()
        print_colored("  📋  Contents", COLORS.CYAN, bold=True)
        print_colored("  " + "─" * 60, COLORS.CYAN)

    # ---------- build payload ----------
    data = {
        "version": 3,
        "exported_at": datetime.now().isoformat(),
        "syllabi": [],
    }

    total_papers = 0
    total_subjects = 0
    total_chapters = 0

    for syl in syllabi:
        papers_out = []
        syl_papers = 0
        syl_subjects = 0
        syl_chapters = 0

        for p in get_papers(active_only=False, syllabus_id=syl['id']):
            subj_out = []
            for s in get_subjects(paper_key=p['paper_key'], active_only=False):
                chapters = get_chapters(subject_id=s['id'], active_only=False)
                subj_out.append({
                    "name": s["name"],
                    "chapter": s.get("chapter") or "",
                    "chapters": [
                        {
                            "chapter_code": c.get("chapter_code") or "",
                            "name": c.get("name") or "",
                            "description": c.get("description") or "",
                            "display_order": c.get("display_order", 0),
                        }
                        for c in chapters
                    ],
                })
                syl_subjects += 1
                syl_chapters += len(chapters)

            papers_out.append({
                "paper_key": p["paper_key"],
                "display_name": p["display_name"],
                "folder_name": p["folder_name"],
                "keywords": p.get("keywords") or "",
                "display_order": p.get("display_order", 0),
                "subjects": subj_out,
            })
            syl_papers += 1

        data["syllabi"].append({
            "syllabus_key": syl["syllabus_key"],
            "display_name": syl["display_name"],
            "level": syl.get("level"),
            "description": syl.get("description"),
            "display_order": syl.get("display_order", 0),
            "papers": papers_out,
        })

        total_papers += syl_papers
        total_subjects += syl_subjects
        total_chapters += syl_chapters

        # ---------- per-syllabus line ----------
        if verbose:
            lvl = f"  (Level {syl['level']})" if syl.get('level') else ""
            print(f"  📚 {color_text(syl['display_name'], COLORS.GREEN, bold=True)}{lvl}")
            if not papers_out:
                print_colored("     (no papers)", COLORS.YELLOW)
            for i, p in enumerate(papers_out):
                last = (i == len(papers_out) - 1)
                branch = "└─" if last else "├─"
                n_subj = len(p["subjects"])
                n_chap = sum(len(s["chapters"]) for s in p["subjects"])
                name = p["display_name"]
                if len(name) > 42:
                    name = name[:39] + "..."
                print(f"     {branch} 📄 {name:<44} "
                      f"{n_subj:>2} subj · {n_chap:>3} ch")
            print()

    # ---------- write file ----------
    if verbose:
        print_colored("  ⏳ Writing to file...", COLORS.BLUE)

    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print_colored(f"\n  [!] Write failed: {e}", COLORS.RED)
        return False

    # ---------- summary ----------
    if verbose:
        try:
            size = os.path.getsize(filepath)
            size_str = _fmt_size(size)
        except OSError:
            size_str = "?"
        elapsed = time.time() - t0

        print()
        print_colored("  ✓ " +
                      f"Exported {len(syllabi)} syllab{'us' if len(syllabi)==1 else 'i'} "
                      f"→ {total_papers} papers · {total_subjects} subjects · "
                      f"{total_chapters} chapters",
                      COLORS.GREEN, bold=True)
        print(f"     📁 {filepath}  ({size_str})")
        print(f"     ⏱️  {elapsed:.2f}s")
        print_colored("═" * 64, COLORS.CYAN)
        print()

    return True

def import_syllabus(filepath, merge=True, target_syllabus_id=None,
                    verbose=True):
    """
    Read a syllabus JSON file and import it.

    Accepts both v3 (top-level "syllabi") and v2 (flat "papers") formats.

    Returns (papers_added, subjects_added, chapters_added).
    """
    import json
    import os
    import time

    t0 = time.time()

    # ---------- load file ----------
    if not os.path.exists(filepath):
        print_colored(f"[!] File not found: {filepath}", COLORS.RED)
        return 0, 0, 0

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print_colored(f"[!] Could not read file: {e}", COLORS.RED)
        return 0, 0, 0

    if not isinstance(data, dict):
        print_colored("[!] Invalid syllabus file — expected a JSON object.",
                      COLORS.RED)
        return 0, 0, 0

    version = data.get("version", 2)

    # ---------- normalise bundles ----------
    if version >= 3 and "syllabi" in data:
        bundles = [(syl, syl.get("papers", [])) for syl in data["syllabi"]]
    else:
        # v2: flat file — wrap in a synthetic syllabus
        if target_syllabus_id is not None:
            target = next((s for s in get_syllabi(active_only=False)
                           if s['id'] == target_syllabus_id), None)
        else:
            target = next((s for s in get_syllabi(active_only=False)), None)
            if not target:
                add_syllabus("imported", "Imported syllabus",
                             level=None,
                             description="Auto-created on v2 import")
                target = next(s for s in get_syllabi(active_only=False)
                              if s['syllabus_key'] == "imported")
        fake_syl = target or {
            "syllabus_key": "imported",
            "display_name": "Imported syllabus",
            "level": None, "description": None, "display_order": 0,
        }
        bundles = [(fake_syl, data.get("papers", []))]

    if target_syllabus_id is not None:
        override = next((s for s in get_syllabi(active_only=False)
                         if s['id'] == target_syllabus_id), None)
        if override:
            bundles = [(override, papers) for (_s, papers) in bundles]

    # ---------- banner ----------
    if verbose:
        print()
        print_colored("═" * 64, COLORS.CYAN)
        print_colored("  📥  IMPORT SYLLABUS", COLORS.CYAN, bold=True)
        print_colored("═" * 64, COLORS.CYAN)
        print()
        fname = os.path.basename(filepath)
        print(f"  📁 File   : {fname}")
        print(f"  🔖 Format : v{version}"
              + (f"  ·  {len(data.get('syllabi', data.get('papers', [])))} syllabi"
                 if version >= 3 else f"  ·  {len(data.get('papers', []))} papers"))
        mode_label = "Wipe existing then import" if not merge else "Merge (add new only)"
        print(f"  ⚙️  Mode   : {mode_label}")
        if target_syllabus_id is not None:
            t = next((s for s in get_syllabi(active_only=False)
                      if s['id'] == target_syllabus_id), None)
            if t:
                print(f"  🎯 Target : {t['display_name']}  (papers will be forced here)")
        print()

    # ---------- wipe if requested ----------
    if not merge:
        if verbose:
            print_colored("  ⚠️  Clearing existing syllabus data...", COLORS.YELLOW)
        clear_all()

    # ---------- preview pass (read-only) ----------
    if verbose:
        print_colored("  📋  PREVIEW", COLORS.CYAN, bold=True)
        print_colored("  " + "─" * 60, COLORS.CYAN)

        existing_syl_keys = {s['syllabus_key'] for s in get_syllabi(active_only=False)}
        existing_paper_keys = {p['paper_key'] for p in get_papers(active_only=False)}

        for syl_spec, papers in bundles:
            skey = syl_spec.get("syllabus_key") or "(missing key)"
            sname = syl_spec.get("display_name") or skey
            lvl = f"  (Level {syl_spec['level']})" if syl_spec.get('level') else ""
            exists = skey in existing_syl_keys
            tag = color_text("[exists]", COLORS.BLUE) if exists \
                  else color_text("[new]   ", COLORS.GREEN)
            print(f"  📚 {color_text(sname, COLORS.GREEN, bold=True)}{lvl}  {tag}")

            if not papers:
                print_colored("     (no papers in file)", COLORS.YELLOW)
            for i, p in enumerate(papers):
                last = (i == len(papers) - 1)
                branch = "└─" if last else "├─"
                pkey = p.get("paper_key", "?")
                pname = p.get("display_name", pkey)
                if len(pname) > 40:
                    pname = pname[:37] + "..."
                n_subj = len(p.get("subjects", []))
                n_chap = sum(len(s.get("chapters", []))
                             for s in p.get("subjects", []))
                ptag = color_text("[~]", COLORS.BLUE) if pkey in existing_paper_keys \
                       else color_text("[+]", COLORS.GREEN)
                print(f"     {branch} {ptag} 📄 {pname:<42} "
                      f"{n_subj:>2} subj · {n_chap:>3} ch")
            print()

        print_colored("  " + "─" * 60, COLORS.CYAN)
        print_colored("  ⏳ Importing...", COLORS.BLUE)
        print()

    # ---------- import pass ----------
    papers_added = 0
    subjects_added = 0
    chapters_added = 0

    papers_skipped = 0
    subjects_skipped = 0
    chapters_skipped = 0
    syllabi_added = 0
    syllabi_existing = 0

    for syl_spec, papers in bundles:
        syllabus_key = syl_spec.get("syllabus_key")
        if not syllabus_key:
            continue

        existing_syl = next(
            (s for s in get_syllabi(active_only=False)
             if s['syllabus_key'] == syllabus_key),
            None,
        )
        if existing_syl:
            syllabus_id = existing_syl['id']
            syllabi_existing += 1
        else:
            syllabus_id = add_syllabus(
                syllabus_key,
                syl_spec.get("display_name", syllabus_key),
                level=syl_spec.get("level"),
                description=syl_spec.get("description"),
            )
            if not syllabus_id:
                continue
            syllabi_added += 1

        for p in papers:
            pkey = p.get("paper_key")
            if not pkey:
                continue

            existing_p = next(
                (x for x in get_papers(active_only=False)
                 if x['paper_key'] == pkey),
                None,
            )
            if existing_p:
                pid = existing_p['id']
                papers_skipped += 1
                if not existing_p.get('syllabus_id'):
                    update_paper(pid, syllabus_id=syllabus_id)
            else:
                pid = add_paper(
                    pkey,
                    p.get("display_name", pkey),
                    p.get("folder_name", pkey),
                    p.get("keywords", ""),
                    syllabus_id=syllabus_id,
                )
                if pid:
                    papers_added += 1

            if not pid:
                continue

            for s in p.get("subjects", []):
                s_code = str(s.get("chapter") or "").zfill(2)
                if not s_code:
                    continue

                existing_s = get_subject_by_paper_and_code(pkey, s_code)
                if existing_s:
                    sid = existing_s["id"]
                    subjects_skipped += 1
                else:
                    sid = add_subject(s["name"], pkey, chapter=s_code)
                    if sid:
                        subjects_added += 1

                if not sid:
                    continue

                existing_chapters = {
                    str(c["chapter_code"]).zfill(2)
                    for c in get_chapters(subject_id=sid, active_only=False)
                }
                for c in s.get("chapters", []):
                    code = str(c.get("chapter_code") or "").zfill(2)
                    cname = c.get("name") or ""
                    if not code or not cname:
                        continue
                    if code in existing_chapters:
                        chapters_skipped += 1
                        continue
                    if add_chapter(sid, code, cname,
                                   description=c.get("description") or None,
                                   display_order=c.get("display_order")):
                        chapters_added += 1

    # ---------- summary ----------
    elapsed = time.time() - t0

    if verbose:
        print()
        if syllabi_added:
            print_colored(f"     ✓ {syllabi_added} new syllab"
                          f"{'us' if syllabi_added == 1 else 'i'} created",
                          COLORS.GREEN)
        if syllabi_existing:
            print_colored(f"     ⏭️  {syllabi_existing} existing syllab"
                          f"{'us' if syllabi_existing == 1 else 'i'} merged into",
                          COLORS.BLUE)

        if papers_added:
            print_colored(f"     ✓ {papers_added} new paper"
                          f"{'s' if papers_added != 1 else ''} created",
                          COLORS.GREEN)
        if papers_skipped:
            print_colored(f"     ⏭️  {papers_skipped} existing paper"
                          f"{'s' if papers_skipped != 1 else ''} skipped",
                          COLORS.BLUE)

        if subjects_added:
            print_colored(f"     ✓ {subjects_added} new subject"
                          f"{'s' if subjects_added != 1 else ''} created",
                          COLORS.GREEN)
        if subjects_skipped:
            print_colored(f"     ⏭️  {subjects_skipped} existing subject"
                          f"{'s' if subjects_skipped != 1 else ''} skipped",
                          COLORS.BLUE)

        if chapters_added:
            print_colored(f"     ✓ {chapters_added} new chapter"
                          f"{'s' if chapters_added != 1 else ''} created",
                          COLORS.GREEN)
        if chapters_skipped:
            print_colored(f"     ⏭️  {chapters_skipped} existing chapter"
                          f"{'s' if chapters_skipped != 1 else ''} skipped",
                          COLORS.BLUE)

        total_new = syllabi_added + papers_added + subjects_added + chapters_added
        if total_new == 0:
            print_colored("     ✓ Nothing to do — file is already in sync.",
                          COLORS.YELLOW)
        else:
            print_colored(f"     ✓ Import complete ({total_new} row"
                          f"{'s' if total_new != 1 else ''} added total)",
                          COLORS.GREEN, bold=True)

        print(f"     ⏱️  {elapsed:.2f}s")
        print_colored("═" * 64, COLORS.CYAN)
        print()

    return papers_added, subjects_added, chapters_added
