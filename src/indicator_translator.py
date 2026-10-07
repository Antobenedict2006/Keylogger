"""
indicator_translator.py
=======================
Simple dictionary-based translator for technical indicators.
Converts technical messages to plain English - no AI/API needed.

This is a lightweight, zero-dependency module that makes security
indicators understandable for non-technical users.
"""

import re
from typing import List

# Lightweight translation dictionary - maps technical terms to plain English
PLAIN_ENGLISH_TRANSLATIONS = {
    # Keyboard hook indicators
    "Low-level keyboard hook (WH_KEYBOARD_LL) detected": 
        "Can record everything you type on your keyboard",
    
    "Keyboard hook APIs loaded (user32.dll)": 
        "Has the ability to monitor keyboard activity",
    
    "Hooks keyboard input with no visible window": 
        "Monitoring your keyboard secretly in the background",
    
    "Keyboard hook combined with active network connections": 
        "Can record your typing AND send it over the internet",
    
    # Network indicators
    "High outbound network traffic": 
        "Sending large amounts of data over the internet",
    
    # File indicators
    "High file-write rate": 
        "Writing lots of data to your hard drive",
    
    "Executable running from a temporary directory": 
        "Running from a suspicious temporary location",
    
    # Startup indicators
    "Registered in Windows startup (Run key)": 
        "Automatically starts when Windows boots up",
    
    # Advanced indicators
    "No executable path — possibly injected / fileless": 
        "Running without a normal program file (very suspicious)",
    
    "hook-related DLLs loaded simultaneously": 
        "Loaded multiple keyboard monitoring components",
    
    "Suspicious kernel-mode driver detected (possible rootkit/keylogger)": 
        "May have deep system access (rootkit behavior)",
    
    "Raw keyboard input registered on hidden window (raw input keylogger pattern)": 
        "Using advanced techniques to capture keystrokes",
}


def translate_to_plain_english(technical_message: str) -> str:
    """
    Convert a technical indicator message to plain English.
    
    This function uses simple pattern matching and string replacement
    to convert technical security indicators into user-friendly language.
    No AI, API, or ML model is used - just dictionary lookups.
    
    Args:
        technical_message: Original technical indicator text
    
    Returns:
        User-friendly plain English explanation
    
    Examples:
        >>> translate_to_plain_english("Keyboard hook APIs loaded (user32.dll)")
        'Has the ability to monitor keyboard activity'
        
        >>> translate_to_plain_english("High outbound network traffic (12512.9 KB sent in scan window)")
        'Sending large amounts of data over the internet (12512.9 KB)'
    """
    # Try to find a matching translation
    for tech_key, plain_text in PLAIN_ENGLISH_TRANSLATIONS.items():
        if tech_key in technical_message:
            # Handle special cases with numbers/metrics
            
            # Case 1: Network traffic with KB value
            if "KB" in technical_message and "network traffic" in tech_key:
                kb_match = re.search(r'\(([0-9.]+) KB', technical_message)
                if kb_match:
                    kb_value = kb_match.group(1)
                    return f"{plain_text} ({kb_value} KB)"
            
            # Case 2: File write rate with KB/s value
            elif "KB/s" in technical_message and "file-write" in tech_key:
                kbs_match = re.search(r'\(([0-9.]+) KB/s\)', technical_message)
                if kbs_match:
                    kbs_value = kbs_match.group(1)
                    return f"{plain_text} ({kbs_value} KB/s)"
            
            # Case 3: Number of hook-related DLLs
            elif "DLL" in technical_message:
                dll_match = re.search(r'(\d+) hook-related', technical_message)
                if dll_match:
                    count = dll_match.group(1)
                    return f"Loaded {count} keyboard monitoring components"
            
            # Default: return plain text translation
            return plain_text
    
    # If no match found, return original (fallback for unknown indicators)
    return technical_message


def translate_indicators_list(indicators: List[str]) -> List[str]:
    """
    Translate a list of technical indicators to plain English.
    
    This is a convenience function that applies translate_to_plain_english()
    to each indicator in a list.
    
    Args:
        indicators: List of technical indicator messages
    
    Returns:
        List of plain English translations
    
    Examples:
        >>> indicators = [
        ...     "Keyboard hook APIs loaded (user32.dll)",
        ...     "Hooks keyboard input with no visible window"
        ... ]
        >>> translate_indicators_list(indicators)
        ['Has the ability to monitor keyboard activity', 
         'Monitoring your keyboard secretly in the background']
    """
    return [translate_to_plain_english(msg) for msg in indicators]


# Optional: Provide a way to add custom translations at runtime
def add_custom_translation(technical_phrase: str, plain_english: str) -> None:
    """
    Add a custom translation to the dictionary.
    
    This allows extending the translator without modifying the source code.
    
    Args:
        technical_phrase: The technical indicator text to match
        plain_english: The user-friendly translation
    """
    PLAIN_ENGLISH_TRANSLATIONS[technical_phrase] = plain_english
