"""
Services Package

This package contains all service modules for the AI PR Reviewer:
- github_auth: GitHub App authentication
- github_client: GitHub API client
- diff_parser: Diff parsing utilities
- ai_engine: AI review engine
"""

from app.services.github_auth import get_github_auth, GitHubAppAuth, GitHubAuthError
from app.services.github_client import get_github_client, GitHubClient, GitHubAPIError
from app.services.diff_parser import get_diff_parser, DiffParser, DiffParserError
from app.services.ai_engine import get_ai_engine, AIReviewEngine, AIReviewError


# Factory function for GitHub client (requires installation_id)
def get_github_client(installation_id: int) -> GitHubClient:
    """Create a GitHub client for a specific installation."""
    return GitHubClient(installation_id)


__all__ = [
    "get_github_auth",
    "GitHubAppAuth",
    "GitHubAuthError",
    "get_github_client",
    "GitHubClient",
    "GitHubAPIError",
    "get_diff_parser",
    "DiffParser",
    "DiffParserError",
    "get_ai_engine",
    "AIReviewEngine",
    "AIReviewError",
]
