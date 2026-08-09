# ============================================================
# Lecture Manager Makefile (v2.7.0)
# Author: Udaya Raj Joshi
# ============================================================

# --- Project settings ---
PROJECT_NAME   := lecture-manager
BACKUP_DIR     := ./backups
TIMESTAMP      := $(shell date +%Y%m%d_%H%M%S)
BACKUP_FILE    := $(BACKUP_DIR)/$(PROJECT_NAME)_backup_$(TIMESTAMP).tar.xz

# --- Database settings (for backup-db) ---
# Credentials are read from environment variables; you can set them in a .env file or pass inline.
DB_HOST        ?= localhost
DB_USER        ?= fox
DB_PASSWORD    ?= fox
DB_NAME        ?= fox
DB_DUMP_FILE   := $(BACKUP_DIR)/$(PROJECT_NAME)_db_$(TIMESTAMP).sql

# --- Files/directories to exclude from backup ---
EXCLUDE := --exclude='__pycache__' \
           --exclude='*.pyc' \
           --exclude='*.pyo' \
           --exclude='*.db' \
           --exclude='cookies.txt' \
           --exclude='.git' \
           --exclude='.env' \
           --exclude='downloads' \
           --exclude='backups' \
           --exclude='.lecture_trash' \
           --exclude='*.log' \
           --exclude='*.sql' \
           --exclude='.DS_Store' \
           --exclude='youtube_token.pickle' \
           --exclude='client_secrets.json'

# --- Python / virtual environment ---
PYTHON          := python3
VENV_DIR        := venv
PIP             := $(VENV_DIR)/bin/pip
PYTHON_VENV     := $(VENV_DIR)/bin/python
FLASK_APP       := lecture_manager/web.py
FLASK_ENV       := development
PORT            := 5000
HOST            := 0.0.0.0

# --- Colors for pretty output ---
RED    := \033[0;31m
GREEN  := \033[0;32m
YELLOW := \033[0;33m
BLUE   := \033[0;34m
NC     := \033[0m

# --- Default target ---
.PHONY: help
help:
	@echo "$(GREEN)Available targets:$(NC)"
	@echo "  $(BLUE)install$(NC)       - Install the package in editable mode with all dependencies"
	@echo "  $(BLUE)venv$(NC)          - Create a virtual environment"
	@echo "  $(BLUE)db-init$(NC)       - Initialize the database tables (via Python module)"
	@echo "  $(BLUE)run$(NC)           - Start the CLI application (lecture-manager)"
	@echo "  $(BLUE)web$(NC)           - Start the web interface (Flask) on $(HOST):$(PORT)"
	@echo "  $(BLUE)pomodoro$(NC)      - Launch the Pomodoro timer GUI"
	@echo "  $(BLUE)converter$(NC)     - Show help for the standalone question converter"
	@echo "  $(BLUE)export-html$(NC)   - Export all questions to HTML (questions_export.html)"
	@echo "  $(BLUE)test$(NC)          - Run tests (placeholder)"
	@echo "  $(BLUE)clean$(NC)         - Remove Python cache and build artifacts"
	@echo "  $(BLUE)distclean$(NC)     - Remove virtual environment and generated files"
	@echo "  $(BLUE)setup$(NC)         - Quick setup: install + db-init"
	@echo "  $(BLUE)backup$(NC)        - Create a timestamped backup tarball of the project"
	@echo "  $(BLUE)backup-db$(NC)     - Dump the MariaDB database to a SQL file (requires DB credentials)"
	@echo "  $(BLUE)dist$(NC)          - Build a source distribution (.tar.gz) for PyPI"

# --- Virtual environment ---
.PHONY: venv
venv:
	@echo "$(BLUE)Creating virtual environment...$(NC)"
	$(PYTHON) -m venv $(VENV_DIR)
	@echo "$(GREEN)Virtual environment created at $(VENV_DIR)$(NC)"
	@echo "To activate: source $(VENV_DIR)/bin/activate"

# --- Installation ---
.PHONY: install
install: venv
	@echo "$(BLUE)Installing $(PROJECT_NAME) in editable mode...$(NC)"
	$(PIP) install --upgrade pip
	$(PIP) install -e .
	@echo "$(GREEN)Installation complete.$(NC)"
	@echo "Run 'make run' to start the CLI, or 'make web' for the web interface."

# --- Database initialisation ---
.PHONY: db-init
db-init:
	@echo "$(BLUE)Initializing database tables...$(NC)"
	$(PYTHON_VENV) -c "from lecture_manager.db import create_table, migrate_table; create_table(); migrate_table()"
	@echo "$(GREEN)Database tables ready.$(NC)"

# --- Run CLI ---
.PHONY: run
run:
	@echo "$(BLUE)Starting Lecture Manager CLI...$(NC)"
	$(PYTHON_VENV) -m lecture_manager.main

# --- Run Web Interface ---
.PHONY: web
web:
	@echo "$(BLUE)Starting web server on $(HOST):$(PORT)...$(NC)"
	FLASK_APP=$(FLASK_APP) FLASK_ENV=$(FLASK_ENV) $(PYTHON_VENV) -m flask run --host=$(HOST) --port=$(PORT)

# --- Pomodoro Timer ---
.PHONY: pomodoro
pomodoro:
	@echo "$(BLUE)Launching Pomodoro timer...$(NC)"
	$(PYTHON_VENV) -m lecture_manager.pomodoro

# --- Question Converter (standalone help) ---
.PHONY: converter
converter:
	@echo "$(BLUE)Question Converter standalone help:$(NC)"
	$(PYTHON_VENV) -m lecture_manager.question_converter.converter_main --help

# --- Export all questions to HTML ---
.PHONY: export-html
export-html:
	@echo "$(BLUE)Exporting all questions to questions_export.html...$(NC)"
	$(PYTHON_VENV) -c "from lecture_manager.question_converter.db_handler import get_questions, export_to_file; qs = get_questions(); export_to_file(qs, 'questions_export.html', 'html')"
	@echo "$(GREEN)Exported to questions_export.html$(NC)"

# --- Testing (placeholder) ---
.PHONY: test
test:
	@echo "$(YELLOW)No tests defined yet.$(NC)"

# --- Clean ---
.PHONY: clean
clean:
	@echo "$(BLUE)Removing Python cache and build artifacts...$(NC)"
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name "*.so" -delete
	rm -rf build/ dist/ *.egg-info .pytest_cache/ .coverage htmlcov/
	@echo "$(GREEN)Clean complete.$(NC)"

# --- Deep clean (remove venv) ---
.PHONY: distclean
distclean: clean
	@echo "$(BLUE)Removing virtual environment...$(NC)"
	rm -rf $(VENV_DIR)
	@echo "$(GREEN)Virtual environment removed.$(NC)"

# --- Quick setup (install + db-init) ---
.PHONY: setup
setup: install db-init
	@echo "$(GREEN)Lecture Manager is ready to use!$(NC)"
	@echo "Run 'make run' to start the CLI or 'make web' for the web interface."

# --- Backup (project files) ---
.PHONY: backup
backup: $(BACKUP_DIR)
	@echo "$(BLUE)Creating backup of $(PROJECT_NAME)...$(NC)"
	tar -cJf $(BACKUP_FILE) $(EXCLUDE) .
	@echo "$(GREEN)Backup created: $(BACKUP_FILE)$(NC)"

$(BACKUP_DIR):
	mkdir -p $(BACKUP_DIR)

# --- Database backup (requires DB credentials) ---
.PHONY: backup-db
backup-db: $(BACKUP_DIR)
	@echo "$(BLUE)Dumping database $(DB_NAME)...$(NC)"
	mysqldump -h $(DB_HOST) -u $(DB_USER) -p$(DB_PASSWORD) $(DB_NAME) > $(DB_DUMP_FILE)
	@echo "$(GREEN)Database dump saved: $(DB_DUMP_FILE)$(NC)"

# --- Build source distribution ---
.PHONY: dist
dist:
	@echo "$(BLUE)Building source distribution (.tar.gz)...$(NC)"
	$(PYTHON_VENV) -m build
	@echo "$(GREEN)Distribution created in ./dist/$(NC)"
	@ls -lh dist/*.tar.gz
