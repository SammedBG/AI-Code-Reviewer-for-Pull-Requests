"""
GitHub API Client Module

This module provides a robust client for interacting with the GitHub API.
It handles authentication, rate limiting, retries, and all PR-related operations.

Design Decisions:
- Use httpx for async HTTP requests
- Integrate with GitHub App auth for automatic token management
- Implement exponential backoff for rate limit handling
- Support pagination for large result sets
"""

import asyncio
from typing import Any, Dict, List, Optional

import httpx
from aiolimiter import AsyncLimiter
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import get_settings
from app.logging_config import get_logger
from app.models import (
    AIReviewResult,
    CreateReviewRequest,
    PRContext,
    PRFile,
    ReviewComment,
    ReviewIssue,
    ReviewState,
    Severity,
)
from app.services.github_auth import get_github_auth, GitHubAuthError

logger = get_logger(__name__)


class GitHubAPIError(Exception):
    """Custom exception for GitHub API errors."""
    def __init__(self, message: str, status_code: int = None, response_body: str = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class GitHubRateLimitError(GitHubAPIError):
    """Exception raised when GitHub rate limit is exceeded."""
    pass


class GitHubClient:
    """
    Async GitHub API client with authentication and rate limiting.
    
    This client handles all interactions with the GitHub API including:
    - Fetching PR files and diffs
    - Creating review comments
    - Handling rate limits and retries
    
    Usage:
        client = GitHubClient(installation_id=123)
        files = await client.get_pr_files("owner", "repo", 42)
    """
    
    GITHUB_API_BASE = "https://api.github.com"
    
    def __init__(self, installation_id: int):
        """
        Initialize the GitHub client.
        
        Args:
            installation_id: GitHub App installation ID for authentication
        """
        self.installation_id = installation_id
        self.settings = get_settings()
        self.auth = get_github_auth()
        
        # Rate limiter: GitHub allows 5000 requests/hour for authenticated requests
        # We'll be conservative and use slightly less
        self._rate_limiter = AsyncLimiter(
            max_rate=self.settings.github_rate_limit,
            time_period=3600
        )
        
        # Track posted comment signatures for idempotency
        self._posted_comments: set = set()
    
    async def _get_headers(self) -> Dict[str, str]:
        """Get authenticated headers for API requests."""
        token = await self.auth.get_installation_token(self.installation_id)
        return {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
    
    async def _handle_rate_limit(self, response: httpx.Response) -> None:
        """
        Handle rate limit headers from GitHub response.
        
        If we're close to the rate limit, log a warning.
        If we've exceeded the limit, wait for reset.
        """
        remaining = response.headers.get("x-ratelimit-remaining")
        reset_time = response.headers.get("x-ratelimit-reset")
        
        if remaining:
            remaining_int = int(remaining)
            if remaining_int < 100:
                logger.warning(
                    "GitHub API rate limit running low",
                    remaining=remaining_int,
                    reset_at=reset_time
                )
            
            if remaining_int == 0 and reset_time:
                import time
                sleep_time = max(0, int(reset_time) - int(time.time())) + 5
                logger.warning(
                    "Rate limit exceeded, waiting for reset",
                    sleep_seconds=sleep_time
                )
                await asyncio.sleep(sleep_time)
                raise GitHubRateLimitError("Rate limit exceeded")
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((httpx.HTTPError, GitHubRateLimitError)),
        reraise=True
    )
    async def _request(
        self,
        method: str,
        endpoint: str,
        **kwargs
    ) -> httpx.Response:
        """
        Make an authenticated request to the GitHub API.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint (without base URL)
            **kwargs: Additional arguments to pass to httpx
            
        Returns:
            httpx.Response object
            
        Raises:
            GitHubAPIError: If the request fails
        """
        async with self._rate_limiter:
            headers = await self._get_headers()
            url = f"{self.GITHUB_API_BASE}{endpoint}"
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.request(
                    method,
                    url,
                    headers=headers,
                    **kwargs
                )
                
                await self._handle_rate_limit(response)
                
                if response.status_code == 401:
                    # Token might be invalidated, clear cache
                    self.auth.invalidate_token(self.installation_id)
                    raise GitHubAuthError("Authentication failed, token invalidated")
                
                if response.status_code >= 400:
                    error_body = response.text
                    logger.error(
                        "GitHub API error",
                        status_code=response.status_code,
                        endpoint=endpoint,
                        error=error_body[:500]  # Limit error length
                    )
                    raise GitHubAPIError(
                        f"GitHub API error: {response.status_code}",
                        status_code=response.status_code,
                        response_body=error_body
                    )
                
                return response
    
    async def get_pr_files(
        self,
        owner: str,
        repo: str,
        pr_number: int
    ) -> List[PRFile]:
        """
        Fetch all files changed in a pull request.
        
        Handles pagination for PRs with many files.
        Filters out files that shouldn't be processed.
        
        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: Pull request number
            
        Returns:
            List of PRFile objects
        """
        logger.info(
            "Fetching PR files",
            owner=owner,
            repo=repo,
            pr_number=pr_number
        )
        
        all_files: List[PRFile] = []
        page = 1
        per_page = 100
        
        while True:
            endpoint = f"/repos/{owner}/{repo}/pulls/{pr_number}/files"
            response = await self._request(
                "GET",
                endpoint,
                params={"page": page, "per_page": per_page}
            )
            
            files_data = response.json()
            
            if not files_data:
                break
            
            for file_data in files_data:
                pr_file = PRFile(
                    filename=file_data["filename"],
                    status=file_data["status"],
                    additions=file_data.get("additions", 0),
                    deletions=file_data.get("deletions", 0),
                    changes=file_data.get("changes", 0),
                    patch=file_data.get("patch"),
                    sha=file_data.get("sha", ""),
                    contents_url=file_data.get("contents_url")
                )
                
                # Filter files
                if self._should_skip_file(pr_file):
                    logger.debug(
                        "Skipping file",
                        filename=pr_file.filename,
                        reason=self._get_skip_reason(pr_file)
                    )
                    continue
                
                all_files.append(pr_file)
            
            # Check if we've hit the limit
            if len(all_files) >= self.settings.max_pr_files:
                logger.warning(
                    "PR file limit reached",
                    limit=self.settings.max_pr_files,
                    total_files=len(all_files)
                )
                break
            
            if len(files_data) < per_page:
                break
            
            page += 1
        
        logger.info(
            "Fetched PR files",
            total_files=len(all_files),
            owner=owner,
            repo=repo,
            pr_number=pr_number
        )
        
        return all_files[:self.settings.max_pr_files]
    
    def _should_skip_file(self, file: PRFile) -> bool:
        """Determine if a file should be skipped from review."""
        # Skip binary files
        if file.is_binary:
            return True
        
        # Skip files without patches (e.g., deleted files with no diff)
        if not file.patch:
            return True
        
        # Skip by extension
        for ext in self.settings.skip_extensions_list:
            if file.filename.endswith(ext):
                return True
        
        # Skip by path
        for skip_path in self.settings.skip_paths_list:
            if skip_path in file.filename:
                return True
        
        # Skip files that are too large
        patch_lines = file.patch.count("\n") + 1 if file.patch else 0
        if patch_lines > self.settings.max_diff_lines:
            return True
        
        return False
    
    def _get_skip_reason(self, file: PRFile) -> str:
        """Get human-readable reason for skipping a file."""
        if file.is_binary:
            return "binary_file"
        if not file.patch:
            return "no_patch"
        for ext in self.settings.skip_extensions_list:
            if file.filename.endswith(ext):
                return f"extension_{ext}"
        for skip_path in self.settings.skip_paths_list:
            if skip_path in file.filename:
                return f"path_{skip_path}"
        patch_lines = file.patch.count("\n") + 1 if file.patch else 0
        if patch_lines > self.settings.max_diff_lines:
            return "too_large"
        return "unknown"
    
    async def create_review(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        commit_sha: str,
        review_result: AIReviewResult,
        parsed_diffs: Dict[str, Any]
    ) -> bool:
        """
        Create a review on a pull request with inline comments.
        
        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: Pull request number
            commit_sha: SHA of the commit to review
            review_result: AI review results
            parsed_diffs: Parsed diff information for line validation
            
        Returns:
            True if review was posted successfully
        """
        if not self.settings.enable_github_comments:
            logger.info("GitHub comments disabled, skipping review post")
            return True
        
        logger.info(
            "Creating PR review",
            owner=owner,
            repo=repo,
            pr_number=pr_number,
            num_issues=len(review_result.reviews)
        )
        
        # Build inline comments
        comments: List[ReviewComment] = []
        
        if self.settings.enable_inline_comments:
            for issue in review_result.reviews:
                # Check severity threshold
                if not self._meets_severity_threshold(issue.severity):
                    continue
                
                # Validate line number exists in diff
                if not self._validate_line_number(issue.file, issue.line, parsed_diffs):
                    logger.warning(
                        "Invalid line number for comment",
                        file=issue.file,
                        line=issue.line
                    )
                    continue
                
                # Check for duplicate
                comment_sig = f"{issue.file}:{issue.line}:{issue.issue[:50]}"
                if comment_sig in self._posted_comments:
                    logger.debug("Skipping duplicate comment", signature=comment_sig)
                    continue
                
                # Format comment body
                body = self._format_inline_comment(issue)
                
                comments.append(ReviewComment(
                    path=issue.file,
                    line=issue.line,
                    body=body,
                    side="RIGHT"
                ))
                
                self._posted_comments.add(comment_sig)
        
        # Build summary body
        summary_body = self._format_summary(review_result)
        
        # Determine review state based on issues
        review_state = self._determine_review_state(review_result.reviews)
        
        # Create the review
        try:
            endpoint = f"/repos/{owner}/{repo}/pulls/{pr_number}/reviews"
            
            payload = {
                "commit_id": commit_sha,
                "body": summary_body if self.settings.enable_summary_comment else "",
                "event": review_state.value,
                "comments": [c.model_dump() for c in comments]
            }
            
            response = await self._request("POST", endpoint, json=payload)
            
            logger.info(
                "Review posted successfully",
                owner=owner,
                repo=repo,
                pr_number=pr_number,
                review_state=review_state.value,
                num_comments=len(comments)
            )
            
            return True
            
        except GitHubAPIError as e:
            logger.error(
                "Failed to post review",
                error=str(e),
                owner=owner,
                repo=repo,
                pr_number=pr_number
            )
            
            # Try posting comments individually if bulk fails
            if comments:
                await self._post_comments_individually(
                    owner, repo, pr_number, commit_sha, comments
                )
            
            return False
    
    async def _post_comments_individually(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        commit_sha: str,
        comments: List[ReviewComment]
    ) -> None:
        """
        Post comments individually as a fallback.
        
        This handles cases where the bulk review API fails
        due to invalid line numbers or other issues.
        """
        logger.info(
            "Attempting to post comments individually",
            num_comments=len(comments)
        )
        
        success_count = 0
        
        for comment in comments:
            try:
                endpoint = f"/repos/{owner}/{repo}/pulls/{pr_number}/comments"
                
                payload = {
                    "commit_id": commit_sha,
                    "path": comment.path,
                    "line": comment.line,
                    "side": comment.side,
                    "body": comment.body
                }
                
                await self._request("POST", endpoint, json=payload)
                success_count += 1
                
            except GitHubAPIError as e:
                logger.warning(
                    "Failed to post individual comment",
                    path=comment.path,
                    line=comment.line,
                    error=str(e)
                )
        
        logger.info(
            "Individual comment posting complete",
            success=success_count,
            failed=len(comments) - success_count
        )
    
    def _meets_severity_threshold(self, severity: str) -> bool:
        """Check if severity meets the minimum threshold."""
        severity_order = {"low": 0, "medium": 1, "high": 2}
        min_level = severity_order.get(self.settings.min_inline_severity, 0)
        issue_level = severity_order.get(severity.lower(), 0)
        return issue_level >= min_level
    
    def _validate_line_number(
        self,
        filename: str,
        line: int,
        parsed_diffs: Dict[str, Any]
    ) -> bool:
        """
        Validate that a line number exists in the diff.
        
        GitHub only accepts comments on lines that are part of the diff.
        """
        if filename not in parsed_diffs:
            return False
        
        diff_info = parsed_diffs[filename]
        valid_lines = diff_info.get("valid_comment_lines", set())
        
        return line in valid_lines
    
    def _format_inline_comment(self, issue: ReviewIssue) -> str:
        """Format an inline comment in markdown."""
        severity_emoji = {
            "low": "💡",
            "medium": "⚠️",
            "high": "🚨"
        }
        
        category_emoji = {
            "bug": "🐛",
            "security": "🔒",
            "performance": "⚡",
            "style": "🎨",
            "logic": "🧠"
        }
        
        emoji = severity_emoji.get(issue.severity, "💡")
        cat_emoji = category_emoji.get(issue.category, "📝")
        
        return f"""{emoji} **{issue.severity.upper()}** | {cat_emoji} {issue.category.upper()}

**Issue:** {issue.issue}

**Suggestion:** {issue.suggestion}

---
*Generated by AI Code Reviewer*"""
    
    def _format_summary(self, result: AIReviewResult) -> str:
        """Format the summary comment in markdown."""
        issue_count = len(result.reviews)
        
        # Count by severity
        severity_counts = {"high": 0, "medium": 0, "low": 0}
        for issue in result.reviews:
            severity_counts[issue.severity] = severity_counts.get(issue.severity, 0) + 1
        
        # Count by category
        category_counts: Dict[str, int] = {}
        for issue in result.reviews:
            category_counts[issue.category] = category_counts.get(issue.category, 0) + 1
        
        summary = f"""## 🤖 AI Code Review Summary

{result.summary}

### 📊 Overview

| Metric | Count |
|--------|-------|
| Total Issues | {issue_count} |
| 🚨 High Severity | {severity_counts['high']} |
| ⚠️ Medium Severity | {severity_counts['medium']} |
| 💡 Low Severity | {severity_counts['low']} |

"""
        
        if category_counts:
            summary += "### 📁 Issues by Category\n\n"
            for category, count in sorted(category_counts.items(), key=lambda x: -x[1]):
                summary += f"- **{category.title()}**: {count}\n"
        
        if issue_count == 0:
            summary += "\n✅ **No significant issues found!** Great work!\n"
        
        summary += "\n---\n*This review was automatically generated by AI Code Reviewer*"
        
        return summary
    
    def _determine_review_state(self, issues: List[ReviewIssue]) -> ReviewState:
        """Determine the review state based on issues found."""
        high_severity_count = sum(1 for i in issues if i.severity == "high")
        
        if high_severity_count > 0:
            return ReviewState.REQUEST_CHANGES
        
        return ReviewState.COMMENT
