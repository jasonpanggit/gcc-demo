"""Response formatter that converts LLM output to structured HTML.

Separates the concern of HTML formatting from the orchestrator logic.
The LLM produces plain-text or lightly-structured answers and this
formatter converts them into the HTML expected by the front-end.
"""
from __future__ import annotations

import html
import json
import re
from typing import Any, Dict, List, Optional


def escape_html(text: str) -> str:
    """HTML-escape a string, returning empty string for None."""
    try:
        return html.escape(text or "")
    except Exception:
        return str(text) if text is not None else ""


class ResponseFormatter:
    """Converts raw LLM text responses into clean HTML for the front-end."""

    # Patterns for detecting content that is already HTML
    _HTML_TAG_RE = re.compile(r"<(?:table|div|h[1-6]|p|ul|ol|tr|td|th|thead|tbody)\b", re.IGNORECASE)
    _MARKDOWN_TABLE_RE = re.compile(r"^\s*\|.+\|", re.MULTILINE)
    _MARKDOWN_HEADER_RE = re.compile(r"^#{1,6}\s+", re.MULTILINE)
    _MARKDOWN_BOLD_RE = re.compile(r"\*\*(.*?)\*\*")
    _MARKDOWN_ITALIC_RE = re.compile(r"(?<!\*)\*([^*]+)\*(?!\*)")
    _MARKDOWN_CODE_RE = re.compile(r"`([^`]+)`")
    _MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
    _MARKDOWN_LIST_RE = re.compile(r"^[\s]*[-*]\s+", re.MULTILINE)
    _CODE_BLOCK_RE = re.compile(r"```(?:html)?\s*\n?(.*?)```", re.DOTALL)

    def format(self, raw_text: str) -> str:
        """Convert raw LLM output to HTML.

        - If the text is already HTML, return it (with light cleanup).
        - If it contains markdown tables, convert them.
        - Otherwise wrap in paragraphs.
        """
        if not raw_text or not raw_text.strip():
            return ""

        text = raw_text.strip()

        # Strip markdown code fences (```html ... ```)
        text = self._strip_code_fences(text)

        # If already valid HTML with structural tags, return as-is
        if self._is_html(text):
            return text

        # Convert markdown-style content to HTML
        text = self._convert_markdown(text)

        return text

    # ------------------------------------------------------------------
    # Detection helpers
    # ------------------------------------------------------------------
    def _is_html(self, text: str) -> bool:
        """Check if text appears to already be HTML."""
        return bool(self._HTML_TAG_RE.search(text))

    # ------------------------------------------------------------------
    # Conversion helpers
    # ------------------------------------------------------------------
    def _strip_code_fences(self, text: str) -> str:
        """Remove ```html ... ``` wrappers."""
        match = self._CODE_BLOCK_RE.search(text)
        if match:
            inner = match.group(1).strip()
            # Replace the code block with its contents
            text = self._CODE_BLOCK_RE.sub(lambda m: m.group(1).strip(), text)
        return text

    def _convert_markdown(self, text: str) -> str:
        """Best-effort markdown → HTML conversion."""
        # Convert markdown tables first
        if self._MARKDOWN_TABLE_RE.search(text):
            text = self._convert_markdown_tables(text)

        # Convert headers
        text = self._convert_headers(text)

        # Convert inline formatting
        text = self._MARKDOWN_BOLD_RE.sub(r"<strong>\1</strong>", text)
        text = self._MARKDOWN_ITALIC_RE.sub(r"<em>\1</em>", text)
        text = self._MARKDOWN_CODE_RE.sub(r"<code>\1</code>", text)
        text = self._MARKDOWN_LINK_RE.sub(r'<a href="\2" target="_blank" rel="noopener noreferrer">\1</a>', text)

        # Convert bullet lists
        text = self._convert_lists(text)

        # Wrap remaining loose text in paragraphs
        text = self._wrap_paragraphs(text)

        return text

    def _convert_headers(self, text: str) -> str:
        """Convert markdown headers to HTML."""
        def _replace_header(match: re.Match) -> str:
            level = len(match.group(1))
            content = match.group(2).strip()
            return f"<h{level}>{content}</h{level}>"

        return re.sub(r"^(#{1,6})\s+(.+)$", _replace_header, text, flags=re.MULTILINE)

    def _convert_lists(self, text: str) -> str:
        """Convert markdown bullet lists to HTML <ul>."""
        lines = text.split("\n")
        result: List[str] = []
        in_list = False

        for line in lines:
            stripped = line.strip()
            is_list_item = bool(re.match(r"^[-*]\s+", stripped))

            if is_list_item:
                if not in_list:
                    result.append("<ul>")
                    in_list = True
                content = re.sub(r"^[-*]\s+", "", stripped)
                result.append(f"  <li>{content}</li>")
            else:
                if in_list:
                    result.append("</ul>")
                    in_list = False
                result.append(line)

        if in_list:
            result.append("</ul>")

        return "\n".join(result)

    def _convert_markdown_tables(self, text: str) -> str:
        """Convert markdown tables to HTML tables."""
        lines = text.split("\n")
        result: List[str] = []
        table_lines: List[str] = []
        in_table = False

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("|") and stripped.endswith("|"):
                table_lines.append(stripped)
                in_table = True
            else:
                if in_table and table_lines:
                    result.append(self._markdown_table_to_html(table_lines))
                    table_lines = []
                    in_table = False
                result.append(line)

        if table_lines:
            result.append(self._markdown_table_to_html(table_lines))

        return "\n".join(result)

    def _markdown_table_to_html(self, lines: List[str]) -> str:
        """Convert a set of markdown table lines to an HTML table."""
        if len(lines) < 2:
            return "\n".join(lines)

        def _parse_row(line: str) -> List[str]:
            cells = line.strip("|").split("|")
            return [cell.strip() for cell in cells]

        header_cells = _parse_row(lines[0])

        # Check if line 1 is the separator (---|---|---)
        separator_idx = 1
        if separator_idx < len(lines) and re.match(r"^\|[\s\-:|]+\|$", lines[separator_idx].strip()):
            data_start = 2
        else:
            data_start = 1

        html_parts = ['<table class="table table-sm">', "<thead>", "<tr>"]
        for cell in header_cells:
            html_parts.append(f"  <th>{escape_html(cell)}</th>")
        html_parts.extend(["</tr>", "</thead>", "<tbody>"])

        for line in lines[data_start:]:
            row_cells = _parse_row(line)
            html_parts.append("<tr>")
            for cell in row_cells:
                html_parts.append(f"  <td>{escape_html(cell)}</td>")
            html_parts.append("</tr>")

        html_parts.extend(["</tbody>", "</table>"])
        return "\n".join(html_parts)

    def _wrap_paragraphs(self, text: str) -> str:
        """Wrap loose text blocks in <p> tags.

        Skips lines that are already inside HTML block elements.
        """
        block_tags = {"table", "thead", "tbody", "tr", "ul", "ol", "li", "div", "h1", "h2", "h3", "h4", "h5", "h6", "p"}
        block_open_re = re.compile(r"^\s*<(" + "|".join(block_tags) + r")[\s>]", re.IGNORECASE)
        block_close_re = re.compile(r"</(" + "|".join(block_tags) + r")>\s*$", re.IGNORECASE)

        lines = text.split("\n")
        result: List[str] = []
        para_buffer: List[str] = []
        in_block = 0  # depth counter for block elements

        def flush_para():
            if para_buffer:
                joined = " ".join(para_buffer).strip()
                if joined:
                    result.append(f"<p>{joined}</p>")
                para_buffer.clear()

        for line in lines:
            # Track block depth
            opens = len(block_open_re.findall(line))
            closes = len(block_close_re.findall(line))

            if in_block > 0 or opens > 0:
                flush_para()
                result.append(line)
                in_block += opens - closes
                in_block = max(in_block, 0)
            elif line.strip() == "":
                flush_para()
            else:
                para_buffer.append(line.strip())

        flush_para()
        return "\n".join(result)

    # ------------------------------------------------------------------
    # Deduplication (moved from orchestrator)
    # ------------------------------------------------------------------
    def deduplicate(self, text: str) -> str:
        """Remove duplicate paragraphs/sections from response text.

        Handles both exact duplicates and near-duplicates (where one block
        is a substring of another).
        """
        if not text or len(text) < 100:
            return text

        blocks: List[tuple] = []
        try:
            pattern = re.compile(r"(?is)(<(?P<tag>table|ul|ol|div|p|h[1-6])\b[^>]*?>.*?</(?P=tag)>)")
            last_index = 0
            for m in pattern.finditer(text):
                start, end = m.span()
                if start > last_index:
                    interm = text[last_index:start]
                    for para in re.split(r"\n\s*\n", interm):
                        if para.strip():
                            blocks.append(("text", para))
                blocks.append(("html", m.group(0)))
                last_index = end
            if last_index < len(text):
                tail = text[last_index:]
                for para in re.split(r"\n\s*\n", tail):
                    if para.strip():
                        blocks.append(("text", para))
        except Exception:
            # Fallback: paragraph-based
            paragraphs = []
            current: List[str] = []
            for line in text.split("\n"):
                if line.strip():
                    current.append(line)
                elif current:
                    paragraphs.append("\n".join(current))
                    current = []
            if current:
                paragraphs.append("\n".join(current))

            seen: set = set()
            unique = []
            for para in paragraphs:
                normalized = " ".join(para.split()).lower()
                if normalized and normalized not in seen:
                    seen.add(normalized)
                    unique.append(para)
                elif not normalized:
                    unique.append(para)
            return "\n\n".join(unique)

        seen_blocks: set = set()
        seen_texts: List[str] = []  # ordered list for substring checks
        unique_blocks: List[tuple] = []
        for btype, content in blocks:
            visible = re.sub(r"<[^>]+>", " ", content) if btype == "html" else content
            normalized = " ".join(visible.split()).lower()
            if not normalized:
                unique_blocks.append((btype, content))
                continue
            # Exact duplicate
            if normalized in seen_blocks:
                continue
            # Near-duplicate: check if this is a substring of a prior block
            # or if a prior block is a substring of this one
            is_near_dup = False
            for prev in seen_texts:
                if normalized in prev or prev in normalized:
                    # Keep the longer one; if current is shorter, skip it
                    if len(normalized) <= len(prev):
                        is_near_dup = True
                    break
            if is_near_dup:
                continue
            seen_blocks.add(normalized)
            seen_texts.append(normalized)
            unique_blocks.append((btype, content))

        parts = [content.strip() if btype == "text" else content for btype, content in unique_blocks]
        return "\n\n".join(parts)
