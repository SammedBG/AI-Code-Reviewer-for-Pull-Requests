"""
Diff Parser Module

This module provides comprehensive parsing of unified diffs.
It extracts structured information that's suitable for LLM analysis.

Design Decisions:
- Parse unified diff format (standard git diff output)
- Extract line numbers accurately for both old and new files
- Identify added, deleted, and context lines
- Provide LLM-friendly output with file context
- Track valid line numbers for GitHub review comments
"""

import re
from typing import Dict, List, Optional, Set, Tuple

from app.logging_config import get_logger
from app.models import DiffHunk, DiffLine, ParsedDiff, PRFile

logger = get_logger(__name__)


# Regex pattern for hunk headers: @@ -old_start,old_count +new_start,new_count @@
HUNK_HEADER_PATTERN = re.compile(
    r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@"
)


class DiffParserError(Exception):
    """Custom exception for diff parsing errors."""
    pass


class DiffParser:
    """
    Parser for unified diff format.
    
    Converts raw diff patches into structured data suitable for
    AI analysis and GitHub comment placement.
    
    Usage:
        parser = DiffParser()
        parsed = parser.parse_file_diff(filename, patch_content)
    """
    
    def __init__(self):
        """Initialize the diff parser."""
        pass
    
    def parse_file_diff(self, filename: str, patch: str) -> ParsedDiff:
        """
        Parse a unified diff patch for a single file.
        
        Args:
            filename: Name of the file being diffed
            patch: Raw unified diff content
            
        Returns:
            ParsedDiff with structured diff information
            
        Raises:
            DiffParserError: If the diff cannot be parsed
        """
        if not patch:
            return ParsedDiff(filename=filename)
        
        try:
            hunks: List[DiffHunk] = []
            lines: List[DiffLine] = []
            added_lines: List[DiffLine] = []
            
            total_additions = 0
            total_deletions = 0
            
            current_hunk: Optional[DiffHunk] = None
            old_line_num = 0
            new_line_num = 0
            
            for raw_line in patch.split("\n"):
                # Check for hunk header
                hunk_match = HUNK_HEADER_PATTERN.match(raw_line)
                
                if hunk_match:
                    # Save previous hunk if exists
                    if current_hunk:
                        hunks.append(current_hunk)
                    
                    # Parse hunk header
                    old_start = int(hunk_match.group(1))
                    old_count = int(hunk_match.group(2)) if hunk_match.group(2) else 1
                    new_start = int(hunk_match.group(3))
                    new_count = int(hunk_match.group(4)) if hunk_match.group(4) else 1
                    
                    current_hunk = DiffHunk(
                        old_start=old_start,
                        old_count=old_count,
                        new_start=new_start,
                        new_count=new_count,
                        content=raw_line
                    )
                    
                    old_line_num = old_start
                    new_line_num = new_start
                    continue
                
                # Skip if we haven't seen a hunk header yet
                if current_hunk is None:
                    continue
                
                # Parse diff line
                if raw_line.startswith("+"):
                    # Added line
                    content = raw_line[1:]  # Remove the + prefix
                    diff_line = DiffLine(
                        content=content,
                        line_type="add",
                        old_line_number=None,
                        new_line_number=new_line_num
                    )
                    lines.append(diff_line)
                    added_lines.append(diff_line)
                    total_additions += 1
                    new_line_num += 1
                    
                elif raw_line.startswith("-"):
                    # Deleted line
                    content = raw_line[1:]  # Remove the - prefix
                    diff_line = DiffLine(
                        content=content,
                        line_type="delete",
                        old_line_number=old_line_num,
                        new_line_number=None
                    )
                    lines.append(diff_line)
                    total_deletions += 1
                    old_line_num += 1
                    
                elif raw_line.startswith(" ") or raw_line == "":
                    # Context line
                    content = raw_line[1:] if raw_line.startswith(" ") else raw_line
                    diff_line = DiffLine(
                        content=content,
                        line_type="context",
                        old_line_number=old_line_num,
                        new_line_number=new_line_num
                    )
                    lines.append(diff_line)
                    old_line_num += 1
                    new_line_num += 1
                
                # Update hunk content
                if current_hunk:
                    current_hunk.content += "\n" + raw_line
            
            # Don't forget the last hunk
            if current_hunk:
                hunks.append(current_hunk)
            
            # Get context lines (lines surrounding changes)
            modified_context = self._extract_modified_context(lines)
            
            return ParsedDiff(
                filename=filename,
                hunks=hunks,
                lines=lines,
                added_lines=added_lines,
                modified_context=modified_context,
                total_additions=total_additions,
                total_deletions=total_deletions
            )
            
        except Exception as e:
            logger.error(
                "Failed to parse diff",
                filename=filename,
                error=str(e)
            )
            raise DiffParserError(f"Failed to parse diff for {filename}: {e}") from e
    
    def _extract_modified_context(
        self,
        lines: List[DiffLine],
        context_size: int = 3
    ) -> List[DiffLine]:
        """
        Extract context lines surrounding modifications.
        
        This provides additional context for the AI reviewer
        without sending the entire file.
        
        Args:
            lines: All diff lines
            context_size: Number of context lines to include around changes
            
        Returns:
            List of context lines around modifications
        """
        if not lines:
            return []
        
        # Find indices of modified lines
        modified_indices: Set[int] = set()
        for i, line in enumerate(lines):
            if line.line_type in ("add", "delete"):
                modified_indices.add(i)
        
        # Expand to include context
        context_indices: Set[int] = set()
        for idx in modified_indices:
            for offset in range(-context_size, context_size + 1):
                context_idx = idx + offset
                if 0 <= context_idx < len(lines):
                    context_indices.add(context_idx)
        
        # Return lines in order
        return [lines[i] for i in sorted(context_indices)]
    
    def get_valid_comment_lines(self, parsed_diff: ParsedDiff) -> Set[int]:
        """
        Get the set of valid line numbers for GitHub comments.
        
        GitHub only allows comments on lines that appear in the diff.
        This method returns all valid line numbers in the new file.
        
        Args:
            parsed_diff: Parsed diff object
            
        Returns:
            Set of valid line numbers for comments
        """
        valid_lines: Set[int] = set()
        
        for line in parsed_diff.lines:
            if line.new_line_number is not None:
                valid_lines.add(line.new_line_number)
        
        return valid_lines
    
    def format_for_llm(
        self,
        parsed_diffs: List[ParsedDiff],
        max_tokens: int = 8000
    ) -> str:
        """
        Format parsed diffs for LLM consumption.
        
        Creates a structured, token-efficient representation
        of the code changes for AI review.
        
        Args:
            parsed_diffs: List of parsed diff objects
            max_tokens: Approximate maximum tokens to use
            
        Returns:
            Formatted string for LLM input
        """
        output_parts: List[str] = []
        total_chars = 0
        char_limit = max_tokens * 4  # Rough chars-to-tokens ratio
        
        for diff in parsed_diffs:
            if total_chars >= char_limit:
                output_parts.append(
                    f"\n... (truncated - {len(parsed_diffs) - len(output_parts)} files remaining)"
                )
                break
            
            file_section = self._format_file_for_llm(diff)
            
            if total_chars + len(file_section) > char_limit:
                # Truncate this file
                remaining = char_limit - total_chars
                file_section = file_section[:remaining] + "\n... (file truncated)"
            
            output_parts.append(file_section)
            total_chars += len(file_section)
        
        return "\n".join(output_parts)
    
    def _format_file_for_llm(self, diff: ParsedDiff) -> str:
        """
        Format a single file diff for LLM consumption.
        
        Creates a clear, structured representation of changes.
        """
        lines: List[str] = [
            f"## File: {diff.filename}",
            f"Changes: +{diff.total_additions} -{diff.total_deletions}",
            "",
            "### Code Changes:",
            "```diff"
        ]
        
        for hunk in diff.hunks:
            lines.append(hunk.content)
        
        lines.append("```")
        lines.append("")
        
        return "\n".join(lines)
    
    def parse_all_files(
        self,
        files: List[PRFile]
    ) -> Tuple[List[ParsedDiff], Dict[str, Dict]]:
        """
        Parse diffs for all files in a PR.
        
        Args:
            files: List of PR files with patches
            
        Returns:
            Tuple of (list of parsed diffs, dict mapping filenames to metadata)
        """
        parsed_diffs: List[ParsedDiff] = []
        file_metadata: Dict[str, Dict] = {}
        
        for file in files:
            if not file.patch:
                continue
            
            try:
                parsed = self.parse_file_diff(file.filename, file.patch)
                parsed_diffs.append(parsed)
                
                # Store metadata for comment validation
                valid_lines = self.get_valid_comment_lines(parsed)
                file_metadata[file.filename] = {
                    "valid_comment_lines": valid_lines,
                    "total_additions": parsed.total_additions,
                    "total_deletions": parsed.total_deletions
                }
                
            except DiffParserError as e:
                logger.warning(
                    "Skipping file due to parse error",
                    filename=file.filename,
                    error=str(e)
                )
                continue
        
        logger.info(
            "Parsed all file diffs",
            total_files=len(parsed_diffs),
            total_additions=sum(d.total_additions for d in parsed_diffs),
            total_deletions=sum(d.total_deletions for d in parsed_diffs)
        )
        
        return parsed_diffs, file_metadata


# Singleton instance
_parser_instance: Optional[DiffParser] = None


def get_diff_parser() -> DiffParser:
    """Get the singleton DiffParser instance."""
    global _parser_instance
    if _parser_instance is None:
        _parser_instance = DiffParser()
    return _parser_instance
