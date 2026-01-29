"""Filename and folder name sanitization utilities."""

import re
import unicodedata
import os


def sanitize_folder_name(name: str) -> str:
    """
    Sanitize author name for use as folder name.

    - Remove/replace special characters not allowed in paths
    - Handle Unicode normalization
    - Ensure valid filesystem name across platforms
    """
    if not name or not name.strip():
        return "Unknown_Author"

    # Normalize Unicode characters (NFKC keeps composed forms)
    name = unicodedata.normalize('NFKC', name)

    # Replace characters not allowed in folder names
    replacements = {
        '/': '-',
        '\\': '-',
        ':': '-',
        '*': '_',
        '?': '',
        '"': "'",
        '<': '(',
        '>': ')',
        '|': '-',
        '\0': '',
        '\n': ' ',
        '\r': '',
        '\t': ' ',
    }

    for char, replacement in replacements.items():
        name = name.replace(char, replacement)

    # Remove leading/trailing spaces and dots (Windows restriction)
    name = name.strip(' .')

    # Collapse multiple spaces or dashes
    name = re.sub(r'[-\s]+', ' ', name)

    # Remove any remaining control characters
    name = ''.join(c for c in name if unicodedata.category(c) != 'Cc')

    # Truncate to reasonable length (255 chars max for most filesystems)
    if len(name) > 200:
        name = name[:200].rstrip()

    return name if name else "Unknown_Author"


def sanitize_filename(filename: str) -> str:
    """
    Sanitize individual filename, preserving extension.
    """
    if not filename:
        return "unnamed_file"

    # Split name and extension
    name, ext = os.path.splitext(filename)

    # Sanitize the name part
    sanitized_name = sanitize_folder_name(name)

    # Clean extension (just in case)
    ext = ext.lower()
    if ext and not ext.startswith('.'):
        ext = '.' + ext

    return f"{sanitized_name}{ext}"


def make_unique_path(base_path: str, name: str, ext: str = "") -> str:
    """
    Create a unique file path by appending a number if file exists.

    Args:
        base_path: Directory path
        name: Base filename without extension
        ext: File extension (including dot)

    Returns:
        Unique file path
    """
    full_path = os.path.join(base_path, f"{name}{ext}")

    if not os.path.exists(full_path):
        return full_path

    counter = 1
    while True:
        full_path = os.path.join(base_path, f"{name} ({counter}){ext}")
        if not os.path.exists(full_path):
            return full_path
        counter += 1
