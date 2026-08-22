#!/data/data/com.termux/files/usr/bin/bash

# ============================================================
# lecture-manager.sh – Termux launcher with auto‑update,
# database management (keep/delete), and import of exports.
# ============================================================

set -e

# ---------- CONFIGURATION (edit these) ----------
# Database action: "keep" (create if missing, don't drop) or "delete" (drop & recreate)
DB_ACTION="keep"

# Force reinstall of Python packages (set to "yes" to force, "no" to skip if installed)
FORCE_REINSTALL="no"

# Automatically import export files found in ~/ and ~/storage/ (overwrite, then delete)
AUTO_IMPORT_EXPORTS="yes"
# ------------------------------------------------

REPO_URL="https://github.com/blee-design/lecture-manager.git"
REPO_DIR="$HOME/lecture-manager"
VENV_DIR="$HOME/venv"
DB_NAME="fox"
DB_USER="lecture_user"
DB_PASS_FILE="$REPO_DIR/.db_pass"
ROOT_PASS_FILE="$REPO_DIR/.mysql_root_pass"
WEB_PID_FILE="$REPO_DIR/.web.pid"
MARIADB_PID_FILE="$REPO_DIR/.mariadb.pid"
CLEANUP_DONE=0
DEFAULT_ROOT_PASS="root"
CONFIG_FILE="$HOME/.lecture_manager_config.json"

# ---------- Colors ----------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# ---------- Trap ----------
cleanup() {
    if [[ $CLEANUP_DONE -eq 1 ]]; then
        return
    fi
    CLEANUP_DONE=1
    info "Cleaning up..."
    if [[ -f "$WEB_PID_FILE" ]]; then
        local pid=$(cat "$WEB_PID_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            info "Stopping web server (PID $pid)..."
            kill -TERM "$pid" 2>/dev/null && wait "$pid" 2>/dev/null || true
        fi
        rm -f "$WEB_PID_FILE"
    fi
    if [[ -f "$MARIADB_PID_FILE" ]]; then
        local pid=$(cat "$MARIADB_PID_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            info "Stopping MariaDB (PID $pid)..."
            kill -TERM "$pid" 2>/dev/null && wait "$pid" 2>/dev/null || true
        fi
        rm -f "$MARIADB_PID_FILE"
    fi
    info "Cleanup done. Goodbye!"
    exit 0
}
trap cleanup EXIT INT TERM

# ---------- Package manager: apt (preferred) or pkg (fallback) ----------
install_pkg() {
    local pkg_name="$1"
    if command -v apt &>/dev/null; then
        sudo apt update && sudo apt install -y "$pkg_name"
    elif command -v pkg &>/dev/null; then
        pkg install -y "$pkg_name"
    else
        error "No supported package manager (apt or pkg)."
    fi
}

# ---------- System dependencies ----------
check_deps() {
    info "Checking system dependencies..."
    local deps=(git python mariadb ffmpeg cmake ninja libxml2 libxslt pkg-config openssl libffi stow)
    for pkg in "${deps[@]}"; do
        if ! pkg list-installed 2>/dev/null | grep -q "^$pkg"; then
            info "Installing $pkg..."
            install_pkg "$pkg" || warn "Failed to install $pkg"
        fi
    done
    for py_pkg in python-cryptography python-numpy python-matplotlib; do
        if ! pkg list-installed 2>/dev/null | grep -q "^$py_pkg"; then
            install_pkg "$py_pkg" 2>/dev/null || warn "$py_pkg not available via pkg"
        fi
    done
}

# ---------- Python interpreter ----------
find_python() {
    for ver in 3.12 3.11 3; do
        if command -v "python$ver" >/dev/null 2>&1; then
            echo "python$ver"
            return
        fi
    done
    error "No Python 3 found. Install with 'pkg install python'."
}

# ---------- MariaDB helpers ----------
is_mariadb_running() {
    pgrep -f "mariadbd" >/dev/null 2>&1
}

wait_for_mariadb() {
    local retries=0
    while [[ $retries -lt 15 ]]; do
        sleep 1
        if is_mariadb_running; then
            return 0
        fi
        ((retries++))
    done
    return 1
}

# ---------- Get root password (auto-detects empty password) ----------
get_root_password() {
    # 1. Try empty password (common in Termux)
    if mysql -u root -e "SELECT 1" >/dev/null 2>&1; then
        echo "" > "$ROOT_PASS_FILE"
        echo ""
        return
    fi

    # 2. Try saved password
    if [[ -f "$ROOT_PASS_FILE" ]]; then
        local saved_pw=$(cat "$ROOT_PASS_FILE")
        if MYSQL_PWD="$saved_pw" mysql -u root -e "SELECT 1" >/dev/null 2>&1; then
            echo "$saved_pw"
            return
        else
            warn "Saved root password is incorrect. Removing it."
            rm -f "$ROOT_PASS_FILE"
        fi
    fi

    # 3. Try default "root"
    if MYSQL_PWD="$DEFAULT_ROOT_PASS" mysql -u root -e "SELECT 1" >/dev/null 2>&1; then
        echo "$DEFAULT_ROOT_PASS" > "$ROOT_PASS_FILE"
        echo "$DEFAULT_ROOT_PASS"
        return
    fi

    # 4. Prompt for password
    warn "MariaDB root password is required."
    while true; do
        read -s -p "Enter MariaDB root password: " pw
        echo
        if MYSQL_PWD="$pw" mysql -u root -e "SELECT 1" >/dev/null 2>&1; then
            echo "$pw" > "$ROOT_PASS_FILE"
            echo "$pw"
            return
        else
            warn "Incorrect password. Try again."
        fi
    done
}

# ---------- Write lecture-manager config ----------
write_config() {
    local db_host="localhost"
    local db_port="3306"
    local db_name="$DB_NAME"
    local db_user="$DB_USER"
    local db_pass="$1"

    cat > "$CONFIG_FILE" << EOF
{
    "host": "$db_host",
    "database": "$db_name",
    "user": "$db_user",
    "password": "$db_pass",
    "port": $db_port
}
EOF
    info "Configuration saved to $CONFIG_FILE"
}

# ---------- MariaDB setup ----------
setup_db() {
    mkdir -p "$REPO_DIR"

    info "Checking MariaDB..."

    if [[ -f "$MARIADB_PID_FILE" ]]; then
        local old_pid=$(cat "$MARIADB_PID_FILE")
        if ! kill -0 "$old_pid" 2>/dev/null; then
            warn "Stale MariaDB PID file found. Removing it."
            rm -f "$MARIADB_PID_FILE"
        fi
    fi

    if is_mariadb_running; then
        local existing_pid=$(pgrep -f "mariadbd" | head -1)
        info "MariaDB already running (PID $existing_pid). Using existing instance."
        [[ -f "$MARIADB_PID_FILE" ]] && rm -f "$MARIADB_PID_FILE"
    else
        info "Starting MariaDB..."
        mariadbd-safe &
        if ! wait_for_mariadb; then
            error "MariaDB failed to start. Check log: $PREFIX/var/lib/mysql/kali.err"
        fi
        local new_pid=$(pgrep -f "mariadbd" | head -1)
        echo "$new_pid" > "$MARIADB_PID_FILE"
        info "MariaDB started with PID $new_pid (will be stopped on exit)."
    fi

    local root_pw=$(get_root_password)
    export MYSQL_PWD="$root_pw"
    local mysql_cmd="mysql -u root"

    if [[ ! -f "$DB_PASS_FILE" ]]; then
        DB_PASS=$(tr -dc 'a-zA-Z0-9!@#$%^&*()_+' < /dev/urandom 2>/dev/null | head -c 20)
        echo "$DB_PASS" > "$DB_PASS_FILE"
        info "Generated app user password: $DB_PASS"
    else
        DB_PASS=$(cat "$DB_PASS_FILE")
        info "Using existing app password."
    fi

    # ---- Database action: delete or keep ----
    if [[ "$DB_ACTION" == "delete" ]]; then
        warn "Dropping database '$DB_NAME' (all data will be lost)..."
        $mysql_cmd -e "DROP DATABASE IF EXISTS $DB_NAME;"
        info "Database dropped."
    fi

    $mysql_cmd -e "CREATE DATABASE IF NOT EXISTS $DB_NAME;"
    local user_exists=$($mysql_cmd -sN -e "SELECT EXISTS(SELECT 1 FROM mysql.user WHERE user = '$DB_USER' AND host = 'localhost');")
    if [[ "$user_exists" != "1" ]]; then
        $mysql_cmd -e "CREATE USER '$DB_USER'@'localhost' IDENTIFIED BY '$DB_PASS';"
    fi
    $mysql_cmd -e "GRANT ALL PRIVILEGES ON $DB_NAME.* TO '$DB_USER'@'localhost'; FLUSH PRIVILEGES;"

    unset MYSQL_PWD
    export DATABASE_URL="mysql+pymysql://$DB_USER:$DB_PASS@localhost:3306/$DB_NAME"
    info "Database ready."

    # ---- Write config file ----
    write_config "$DB_PASS"
}

# ---------- Repository ----------
setup_repo() {
    info "Setting up repository..."
    if [[ -d "$REPO_DIR/.git" ]]; then
        cd "$REPO_DIR"
        # Check if we need to pull
        git fetch --quiet
        LOCAL=$(git rev-parse HEAD)
        REMOTE=$(git rev-parse @{u} 2>/dev/null || echo "")
        if [[ -n "$REMOTE" && "$LOCAL" != "$REMOTE" ]]; then
            info "Updates available. Pulling..."
            git pull --rebase || warn "Git pull failed."
        else
            info "Repository already up‑to‑date."
        fi
    else
        git clone "$REPO_URL" "$REPO_DIR" || error "Clone failed."
        cd "$REPO_DIR"
    fi

    # Update this script if it has changed (if we are inside the repo)
    SCRIPT_SOURCE="$REPO_DIR/lecture-manager.sh"
    if [[ -f "$SCRIPT_SOURCE" && "$0" != "$SCRIPT_SOURCE" ]]; then
        if ! cmp -s "$0" "$SCRIPT_SOURCE"; then
            info "This script has been updated. Copying newer version..."
            cp "$SCRIPT_SOURCE" "$0"
            chmod +x "$0"
            info "Script updated. Please restart."
            exit 0
        fi
    fi
}

# ---------- Virtual environment ----------
setup_venv() {
    local python_cmd=$(find_python)
    info "Using Python: $python_cmd"

    if [[ ! -d "$VENV_DIR" ]]; then
        info "Creating new venv at $VENV_DIR..."
        $python_cmd -m venv "$VENV_DIR" || error "Failed to create venv."
    fi

    source "$VENV_DIR/bin/activate"
    info "Activated venv."

    pip install --upgrade pip

    # Install or update lecture-manager
    if [[ "$FORCE_REINSTALL" == "yes" ]] || ! python -c "import lecture_manager" >/dev/null 2>&1; then
        info "Installing/updating lecture-manager package..."
        cd "$REPO_DIR"
        pip install -e . || warn "Failed to install lecture-manager."
    else
        info "lecture-manager already installed. (Set FORCE_REINSTALL=yes to reinstall)"
    fi

    # Install optional heavy packages only if missing
    for pkg in numpy matplotlib scipy pandas; do
        if ! python -c "import $pkg" >/dev/null 2>&1; then
            info "Installing $pkg (may take a while)..."
            pip install --index-url https://www.piwheels.org/simple $pkg 2>/dev/null || pip install $pkg
        fi
    done

    info "Virtual environment ready."
}

# ---------- Import exported lecture files ----------
import_exports() {
    if [[ "$AUTO_IMPORT_EXPORTS" != "yes" ]]; then
        info "Auto‑import disabled. Skipping."
        return
    fi

    info "Searching for exported lecture files to import..."
    source "$VENV_DIR/bin/activate"

    # Added ~/storage/shared/ to the search list
    # SEARCH_DIRS=("$HOME" "$HOME/storage" "$HOME/storage/shared" "$HOME/storage/downloads" "$HOME/downloads")
    SEARCH_DIRS=("$HOME/storage/downloads" "$HOME/downloads")
    FOUND_FILES=()

    for dir in "${SEARCH_DIRS[@]}"; do
        if [[ -d "$dir" ]]; then
            for pattern in "lectures_export*.csv" "lectures_export*.json"; do
                for file in "$dir"/$pattern; do
                    if [[ -f "$file" ]]; then
                        FOUND_FILES+=("$file")
                    fi
                done
            done
        fi
    done

    if [[ ${#FOUND_FILES[@]} -eq 0 ]]; then
        info "No export files found. Skipping import."
        return
    fi

    info "Found ${#FOUND_FILES[@]} export file(s)."

    # Use the venv's Python to run the import (overwrite mode)
    for file in "${FOUND_FILES[@]}"; do
        info "Importing: $file"
        if python -c "
import sys, json, csv
from lecture_manager.export import _import_rows

def import_file(filepath):
    ext = filepath.split('.')[-1].lower()
    try:
        if ext == 'csv':
            with open(filepath, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                rows = list(reader)
        elif ext == 'json':
            with open(filepath, 'r', encoding='utf-8') as f:
                rows = json.load(f)
        else:
            print(f'Unsupported extension: {ext}')
            return False
        if not rows:
            print('No data found.')
            return False
        # choice='2' means overwrite existing
        _import_rows(rows, ext.upper(), choice='2')
        return True
    except Exception as e:
        print(f'Import failed: {e}')
        return False

sys.exit(0 if import_file('$file') else 1)
" ; then
            info "Import successful. Deleting $file"
            rm -f "$file"
        else
            warn "Import failed for $file. Keeping file for manual inspection."
        fi
    done
}

# ---------- Run web server ----------
run_web() {
    info "Starting web server..."
    cd "$REPO_DIR"
    source "$VENV_DIR/bin/activate"
    export DATABASE_URL="${DATABASE_URL:-mysql+pymysql://$DB_USER:$DB_PASS@localhost:3306/$DB_NAME}"

    # Apply any pending database migrations
    python -c "from lecture_manager.db import migrate_table; migrate_table()" || warn "Migration failed."

    if command -v make >/dev/null 2>&1 && grep -q "^web:" Makefile 2>/dev/null; then
        make web &
    else
        python lecture.py &
    fi
    local pid=$!
    echo $pid > "$WEB_PID_FILE"
    info "Web server started (PID $pid). Press Ctrl+C to stop."
    wait $pid
}

# ---------- Main ----------
main() {
    info "===== lecture-manager Termux launcher ====="
    check_deps
    setup_repo          # Clone/pull and update script
    setup_db            # Database (keep or delete) and write config
    setup_venv          # Virtual environment and dependencies
    import_exports      # Import export files (overwrite & delete)
    run_web             # Start the web server
}

main
