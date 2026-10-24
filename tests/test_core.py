import pytest
from lecture_manager.utils import normalize_syllabus_id, sanitize_filename
from lecture_manager.question_bank import split_level_and_alias, normalize_question_number, canonical_qno
from lecture_manager.question_converter.utils import is_correct_option

def test_normalize_syllabus_id():
    assert normalize_syllabus_id("4.2.5") == "04.02.05"
    assert normalize_syllabus_id("04.02.05-1") == "04.02.05-1"
    assert normalize_syllabus_id("4.2") == "04.02"

def test_sanitize_filename():
    assert sanitize_filename("valid_name.mp4") == "valid_name.mp4"
    # Tests that illegal OS characters are stripped
    assert sanitize_filename("invalid/<name>?.mp4") == "invalidname.mp4"

def test_split_level_and_alias():
    assert split_level_and_alias("Level 6 (Business Officer)") == ("6", "Business Officer")
    assert split_level_and_alias("6") == ("6", None)
    assert split_level_and_alias("Business Officer") == (None, "Business Officer")

def test_question_numbering():
    assert normalize_question_number("Q. 1") == "1"
    assert normalize_question_number(" 10a ") == "10a"
    assert canonical_qno("01") == "1"
    assert canonical_qno("Q1") == "1"

def test_mcq_option_parsing():
    correct, text = is_correct_option("Kathmandu *")
    assert correct is True
    assert text == "Kathmandu"

    correct, text = is_correct_option("Pokhara")
    assert correct is False
    assert text == "Pokhara"
