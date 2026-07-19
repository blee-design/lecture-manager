# File db.py

import mysql.connector
from mysql.connector import Error
from . import config
from .utils import print_colored, COLORS

TABLE_NAME = 'youtube_lectures'

def get_connection():
    if config.db_config is None:
        config.load_or_create_config()
    try:
        return mysql.connector.connect(**config.db_config)
    except Error as e:
        print_colored(f"[!] Database connection error: {e}", COLORS.RED)
        print("Please check your credentials and try again.")
        exit(1)

def create_table():
    conn = get_connection()
    cursor = conn.cursor()
    # Main lectures table with unique index on mirror_video_id
    cursor.execute(f"""
    CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
        id INT AUTO_INCREMENT PRIMARY KEY,
        video_id VARCHAR(20) NOT NULL UNIQUE,
        video_title TEXT,
        syllabus_id VARCHAR(20),
        subject VARCHAR(255),
        chapter VARCHAR(255),
        lecturer VARCHAR(255),
        nepali_date VARCHAR(20),
        time VARCHAR(20),
        notes TEXT,
        mirror_video_id VARCHAR(20) NULL,
        file_hash VARCHAR(32) NULL,
        paper ENUM('pretest','paper_i','paper_ii','paper_iii') NULL,
        UNIQUE INDEX idx_mirror_video_id (mirror_video_id),
        INDEX idx_paper (paper)
    );
    """)
    # Trash entries
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS trash_entries (
        id INT AUTO_INCREMENT PRIMARY KEY,
        original_path VARCHAR(512) NOT NULL,
        record_id INT NULL,
        trash_filename VARCHAR(255) NOT NULL,
        deleted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (record_id) REFERENCES youtube_lectures(id) ON DELETE SET NULL
    );
    """)
    # Hash cache
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS hash_cache (
        id INT AUTO_INCREMENT PRIMARY KEY,
        file_path VARCHAR(512) NOT NULL UNIQUE,
        file_hash VARCHAR(32) NOT NULL,
        status ENUM('active', 'trashed') DEFAULT 'active',
        last_scan DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_status (status)
    );
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS cookies (
        id INT PRIMARY KEY DEFAULT 1,
        cookie_data LONGTEXT NOT NULL,
        last_refresh DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """)
        # Facebook entries
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS facebook_entries (
        id INT AUTO_INCREMENT PRIMARY KEY,
        facebook_id VARCHAR(50) NOT NULL UNIQUE,
        type ENUM('video', 'photo') NOT NULL,
        title VARCHAR(512),
        uploader VARCHAR(255),
        url VARCHAR(512) NOT NULL,
        file_hash VARCHAR(32) NULL,
        original_filename VARCHAR(512) NULL,
        download_date DATETIME DEFAULT CURRENT_TIMESTAMP,
        notes TEXT,
        INDEX idx_uploader (uploader),
        INDEX idx_type (type)
    );
    """)
    from .question_bank import create_question_table
    create_question_table()
    conn.commit()
    cursor.close()
    conn.close()
    print_colored(f"[✓] Tables ready.", COLORS.GREEN)

def migrate_table():
    conn = get_connection()
    cursor = conn.cursor()

    # Add paper column if missing
    cursor.execute("SHOW COLUMNS FROM youtube_lectures LIKE 'paper'")
    if not cursor.fetchone():
        cursor.execute("ALTER TABLE youtube_lectures ADD COLUMN paper ENUM('pretest','paper_i','paper_ii','paper_iii') NULL")
        print_colored("[✓] Added 'paper' column.", COLORS.GREEN)
        cursor.execute("ALTER TABLE youtube_lectures ADD INDEX idx_paper (paper)")
        print_colored("[✓] Added index on 'paper'.", COLORS.GREEN)

    # Ensure trash_entries exists
    cursor.execute("SHOW TABLES LIKE 'trash_entries'")
    if not cursor.fetchone():
        cursor.execute("""
        CREATE TABLE trash_entries (
            id INT AUTO_INCREMENT PRIMARY KEY,
            original_path VARCHAR(512) NOT NULL,
            record_id INT NULL,
            trash_filename VARCHAR(255) NOT NULL,
            deleted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (record_id) REFERENCES youtube_lectures(id) ON DELETE SET NULL
        );
        """)
        print_colored("[✓] Created 'trash_entries' table.", COLORS.GREEN)

    # Ensure hash_cache exists and has correct columns
    cursor.execute("SHOW TABLES LIKE 'hash_cache'")
    if not cursor.fetchone():
        cursor.execute("""
        CREATE TABLE hash_cache (
            id INT AUTO_INCREMENT PRIMARY KEY,
            file_path VARCHAR(512) NOT NULL UNIQUE,
            file_hash VARCHAR(32) NOT NULL,
            status ENUM('active', 'trashed') DEFAULT 'active',
            last_scan DATETIME DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_status (status)
        );
        """)
        print_colored("[✓] Created 'hash_cache' table.", COLORS.GREEN)
    else:
        # Drop obsolete scan_session if present
        cursor.execute("SHOW COLUMNS FROM hash_cache LIKE 'scan_session'")
        if cursor.fetchone():
            cursor.execute("ALTER TABLE hash_cache DROP COLUMN scan_session")
            print_colored("[✓] Dropped obsolete 'scan_session' column.", COLORS.GREEN)
        # Add status if missing
        cursor.execute("SHOW COLUMNS FROM hash_cache LIKE 'status'")
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE hash_cache ADD COLUMN status ENUM('active', 'trashed') DEFAULT 'active'")
            print_colored("[✓] Added 'status' column to hash_cache.", COLORS.GREEN)
        # Add last_scan if missing
        cursor.execute("SHOW COLUMNS FROM hash_cache LIKE 'last_scan'")
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE hash_cache ADD COLUMN last_scan DATETIME DEFAULT CURRENT_TIMESTAMP")
            print_colored("[✓] Added 'last_scan' column to hash_cache.", COLORS.GREEN)

    # Ensure facebook_entries exists
    cursor.execute("SHOW TABLES LIKE 'facebook_entries'")
    if not cursor.fetchone():
        cursor.execute("""
        CREATE TABLE facebook_entries (
            id INT AUTO_INCREMENT PRIMARY KEY,
            facebook_id VARCHAR(50) NOT NULL UNIQUE,
            type ENUM('video', 'photo') NOT NULL,
            title VARCHAR(512),
            uploader VARCHAR(255),
            url VARCHAR(512) NOT NULL,
            file_hash VARCHAR(32) NULL,
            original_filename VARCHAR(512) NULL,
            download_date DATETIME DEFAULT CURRENT_TIMESTAMP,
            notes TEXT,
            INDEX idx_uploader (uploader),
            INDEX idx_type (type)
        );
        """)
        print_colored("[✓] Created 'facebook_entries' table.", COLORS.GREEN)
    else:
        # Drop obsolete scan_session if present (only if it exists)
        cursor.execute("SHOW COLUMNS FROM hash_cache LIKE 'scan_session'")
        if cursor.fetchone():
            cursor.execute("ALTER TABLE hash_cache DROP COLUMN scan_session")
            print_colored("[✓] Dropped obsolete 'scan_session' column.", COLORS.GREEN)

    # --- NEW: Add unique index on mirror_video_id if missing ---
    cursor.execute("SHOW INDEX FROM youtube_lectures WHERE Key_name = 'idx_mirror_video_id'")
    if not cursor.fetchone():
        print_colored("[i] Adding unique index on mirror_video_id...", COLORS.YELLOW)
        try:
            cursor.execute("ALTER TABLE youtube_lectures ADD UNIQUE INDEX idx_mirror_video_id (mirror_video_id)")
            print_colored("[✓] Added unique index on mirror_video_id.", COLORS.GREEN)
        except mysql.connector.Error as e:
            if e.errno == 1062:  # Duplicate entry
                print_colored("[!] Cannot add unique index: duplicate mirror_video_id entries exist.", COLORS.RED)
                print("Please remove duplicate mirror_video_id entries manually, then run the migration again.")
                print("You can find duplicates with:")
                print("  SELECT mirror_video_id, COUNT(*) FROM youtube_lectures WHERE mirror_video_id IS NOT NULL GROUP BY mirror_video_id HAVING COUNT(*) > 1;")
                print("After cleaning, run 'ALTER TABLE youtube_lectures ADD UNIQUE INDEX idx_mirror_video_id (mirror_video_id);' manually.")
            else:
                print_colored(f"[!] Failed to add unique index: {e}", COLORS.RED)

    # Add original_filename column if missing
    cursor.execute("SHOW COLUMNS FROM youtube_lectures LIKE 'original_filename'")
    if not cursor.fetchone():
        cursor.execute("ALTER TABLE youtube_lectures ADD COLUMN original_filename VARCHAR(512) NULL")
        print_colored("[✓] Added 'original_filename' column.", COLORS.GREEN)

    # --- NEW: Add index on facebook_entries.url for faster duplicate lookups ---
    cursor.execute("SHOW INDEX FROM facebook_entries WHERE Key_name = 'idx_url'")
    if not cursor.fetchone():
        try:
            cursor.execute("ALTER TABLE facebook_entries ADD INDEX idx_url (url(255))")
            print_colored("[✓] Added index on facebook_entries.url", COLORS.GREEN)
        except mysql.connector.Error as e:
            print_colored(f"[!] Failed to add index: {e}", COLORS.YELLOW)

    # ---- NEW: YouTube upload columns ----
    cursor.execute("SHOW COLUMNS FROM youtube_lectures LIKE 'youtube_upload_id'")
    if not cursor.fetchone():
        cursor.execute("ALTER TABLE youtube_lectures ADD COLUMN youtube_upload_id VARCHAR(255) NULL")
        print_colored("[✓] Added 'youtube_upload_id' column.", COLORS.GREEN)

    cursor.execute("SHOW COLUMNS FROM youtube_lectures LIKE 'youtube_upload_status'")
    if not cursor.fetchone():
        cursor.execute("ALTER TABLE youtube_lectures ADD COLUMN youtube_upload_status ENUM('pending','uploaded','failed') DEFAULT NULL")
        print_colored("[✓] Added 'youtube_upload_status' column.", COLORS.GREEN)

    # ---- NEW: OAuth credentials table ----
    cursor.execute("SHOW TABLES LIKE 'oauth_credentials'")
    if not cursor.fetchone():
        cursor.execute("""
        CREATE TABLE oauth_credentials (
            id INT PRIMARY KEY DEFAULT 1,
            token_data LONGBLOB NULL,
            client_secrets TEXT NULL,
            last_refresh DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        """)
        print_colored("[✓] Created 'oauth_credentials' table.", COLORS.GREEN)
    else:
        # Ensure columns exist
        cursor.execute("SHOW COLUMNS FROM oauth_credentials LIKE 'token_data'")
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE oauth_credentials ADD COLUMN token_data LONGBLOB NULL")
            print_colored("[✓] Added 'token_data' column to oauth_credentials.", COLORS.GREEN)
        cursor.execute("SHOW COLUMNS FROM oauth_credentials LIKE 'client_secrets'")
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE oauth_credentials ADD COLUMN client_secrets TEXT NULL")
            print_colored("[✓] Added 'client_secrets' column to oauth_credentials.", COLORS.GREEN)
    from .question_bank import create_question_table
    create_question_table()
    cursor.execute("SHOW COLUMNS FROM questions LIKE 'notes'")
    if not cursor.fetchone():
        cursor.execute("ALTER TABLE questions ADD COLUMN notes TEXT NULL")
        print_colored("[✓] Added 'notes' column to questions table.", COLORS.GREEN)
    cursor.close()
    conn.close()

def get_record_by_video_id(video_id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True, buffered=True)
    try:
        cursor.execute(f"SELECT * FROM {TABLE_NAME} WHERE video_id = %s", (video_id,))
        return cursor.fetchone()
    finally:
        cursor.close()
        conn.close()

def get_record_by_any_id(identifier):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True, buffered=True)
    try:
        cursor.execute(f"""
            SELECT * FROM {TABLE_NAME}
            WHERE video_id = %s OR mirror_video_id = %s OR file_hash = %s
        """, (identifier, identifier, identifier))
        return cursor.fetchone()
    finally:
        cursor.close()
        conn.close()

def get_any_media_record(identifier):
    """
    Search both youtube_lectures and facebook_entries for a given identifier.
    Returns a dict with 'source' ('youtube' or 'facebook') and the record data,
    or None if not found.
    """
    # Try YouTube first
    from .facebook_manager import get_facebook_entry_by_id
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(f"SELECT * FROM {TABLE_NAME} WHERE video_id = %s OR mirror_video_id = %s OR file_hash = %s OR syllabus_id = %s",
                   (identifier, identifier, identifier, identifier))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    if row:
        row['source'] = 'youtube'
        return row

    # Try Facebook
    fb_row = get_facebook_entry_by_id(identifier)
    if fb_row:
        fb_row['source'] = 'facebook'
        return fb_row

    return None
