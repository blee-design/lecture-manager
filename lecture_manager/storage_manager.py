# lecture_manager/storage_manager.py
"""
Storage-state helpers for cloud-only / local / both modes.

No schema changes needed — everything is inferred from existing columns:
    file_hash           → local file present
    youtube_upload_id
      OR mirror_video_id → cloud copy present
"""

import os
import glob
from .db import get_connection, TABLE_NAME
from .utils import print_colored, COLORS, color_text


STATE_LOCAL  = 'local'    # local file only
STATE_CLOUD  = 'cloud'    # uploaded to YouTube, no local file
STATE_BOTH   = 'both'     # both local and cloud
STATE_NONE   = 'none'     # DB record only, no media at all


def get_record_storage_state(record):
    """Return one of STATE_LOCAL / STATE_CLOUD / STATE_BOTH / STATE_NONE."""
    has_local = bool(record.get('file_hash'))
    has_cloud = bool(record.get('youtube_upload_id') or record.get('mirror_video_id'))
    if has_local and has_cloud:
        return STATE_BOTH
    if has_local:
        return STATE_LOCAL
    if has_cloud:
        return STATE_CLOUD
    return STATE_NONE


def _rows(sql, params=()):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(sql, params)
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return rows


def list_cloud_only_records():
    """Records that exist on YouTube but have no local file."""
    return _rows(f"""
        SELECT * FROM {TABLE_NAME}
        WHERE (file_hash IS NULL OR file_hash = '')
          AND (youtube_upload_id IS NOT NULL OR mirror_video_id IS NOT NULL)
        ORDER BY nepali_date DESC, time DESC
    """)


def list_both_records():
    """Records that have BOTH a local file and a cloud copy — safe to purge."""
    return _rows(f"""
        SELECT * FROM {TABLE_NAME}
        WHERE file_hash IS NOT NULL AND file_hash != ''
          AND (youtube_upload_id IS NOT NULL OR mirror_video_id IS NOT NULL)
        ORDER BY nepali_date DESC, time DESC
    """)


def list_local_only_records():
    """Records with a local file but no cloud copy."""
    return _rows(f"""
        SELECT * FROM {TABLE_NAME}
        WHERE file_hash IS NOT NULL AND file_hash != ''
          AND youtube_upload_id IS NULL AND mirror_video_id IS NULL
        ORDER BY nepali_date DESC, time DESC
    """)


def list_no_media_records():
    """Records with neither local file nor cloud copy."""
    return _rows(f"""
        SELECT * FROM {TABLE_NAME}
        WHERE (file_hash IS NULL OR file_hash = '')
          AND youtube_upload_id IS NULL AND mirror_video_id IS NULL
        ORDER BY nepali_date DESC, time DESC
    """)


def stats_summary():
    """Return a dict with counts by storage state."""
    rows = _rows(f"""
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN file_hash IS NOT NULL AND file_hash != ''
                     THEN 1 ELSE 0 END) AS with_local,
            SUM(CASE WHEN youtube_upload_id IS NOT NULL OR mirror_video_id IS NOT NULL
                     THEN 1 ELSE 0 END) AS with_cloud,
            SUM(CASE WHEN file_hash IS NOT NULL AND file_hash != ''
                      AND (youtube_upload_id IS NOT NULL OR mirror_video_id IS NOT NULL)
                     THEN 1 ELSE 0 END) AS both_count,
            SUM(CASE WHEN (file_hash IS NULL OR file_hash = '')
                      AND (youtube_upload_id IS NOT NULL OR mirror_video_id IS NOT NULL)
                     THEN 1 ELSE 0 END) AS cloud_only_count,
            SUM(CASE WHEN (file_hash IS NULL OR file_hash = '')
                      AND youtube_upload_id IS NULL AND mirror_video_id IS NULL
                     THEN 1 ELSE 0 END) AS no_media_count
        FROM {TABLE_NAME}
    """)
    return (rows[0] if rows else {}) or {}


def _locate_local_file(record):
    """Return the full path of the record's local file, or None."""
    file_hash = record.get('file_hash')
    if not file_hash:
        return None

    # 1. hash_cache first
    rows = _rows(
        "SELECT file_path FROM hash_cache "
        "WHERE file_hash = %s AND status = 'active' LIMIT 1",
        (file_hash,))
    if rows and os.path.exists(rows[0]['file_path']):
        return rows[0]['file_path']

    # 2. target directory
    try:
        from .file_manager import get_target_path
        target_dir, _ = get_target_path(record, interactive=False)
        if target_dir and os.path.isdir(target_dir):
            matches = glob.glob(os.path.join(target_dir, file_hash + '.*'))
            if matches:
                return matches[0]
    except Exception:
        pass

    # 3. deep scan of ROOT_DIR
    try:
        from .file_manager import ROOT_DIR
        for root, _, files in os.walk(ROOT_DIR):
            for f in files:
                if f.startswith(file_hash) and f.lower().endswith(
                        ('.mp4', '.mkv', '.webm', '.avi', '.mov')):
                    return os.path.join(root, f)
    except Exception:
        pass

    return None


def purge_local_file_for_record(record, dry_run=False):
    """
    Delete the local file for one record, keep the DB row intact.

    Refuses if the record has no cloud copy (safety — we never leave
    you with a record whose file is gone and can't be re-fetched).
    Returns (success: bool, message: str).
    """
    if not record.get('youtube_upload_id') and not record.get('mirror_video_id'):
        return False, "Refusing to purge: no cloud backup available"

    file_path = _locate_local_file(record)
    if not file_path:
        if dry_run:
            return True, "No local file found (would clear DB refs)"
        return _clear_local_refs(record)

    if dry_run:
        size_mb = os.path.getsize(file_path) / (1024 * 1024)
        return True, f"Would delete {file_path} ({size_mb:.1f} MB)"

    try:
        os.remove(file_path)
        # Clean up empty parent dirs, honouring existing safety rules
        try:
            from .file_manager import remove_empty_directories
            remove_empty_directories(os.path.dirname(file_path))
        except Exception:
            pass
    except Exception as e:
        return False, f"Delete failed: {e}"

    ok, msg = _clear_local_refs(record)
    return True, f"Deleted {os.path.basename(file_path)} — {msg}"


def _clear_local_refs(record):
    """NULL out file_hash / original_filename and drop hash_cache rows."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        old_hash = record.get('file_hash')
        cursor.execute(f"""
            UPDATE {TABLE_NAME}
            SET file_hash = NULL, original_filename = NULL
            WHERE id = %s
        """, (record['id'],))
        if old_hash:
            cursor.execute("DELETE FROM hash_cache WHERE file_hash = %s",
                           (old_hash,))
        conn.commit()
        return True, "DB refs cleared"
    except Exception as e:
        conn.rollback()
        return False, f"DB update failed: {e}"
    finally:
        cursor.close()
        conn.close()
