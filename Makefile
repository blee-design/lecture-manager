# Makefile for YouTube Lecture Manager

# --- Project settings ---
PROJECT_NAME   := youtube-lecture-manager
BACKUP_DIR     := ./backups
TIMESTAMP      := $(shell date +%Y%m%d_%H%M%S)
BACKUP_FILE    := $(BACKUP_DIR)/$(PROJECT_NAME)_backup_$(TIMESTAMP).tar.xz

# --- Database settings (for backup-db) ---
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
           --exclude='.DS_Store'

# --- Targets ---

.PHONY: help backup backup-db clean install dist

help:
	@echo "Available targets:"
	@echo "  make backup      - Create a timestamped backup tarball of the project."
	@echo "  make backup-db   - Dump the MariaDB database to a SQL file (requires DB credentials)."
	@echo "  make clean       - Remove Python cache files and temporary files."
	@echo "  make install     - Install the package in editable (development) mode."
	@echo "  make dist        - Build a source distribution (.tar.gz) for distribution."

backup: $(BACKUP_DIR)
	@echo "Creating backup of $(PROJECT_NAME)..."
	tar -czf $(BACKUP_FILE) $(EXCLUDE) .
	@echo "Backup created: $(BACKUP_FILE)"

$(BACKUP_DIR):
	mkdir -p $(BACKUP_DIR)

backup-db: $(BACKUP_DIR)
	@echo "Dumping database $(DB_NAME)..."
	mysqldump -h $(DB_HOST) -u $(DB_USER) -p$(DB_PASSWORD) $(DB_NAME) > $(DB_DUMP_FILE)
	@echo "Database dump saved: $(DB_DUMP_FILE)"

clean:
	@echo "Removing Python cache files..."
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	@echo "Clean complete."

install:
	@echo "Installing $(PROJECT_NAME) in development mode..."
	pip install -e .
	@echo "Installation complete."

dist:
	@echo "Building source distribution (.tar.gz)..."
	python -m build
	@echo "Distribution created in ./dist/"
	@ls -lh dist/*.tar.gz
