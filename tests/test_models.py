"""
Tests for Data Models

Tests for all Pydantic models used in the application.
"""

from datetime import datetime

import pytest
from pydantic import ValidationError

from app.models import (
    AIReviewResult,
    DiffHunk,
    DiffLine,
    GitHubInstallation,
    GitHubPullRequest,
    GitHubPullRequestBase,
    GitHubPullRequestHead,
    GitHubRepository,
    GitHubUser,
    IssueCategory,
    PRContext,
    PRFile,
    PullRequestWebhookPayload,
    ReviewComment,
    ReviewIssue,
    Severity,
)


class TestGitHubModels:
    """Tests for GitHub-related models."""
    
    def test_github_user(self):
        """Test GitHubUser model."""
        user = GitHubUser(login="testuser", id=123, type="User")
        
        assert user.login == "testuser"
        assert user.id == 123
        assert user.type == "User"
    
    def test_github_repository(self):
        """Test GitHubRepository model."""
        owner = GitHubUser(login="owner", id=1, type="User")
        repo = GitHubRepository(
            id=100,
            name="repo",
            full_name="owner/repo",
            private=False,
            owner=owner,
            html_url="https://github.com/owner/repo"
        )
        
        assert repo.full_name == "owner/repo"
        assert repo.private is False
        assert repo.owner.login == "owner"
    
    def test_pr_file_is_binary(self):
        """Test PRFile binary detection."""
        # File with patch is not binary
        file_with_patch = PRFile(
            filename="test.py",
            status="modified",
            patch="@@ -1 +1 @@\n-old\n+new"
        )
        assert not file_with_patch.is_binary
        
        # File without patch and not removed is binary
        binary_file = PRFile(
            filename="image.png",
            status="added",
            patch=None
        )
        assert binary_file.is_binary
        
        # Removed file without patch is not binary
        removed_file = PRFile(
            filename="deleted.py",
            status="removed",
            patch=None
        )
        assert not removed_file.is_binary
    
    def test_pr_file_total_lines(self):
        """Test PRFile total lines calculation."""
        file = PRFile(
            filename="test.py",
            status="modified",
            additions=10,
            deletions=5
        )
        
        assert file.total_lines == 15


class TestReviewModels:
    """Tests for review-related models."""
    
    def test_review_issue_valid(self):
        """Test valid ReviewIssue."""
        issue = ReviewIssue(
            file="test.py",
            line=42,
            severity=Severity.HIGH,
            category=IssueCategory.BUG,
            issue="This is a bug that causes a crash",
            suggestion="Fix the bug by handling the null case"
        )
        
        assert issue.file == "test.py"
        assert issue.line == 42
        assert issue.severity == Severity.HIGH
        assert issue.category == IssueCategory.BUG
    
    def test_review_issue_invalid_line(self):
        """Test ReviewIssue with invalid line number."""
        with pytest.raises(ValidationError):
            ReviewIssue(
                file="test.py",
                line=0,  # Invalid: must be >= 1
                severity="high",
                category="bug",
                issue="This is a bug that causes a crash",
                suggestion="Fix the bug by handling the null case"
            )
    
    def test_review_issue_short_issue(self):
        """Test ReviewIssue with too short issue description."""
        with pytest.raises(ValidationError):
            ReviewIssue(
                file="test.py",
                line=10,
                severity="high",
                category="bug",
                issue="Short",  # Too short
                suggestion="Fix the bug by handling the null case"
            )
    
    def test_ai_review_result(self):
        """Test AIReviewResult model."""
        result = AIReviewResult(
            reviews=[
                ReviewIssue(
                    file="test.py",
                    line=42,
                    severity="high",
                    category="bug",
                    issue="Potential null pointer exception here",
                    suggestion="Add null check before accessing"
                )
            ],
            summary="This PR has one critical issue that needs attention."
        )
        
        assert len(result.reviews) == 1
        assert "critical" in result.summary.lower()
    
    def test_ai_review_result_empty_reviews(self):
        """Test AIReviewResult with no issues."""
        result = AIReviewResult(
            reviews=[],
            summary="This PR looks good. No issues found."
        )
        
        assert len(result.reviews) == 0
    
    def test_review_comment(self):
        """Test ReviewComment model."""
        comment = ReviewComment(
            path="src/main.py",
            line=42,
            body="Consider using a more descriptive variable name."
        )
        
        assert comment.path == "src/main.py"
        assert comment.side == "RIGHT"  # Default


class TestPRContext:
    """Tests for PRContext model."""
    
    def test_pr_context_full_repo_name(self):
        """Test PRContext full_repo_name property."""
        context = PRContext(
            owner="myowner",
            repo="myrepo",
            pr_number=123,
            head_sha="abc123",
            base_sha="def456",
            installation_id=999,
            title="Test PR",
            author="testuser"
        )
        
        assert context.full_repo_name == "myowner/myrepo"
    
    def test_pr_context_optional_body(self):
        """Test PRContext with optional body."""
        context = PRContext(
            owner="owner",
            repo="repo",
            pr_number=1,
            head_sha="abc",
            base_sha="def",
            installation_id=1,
            title="Title",
            author="author"
        )
        
        assert context.body is None


class TestDiffModels:
    """Tests for diff-related models."""
    
    def test_diff_hunk(self):
        """Test DiffHunk model."""
        hunk = DiffHunk(
            old_start=10,
            old_count=5,
            new_start=10,
            new_count=7,
            content="@@ -10,5 +10,7 @@\n context\n+added"
        )
        
        assert hunk.old_start == 10
        assert hunk.new_count == 7
    
    def test_diff_line_add(self):
        """Test DiffLine for added line."""
        line = DiffLine(
            content="new code here",
            line_type="add",
            old_line_number=None,
            new_line_number=42
        )
        
        assert line.line_type == "add"
        assert line.new_line_number == 42


class TestEnums:
    """Tests for enum values."""
    
    def test_severity_values(self):
        """Test Severity enum values."""
        assert Severity.LOW.value == "low"
        assert Severity.MEDIUM.value == "medium"
        assert Severity.HIGH.value == "high"
    
    def test_category_values(self):
        """Test IssueCategory enum values."""
        assert IssueCategory.BUG.value == "bug"
        assert IssueCategory.SECURITY.value == "security"
        assert IssueCategory.PERFORMANCE.value == "performance"
        assert IssueCategory.STYLE.value == "style"
        assert IssueCategory.LOGIC.value == "logic"
