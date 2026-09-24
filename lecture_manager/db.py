# File db.py

import mysql.connector
from mysql.connector import Error
from . import config
from .utils import print_colored, COLORS

TABLE_NAME = 'youtube_lectures'

# ---------- Collation unification ----------
# MariaDB 11.4+ defaults utf8mb4 to utf8mb4_uca1400_ai_ci. Our app's tables
# were written assuming utf8mb4_unicode_ci (Moodle, question bank, etc.), so
# any table created without an explicit COLLATE clause ends up on the wrong
# family and joins between it and the app's tables raise error 1267.
# The fix below runs at every startup and converts any mismatched table.
_UNIFIED_CHARSET    = 'utf8mb4'
_UNIFIED_COLLATION  = 'utf8mb4_unicode_ci'

# Every table this application owns. If you add a new table, add it here.
_APP_TABLES = [
    'youtube_lectures', 'trash_entries', 'hash_cache', 'cookies',
    'facebook_entries',
    'pomodoro_settings', 'pomodoro_tasks', 'pomodoro_log',
    'pomodoro_state', 'pomodoro_badges', 'user_badges', 'pomodoro_pauses',
    'subjects', 'chapters', 'papers',
    'questions', 'question_options', 'question_matching_pairs', 'question_hints',
    'oauth_credentials',
    'instapaper_credentials', 'instapaper_articles', 'instapaper_oauth',
]

def _ensure_unified_collation(cursor):
    """
    Convert any app table whose collation isn't utf8mb4_unicode_ci.

    Handles foreign keys that reference character columns by temporarily
    dropping them, converting every mismatched table, then recreating them.
    Foreign keys on integer columns are left alone — INT has no collation.
    """
    placeholders = ','.join(['%s'] * len(_APP_TABLES))

    # ---- 1. Which of our tables are on the wrong collation? ----
    cursor.execute(f"""
        SELECT TABLE_NAME, TABLE_COLLATION
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME IN ({placeholders})
          AND TABLE_COLLATION IS NOT NULL
          AND TABLE_COLLATION <> %s
    """, (*_APP_TABLES, _UNIFIED_COLLATION))
    bad = cursor.fetchall()
    if not bad:
        return

    # ---- 2. Find string-column FKs involving any of those tables ----
    cursor.execute(f"""
        SELECT DISTINCT
            rc.CONSTRAINT_NAME,
            rc.TABLE_NAME             AS child_table,
            rc.REFERENCED_TABLE_NAME  AS parent_table,
            rc.UPDATE_RULE,
            rc.DELETE_RULE
        FROM INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS rc
        JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu
          ON  kcu.CONSTRAINT_SCHEMA = rc.CONSTRAINT_SCHEMA
          AND kcu.CONSTRAINT_NAME   = rc.CONSTRAINT_NAME
        JOIN INFORMATION_SCHEMA.COLUMNS c
          ON  c.TABLE_SCHEMA = kcu.TABLE_SCHEMA
          AND c.TABLE_NAME   = kcu.TABLE_NAME
          AND c.COLUMN_NAME  = kcu.COLUMN_NAME
        WHERE rc.CONSTRAINT_SCHEMA = DATABASE()
          AND (rc.TABLE_NAME IN ({placeholders})
               OR rc.REFERENCED_TABLE_NAME IN ({placeholders}))
          AND c.DATA_TYPE IN ('char','varchar','tinytext','text','mediumtext','longtext')
    """, (*_APP_TABLES, *_APP_TABLES))

    fk_defs = []
    for fk_name, child, parent, on_update, on_delete in cursor.fetchall():
        cursor.execute("""
            SELECT COLUMN_NAME, REFERENCED_COLUMN_NAME
            FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
            WHERE CONSTRAINT_SCHEMA = DATABASE()
              AND CONSTRAINT_NAME   = %s
            ORDER BY ORDINAL_POSITION
        """, (fk_name,))
        cols = cursor.fetchall()
        fk_defs.append((fk_name, child, parent, cols, on_update, on_delete))

    # ---- 3. Drop those FKs ----
    for fk_name, child, _parent, _cols, _u, _d in fk_defs:
        print_colored(
            f"[i] Temporarily dropping FK `{fk_name}` on `{child}`...",
            COLORS.BLUE,
        )
        cursor.execute(f"ALTER TABLE `{child}` DROP FOREIGN KEY `{fk_name}`")

    # ---- 4. Convert every mismatched table ----
    for tbl, current in bad:
        print_colored(
            f"[i] Collation mismatch on '{tbl}' ({current}) – converting to "
            f"{_UNIFIED_COLLATION}...",
            COLORS.YELLOW,
        )
        cursor.execute(
            f"ALTER TABLE `{tbl}` "
            f"CONVERT TO CHARACTER SET {_UNIFIED_CHARSET} "
            f"COLLATE {_UNIFIED_COLLATION}"
        )
        print_colored(f"[✓] '{tbl}' converted.", COLORS.GREEN)

    # ---- 5. Recreate the FKs ----
    for fk_name, child, parent, cols, on_update, on_delete in fk_defs:
        col_list     = ', '.join(f"`{c[0]}`" for c in cols)
        ref_col_list = ', '.join(f"`{c[1]}`" for c in cols)
        print_colored(
            f"[i] Recreating FK `{fk_name}` on `{child}` → `{parent}`...",
            COLORS.BLUE,
        )
        cursor.execute(
            f"ALTER TABLE `{child}` "
            f"ADD CONSTRAINT `{fk_name}` FOREIGN KEY ({col_list}) "
            f"REFERENCES `{parent}` ({ref_col_list}) "
            f"ON UPDATE {on_update} ON DELETE {on_delete}"
        )

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
        source VARCHAR(255) NULL,
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
        paper VARCHAR(50) NULL,
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
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS pomodoro_settings (
        id INT PRIMARY KEY DEFAULT 1,
        work_min INT NOT NULL DEFAULT 25,
        short_break_min INT NOT NULL DEFAULT 5,
        long_break_min INT NOT NULL DEFAULT 15,
        cycles_before_long INT NOT NULL DEFAULT 4,
        daily_goal INT NOT NULL DEFAULT 12,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
    );
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS pomodoro_tasks (
        id INT AUTO_INCREMENT PRIMARY KEY,
        task_text VARCHAR(255) NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS pomodoro_log (
        id INT AUTO_INCREMENT PRIMARY KEY,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        phase ENUM('work', 'short_break', 'long_break') NOT NULL,
        duration_min INT NOT NULL,
        notes TEXT
    );
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS pomodoro_state (
        id INT PRIMARY KEY DEFAULT 1,
        current_phase ENUM('work','short_break','long_break') NOT NULL,
        remaining_seconds INT NOT NULL,
        notes TEXT,
        subject VARCHAR(255),
        cycles_completed INT DEFAULT 0,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
    );
    """)

    # Inside create_table(), after the existing tables
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS subjects (
        id INT AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(255) NOT NULL UNIQUE,
        paper VARCHAR(50) NULL,
        chapter VARCHAR(50) NULL,
        active BOOLEAN DEFAULT TRUE,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # ---------- Chapters (linked to subjects) ----------
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS chapters (
        id INT AUTO_INCREMENT PRIMARY KEY,
        subject_id INT NOT NULL,
        chapter_code VARCHAR(10) NOT NULL,
        name VARCHAR(255) NOT NULL,
        description TEXT NULL,
        display_order INT DEFAULT 0,
        active BOOLEAN DEFAULT TRUE,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY idx_subject_chapter (subject_id, chapter_code),
        FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
    """)

    # ---- Question supporting tables (from merged converter) ----
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS question_options (
        id INT AUTO_INCREMENT PRIMARY KEY,
        question_id INT NOT NULL,
        text LONGTEXT NOT NULL,
        fraction DECIMAL(10,2) DEFAULT 0.00,
        feedback LONGTEXT,
        display_order INT DEFAULT 0,
        FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS question_matching_pairs (
        id INT AUTO_INCREMENT PRIMARY KEY,
        question_id INT NOT NULL,
        subquestion LONGTEXT NOT NULL,
        answer LONGTEXT NOT NULL,
        display_order INT DEFAULT 0,
        FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS question_hints (
        id INT AUTO_INCREMENT PRIMARY KEY,
        question_id INT NOT NULL,
        hint_text LONGTEXT NOT NULL,
        clear_incorrect BOOLEAN DEFAULT FALSE,
        show_num_correct BOOLEAN DEFAULT FALSE,
        hint_number INT NOT NULL,
        FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
    """)


    # Insert a dummy row if not exists (for easier update)
    cursor.execute("INSERT IGNORE INTO pomodoro_state (id, current_phase, remaining_seconds) VALUES (1, 'work', 0)")
    # Insert default settings if they don't exist
    cursor.execute("INSERT IGNORE INTO pomodoro_settings (id) VALUES (1)")
    # Add subject column to pomodoro_log if missing
    cursor.execute("SHOW COLUMNS FROM pomodoro_log LIKE 'subject'")
    if not cursor.fetchone():
        cursor.execute("ALTER TABLE pomodoro_log ADD COLUMN subject VARCHAR(255) NULL")
        print_colored("[✓] Added 'subject' column to pomodoro_log.", COLORS.GREEN)
    conn.commit()
    cursor.close()
    conn.close()
    print_colored(f"[✓] Tables ready.", COLORS.GREEN)

def migrate_table():
    conn = get_connection()
    cursor = conn.cursor(buffered=True)

    # ---- Fix collation drift before anything else touches the schema ----
    _ensure_unified_collation(cursor)
    conn.commit()

    # Add paper column if missing
    cursor.execute("SHOW COLUMNS FROM youtube_lectures LIKE 'paper'")
    if not cursor.fetchone():
        cursor.execute("ALTER TABLE youtube_lectures ADD COLUMN paper VARCHAR(50) NULL")
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

    # ---- Add youtube_title_updated column ----
    cursor.execute("SHOW COLUMNS FROM youtube_lectures LIKE 'youtube_title_updated'")
    if not cursor.fetchone():
        cursor.execute("ALTER TABLE youtube_lectures ADD COLUMN youtube_title_updated BOOLEAN DEFAULT FALSE")
        print_colored("[✓] Added 'youtube_title_updated' column.", COLORS.GREEN)

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

    cursor.execute("SHOW COLUMNS FROM questions LIKE 'notes'")
    if not cursor.fetchone():
        cursor.execute("ALTER TABLE questions ADD COLUMN notes TEXT NULL")
        print_colored("[✓] Added 'notes' column to questions table.", COLORS.GREEN)

    # ---- ADD THIS BLOCK ----
    cursor.execute("SHOW COLUMNS FROM questions LIKE 'source'")
    if not cursor.fetchone():
        cursor.execute("ALTER TABLE questions ADD COLUMN source VARCHAR(255) NULL")
        print_colored("[✓] Added 'source' column to questions table.", COLORS.GREEN)

    # ---- Add type column to questions if missing ----
    cursor.execute("SHOW COLUMNS FROM questions LIKE 'type'")
    if not cursor.fetchone():
        cursor.execute("ALTER TABLE questions ADD COLUMN type ENUM('multichoice','essay','truefalse','matching') DEFAULT 'essay'")
        print_colored("[✓] Added 'type' column to questions table.", COLORS.GREEN)

    # ---- Handle syllabus_code column (support multiple codes) ----
    cursor.execute("SHOW COLUMNS FROM questions LIKE 'syllabus_code'")
    col = cursor.fetchone()
    if not col:
        cursor.execute("ALTER TABLE questions ADD COLUMN syllabus_code TEXT NULL")
        print_colored("[✓] Added 'syllabus_code' column (TEXT).", COLORS.GREEN)
    else:
        # If it's VARCHAR(50), change to TEXT
        if col[1].lower() == 'varchar(50)':
            cursor.execute("ALTER TABLE questions MODIFY syllabus_code TEXT NULL")
            print_colored("[✓] Changed syllabus_code to TEXT.", COLORS.GREEN)

    # ---- Add index only if missing ----
    cursor.execute("SHOW INDEX FROM questions WHERE Key_name = 'idx_syllabus_code'")
    if not cursor.fetchone():
        # For TEXT columns, we need a prefix length
        cursor.execute("ALTER TABLE questions ADD INDEX idx_syllabus_code (syllabus_code(191))")
        print_colored("[✓] Added index on 'syllabus_code'.", COLORS.GREEN)

    # ---- Backfill syllabus_code from chapter field (enhanced) ----
    import re

    # ---- Backfill syllabus_code from chapter field ----
    # Extract the FIRST code from any parentheses, normalise to numeric form,
    # store as the primary syllabus_code. Does not modify `chapter`.
    from .utils import normalize_syllabus_code

    cursor.execute("""
        SELECT id, chapter FROM questions
        WHERE (syllabus_code IS NULL)
        AND chapter IS NOT NULL AND chapter != ''
    """)
    rows = cursor.fetchall()
    updated = 0

    def _extract_primary_code(chapter_text):
        """Return the first syllabus code found in a chapter description,
        normalised to numeric XX.YY form. Returns None if nothing matches."""
        if not chapter_text:
            return None
        # 1) Codes inside parentheses (any separator: &, /, comma)
        paren_groups = re.findall(r'\(([^)]+)\)', chapter_text)
        for group in paren_groups:
            for candidate in re.split(r'\s*[&/,]\s*', group.strip()):
                c = candidate.strip()
                if c:
                    return normalize_syllabus_code(c)
        # 2) Bare legacy code in the text (e.g. "P1-B6.3" without parens)
        m = re.search(r'P\d-[A-C]\d+\.\d+', chapter_text)
        if m:
            return normalize_syllabus_code(m.group(0))
        # 3) Bare numeric code (already in XX.YY form)
        m = re.search(r'\b(\d{1,2}\.\d{1,2})\b', chapter_text)
        if m:
            parts = m.group(1).split('.')
            return '.'.join(p.zfill(2) for p in parts)
        return None

    for qid, chapter in rows:
        code = _extract_primary_code(chapter)
        if code:
            cursor.execute(
                "UPDATE questions SET syllabus_code = %s WHERE id = %s",
                (code, qid)
            )
            updated += 1

    conn.commit()
    print_colored(f"[✓] Backfilled {updated} syllabus codes from chapter field.", COLORS.GREEN)

    # ---------- Full‑text index for question search ----------
    cursor.execute("SHOW INDEX FROM questions WHERE Key_name = 'ft_search'")
    if not cursor.fetchone():
        cursor.execute("""
            ALTER TABLE questions ADD FULLTEXT INDEX ft_search
            (subject, institution, paper, `group`, chapter,
            nepali_transcription, english_transcription, notes)
        """)
        print_colored("[✓] Added full‑text index ft_search for question search.", COLORS.GREEN)

    # ---- Alias column: role / designation split from level ----
    cursor.execute("SHOW COLUMNS FROM questions LIKE 'alias'")
    if not cursor.fetchone():
        cursor.execute("ALTER TABLE questions ADD COLUMN alias VARCHAR(255) NULL")
        print_colored("[✓] Added 'alias' column to questions.", COLORS.GREEN)

    # One-time backfill: only fires if any 'level' value still contains
    # letters (i.e. a combined "Level 6 (Business Officer)" style string).
    # Silent on databases that are already migrated.
    cursor.execute("""
        SELECT COUNT(*) FROM questions
        WHERE level IS NOT NULL AND level REGEXP '[A-Za-z]'
    """)
    if cursor.fetchone()[0] > 0:
        from .question_bank import split_level_and_alias
        cursor.execute("""
            SELECT id, level FROM questions
            WHERE level IS NOT NULL AND level != ''
        """)
        rows = cursor.fetchall()
        updated = 0
        for qid, lvl in rows:
            num, alias = split_level_and_alias(lvl)
            if num != lvl or alias is not None:
                cursor.execute(
                    "UPDATE questions SET level = %s, alias = %s WHERE id = %s",
                    (num, alias, qid)
                )
                updated += 1
        conn.commit()
        if updated:
            print_colored(f"[✓] Split {updated} level values into number + alias.", COLORS.GREEN)

    # ---- Add all missing columns to questions table ----
    columns_to_add = {
        'source': 'VARCHAR(255) NULL',
        'general_feedback': 'TEXT NULL',
        'fraction_correct': 'DECIMAL(10,2) DEFAULT 100.00',
        'fraction_wrong': 'DECIMAL(10,2) DEFAULT -20.00',
        'shuffle_answers': 'BOOLEAN DEFAULT TRUE',
        'show_num_correct': 'BOOLEAN DEFAULT FALSE',
        'correct_feedback': 'TEXT NULL',
        'partially_correct_feedback': 'TEXT NULL',
        'incorrect_feedback': 'TEXT NULL',
        'response_lines': 'INT DEFAULT 15',
        'attachments': 'INT DEFAULT 0',
        'filetypes': "VARCHAR(255) DEFAULT '.doc,.docx,.pdf,.png,.jpg,.jpeg'",
        'maxbytes': 'INT DEFAULT 2097152',
        'grader_info': 'TEXT NULL',
    }
    for col, definition in columns_to_add.items():
        cursor.execute(f"SHOW COLUMNS FROM questions LIKE '{col}'")
        if not cursor.fetchone():
            cursor.execute(f"ALTER TABLE questions ADD COLUMN {col} {definition}")
            print_colored(f"[✓] Added '{col}' column to questions.", COLORS.GREEN)

    # ---- New columns added after v3.0.0 ----
    newer_columns = {
        'feedback_true':  'TEXT NULL',
        'feedback_false': 'TEXT NULL',
        'penalty':        'DECIMAL(10,2) DEFAULT 0.00',
        # Exam type: open / internal / promotional / other
        'exam_type':      "VARCHAR(50) DEFAULT 'open'",
    }
    for col, definition in newer_columns.items():
        cursor.execute(f"SHOW COLUMNS FROM questions LIKE '{col}'")
        if not cursor.fetchone():
            cursor.execute(f"ALTER TABLE questions ADD COLUMN {col} {definition}")
            print_colored(f"[✓] Added '{col}' column to questions.", COLORS.GREEN)

    # ---- Add unique constraint ----
    cursor.execute("SHOW INDEX FROM questions WHERE Key_name = 'unique_question'")
    if not cursor.fetchone():
        try:
            cursor.execute("""
                ALTER TABLE questions ADD UNIQUE INDEX unique_question
                (question_date, institution, level, paper, `group`, question_number)
            """)
            print_colored("[✓] Added unique constraint on (date, institution, level, paper, group, question_number).", COLORS.GREEN)
        except mysql.connector.Error as e:
            print_colored(f"[!] Could not add unique constraint: {e}", COLORS.RED)
            print_colored("[i] You may have duplicate entries. Clean them up first.", COLORS.YELLOW)

    # ---- Ensure supporting tables exist (if they were not created in create_table) ----
    cursor.execute("SHOW TABLES LIKE 'question_options'")
    if not cursor.fetchone():
        cursor.execute("""
        CREATE TABLE question_options (
            id INT AUTO_INCREMENT PRIMARY KEY,
            question_id INT NOT NULL,
            text LONGTEXT NOT NULL,
            fraction DECIMAL(10,2) DEFAULT 0.00,
            feedback LONGTEXT,
            display_order INT DEFAULT 0,
            FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
        """)
        print_colored("[✓] Created question_options table.", COLORS.GREEN)

    cursor.execute("SHOW TABLES LIKE 'question_matching_pairs'")
    if not cursor.fetchone():
        cursor.execute("""
        CREATE TABLE question_matching_pairs (
            id INT AUTO_INCREMENT PRIMARY KEY,
            question_id INT NOT NULL,
            subquestion LONGTEXT NOT NULL,
            answer LONGTEXT NOT NULL,
            display_order INT DEFAULT 0,
            FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
        """)
        print_colored("[✓] Created question_matching_pairs table.", COLORS.GREEN)

    cursor.execute("SHOW TABLES LIKE 'question_hints'")
    if not cursor.fetchone():
        cursor.execute("""
        CREATE TABLE question_hints (
            id INT AUTO_INCREMENT PRIMARY KEY,
            question_id INT NOT NULL,
            hint_text LONGTEXT NOT NULL,
            clear_incorrect BOOLEAN DEFAULT FALSE,
            show_num_correct BOOLEAN DEFAULT FALSE,
            hint_number INT NOT NULL,
            FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
        """)
        print_colored("[✓] Created question_hints table.", COLORS.GREEN)

    # ---- ADD THIS BLOCK ----
    cursor.execute("SHOW COLUMNS FROM questions LIKE 'source'")
    if not cursor.fetchone():
        cursor.execute("ALTER TABLE questions ADD COLUMN source VARCHAR(255) NULL")
        print_colored("[✓] Added 'source' column to questions table.", COLORS.GREEN)

    # ---- Instapaper credentials table ----
    cursor.execute("SHOW TABLES LIKE 'instapaper_credentials'")
    if not cursor.fetchone():
        cursor.execute("""
        CREATE TABLE instapaper_credentials (
            id INT PRIMARY KEY DEFAULT 1,
            consumer_key VARCHAR(255) NOT NULL,
            consumer_secret VARCHAR(255) NOT NULL,
            username VARCHAR(255) NOT NULL,
            password VARCHAR(255) NOT NULL
        );
        """)
        print_colored("[✓] Created 'instapaper_credentials' table.", COLORS.GREEN)
    # instapaper_articles
    cursor.execute("SHOW TABLES LIKE 'instapaper_articles'")
    if not cursor.fetchone():
        cursor.execute("""
        CREATE TABLE instapaper_articles (
            id INT AUTO_INCREMENT PRIMARY KEY,
            bookmark_id VARCHAR(32) UNIQUE,
            url VARCHAR(512) NOT NULL,
            title VARCHAR(512),
            author VARCHAR(255),
            content LONGTEXT,
            saved_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        );
        """)
        print_colored("[✓] Created 'instapaper_articles' table.", COLORS.GREEN)
    # oauth token
    cursor.execute("SHOW COLUMNS FROM instapaper_credentials LIKE 'oauth_token'")
    if not cursor.fetchone():
        cursor.execute("ALTER TABLE instapaper_credentials ADD COLUMN oauth_token VARCHAR(255) NULL")
        cursor.execute("ALTER TABLE instapaper_credentials ADD COLUMN oauth_secret VARCHAR(255) NULL")
        print_colored("[✓] Added OAuth columns to instapaper_credentials.", COLORS.GREEN)
        # ---- NEW: Instapaper OAuth tokens table ----
    cursor.execute("SHOW TABLES LIKE 'instapaper_oauth'")
    if not cursor.fetchone():
        cursor.execute("""
        CREATE TABLE instapaper_oauth (
            id INT PRIMARY KEY DEFAULT 1,
            oauth_token VARCHAR(255) NOT NULL,
            oauth_secret VARCHAR(255) NOT NULL
        );
        """)
        print_colored("[✓] Created 'instapaper_oauth' table.", COLORS.GREEN)
    # Ensure pomodoro_state table exists
    cursor.execute("SHOW TABLES LIKE 'pomodoro_state'")
    if not cursor.fetchone():
        cursor.execute("""
        CREATE TABLE pomodoro_state (
            id INT PRIMARY KEY DEFAULT 1,
            current_phase ENUM('work','short_break','long_break') NOT NULL,
            remaining_seconds INT NOT NULL,
            notes TEXT,
            subject VARCHAR(255),
            cycles_completed INT DEFAULT 0,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        );
        """)
        cursor.execute("INSERT INTO pomodoro_state (id, current_phase, remaining_seconds) VALUES (1, 'work', 0)")
        print_colored("[✓] Created pomodoro_state table.", COLORS.GREEN)

    cursor.execute("SHOW COLUMNS FROM pomodoro_state LIKE 'session_type'")
    if not cursor.fetchone():
        cursor.execute("ALTER TABLE pomodoro_state ADD COLUMN session_type VARCHAR(50) NULL")
        print_colored("[✓] Added 'session_type' column to pomodoro_state.", COLORS.GREEN)

    cursor.execute("SHOW COLUMNS FROM pomodoro_state LIKE 'task_id'")
    if not cursor.fetchone():
        cursor.execute("ALTER TABLE pomodoro_state ADD COLUMN task_id INT NULL")
        print_colored("[✓] Added 'task_id' column to pomodoro_state.", COLORS.GREEN)

    # --- Add subject_id and session_type to pomodoro_log ---
    cursor.execute("SHOW COLUMNS FROM pomodoro_log LIKE 'subject_id'")
    if not cursor.fetchone():
        cursor.execute("ALTER TABLE pomodoro_log ADD COLUMN subject_id INT NULL")
        cursor.execute("ALTER TABLE pomodoro_log ADD FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE SET NULL")
    # ---- session_type column ----
    cursor.execute("SHOW COLUMNS FROM pomodoro_log LIKE 'session_type'")
    col = cursor.fetchone()
    if col:
        # If it's ENUM, change to VARCHAR; if already VARCHAR, nothing changes
        cursor.execute("ALTER TABLE pomodoro_log MODIFY session_type VARCHAR(50) DEFAULT 'study'")
        print_colored("[✓] session_type column updated to VARCHAR(50).", COLORS.GREEN)
    else:
        cursor.execute("ALTER TABLE pomodoro_log ADD COLUMN session_type VARCHAR(50) DEFAULT 'study'")
        print_colored("[✓] Added session_type column (VARCHAR).", COLORS.GREEN)

    # --- Optional: add subject_goals to pomodoro_settings ---
    cursor.execute("SHOW COLUMNS FROM pomodoro_settings LIKE 'subject_goals'")
    if not cursor.fetchone():
        cursor.execute("ALTER TABLE pomodoro_settings ADD COLUMN subject_goals JSON NULL")
        cursor.execute("ALTER TABLE pomodoro_settings ADD COLUMN revision_goals JSON NULL")

    # Add weekly and monthly goal columns to pomodoro_settings
    cursor.execute("SHOW COLUMNS FROM pomodoro_settings LIKE 'weekly_goal_hours'")
    if not cursor.fetchone():
        cursor.execute("ALTER TABLE pomodoro_settings ADD COLUMN weekly_goal_hours INT NOT NULL DEFAULT 10")

    cursor.execute("SHOW COLUMNS FROM pomodoro_settings LIKE 'monthly_goal_hours'")
    if not cursor.fetchone():
        cursor.execute("ALTER TABLE pomodoro_settings ADD COLUMN monthly_goal_hours INT NOT NULL DEFAULT 40")

    # Add task_id column if missing
    cursor.execute("SHOW COLUMNS FROM pomodoro_log LIKE 'task_id'")
    if not cursor.fetchone():
        cursor.execute("ALTER TABLE pomodoro_log ADD COLUMN task_id INT NULL")
        cursor.execute("ALTER TABLE pomodoro_log ADD FOREIGN KEY (task_id) REFERENCES pomodoro_tasks(id) ON DELETE SET NULL")
        print_colored("[✓] Added 'task_id' column to pomodoro_log.", COLORS.GREEN)

    # Add priority and completed columns to pomodoro_tasks if missing
    cursor.execute("SHOW COLUMNS FROM pomodoro_tasks LIKE 'priority'")
    if not cursor.fetchone():
        cursor.execute("ALTER TABLE pomodoro_tasks ADD COLUMN priority INT DEFAULT 3")
    cursor.execute("SHOW COLUMNS FROM pomodoro_tasks LIKE 'completed'")
    if not cursor.fetchone():
        cursor.execute("ALTER TABLE pomodoro_tasks ADD COLUMN completed BOOLEAN DEFAULT FALSE")

    # 1. Badges table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS pomodoro_badges (
        id INT AUTO_INCREMENT PRIMARY KEY,
        badge_name VARCHAR(50) NOT NULL UNIQUE,
        description VARCHAR(255),
        icon CHAR(2)  -- emoji icon
    );
    """)

    # 2. User badges (earned)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_badges (
        id INT AUTO_INCREMENT PRIMARY KEY,
        badge_name VARCHAR(50) NOT NULL,
        earned_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (badge_name) REFERENCES pomodoro_badges(badge_name) ON DELETE CASCADE
    );
    """)

    # 3. Pauses log (for interruption tracking)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS pomodoro_pauses (
        id INT AUTO_INCREMENT PRIMARY KEY,
        session_id INT NOT NULL,  -- references pomodoro_log.id
        pause_start DATETIME NOT NULL,
        pause_end DATETIME,
        duration_sec INT,
        FOREIGN KEY (session_id) REFERENCES pomodoro_log(id) ON DELETE CASCADE
    );
    """)

    # Ensure subjects table exists and is populated
    cursor.execute("SHOW TABLES LIKE 'subjects'")
    if not cursor.fetchone():
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS subjects (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(255) NOT NULL UNIQUE,
            paper ENUM('pretest','paper_i','paper_ii','paper_iii') NULL,
            chapter VARCHAR(50) NULL,
            active BOOLEAN DEFAULT TRUE,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        """)
        print_colored("[✓] Created subjects table.", COLORS.GREEN)

    # ---- Add unique index on subjects.name to prevent duplicates ----
    cursor.execute("SHOW INDEX FROM subjects WHERE Key_name = 'idx_name'")
    if not cursor.fetchone():
        print_colored("[i] Adding unique index on subjects.name...", COLORS.YELLOW)
        try:
            cursor.execute("ALTER TABLE subjects ADD UNIQUE INDEX idx_name (name)")
            print_colored("[✓] Added unique index on subjects.name", COLORS.GREEN)
        except mysql.connector.Error as e:
            if e.errno == 1062:
                print_colored("[!] Cannot add unique index: duplicate subject names exist.", COLORS.RED)
                print("   Please remove duplicates manually and restart the system.")
            else:
                print_colored(f"[!] Failed to add unique index: {e}", COLORS.RED)

    # 4. Add pause_count and pause_total_sec to pomodoro_log (optional, for quick stats)
    cursor.execute("SHOW COLUMNS FROM pomodoro_log LIKE 'pause_count'")
    if not cursor.fetchone():
        cursor.execute("ALTER TABLE pomodoro_log ADD COLUMN pause_count INT DEFAULT 0")
        cursor.execute("ALTER TABLE pomodoro_log ADD COLUMN pause_total_sec INT DEFAULT 0")

    # 5. Pre‑seed badges
    badges = [
        ('first_pomodoro', 'Completed your first Pomodoro', '🌟'),
        ('ten_sessions', 'Completed 10 work sessions', '🏅'),
        ('fifty_sessions', 'Completed 50 work sessions', '🥈'),
        ('hundred_sessions', 'Completed 100 work sessions', '🥇'),
        ('five_day_streak', 'Studied for 5 days in a row', '🔥'),
        ('ten_day_streak', 'Studied for 10 days in a row', '💎'),
        ('early_bird', 'Completed a session before 8 AM', '🌅'),
        ('night_owl', 'Completed a session after 10 PM', '🌙'),
        ('subject_specialist', 'Spent 5+ hours on one subject', '📚'),
        ('balanced_learner', 'Studied 3+ subjects in a week', '⚖️'),
    ]
    for badge_name, desc, icon in badges:
        cursor.execute("INSERT IGNORE INTO pomodoro_badges (badge_name, description, icon) VALUES (%s, %s, %s)",
                    (badge_name, desc, icon))

    # ---- Add unique index on user_badges.badge_name to prevent duplicate entries ----
    cursor.execute("SHOW INDEX FROM user_badges WHERE Key_name = 'idx_badge_name'")
    if not cursor.fetchone():
        try:
            cursor.execute("ALTER TABLE user_badges ADD UNIQUE INDEX idx_badge_name (badge_name)")
            print_colored("[✓] Added unique index on user_badges.badge_name", COLORS.GREEN)
        except mysql.connector.Error as e:
            print_colored(f"[!] Could not add unique index: {e}", COLORS.RED)
            print_colored("[i] You may have duplicate badge entries. Run: DELETE u1 FROM user_badges u1 INNER JOIN user_badges u2 WHERE u1.id > u2.id AND u1.badge_name = u2.badge_name;", COLORS.YELLOW)
        # ---- Fix duplicate transcriptions (one-time cleanup) ----
        try:
            cursor.execute("""
                SELECT COUNT(*) FROM questions
                WHERE nepali_transcription IS NOT NULL
                AND english_transcription IS NOT NULL
                AND nepali_transcription != ''
                AND english_transcription != ''
                AND nepali_transcription = english_transcription
            """)
            dup_count = cursor.fetchone()[0]
            if dup_count > 0:
                print_colored(f"[i] Found {dup_count} questions with duplicate transcriptions. Cleaning up...", COLORS.YELLOW)

                # Keep Nepali if Devanagari is present
                cursor.execute("""
                    UPDATE questions
                    SET english_transcription = ''
                    WHERE nepali_transcription IS NOT NULL
                    AND english_transcription IS NOT NULL
                    AND nepali_transcription != ''
                    AND english_transcription != ''
                    AND nepali_transcription = english_transcription
                    AND nepali_transcription REGEXP '[ऀ-ॿ]'
                """)
                devanagari_updated = cursor.rowcount

                # Keep English if no Devanagari
                cursor.execute("""
                    UPDATE questions
                    SET nepali_transcription = ''
                    WHERE nepali_transcription IS NOT NULL
                    AND english_transcription IS NOT NULL
                    AND nepali_transcription != ''
                    AND english_transcription != ''
                    AND nepali_transcription = english_transcription
                    AND NOT (nepali_transcription REGEXP '[ऀ-ॿ]')
                """)
                english_updated = cursor.rowcount

                conn.commit()
                print_colored(f"[✓] Fixed {devanagari_updated + english_updated} duplicate transcriptions "
                            f"({devanagari_updated} kept Nepali, {english_updated} kept English).", COLORS.GREEN)
            else:
                print_colored("[✓] No duplicate transcriptions found.", COLORS.GREEN)
        except Exception as e:
            print_colored(f"[!] Failed to clean duplicate transcriptions: {e}", COLORS.RED)

    # ---- Add full‑text index for faster search ----
    cursor.execute("SHOW INDEX FROM youtube_lectures WHERE Key_name = 'ft_search'")
    if not cursor.fetchone():
        print_colored("[i] Adding full‑text index on youtube_lectures...", COLORS.BLUE)
        cursor.execute("ALTER TABLE youtube_lectures ADD FULLTEXT INDEX ft_search (syllabus_id, subject, chapter, lecturer, notes, video_title)")
        print_colored("[✓] Full‑text index added.", COLORS.GREEN)

    # ---------- Papers table (user-definable) ----------
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS papers (
        id INT AUTO_INCREMENT PRIMARY KEY,
        paper_key VARCHAR(50) NOT NULL UNIQUE,     -- 'paper_i', 'semester_3'
        display_name VARCHAR(255) NOT NULL,        -- 'First Paper: Economics'
        folder_name VARCHAR(255) NOT NULL,         -- 'First Paper: Economics'
        keywords TEXT,                             -- comma-separated for auto-detect
        active BOOLEAN DEFAULT TRUE,
        display_order INT DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
    """)

    # ---------- Relax ENUMs to VARCHAR (only if still ENUM) ----------
    for tbl, col in [('youtube_lectures', 'paper'), ('subjects', 'paper')]:
        cursor.execute(f"""
            SELECT DATA_TYPE, COLUMN_TYPE FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_NAME = %s
        """, (tbl, col))
        row = cursor.fetchone()
        if row and row[0].lower() == 'enum':
            cursor.execute(f"ALTER TABLE {tbl} MODIFY {col} VARCHAR(50) NULL")
            print_colored(f"[✓] Converted {tbl}.{col} from ENUM to VARCHAR.", COLORS.GREEN)

    # ---------- Backfill papers table from legacy hardcoded keys ----------
    # Runs only when the papers table is empty AND legacy paper keys exist in DB.
    # This makes existing installs keep working without losing anything.
    cursor.execute("SELECT COUNT(*) FROM papers")
    paper_count = cursor.fetchone()[0]

    if paper_count == 0:
        # Collect paper keys actually used in the DB
        cursor.execute("SELECT DISTINCT paper FROM subjects WHERE paper IS NOT NULL AND paper != ''")
        used_keys = [row[0] for row in cursor.fetchall()]
        cursor.execute("SELECT DISTINCT paper FROM youtube_lectures WHERE paper IS NOT NULL AND paper != ''")
        for row in cursor.fetchall():
            if row[0] not in used_keys:
                used_keys.append(row[0])

        if used_keys:
            print_colored(f"[i] Backfilling {len(used_keys)} legacy paper(s) into 'papers' table...", COLORS.BLUE)
            LEGACY_FOLDERS = {
                'pretest':   'Pretest Officer',
                'paper_i':   'First Paper: Economics',
                'paper_ii':  'Second Paper: Management',
                'paper_iii': 'Third Paper: Research Methodologies, ICT and Banking Laws & Regulation',
            }
            LEGACY_KEYWORDS = {
                'pretest':   'gk,pretest,english,nepali,geography,history,constitution',
                'paper_i':   'microeconomics,development economics,public economics,macroeconomics,economics',
                'paper_ii':  'general management,human resource,financial economics,managerial economics',
                'paper_iii': 'research methodology,information technology,ict,banking laws,regulations',
            }
            # Canonical order for legacy keys so menus render naturally
            LEGACY_ORDER = {
                'pretest':   10,
                'paper_i':   20,
                'paper_ii':  30,
                'paper_iii': 40,
            }
            for idx, key in enumerate(used_keys):
                folder = LEGACY_FOLDERS.get(key, key.replace('_', ' ').title())
                keywords = LEGACY_KEYWORDS.get(key, '')
                display_order = LEGACY_ORDER.get(key, 100 + idx)
                cursor.execute("""
                    INSERT IGNORE INTO papers (paper_key, display_name, folder_name, keywords, display_order)
                    VALUES (%s, %s, %s, %s, %s)
                """, (key, folder, folder, keywords, display_order))
            print_colored(f"[✓] Backfilled {len(used_keys)} legacy paper(s).", COLORS.GREEN)
        else:
            print_colored("[i] Fresh install — no legacy papers to backfill.", COLORS.BLUE)

    conn.commit()
    cursor.close()
    conn.close()

def ensure_subjects_populated():
    from .syllabus_config import is_configured
    if not is_configured():
        print_colored("[i] No syllabus configured yet. "
                      "Use '📚 Syllabus Setup' or load the default template.",
                      COLORS.YELLOW)
        return
    print_colored("[✓] Syllabus is configured.", COLORS.BLUE)

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
