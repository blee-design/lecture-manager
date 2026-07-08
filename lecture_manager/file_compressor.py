# file_compressor.py

import os
import subprocess
import shutil
from .db import get_connection, TABLE_NAME, get_record_by_any_id
from .utils import print_colored, COLORS, compute_md5, ROOT_DIR
from .file_manager import get_target_path

def get_file_path_for_record(record):
    """
    Locate the video file for a given record.
    Uses hash_cache first, then falls back to target directory, then whole ROOT_DIR.
    """
    file_hash = record.get('file_hash')
    if file_hash:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT file_path FROM hash_cache WHERE file_hash = %s AND status = 'active'", (file_hash,))
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        if row and os.path.exists(row['file_path']):
            return row['file_path']
        else:
            target_dir, _ = get_target_path(record, interactive=False)
            if target_dir and os.path.exists(target_dir):
                import glob
                pattern = os.path.join(target_dir, file_hash + '.*')
                matches = glob.glob(pattern)
                if matches:
                    return matches[0]
    # Fallback
    for root, _, files in os.walk(ROOT_DIR):
        for f in files:
            if f.lower().endswith(('.mp4','.mkv','.webm','.avi','.mov')):
                if record['video_id'] in f:
                    return os.path.join(root, f)
    return None

def compress_file(filepath):
    """
    Compress a single video file to 480p H.264 (CRF 28).
    Returns a dict with status and message.
    """
    # 1. Check resolution
    try:
        cmd = ['ffprobe', '-v', 'error', '-show_entries', 'stream=width,height', '-of', 'csv=p=0', filepath]
        result = subprocess.run(cmd, capture_output=True, text=True)
        output = result.stdout.strip()
        if not output:
            return {'status': 'failed', 'message': 'No video stream found'}
        width, height = None, None
        for line in output.split('\n'):
            if ',' in line:
                w, h = line.split(',')
                width, height = int(w), int(h)
                break
        if width is None or height is None:
            return {'status': 'failed', 'message': 'Could not determine resolution'}
    except Exception as e:
        return {'status': 'failed', 'message': f'ffprobe error: {e}'}

    # Skip if already <= 480p
    if height <= 480:
        return {'status': 'skipped', 'message': f'Already {width}x{height} (≤480p), skipping'}

    # 2. Prepare output paths and ffmpeg command
    dirname = os.path.dirname(filepath)
    basename = os.path.basename(filepath)
    temp_output = os.path.join(dirname, f"temp_{os.urandom(4).hex()}.mkv")

    cmd = [
        'ffmpeg', '-i', filepath,
        '-c:v', 'libx264',
        '-crf', '28',
        '-preset', 'medium', # medium, slow, fast
        '-vf', 'scale=854:-2',
        '-c:a', 'aac',
        '-b:a', '128k',
        '-movflags', '+faststart',
        '-y',
        temp_output
    ]
    # this is example which creates 660MB into 320MB
    # ffmpeg -i ea328ccd46284546917555b787658124.mkv -c:v libx265 -crf 28 -preset medium -c:a aac compressed_video.mkv

    print(f"  Compressing: {basename}")

    # 3. Run ffmpeg (with live output and cancellable)
    proc = None
    try:
        proc = subprocess.Popen(cmd, stdout=None, stderr=None, stdin=subprocess.DEVNULL)
        proc.wait()
        if proc.returncode != 0:
            raise subprocess.CalledProcessError(proc.returncode, cmd)
    except KeyboardInterrupt:
        # Cancel the current ffmpeg process
        if proc is not None and proc.poll() is None:
            proc.terminate()
            proc.wait()
        if os.path.exists(temp_output):
            os.remove(temp_output)
        print_colored("\n[!] Compression cancelled by user.", COLORS.YELLOW)
        return {'status': 'failed', 'message': 'Cancelled by user'}
    except Exception as e:
        # Clean up temp file on any other error
        if os.path.exists(temp_output):
            os.remove(temp_output)
        return {'status': 'failed', 'message': f'ffmpeg error: {e}'}

    # 4. Compute new hash and rename
    new_hash = compute_md5(temp_output)
    new_filename = f"{new_hash}.mkv"
    new_filepath = os.path.join(dirname, new_filename)

    try:
        shutil.move(temp_output, new_filepath)
        if os.path.exists(filepath) and filepath != new_filepath:
            os.remove(filepath)
    except Exception as e:
        return {'status': 'failed', 'message': f'Move error: {e}'}

    # 5. Update database
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT file_hash FROM hash_cache WHERE file_path = %s AND status = 'active'", (filepath,))
        row = cursor.fetchone()
        if row:
            old_hash = row[0]
            cursor.execute(f"UPDATE {TABLE_NAME} SET file_hash = %s WHERE file_hash = %s", (new_hash, old_hash))
            cursor.execute("""
                UPDATE hash_cache
                SET file_path = %s, file_hash = %s, last_scan = NOW()
                WHERE file_path = %s
            """, (new_filepath, new_hash, filepath))
            conn.commit()
        else:
            print_colored(f"  [WARN] No cache entry for {basename}, DB not updated.", COLORS.YELLOW)

        cursor.close()
        conn.close()
    except Exception as e:
        return {'status': 'failed', 'message': f'DB update error: {e}'}

    return {'status': 'compressed', 'new_path': new_filepath, 'message': f'Compressed to {new_filename} (was {basename})'}

def compress_library_to_480p():
    """
    Batch compress all video files with resolution > 480p.
    """
    video_exts = ('.mp4', '.mkv', '.webm', '.avi', '.mov')
    all_videos = []

    print_colored("[i] Scanning for video files...", COLORS.BLUE)
    for root, _, files in os.walk(ROOT_DIR):
        for f in files:
            if f.lower().endswith(video_exts):
                all_videos.append(os.path.join(root, f))

    if not all_videos:
        print_colored("[i] No video files found.", COLORS.YELLOW)
        return

    total = len(all_videos)
    processed = 0
    skipped = 0
    failed = 0

    print_colored(f"[i] Found {total} video files. Checking resolutions...", COLORS.BLUE)

    for idx, filepath in enumerate(all_videos, 1):
        basename = os.path.basename(filepath)
        print(f"  [{idx}/{total}] {basename[:60]}", end="\r")
        result = compress_file(filepath)
        if result['status'] == 'compressed':
            processed += 1
            print(f"  [{idx}/{total}] {result['message']}")
        elif result['status'] == 'skipped':
            skipped += 1
        else:
            failed += 1
            print_colored(f"  [{idx}/{total}] FAIL: {result['message']}", COLORS.RED)

    print_colored(f"\n[✓] Compression complete: {processed} processed, {skipped} skipped, {failed} failed.", COLORS.GREEN)

def compress_single_by_id(identifier):
    record = get_record_by_any_id(identifier)
    if not record:
        return {'status': 'failed', 'message': f'No record found for ID: {identifier}'}

    filepath = get_file_path_for_record(record)
    if not filepath:
        return {'status': 'failed', 'message': f'Could not locate file for record {identifier}'}

    print_colored(f"Found file: {filepath}", COLORS.BLUE)
    return compress_file(filepath)

def list_largest_files(n=5):
    """Find and list the n largest video files with height > 480.
       Returns a list of (hash, size_mb, filepath) for easy selection.
    """
    video_exts = ('.mp4', '.mkv', '.webm', '.avi', '.mov')
    candidates = []
    for root, _, files in os.walk(ROOT_DIR):
        for f in files:
            if f.lower().endswith(video_exts):
                fp = os.path.join(root, f)
                try:
                    cmd = ['ffprobe', '-v', 'error', '-show_entries', 'stream=height', '-of', 'csv=p=0', fp]
                    result = subprocess.run(cmd, capture_output=True, text=True)
                    h = result.stdout.strip().split('\n')[0]
                    if h.isdigit() and int(h) > 480:
                        size = os.path.getsize(fp)
                        hash_part = os.path.splitext(f)[0]
                        candidates.append((size, fp, hash_part))
                except:
                    pass
    candidates.sort(reverse=True)  # largest first
    print("\n" + "═" * 60)
    print_colored(f"  TOP {min(n, len(candidates))} LARGE VIDEOS (≥720p)", COLORS.CYAN, bold=True)
    print("═" * 60)
    result_list = []
    for i, (size, fp, hash_part) in enumerate(candidates[:n], 1):
        size_mb = size / (1024*1024)
        print(f"  {i}. {hash_part}  ({size_mb:.1f} MB)")
        result_list.append({'number': i, 'hash': hash_part, 'path': fp, 'size_mb': size_mb})
    print("═" * 60)
    print("Enter the number (1-5) or hash to compress that file.\n")
    return result_list
