# File: exceptions.py
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
