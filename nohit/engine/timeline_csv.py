"""Tokenize Timeline input exactly like the original AJAX and tokenat calls.

The game's .csv extension does not imply RFC CSV quoting. TLPlay splits on
newline, TLLoadLine splits on commas, and quote characters remain literal.
Keep missing cells missing: native Array.At supplies numeric zero, whereas an
explicit trailing comma supplies an empty string to the called function.
"""
from pathlib import Path


def parse_timeline_rows(text: str) -> list[list[str]]:
    return [line.split(',') for line in text.replace('\r\n','\n').split('\n')]


def read_timeline_rows(path) -> list[list[str]]:
    return parse_timeline_rows(Path(path).read_bytes().decode('utf-8-sig'))
