"""
Speech formatting for Echo-Node v2.

Transforms raw LLM output into concise, speech-friendly responses.
Tables become summaries, long replies get trimmed, code gets described.
"""

from __future__ import annotations

import re
from typing import Any


# ── Defaults ────────────────────────────────────────────────────────

DEFAULT_MAX_SENTENCES = 4
VERBOSE_MAX_SENTENCES = 999  # effectively unlimited


# ── Detection helpers ───────────────────────────────────────────────

def _has_table(text: str) -> bool:
    """Detect markdown or ASCII tables."""
    lines = text.split("\n")
    pipe_rows = sum(1 for l in lines if "|" in l and l.strip().startswith("|"))
    if pipe_rows >= 2:
        return True
    dash_rows = sum(1 for l in lines if re.match(r"^\s*\|[-:\s|]+\|\s*$", l))
    if dash_rows >= 1:
        return True
    # ASCII table with +---+---+
    if re.search(r"\+\s*-+\s*\+", text):
        return True
    return False


def _count_sentences(text: str) -> int:
    """Rough sentence count."""
    # Split on sentence-ending punctuation followed by space or end
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return len([p for p in parts if p.strip()])


def _extract_table_summary(text: str) -> str:
    """Extract a natural-language summary from a table.

    Looks for patterns like:
    - Column headers → count of rows
    - First/last/important rows
    """
    lines = text.split("\n")
    table_lines = [l.strip() for l in lines if "|" in l and l.strip().startswith("|")]

    if len(table_lines) < 2:
        return ""

    # Parse header row
    header_line = table_lines[0]
    headers = [h.strip() for h in header_line.split("|") if h.strip()]

    # Count data rows (skip separator)
    data_rows = []
    for line in table_lines[1:]:
        if re.match(r"^\|[-:\s|]+\|$", line):
            continue
        cells = [c.strip() for c in line.split("|") if c.strip()]
        if cells:
            data_rows.append(cells)

    if not data_rows or not headers:
        return ""

    parts = []
    parts.append(f"The table has {len(data_rows)} rows with columns: {', '.join(headers)}.")

    # Summarize first and last entries if meaningful
    if len(data_rows) <= 3:
        for row in data_rows:
            if len(row) >= 2:
                parts.append(f"{row[0]}: {row[1]}.")
    else:
        first = data_rows[0]
        last = data_rows[-1]
        if len(first) >= 2:
            parts.append(f"Starting with {first[0]}: {first[1]}.")
        if len(last) >= 2:
            parts.append(f"Ending with {last[0]}: {last[1]}.")

    return " ".join(parts)


def _summarize_code(text: str) -> str:
    """Describe code blocks instead of reading them."""
    def _replace_code(m: re.Match) -> str:
        full = m.group(0)
        # Strip ``` markers
        code = re.sub(r"^```\w*\n?", "", full, count=1)
        code = re.sub(r"\n?```$", "", code)
        lines = code.strip().split("\n")
        lang = ""
        # Check for language hint after ```
        first_line = lines[0] if lines else ""
        if first_line and not first_line.strip().startswith(("def ", "class ", "import ", "from ", "if ", "for ", "#", "//")):
            lang = first_line.strip()
            lines = lines[1:] if len(lines) > 1 else []

        func_defs = re.findall(r"(?:def|function|func)\s+(\w+)", code)
        class_defs = re.findall(r"class\s+(\w+)", code)
        imports = re.findall(r"^(?:import|from)\s+(\S+)", code, re.MULTILINE)

        parts = []
        if lang:
            parts.append(f"In {lang}")
        if class_defs:
            parts.append(f"defining {', '.join(class_defs[:3])}")
        if func_defs:
            parts.append(f"with functions {', '.join(func_defs[:5])}")
        if imports:
            parts.append(f"importing {', '.join(imports[:3])}")

        if parts:
            return "[Code block " + " ".join(parts) + "]."
        return f"[Code block with {len(lines)} lines]."

    return re.sub(r"```[\s\S]*?```", _replace_code, text)


def _trim_to_sentences(text: str, max_sentences: int) -> str:
    """Keep only the first N sentences."""
    if max_sentences >= 999:
        return text
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    if len(parts) <= max_sentences:
        return text.strip()
    return " ".join(parts[:max_sentences]).strip()


# ── Main formatter ──────────────────────────────────────────────────

def format_for_speech(
    text: str,
    max_sentences: int = DEFAULT_MAX_SENTENCES,
    verbose: bool = False,
) -> str:
    """Transform raw LLM output into speech-friendly text.

    Args:
        text: Raw LLM response
        max_sentences: Hard cap on sentence count (ignored if verbose)
        verbose: If True, bypass sentence cap

    Returns:
        Speech-formatted text
    """
    if not text or not text.strip():
        return text

    effective_max = VERBOSE_MAX_SENTENCES if verbose else max_sentences
    result = text.strip()

    # 1. Replace code blocks with descriptions
    result = _summarize_code(result)

    # 2. Handle tables
    if _has_table(result):
        summary = _extract_table_summary(result)
        if summary:
            # Keep the summary and any text before/after the table
            parts = []
            before_table = ""
            after_table = ""
            lines = result.split("\n")
            in_table = False
            table_lines = []

            for line in lines:
                stripped = line.strip()
                is_table_line = ("|" in stripped and stripped.startswith("|")) or bool(
                    re.match(r"^\s*\|[-:\s|]+\|\s*$", stripped)
                )
                if is_table_line:
                    in_table = True
                    table_lines.append(line)
                elif in_table:
                    # We've left the table
                    after_table += line + "\n"
                else:
                    before_table += line + "\n"

            result = f"{before_table.strip()} {summary} {after_table.strip()}".strip()

    # 3. Strip markdown formatting for speech
    # Remove bold/italic markers
    result = re.sub(r"\*{1,2}([^*]+)\*{1,2}", r"\1", result)
    # Remove heading markers
    result = re.sub(r"^#{1,6}\s+", "", result, flags=re.MULTILINE)
    # Remove link syntax, keep text
    result = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", result)
    # Remove image syntax
    result = re.sub(r"!\[([^\]]*)\]\([^)]+\)", "", result)
    # Remove horizontal rules
    result = re.sub(r"^[-*_]{3,}\s*$", "", result, flags=re.MULTILINE)

    # 4. Collapse excessive whitespace
    result = re.sub(r"\n{3,}", "\n\n", result)
    result = re.sub(r"[ \t]+", " ", result)
    result = result.strip()

    # 5. Trim to sentence cap
    result = _trim_to_sentences(result, effective_max)

    return result


# ── Convenience ─────────────────────────────────────────────────────

def format_for_speech_flexible(text: str, config: dict[str, Any]) -> str:
    """Format using config dict keys:
    - speech_format.max_sentences (int)
    - speech_format.verbose (bool, default False)
    """
    sf_cfg = config.get("speech_format", {})
    return format_for_speech(
        text,
        max_sentences=int(sf_cfg.get("max_sentences", DEFAULT_MAX_SENTENCES)),
        verbose=bool(sf_cfg.get("verbose", False)),
    )
