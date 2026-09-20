# lecture_manager/syllabus_config.py
"""
User-configurable papers and subjects.
All reads happen through get_papers() / get_subjects(), which pull from the DB.
Hardcoded templates in DEFAULT_PAPER_TEMPLATE exist only as optional seeds.
"""
from .db import get_connection
from .utils import print_colored, color_text, COLORS


# ---------- READ ----------
def get_papers(active_only=True):
    """Return list of paper dicts. Empty list means user hasn't set up yet."""
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    sql = "SELECT * FROM papers"
    if active_only:
        sql += " WHERE active = 1"
    sql += " ORDER BY display_order, display_name"
    cursor.execute(sql)
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
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


# ---------- WRITE ----------
def add_paper(paper_key, display_name, folder_name, keywords=""):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        # Append new papers after existing ones: max(display_order) + 10
        cursor.execute("SELECT COALESCE(MAX(display_order), 0) FROM papers")
        next_order = (cursor.fetchone()[0] or 0) + 10
        cursor.execute("""
            INSERT INTO papers (paper_key, display_name, folder_name, keywords, display_order)
            VALUES (%s, %s, %s, %s, %s)
        """, (paper_key, display_name, folder_name, keywords, next_order))
        conn.commit()
        return cursor.lastrowid
    except Exception as e:
        print_colored(f"[!] Could not add paper: {e}", COLORS.RED)
        return None
    finally:
        cursor.close(); conn.close()


def update_paper(paper_id, **fields):
    allowed = {'display_name', 'folder_name', 'keywords', 'active', 'display_order'}
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
    """Wipe papers + subjects (used by first-run wizard)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM subjects")
    cursor.execute("DELETE FROM papers")
    conn.commit()
    cursor.close(); conn.close()


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
def export_syllabus(filepath):
    """
    Write all papers + subjects to a JSON file.
    Structure:
    {
      "version": 1,
      "exported_at": "...",
      "papers": [ {paper_key, display_name, folder_name, keywords, display_order, subjects:[{name, chapter}]} ]
    }
    """
    import json
    from datetime import datetime

    papers = get_papers(active_only=False)
    data = {
        "version": 1,
        "exported_at": datetime.now().isoformat(),
        "papers": []
    }
    for p in papers:
        subs = get_subjects(paper_key=p["paper_key"], active_only=False)
        data["papers"].append({
            "paper_key": p["paper_key"],
            "display_name": p["display_name"],
            "folder_name": p["folder_name"],
            "keywords": p.get("keywords") or "",
            "display_order": p.get("display_order", 0),
            "subjects": [
                {"name": s["name"], "chapter": s.get("chapter") or ""}
                for s in subs
            ],
        })

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print_colored(f"[✓] Exported {len(papers)} papers to {filepath}", COLORS.GREEN)
    return True


def import_syllabus(filepath, merge=True):
    """
    Read papers + subjects from a JSON file (created by export_syllabus).
    merge=True  → add only papers that don't already exist
    merge=False → replace everything (destructive)
    Returns (papers_added, subjects_added).
    """
    import json
    import os

    if not os.path.exists(filepath):
        print_colored(f"[!] File not found: {filepath}", COLORS.RED)
        return 0, 0

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print_colored(f"[!] Could not read file: {e}", COLORS.RED)
        return 0, 0

    if not isinstance(data, dict) or "papers" not in data:
        print_colored("[!] Invalid syllabus file — missing 'papers' key.", COLORS.RED)
        return 0, 0

    if not merge:
        clear_all()
        print_colored("[i] Cleared existing syllabus.", COLORS.YELLOW)

    existing_keys = {p["paper_key"] for p in get_papers(active_only=False)}
    papers_added = 0
    subjects_added = 0

    for p in data["papers"]:
        key = p.get("paper_key")
        if not key:
            continue
        if key in existing_keys:
            print_colored(f"[i] Paper '{key}' already exists — skipping.", COLORS.YELLOW)
            continue
        if add_paper(key,
                     p.get("display_name", key),
                     p.get("folder_name", key),
                     p.get("keywords", "")):
            papers_added += 1
            for s in p.get("subjects", []):
                if add_subject(s["name"], key, chapter=s.get("chapter") or ""):
                    subjects_added += 1

    print_colored(f"[✓] Imported {papers_added} papers, {subjects_added} subjects.", COLORS.GREEN)
    return papers_added, subjects_added
