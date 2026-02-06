"""
Tests for Diff Parser

Tests the unified diff parsing functionality.
"""

import pytest

from app.models import DiffLine, ParsedDiff
from app.services.diff_parser import DiffParser, get_diff_parser


class TestDiffParser:
    """Test suite for DiffParser."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.parser = DiffParser()
    
    def test_parse_simple_diff(self, sample_diff_patch):
        """Test parsing a simple diff."""
        result = self.parser.parse_file_diff("test.py", sample_diff_patch)
        
        assert isinstance(result, ParsedDiff)
        assert result.filename == "test.py"
        assert result.total_additions == 3
        assert result.total_deletions == 1
        assert len(result.hunks) == 1
    
    def test_parse_empty_patch(self):
        """Test parsing an empty patch."""
        result = self.parser.parse_file_diff("test.py", "")
        
        assert result.filename == "test.py"
        assert result.total_additions == 0
        assert result.total_deletions == 0
        assert len(result.hunks) == 0
    
    def test_parse_addition_only(self):
        """Test parsing a patch with only additions."""
        patch = '''@@ -1,3 +1,5 @@
 line 1
+new line 1
+new line 2
 line 2
 line 3
'''
        result = self.parser.parse_file_diff("test.py", patch)
        
        assert result.total_additions == 2
        assert result.total_deletions == 0
    
    def test_parse_deletion_only(self):
        """Test parsing a patch with only deletions."""
        patch = '''@@ -1,5 +1,3 @@
 line 1
-deleted line 1
-deleted line 2
 line 2
 line 3
'''
        result = self.parser.parse_file_diff("test.py", patch)
        
        assert result.total_additions == 0
        assert result.total_deletions == 2
    
    def test_parse_multiple_hunks(self):
        """Test parsing a patch with multiple hunks."""
        patch = '''@@ -1,3 +1,4 @@
 line 1
+new line
 line 2
 line 3
@@ -10,3 +11,4 @@
 line 10
+another new line
 line 11
 line 12
'''
        result = self.parser.parse_file_diff("test.py", patch)
        
        assert len(result.hunks) == 2
        assert result.total_additions == 2
    
    def test_get_valid_comment_lines(self, sample_diff_patch):
        """Test getting valid line numbers for comments."""
        parsed = self.parser.parse_file_diff("test.py", sample_diff_patch)
        valid_lines = self.parser.get_valid_comment_lines(parsed)
        
        assert isinstance(valid_lines, set)
        assert len(valid_lines) > 0
        # All valid lines should be positive integers
        assert all(line > 0 for line in valid_lines)
    
    def test_format_for_llm(self, sample_diff_patch):
        """Test formatting diffs for LLM consumption."""
        parsed = self.parser.parse_file_diff("test.py", sample_diff_patch)
        formatted = self.parser.format_for_llm([parsed])
        
        assert "test.py" in formatted
        assert "```diff" in formatted
        assert "@@" in formatted
    
    def test_get_diff_parser_singleton(self):
        """Test that get_diff_parser returns a singleton."""
        parser1 = get_diff_parser()
        parser2 = get_diff_parser()
        
        assert parser1 is parser2


class TestDiffLine:
    """Tests for DiffLine model."""
    
    def test_added_line(self):
        """Test an added line."""
        line = DiffLine(
            content="new code",
            line_type="add",
            old_line_number=None,
            new_line_number=5
        )
        
        assert line.line_type == "add"
        assert line.new_line_number == 5
        assert line.old_line_number is None
    
    def test_deleted_line(self):
        """Test a deleted line."""
        line = DiffLine(
            content="old code",
            line_type="delete",
            old_line_number=3,
            new_line_number=None
        )
        
        assert line.line_type == "delete"
        assert line.old_line_number == 3
        assert line.new_line_number is None
    
    def test_context_line(self):
        """Test a context line."""
        line = DiffLine(
            content="unchanged code",
            line_type="context",
            old_line_number=2,
            new_line_number=3
        )
        
        assert line.line_type == "context"
        assert line.old_line_number == 2
        assert line.new_line_number == 3
