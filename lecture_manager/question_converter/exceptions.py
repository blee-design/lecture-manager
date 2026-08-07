class ConverterError(Exception):
    """Base exception for all converter errors."""
    pass

class ParseError(ConverterError):
    """Error during parsing (invalid format, missing fields, etc.)."""
    pass

class ValidationError(ConverterError):
    """Error during validation (duplicate questions, missing correct answer, etc.)."""
    pass

class IOError(ConverterError):
    """File read/write errors."""
    pass

# NEW: more specific errors
class DuplicateQuestionError(ValidationError):
    """Duplicate question detected."""
    pass

class MissingCorrectOptionError(ValidationError):
    """No correct option found in MCQ."""
    pass

class MultipleCorrectOptionsError(ValidationError):
    """More than one correct option found in MCQ."""
    pass

class InsufficientOptionsError(ValidationError):
    """Less than 4 options for MCQ."""
    pass

class MatchingPairError(ValidationError):
    """Invalid matching pairs."""
    pass

class UnknownQuestionTypeError(ParseError):
    """Unrecognized question type."""
    pass

class UndefinedPassageError(ParseError):
    """Referenced passage not defined."""
    pass

class InvalidFilterError(ValidationError):
    """Invalid question filter pattern."""
    pass
