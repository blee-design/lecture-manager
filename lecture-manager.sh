#!/data/data/com.termux/files/usr/bin/bash
# ============================================================
#  lecture-manager.sh — automatic installer & launcher
#  Works on Termux (Android) and any Linux with pkg/apt/dnf/pacman
#  Version: 4.0
# ============================================================

set -u   # report unset vars, but don't abort on every error

# ------------------------------------------------------------
#  USER CONFIGURATION
# ------------------------------------------------------------
DB_ACTION="keep"           # "keep" or "delete" (delete = fresh DB)
FORCE_REINSTALL="no"       # "yes" forces pip reinstall of the package
AUTO_IMPORT_EXPORTS="yes"  # "yes" auto-imports lectures_export*.csv/json

REPO_URL="https://github.com/blee-design/lecture-manager.git"
REPO_DIR="$HOME/lecture-manager"
VENV_DIR="$HOME/venv"
DB_NAME="fox"
DB_USER="lecture_user"
DB_PASS_FILE="$REPO_DIR/.db_pass"
ROOT_PASS_FILE="$REPO_DIR/.mysql_root_pass"
WEB_PID_FILE="$REPO_DIR/.web.pid"
MARIADB_PID_FILE="$REPO_DIR/.mariadb.pid"
CONFIG_FILE="$HOME/.lecture_manager_config.json"
HOME_SCRIPT="$HOME/lecture-manager.sh"
DEFAULT_ROOT_PASS="root"
WEB_PORT="5000"

# ------------------------------------------------------------
#  COLORS & LOGGING
# ------------------------------------------------------------
if [ -t 1 ]; then
    RED=$'\033[0;31m'; GREEN=$'\033[0;32m'; YELLOW=$'\033[0;33m'
    BLUE=$'\033[0;34m'; CYAN=$'\033[0;36m'; BOLD=$'\033[1m'; NC=$'\033[0m'
else
    RED=""; GREEN=""; YELLOW=""; BLUE=""; CYAN=""; BOLD=""; NC=""
fi

info()  { printf "%s[INFO]%s  %s\n"  "$GREEN"  "$NC" "$*"; }
warn()  { printf "%s[WARN]%s  %s\n"  "$YELLOW" "$NC" "$*"; }
error() { printf "%s[ERROR]%s %s\n"  "$RED"    "$NC" "$*" >&2; }
ok()    { printf "%s[ OK ]%s  %s\n"  "$GREEN"  "$NC" "$*"; }
step()  { printf "\n%s%s━━━ %s ━━━%s\n" "$BOLD" "$CYAN" "$*" "$NC"; }

banner() {
    printf "\n%s%s" "$BOLD" "$CYAN"
    cat <<'EOF'
   ┌─────────────────────────────────────────────┐
   │   📚  Lecture Manager — Auto Setup          │
   │   YouTube / Facebook / Questions / Pomodoro │
   └─────────────────────────────────────────────┘
EOF
    printf "%s\n" "$NC"
}

# ------------------------------------------------------------
#  CLEANUP (Ctrl+C / exit)
# ------------------------------------------------------------
CLEANUP_DONE=0
cleanup() {
    [ "$CLEANUP_DONE" -eq 1 ] && return
    CLEANUP_DONE=1
    echo
    info "Shutting down..."
    for pid_file in "$WEB_PID_FILE" "$MARIADB_PID_FILE"; do
        if [ -f "$pid_file" ]; then
            pid=$(cat "$pid_file" 2>/dev/null || echo "")
            if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
                info "Stopping process $pid..."
                kill -TERM "$pid" 2>/dev/null
                wait "$pid" 2>/dev/null || true
            fi
            rm -f "$pid_file"
        fi
    done
    ok "Cleanup done. Goodbye!"
    exit 0
}
trap cleanup EXIT INT TERM

# ------------------------------------------------------------
#  ENVIRONMENT DETECTION
# ------------------------------------------------------------
detect_env() {
    if [ -n "${TERMUX_VERSION:-}" ] || [ -d "/data/data/com.termux" ]; then
        ENV_TYPE="termux"; PKG_MGR="pkg"; SUDO=""
    elif command -v apt-get >/dev/null 2>&1; then
        ENV_TYPE="debian"; PKG_MGR="apt-get"; SUDO="sudo"
    elif command -v dnf >/dev/null 2>&1; then
        ENV_TYPE="fedora"; PKG_MGR="dnf"; SUDO="sudo"
    elif command -v pacman >/dev/null 2>&1; then
        ENV_TYPE="arch"; PKG_MGR="pacman"; SUDO="sudo"
    else
        error "No supported package manager found (pkg / apt / dnf / pacman)."
        exit 1
    fi
    info "Environment: $ENV_TYPE"
}

pkg_install() {
    case "$ENV_TYPE" in
        termux)  pkg install -y "$@"  >/dev/null 2>&1 ;;
        debian)  sudo apt-get install -y "$@" >/dev/null 2>&1 ;;
        fedora)  sudo dnf install -y "$@" >/dev/null 2>&1 ;;
        arch)    sudo pacman -S --noconfirm "$@" >/dev/null 2>&1 ;;
    esac
}

pkg_is_installed() {
    case "$ENV_TYPE" in
        termux|debian) dpkg -s "$1" >/dev/null 2>&1 ;;
        fedora)        rpm -q   "$1" >/dev/null 2>&1 ;;
        arch)          pacman -Q "$1" >/dev/null 2>&1 ;;
    esac
}

enable_termux_repos() {
    [ "$ENV_TYPE" = "termux" ] || return 0
    for repo in x11-repo tur-repo; do
        if ! pkg_is_installed "$repo"; then
            info "Enabling Termux repo: $repo"
            pkg install -y "$repo" >/dev/null 2>&1 || warn "Could not install $repo"
        fi
    done
}

# ------------------------------------------------------------
#  SYSTEM DEPENDENCIES
# ------------------------------------------------------------
install_system_deps() {
    step "Installing system dependencies"
    enable_termux_repos

    # ---------- Required (abort if any fails) ----------
    case "$ENV_TYPE" in
        termux)
            CORE=(git python ffmpeg mariadb clang make pkg-config openssl libffi libxml2 libxslt)
            ;;
        debian)
            CORE=(git python3 python3-venv python3-pip ffmpeg mariadb-server
                  build-essential pkg-config libssl-dev libffi-dev libxml2-dev libxslt1-dev)
            ;;
        fedora)
            CORE=(git python3 python3-pip ffmpeg mariadb-server
                  gcc make pkgconf openssl-devel libffi-devel libxml2-devel libxslt-devel)
            ;;
        arch)
            CORE=(git python python-pip ffmpeg mariadb
                  base-devel pkgconf openssl libffi libxml2 libxslt)
            ;;
    esac

    local missing=()
    for p in "${CORE[@]}"; do
        pkg_is_installed "$p" || missing+=("$p")
    done
    if [ ${#missing[@]} -gt 0 ]; then
        info "Installing required packages: ${missing[*]}"
        if ! pkg_install "${missing[@]}"; then
            error "Failed to install required packages."
            error "Try: $PKG_MGR update && $PKG_MGR upgrade"
            exit 1
        fi
    fi
    ok "Required packages in place"

    # ---------- Optional build tools ----------
    OPTIONAL=(cmake ninja rust)
    for p in "${OPTIONAL[@]}"; do
        pkg_is_installed "$p" || pkg_install "$p" || warn "Optional package $p skipped"
    done
    ok "Build tools ready"

    # ---------- GUI (Pomodoro charts & tkinter) ----------
    case "$ENV_TYPE" in
        termux) GUI=(python-tkinter) ;;
        debian) GUI=(python3-tk python3-matplotlib) ;;
        fedora) GUI=(python3-tkinter python3-matplotlib) ;;
        arch)   GUI=(tk python-matplotlib) ;;
    esac
    for p in "${GUI[@]}"; do
        pkg_is_installed "$p" || pkg_install "$p" || warn "$p skipped (Pomodoro GUI may not run)"
    done
    ok "GUI dependencies done"
}

# ------------------------------------------------------------
#  MARIADB HELPERS
# ------------------------------------------------------------
is_mariadb_running() { pgrep -f "mariadbd" >/dev/null 2>&1; }

wait_for_mariadb() {
    local tries="${1:-15}"
    for ((i=0; i<tries; i++)); do
        sleep 1
        is_mariadb_running && return 0
    done
    return 1
}

get_root_password() {
    # 1) empty password?
    if mysql -u root -e "SELECT 1" >/dev/null 2>&1; then
        echo "" > "$ROOT_PASS_FILE"; echo ""; return 0
    fi
    # 2) saved password?
    if [ -f "$ROOT_PASS_FILE" ]; then
        local saved; saved=$(cat "$ROOT_PASS_FILE")
        if MYSQL_PWD="$saved" mysql -u root -e "SELECT 1" >/dev/null 2>&1; then
            echo "$saved"; return 0
        fi
        warn "Saved root password wrong. Removing."
        rm -f "$ROOT_PASS_FILE"
    fi
    # 3) default "root"?
    if MYSQL_PWD="$DEFAULT_ROOT_PASS" mysql -u root -e "SELECT 1" >/dev/null 2>&1; then
        echo "$DEFAULT_ROOT_PASS" > "$ROOT_PASS_FILE"
        echo "$DEFAULT_ROOT_PASS"; return 0
    fi
    # 4) ask
    warn "MariaDB root password is required."
    while true; do
        read -s -r -p "Enter MariaDB root password: " pw; echo
        if MYSQL_PWD="$pw" mysql -u root -e "SELECT 1" >/dev/null 2>&1; then
            echo "$pw" > "$ROOT_PASS_FILE"
            echo "$pw"; return 0
        fi
        warn "Incorrect password. Try again."
    done
}

write_config() {
    local db_pass="$1"
    cat > "$CONFIG_FILE" <<EOF
{
    "host": "localhost",
    "database": "$DB_NAME",
    "user": "$DB_USER",
    "password": "$db_pass",
    "port": 3306
}
EOF
    ok "Config written to $CONFIG_FILE"
}

# ------------------------------------------------------------
#  MARIADB SETUP
# ------------------------------------------------------------
setup_db() {
    step "Setting up MariaDB"
    mkdir -p "$REPO_DIR"

    # Stale PID cleanup
    if [ -f "$MARIADB_PID_FILE" ]; then
        old=$(cat "$MARIADB_PID_FILE")
        kill -0 "$old" 2>/dev/null || { warn "Removing stale MariaDB PID"; rm -f "$MARIADB_PID_FILE"; }
    fi

    # Start if not running
    if is_mariadb_running; then
        info "MariaDB already running (PID $(pgrep -f mariadbd | head -1))"
    else
        info "Starting MariaDB..."
        case "$ENV_TYPE" in
            termux)
                mariadbd-safe >/dev/null 2>&1 &
                ;;
            debian)
                sudo service mariadb start >/dev/null 2>&1 \
                    || sudo systemctl start mariadb >/dev/null 2>&1 \
                    || mariadbd-safe >/dev/null 2>&1 &
                ;;
            fedora)
                sudo systemctl start mariadb >/dev/null 2>&1 \
                    || mariadbd-safe >/dev/null 2>&1 &
                ;;
            arch)
                sudo systemctl start mariadb >/dev/null 2>&1 \
                    || mariadbd-safe >/dev/null 2>&1 &
                ;;
        esac
        if ! wait_for_mariadb 15; then
            error "MariaDB failed to start."
            error "On Termux, try: mariadb-install-db"
            exit 1
        fi
        pgrep -f mariadbd | head -1 > "$MARIADB_PID_FILE"
        ok "MariaDB started (PID $(cat "$MARIADB_PID_FILE"))"
    fi

    # Root password
    local root_pw; root_pw=$(get_root_password)
    export MYSQL_PWD="$root_pw"
    local mysql_cmd="mysql -u root"

    # App user password
    if [ ! -f "$DB_PASS_FILE" ]; then
        DB_PASS=$(tr -dc 'a-zA-Z0-9' </dev/urandom 2>/dev/null | head -c 24)
        echo "$DB_PASS" > "$DB_PASS_FILE"
        chmod 600 "$DB_PASS_FILE"
        ok "Generated app password (saved to $DB_PASS_FILE)"
    else
        DB_PASS=$(cat "$DB_PASS_FILE")
        info "Using existing app password"
    fi

    # Reset DB if requested
    if [ "$DB_ACTION" = "delete" ]; then
        warn "Dropping database '$DB_NAME' (data will be lost)"
        $mysql_cmd -e "DROP DATABASE IF EXISTS \`$DB_NAME\`;" || true
        ok "Database dropped"
    fi

    # Create DB + user
    $mysql_cmd -e "CREATE DATABASE IF NOT EXISTS \`$DB_NAME\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
    $mysql_cmd -e "CREATE USER IF NOT EXISTS '$DB_USER'@'localhost' IDENTIFIED BY '$DB_PASS';"
    $mysql_cmd -e "ALTER USER '$DB_USER'@'localhost' IDENTIFIED BY '$DB_PASS';"
    $mysql_cmd -e "GRANT ALL PRIVILEGES ON \`$DB_NAME\`.* TO '$DB_USER'@'localhost'; FLUSH PRIVILEGES;"
    unset MYSQL_PWD
    export DATABASE_URL="mysql+pymysql://$DB_USER:$DB_PASS@localhost:3306/$DB_NAME"
    ok "Database '$DB_NAME' ready (user: $DB_USER)"

    write_config "$DB_PASS"
}

# ------------------------------------------------------------
#  REPOSITORY (clone / self-update)
# ------------------------------------------------------------
setup_repo() {
    step "Setting up repository"

    # ---------- Detect the state of $REPO_DIR ----------
    local state="unknown"
    if [ -d "$REPO_DIR/.git" ] && git -C "$REPO_DIR" rev-parse --git-dir >/dev/null 2>&1; then
        state="git"
    elif [ -e "$REPO_DIR" ]; then
        state="exists_non_git"
    else
        state="missing"
    fi

    case "$state" in
        # =============================================
        # 1. Real git repo — update it
        # =============================================
        git)
            cd "$REPO_DIR"
            info "Existing repo detected — fetching updates"

            # Make sure a remote is configured
            if ! git remote get-url origin >/dev/null 2>&1; then
                warn "No 'origin' remote configured. Fixing..."
                git remote add origin "$REPO_URL"
            fi

            git fetch --quiet || {
                warn "Fetch failed — network issue? Retrying once in 3s"
                sleep 3
                git fetch --quiet || { error "Cannot reach GitHub. Check internet."; exit 1; }
            }

            # Make sure the current branch tracks a remote
            if ! git rev-parse --abbrev-ref --symbolic-full-name '@{u}' >/dev/null 2>&1; then
                warn "No upstream tracking. Setting to origin/$(git rev-parse --abbrev-ref HEAD)"
                git branch --set-upstream-to="origin/$(git rev-parse --abbrev-ref HEAD)" 2>/dev/null || true
            fi

            LOCAL=$(git rev-parse HEAD)
            REMOTE=$(git rev-parse '@{u}' 2>/dev/null || echo "")

            if [ -z "$REMOTE" ]; then
                warn "Cannot determine remote HEAD — skipping pull"
            elif [ "$LOCAL" != "$REMOTE" ]; then
                info "Updates available — pulling..."
                if git pull --rebase --autostash; then
                    touch "$REPO_DIR/.update_needed"
                    ok "Updated to $(git rev-parse --short HEAD)"
                else
                    warn "Pull failed — resetting to remote"
                    git reset --hard '@{u}' && touch "$REPO_DIR/.update_needed"
                fi
            else
                info "Repository is up-to-date ($(git rev-parse --short HEAD))"
            fi
            ;;

        # =============================================
        # 2. Directory exists but is NOT a git repo
        # =============================================
        exists_non_git)
            warn "Found $REPO_DIR but it is not a git repository."
            warn "This usually means a partial download or manual copy."

            # Back it up (never destroy without asking)
            local backup="$REPO_DIR.broken.$(date +%Y%m%d_%H%M%S)"
            info "Moving it to $backup"
            mv "$REPO_DIR" "$backup" || {
                error "Could not move $REPO_DIR aside. Check permissions."
                exit 1
            }
            ok "Old directory preserved at $backup (safe to delete later)"

            info "Cloning fresh copy from $REPO_URL"
            if ! git clone "$REPO_URL" "$REPO_DIR"; then
                error "Clone failed."
                error "Restoring your previous directory from backup..."
                rm -rf "$REPO_DIR"
                mv "$backup" "$REPO_DIR"
                error "Restored. Fix network and re-run."
                exit 1
            fi
            cd "$REPO_DIR"
            touch "$REPO_DIR/.update_needed"
            ok "Fresh clone complete"
            ;;

        # =============================================
        # 3. Nothing there — just clone
        # =============================================
        missing)
            info "Cloning $REPO_URL"
            if ! git clone "$REPO_URL" "$REPO_DIR"; then
                error "Clone failed. Check internet and try again."
                exit 1
            fi
            cd "$REPO_DIR"
            touch "$REPO_DIR/.update_needed"
            ok "Clone complete"
            ;;

        *)
            error "Unexpected state for $REPO_DIR. Aborting."
            exit 1
            ;;
    esac

    # ---------- Sanity check the clone/update ----------
    if [ ! -f "$REPO_DIR/setup.py" ] && [ ! -f "$REPO_DIR/pyproject.toml" ]; then
        error "Repository looks incomplete — neither setup.py nor pyproject.toml found."
        error "Try deleting $REPO_DIR and re-running."
        exit 1
    fi

    # ---------- Install / update the launcher in $HOME ----------
    local src="$REPO_DIR/lecture-manager.sh"
    if [ -f "$src" ]; then
        if ! cmp -s "$src" "$HOME_SCRIPT" 2>/dev/null; then
            info "Updating launcher at $HOME_SCRIPT"
            cp "$src" "$HOME_SCRIPT"
            chmod +x "$HOME_SCRIPT"
            ok "Launcher updated"
        fi
    else
        error "lecture-manager.sh missing from repository"
        exit 1
    fi

    # If we're not already running from $HOME, hand over to it
    if [ "$(readlink -f "$0" 2>/dev/null)" != "$(readlink -f "$HOME_SCRIPT" 2>/dev/null)" ]; then
        rm -f "$REPO_DIR/.update_needed"
        info "Restarting under $HOME_SCRIPT"
        exec "$HOME_SCRIPT" "$@"
    fi
}

# ------------------------------------------------------------
#  VIRTUAL ENVIRONMENT  (repo-first, pip-fallback)
# ------------------------------------------------------------
find_python() {
    for v in python3.12 python3.11 python3.10 python3 python; do
        command -v "$v" >/dev/null 2>&1 && { echo "$v"; return 0; }
    done
    return 1
}

# ------------------------------------------------------------
#  NATIVE PYTHON PACKAGES (Termux-first, avoids pip compile)
# ------------------------------------------------------------
install_native_python_packages() {
    step "Installing native Python packages (avoids pip compilation)"

    # ---------- Build the package list per platform ----------
    local required=() optional=()

    case "$ENV_TYPE" in
        termux)
            # Termux needs a repo refresh so we see the latest packages
            if ! pkg show python-numpy >/dev/null 2>&1; then
                warn "python-numpy not visible — running 'pkg update' first..."
                pkg update -y >/dev/null 2>&1 || true
            fi
            enable_termux_repos

            required=(
                python-numpy
                matplotlib
                python-cryptography
                python-pillow
                python-lxml
                python-cffi
                python-psutil
            )
            optional=(python-scipy python-pandas python-tkinter)
            ;;

        debian)
            required=(
                python3-numpy
                python3-matplotlib
                python3-cryptography
                python3-pil
                python3-lxml
                python3-cffi
                python3-psutil
            )
            optional=(python3-scipy python3-pandas python3-tk)
            ;;

        fedora)
            required=(
                python3-numpy
                python3-matplotlib
                python3-cryptography
                python3-pillow
                python3-lxml
                python3-cffi
                python3-psutil
            )
            optional=(python3-scipy python3-pandas python3-tkinter)
            ;;

        arch)
            required=(
                python-numpy
                python-matplotlib
                python-cryptography
                python-pillow
                python-lxml
                python-cffi
                python-psutil
            )
            optional=(python-scipy python-pandas tk)
            ;;
    esac

    # ---------- Install required (abort on failure) ----------
    for p in "${required[@]}"; do
        if pkg_is_installed "$p"; then
            ok "$p already installed"
        else
            info "Installing native: $p"
            if ! pkg_install "$p"; then
                error "Failed to install $p"
                error "Try: $PKG_MGR update && $PKG_MGR upgrade"
                exit 1
            fi
            ok "$p installed"
        fi
    done

    # ---------- Install optional (warn only) ----------
    for p in "${optional[@]}"; do
        if pkg_is_installed "$p"; then
            ok "$p already installed"
        else
            if pkg_install "$p"; then
                ok "$p installed"
            else
                warn "$p not available — pip will try (may compile)"
            fi
        fi
    done

    # ---------- Rust (only needed if a pip build falls back to source) ----------
    if [ "$ENV_TYPE" = "termux" ] && ! command -v rustc >/dev/null 2>&1; then
        info "Installing rust (in case pip needs to build something)"
        pkg_install rust || warn "rust skipped"
    fi

    ok "Native Python packages done"
}

setup_venv() {
    step "Setting up Python environment"

    # ---- NEW: native prebuilts first, so pip sees them ----
    install_native_python_packages

    local py; py=$(find_python) || { error "No Python 3 found"; exit 1; }
    info "Using $py ($($py --version 2>&1))"

    # ---- Create venv with system site-packages (sees pkg-installed numpy etc.) ----
    if [ ! -d "$VENV_DIR" ]; then
        info "Creating venv at $VENV_DIR"
        "$py" -m venv --system-site-packages "$VENV_DIR" || {
            error "Failed to create venv."
            error "Try: pkg install python-pip"
            exit 1
        }
    else
        info "Reusing existing venv"
    fi

    # shellcheck disable=SC1091
    source "$VENV_DIR/bin/activate"
    ok "venv activated"

    pip install --quiet --upgrade pip wheel setuptools
    ok "pip / wheel / setuptools upgraded"

    # ---- Install / update lecture-manager ----
    local update_needed=0
    [ -f "$REPO_DIR/.update_needed" ] && { update_needed=1; rm -f "$REPO_DIR/.update_needed"; }

    if [ "$FORCE_REINSTALL" = "yes" ] || [ "$update_needed" -eq 1 ] || ! pip show lecture_manager >/dev/null 2>&1; then
        info "Installing lecture-manager + Python dependencies via pip..."
        cd "$REPO_DIR"

        if [ -f requirements.txt ]; then
            info "Upgrading requirements.txt deps..."
            pip install --upgrade -r requirements.txt || warn "Some requirements failed"
        fi

        if ! pip install -e . ; then
            error "pip install -e . failed."
            error "On Termux try: pkg install rust clang libjpeg-turbo"
            exit 1
        fi
        ok "Package installed"
    else
        info "Package already installed (FORCE_REINSTALL=yes to force)"
    fi

    # ---- Verify critical imports ----
    info "Verifying Python imports..."
    local missing=()
    for mod in flask mysql.connector yt_dlp googleapiclient requests bs4 html2text; do
        python -c "import $mod" >/dev/null 2>&1 || missing+=("$mod")
    done
    if [ ${#missing[@]} -gt 0 ]; then
        warn "Missing modules: ${missing[*]}"
        warn "Trying pip fallback..."
        pip install "${missing[@]}" || warn "Some modules still missing"
    fi

    # ---- Optional heavy (charts) — do not abort if they fail ----
    for mod in numpy matplotlib; do
        python -c "import $mod" >/dev/null 2>&1 \
            || { warn "$mod missing — installing via pip"; pip install "$mod" || warn "$mod failed (charts disabled)"; }
    done

    ok "Python environment ready"
}

# ------------------------------------------------------------
#  AUTO-IMPORT EXPORTS
# ------------------------------------------------------------
import_exports() {
    if [ "$ENV_TYPE" = "termux" ] && [ ! -d "$HOME/storage" ]; then
        info "Requesting Termux storage access (tap Allow on the popup)"
        termux-setup-storage 2>/dev/null || true
        sleep 2
    fi

    [ "$AUTO_IMPORT_EXPORTS" != "yes" ] && { info "Auto-import disabled"; return 0; }

    step "Looking for lecture exports"
    source "$VENV_DIR/bin/activate"

    local search_dirs=("$REPO_DIR" "$HOME" "$HOME/storage" "$HOME/storage/shared" "$HOME/storage/downloads" "$HOME/downloads")
    local found=()
    for dir in "${search_dirs[@]}"; do
        [ -d "$dir" ] || continue
        for pat in "lectures_export*.csv" "lectures_export*.json"; do
            for f in "$dir"/$pat; do
                [ -f "$f" ] && found+=("$f")
            done
        done
    done

    if [ ${#found[@]} -eq 0 ]; then
        info "No export files found — skipping"
        return 0
    fi

    info "Found ${#found[@]} export file(s)"

    # Non-interactive import helper
    local tmp; tmp=$(mktemp)
    cat > "$tmp" <<'PYEOF'
import sys, json, csv, builtins
from lecture_manager.export import _import_rows

def import_file(path, choice='2'):
    ext = path.rsplit('.', 1)[-1].lower()
    try:
        if ext == 'csv':
            with open(path, encoding='utf-8') as f:
                rows = list(csv.DictReader(f))
        elif ext == 'json':
            with open(path, encoding='utf-8') as f:
                rows = json.load(f)
        else:
            return False
        if not rows:
            return False
        orig = builtins.input
        builtins.input = lambda prompt='': choice
        try:
            _import_rows(rows, ext.upper())
        finally:
            builtins.input = orig
        return True
    except Exception as e:
        print(f"Import failed: {e}")
        return False

if __name__ == "__main__":
    sys.exit(0 if import_file(sys.argv[1]) else 1)
PYEOF

    for f in "${found[@]}"; do
        info "Importing $(basename "$f")"
        if python "$tmp" "$f"; then
            ok "Imported; deleting $f"
            rm -f "$f"
        else
            warn "Import failed — keeping $f"
        fi
    done
    rm -f "$tmp"
}

# ------------------------------------------------------------
#  RUN WEB SERVER
# ------------------------------------------------------------
run_web() {
    step "Starting web server"

    cd "$REPO_DIR"
    source "$VENV_DIR/bin/activate"
    export DATABASE_URL="${DATABASE_URL:-mysql+pymysql://$DB_USER:$DB_PASS@localhost:3306/$DB_NAME}"

    # Apply migrations
    python -c "from lecture_manager.db import migrate_table; migrate_table()" || warn "Migration failed"

    # Start server
    python -c "from lecture_manager.web import run_web_server; run_web_server(debug=False, host='0.0.0.0', port=$WEB_PORT)" &
    local pid=$!
    echo "$pid" > "$WEB_PID_FILE"

    # Try to get LAN IP for QR/URL display
    local ip=""
    if command -v ip >/dev/null 2>&1; then
        ip=$(ip -4 addr show 2>/dev/null | awk '/inet /{print $2}' | grep -v '127.0.0.1' | cut -d/ -f1 | head -1)
    elif command -v ifconfig >/dev/null 2>&1; then
        ip=$(ifconfig 2>/dev/null | awk '/inet /{print $2}' | grep -v '127.0.0.1' | head -1)
    fi

    echo
    printf "%s%s━━━ Lecture Manager is running ━━━%s\n" "$BOLD" "$GREEN" "$NC"
    printf "   Local:  %shttp://127.0.0.1:%s%s\n" "$CYAN" "$WEB_PORT" "$NC"
    [ -n "$ip" ] && printf "   LAN:    %shttp://%s:%s%s\n" "$CYAN" "$ip" "$WEB_PORT" "$NC"
    printf "\n   Press %sCtrl+C%s to stop.\n\n" "$BOLD" "$NC"

    wait "$pid"
}

# ------------------------------------------------------------
#  MAIN
# ------------------------------------------------------------
main() {
    banner
    detect_env
    setup_repo
    install_system_deps
    setup_db
    setup_venv
    import_exports
    run_web
}

main "$@"
