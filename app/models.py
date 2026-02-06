"""
Data Models Module

This module defines all Pydantic models used throughout the application.
Strong typing ensures data integrity and provides clear contracts between components.

Design Decisions:
- Use Pydantic models for all data transfer objects
- Strict validation to fail fast on invalid data
- Clear separation between GitHub models, AI models, and internal models
"""

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


# =============================================================================
# Enums
# =============================================================================

class PRAction(str, Enum):
    """Valid pull request actions we handle."""
    OPENED = "opened"
    SYNCHRONIZE = "synchronize"


class Severity(str, Enum):
    """Severity levels for code review issues."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class IssueCategory(str, Enum):
    """Categories for code review issues."""
    BUG = "bug"
    SECURITY = "security"
    PERFORMANCE = "performance"
    STYLE = "style"
    LOGIC = "logic"


class ReviewState(str, Enum):
    """GitHub review states."""
    APPROVE = "APPROVE"
    REQUEST_CHANGES = "REQUEST_CHANGES"
    COMMENT = "COMMENT"


# =============================================================================
# GitHub Webhook Models
# =============================================================================

class GitHubUser(BaseModel):
    """GitHub user information."""
    login: str
    id: int
    type: str = "User"


class GitHubRepository(BaseModel):
    """GitHub repository information."""
    id: int
    name: str
    full_name: str
    private: bool
    owner: GitHubUser
    html_url: str
    default_branch: str = "main"


class GitHubPullRequestHead(BaseModel):
    """PR head (source branch) information."""
    ref: str
    sha: str
    repo: Optional[GitHubRepository] = None


class GitHubPullRequestBase(BaseModel):
    """PR base (target branch) information."""
    ref: str
    sha: str
    repo: Optional[GitHubRepository] = None


class GitHubPullRequest(BaseModel):
    """Pull request information from webhook."""
    id: int
    number: int
    state: str
    title: str
    body: Optional[str] = None
    user: GitHubUser
    html_url: str
    diff_url: str
    patch_url: str
    head: GitHubPullRequestHead
    base: GitHubPullRequestBase
    merged: bool = False
    draft: bool = False
    created_at: datetime
    updated_at: datetime


class GitHubInstallation(BaseModel):
    """GitHub App installation information."""
    id: int
    account: Optional[GitHubUser] = None


class PullRequestWebhookPayload(BaseModel):
    """Complete pull request webhook payload."""
    action: str
    number: int
    pull_request: GitHubPullRequest
    repository: GitHubRepository
    sender: GitHubUser
    installation: GitHubInstallation


# =============================================================================
# PR File Models
# =============================================================================

class PRFile(BaseModel):
    """
    Information about a file in a pull request.
    
    Attributes:
        filename: Path to the file in the repository
        status: Change status (added, removed, modified, renamed, copied)
        additions: Number of added lines
        deletions: Number of deleted lines
        changes: Total number of changes
        patch: Unified diff patch (may be None for binary files)
        sha: Blob SHA of the file
        contents_url: API URL to fetch file contents
    """
    filename: str
    status: str
    additions: int = 0
    deletions: int = 0
    changes: int = 0
    patch: Optional[str] = None
    sha: str = ""
    contents_url: Optional[str] = None
    
    @property
    def is_binary(self) -> bool:
        """Check if file appears to be binary (no patch available)."""
        return self.patch is None and self.status != "removed"
    
    @property
    def total_lines(self) -> int:
        """Get total number of changed lines."""
        return self.additions + self.deletions


# =============================================================================
# Diff Parsing Models
# =============================================================================

class DiffHunk(BaseModel):
    """
    Represents a single hunk in a diff.
    
    A hunk is a contiguous section of changes in a file.
    """
    old_start: int = Field(ge=0, description="Starting line in old file")
    old_count: int = Field(ge=0, description="Number of lines in old file")
    new_start: int = Field(ge=0, description="Starting line in new file")
    new_count: int = Field(ge=0, description="Number of lines in new file")
    content: str = Field(description="Raw hunk content including headers")


class DiffLine(BaseModel):
    """
    Represents a single line in a diff.
    
    Attributes:
        content: The actual line content (without +/- prefix)
        line_type: Type of change (add, delete, context)
        old_line_number: Line number in old file (None for additions)
        new_line_number: Line number in new file (None for deletions)
    """
    content: str
    line_type: str  # "add", "delete", "context"
    old_line_number: Optional[int] = None
    new_line_number: Optional[int] = None


class ParsedDiff(BaseModel):
    """
    Fully parsed diff for a single file.
    
    This is the LLM-friendly representation of file changes.
    """
    filename: str
    hunks: List[DiffHunk] = []
    lines: List[DiffLine] = []
    added_lines: List[DiffLine] = []
    modified_context: List[DiffLine] = []
    total_additions: int = 0
    total_deletions: int = 0


# =============================================================================
# AI Review Models
# =============================================================================

class ReviewIssue(BaseModel):
    """
    A single issue identified by the AI reviewer.
    
    This model is strictly enforced - the AI must return data matching this schema.
    """
    file: str = Field(description="Filename where the issue was found")
    line: int = Field(ge=1, description="Line number in the new file")
    severity: Severity = Field(description="Issue severity level")
    category: IssueCategory = Field(description="Issue category")
    issue: str = Field(min_length=10, description="Description of the issue")
    suggestion: str = Field(min_length=10, description="Suggested fix or improvement")
    
    class Config:
        use_enum_values = True


class AIReviewResult(BaseModel):
    """
    Complete AI review result for a pull request.
    
    The AI must return data matching this exact schema.
    """
    reviews: List[ReviewIssue] = Field(
        default=[],
        description="List of specific issues found"
    )
    summary: str = Field(
        min_length=20,
        description="Overall summary of the code review"
    )


# =============================================================================
# GitHub Comment Models
# =============================================================================

class ReviewComment(BaseModel):
    """
    A review comment to be posted on GitHub.
    
    This maps to GitHub's review comment API structure.
    """
    path: str = Field(description="Relative path to the file")
    line: int = Field(ge=1, description="Line number in the new file")
    body: str = Field(min_length=1, description="Comment content in markdown")
    side: str = Field(default="RIGHT", description="Side of the diff (LEFT or RIGHT)")


class CreateReviewRequest(BaseModel):
    """
    Request to create a review on GitHub.
    
    Includes both the summary comment and inline comments.
    """
    commit_id: str = Field(description="SHA of the commit being reviewed")
    body: str = Field(description="Summary comment body")
    event: ReviewState = Field(default=ReviewState.COMMENT)
    comments: List[ReviewComment] = Field(default=[])


# =============================================================================
# Internal Processing Models
# =============================================================================

class PRContext(BaseModel):
    """
    Complete context for processing a pull request review.
    
    This is the main data structure passed through the review pipeline.
    """
    owner: str
    repo: str
    pr_number: int
    head_sha: str
    base_sha: str
    installation_id: int
    title: str
    body: Optional[str] = None
    author: str
    files: List[PRFile] = []
    parsed_diffs: List[ParsedDiff] = []
    
    @property
    def full_repo_name(self) -> str:
        """Get the full repository name (owner/repo)."""
        return f"{self.owner}/{self.repo}"


class ReviewJob(BaseModel):
    """
    A queued review job for background processing.
    """
    id: str = Field(description="Unique job identifier")
    pr_context: PRContext
    created_at: datetime = Field(default_factory=datetime.utcnow)
    status: str = Field(default="pending")
    error: Optional[str] = None
    result: Optional[AIReviewResult] = None
