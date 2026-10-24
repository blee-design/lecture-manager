# tests/test_database.py
import pytest
from unittest.mock import MagicMock
from lecture_manager.question_converter.db_handler import count_questions

def test_count_questions(mocker):
    """
    Tests if the count_questions function builds the SQL correctly.
    Uses a Mock (fake) database so it doesn't touch your real data.
    """
    # 1. Create a fake database connection
    mock_conn = MagicMock()
    mock_cursor = MagicMock()

    # 2. Tell the fake connection to return '42' when asked for a count
    mock_cursor.fetchone.return_value = [42]
    mock_conn.cursor.return_value = mock_cursor

    # 3. Intercept the get_connection call inside the app and give it the fake one
    mocker.patch('lecture_manager.question_converter.db_handler.get_connection', return_value=mock_conn)

    # 4. Run the function (it will use the fake DB)
    result = count_questions({'type': 'multichoice'})

    # 5. Assert the result is 42 and that the DB was asked for a count
    assert result == 42
    mock_cursor.execute.assert_called_once()

    # Check that the SQL query generated includes the filter
    sql_called = mock_cursor.execute.call_args[0][0]
    assert "WHERE" in sql_called
    assert "q.type = %s" in sql_called

def test_count_questions_empty(mocker):
    """Tests that an empty database returns 0."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = [0] # 0 results
    mock_conn.cursor.return_value = mock_cursor

    mocker.patch('lecture_manager.question_converter.db_handler.get_connection', return_value=mock_conn)

    result = count_questions({})
    assert result == 0
