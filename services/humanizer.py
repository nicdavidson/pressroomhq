"""Humanizer — Strip AI slop patterns from generated content."""

import re

# Anti-patterns from Wikipedia "Signs of AI writing" + our own list
SLOP_PATTERNS = [
    (r"\bexcited to (?:share|announce)\b", ""),
    (r"\bgame[- ]?changer\b", "significant"),
    (r"\bleverage\b", "use"),
    (r"\bsynergy\b", "overlap"),
    (r"\bthrilled\b", "glad"),
    (r"\bcomprehensive\b", "full"),
    (r"\brobust\b", "solid"),
    (r"\bseamless(?:ly)?\b", "smooth"),
    (r"\btransformative\b", "meaningful"),
    (r"\binnovative\b", "new"),
    (r"\bcutting[- ]?edge\b", "modern"),
    (r"\bstate[- ]?of[- ]?the[- ]?art\b", "current"),
    (r"\bunlock(?:ing)?\b", "enable"),
    (r"\bempower(?:ing|s)?\b", "help"),
    (r"\bdelve\b", "dig"),
    (r"\btapestry\b", "mix"),
    (r"\blandscape\b", "space"),
    (r"\bparadigm\b", "model"),
    (r"\bholistic\b", "complete"),
    (r"\bin today'?s (?:fast[- ]?paced|rapidly evolving|digital)\b", ""),
    (r"\bIt'?s worth noting that\b", ""),
    (r"\bIt'?s important to (?:note|remember) that\b", ""),
    (r"\bIn conclusion\b", ""),
]

# Structural patterns
STRUCTURAL_SLOP = [
    # Triple exclamation / emoji spam
    (r"!{3,}", "!"),
    # Excessive em-dashes used as filler
    (r" — (?:and|but|so|yet) — ", " — "),
    # "Let's dive in" and variants
    (r"\bLet'?s (?:dive|jump|get) (?:in|into|started)[.!]?\s*", ""),
    # "Without further ado"
    (r"\b[Ww]ithout further ado[,.]?\s*", ""),
]


def humanize(text: str) -> str:
    """Run the humanizer pass on generated content. Returns cleaned text."""
    result = text

    for pattern, replacement in SLOP_PATTERNS:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)

    for pattern, replacement in STRUCTURAL_SLOP:
        result = re.sub(pattern, replacement, result)

    # Clean up double spaces from removals
    result = re.sub(r"  +", " ", result)
    # Clean up lines that are now just whitespace
    result = re.sub(r"\n\s*\n\s*\n", "\n\n", result)
    # Clean up leading spaces on lines
    result = "\n".join(line.rstrip() for line in result.split("\n"))

    return result.strip()
