"""
PR Review Processor Module

This module orchestrates the entire PR review process.
It coordinates fetching PR data, parsing diffs, running AI review,
and posting comments back to GitHub.

Design Decisions:
- Single responsibility: orchestrate the review process
- Handle errors gracefully, continuing with other files on failure
- Log extensively for debugging and monitoring
- Support dry-run mode for testing
"""

import asyncio
from typing import Dict, Optional

from app.config import get_settings
from app.logging_config import get_logger
from app.models import AIReviewResult, ParsedDiff, PRContext, PRFile
from app.services.ai_engine import get_ai_engine, AIReviewError
from app.services.diff_parser import get_diff_parser
from app.services.github_client import GitHubClient, GitHubAPIError

logger = get_logger(__name__)


class ReviewProcessorError(Exception):
    """Custom exception for review processing errors."""
    pass


class PRReviewProcessor:
    """
    Orchestrates the PR review process.
    
    This is the main coordinator that:
    1. Fetches PR files from GitHub
    2. Parses the diffs
    3. Sends code to AI for review
    4. Posts comments back to GitHub
    
    Usage:
        processor = PRReviewProcessor(pr_context)
        result = await processor.process()
    """
    
    def __init__(self, pr_context: PRContext):
        """
        Initialize the review processor.
        
        Args:
            pr_context: Complete PR context with metadata
        """
        self.pr_context = pr_context
        self.settings = get_settings()
        self.github_client = GitHubClient(pr_context.installation_id)
        self.diff_parser = get_diff_parser()
        self.ai_engine = get_ai_engine()
        
        # Store parsed data for later use
        self._parsed_diffs: list[ParsedDiff] = []
        self._file_metadata: Dict[str, Dict] = {}
    
    async def process(self) -> Optional[AIReviewResult]:
        """
        Execute the complete review process.
        
        Returns:
            AIReviewResult if successful, None on failure
        """
        logger.info(
            "Starting PR review process",
            owner=self.pr_context.owner,
            repo=self.pr_context.repo,
            pr_number=self.pr_context.pr_number,
            author=self.pr_context.author
        )
        
        try:
            # Step 1: Fetch PR files
            files = await self._fetch_files()
            if not files:
                logger.info("No reviewable files found")
                return None
            
            # Step 2: Parse diffs
            await self._parse_diffs(files)
            if not self._parsed_diffs:
                logger.info("No parseable diffs found")
                return None
            
            # Step 3: Check total diff size
            if not self._check_diff_size():
                logger.warning(
                    "PR too large, skipping review",
                    total_lines=sum(d.total_additions + d.total_deletions for d in self._parsed_diffs)
                )
                return None
            
            # Step 4: Run AI review
            review_result = await self._run_ai_review()
            if not review_result:
                logger.error("AI review returned no result")
                return None
            
            # Step 5: Post review to GitHub
            await self._post_review(review_result)
            
            logger.info(
                "PR review completed successfully",
                owner=self.pr_context.owner,
                repo=self.pr_context.repo,
                pr_number=self.pr_context.pr_number,
                num_issues=len(review_result.reviews)
            )
            
            return review_result
            
        except Exception as e:
            logger.error(
                "PR review process failed",
                owner=self.pr_context.owner,
                repo=self.pr_context.repo,
                pr_number=self.pr_context.pr_number,
                error=str(e),
                error_type=type(e).__name__
            )
            raise ReviewProcessorError(f"Review process failed: {e}") from e
    
    async def _fetch_files(self) -> list[PRFile]:
        """Fetch PR files from GitHub."""
        logger.debug("Fetching PR files")
        
        try:
            files = await self.github_client.get_pr_files(
                self.pr_context.owner,
                self.pr_context.repo,
                self.pr_context.pr_number
            )
            
            logger.info(
                "Fetched PR files",
                num_files=len(files),
                total_additions=sum(f.additions for f in files),
                total_deletions=sum(f.deletions for f in files)
            )
            
            # Update context with files
            self.pr_context.files = files
            
            return files
            
        except GitHubAPIError as e:
            logger.error(
                "Failed to fetch PR files",
                error=str(e)
            )
            raise ReviewProcessorError(f"Failed to fetch PR files: {e}") from e
    
    async def _parse_diffs(self, files: list[PRFile]) -> None:
        """Parse diffs for all files."""
        logger.debug("Parsing diffs", num_files=len(files))
        
        self._parsed_diffs, self._file_metadata = self.diff_parser.parse_all_files(files)
        
        logger.info(
            "Parsed diffs",
            num_files=len(self._parsed_diffs),
            total_additions=sum(d.total_additions for d in self._parsed_diffs),
            total_deletions=sum(d.total_deletions for d in self._parsed_diffs)
        )
    
    def _check_diff_size(self) -> bool:
        """Check if the total diff size is within limits."""
        total_lines = sum(
            d.total_additions + d.total_deletions
            for d in self._parsed_diffs
        )
        
        return total_lines <= self.settings.max_total_diff_lines
    
    async def _run_ai_review(self) -> Optional[AIReviewResult]:
        """Run AI review on the parsed diffs."""
        logger.debug("Running AI review")
        
        try:
            result = await self.ai_engine.review_changes(
                self._parsed_diffs,
                pr_title=self.pr_context.title,
                pr_body=self.pr_context.body
            )
            
            return result
            
        except AIReviewError as e:
            logger.error(
                "AI review failed",
                error=str(e)
            )
            raise ReviewProcessorError(f"AI review failed: {e}") from e
    
    async def _post_review(self, result: AIReviewResult) -> None:
        """Post review comments to GitHub."""
        logger.debug(
            "Posting review to GitHub",
            num_issues=len(result.reviews)
        )
        
        try:
            await self.github_client.create_review(
                self.pr_context.owner,
                self.pr_context.repo,
                self.pr_context.pr_number,
                self.pr_context.head_sha,
                result,
                self._file_metadata
            )
            
        except GitHubAPIError as e:
            logger.error(
                "Failed to post review",
                error=str(e)
            )
            # Don't fail the entire process if posting fails
            # The review was still generated successfully


async def process_pr_review(pr_context: PRContext) -> Optional[AIReviewResult]:
    """
    Convenience function to process a PR review.
    
    This is the main entry point for background task processing.
    
    Args:
        pr_context: Complete PR context
        
    Returns:
        AIReviewResult if successful, None otherwise
    """
    processor = PRReviewProcessor(pr_context)
    return await processor.process()
