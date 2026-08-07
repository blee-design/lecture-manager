# File: __init__.py

"""
Question Converter Package – Moodle‑compatible import/export
with optional database storage.
"""

from .constants import C, HELP_FORMAT_TEXT, PROGRAM_BANNER
from .converter_core import run_conversion
from .db_handler import (
    create_tables,
    insert_question,
    get_questions,
    delete_question,
    update_question,
    import_from_file,
    export_to_file
)

__all__ = [
    'C', 'HELP_FORMAT_TEXT', 'PROGRAM_BANNER',
    'run_conversion',
    'create_tables',
    'insert_question',
    'get_questions',
    'delete_question',
    'update_question',
    'import_from_file',
    'export_to_file'
]
