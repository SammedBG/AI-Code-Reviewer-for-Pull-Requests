"""
AI Review Engine Module

This module handles the AI-powered code review using OpenAI's API.
It generates structured, actionable feedback on code changes.

Design Decisions:
- Use OpenAI's JSON mode for structured output
- Implement strict schema validation for AI responses
- Rate limit API calls to avoid hitting quotas
- Provide detailed prompts for high-quality reviews
- Handle token limits gracefully
"""

import json
from typing import Any, Dict, List, Optional

from aiolimiter import AsyncLimiter
from openai import AsyncOpenAI
from pydantic import ValidationError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import get_settings
from app.logging_config import get_logger
from app.models import AIReviewResult, IssueCategory, ParsedDiff, ReviewIssue, Severity
from app.services.diff_parser import get_diff_parser

logger = get_logger(__name__)


class AIReviewError(Exception):
    """Custom exception for AI review errors."""
    pass


class AIReviewEngine:
    """
    AI-powered code review engine.
    
    Uses OpenAI's API to analyze code changes and generate
    structured, actionable feedback.
    
    Usage:
        engine = AIReviewEngine()
        result = await engine.review_changes(parsed_diffs)
    """
    
    # System prompt for the AI reviewer
    SYSTEM_PROMPT = """You are an expert code reviewer with deep expertise in software engineering best practices, security, performance optimization, and clean code principles.

Your task is to review code changes (diffs) and provide specific, actionable feedback.

## Review Guidelines:

1. **Focus on significant issues only** - Don't nitpick minor style issues unless they impact readability significantly.

2. **Be specific** - Reference exact line numbers, variable names, and code snippets.

3. **Provide actionable suggestions** - Don't just identify problems; explain how to fix them.

4. **Prioritize by severity**:
   - HIGH: Bugs, security vulnerabilities, data loss risks, crashes
   - MEDIUM: Performance issues, maintainability concerns, potential edge cases
   - LOW: Style improvements, minor optimizations, suggestions

5. **Categories to look for**:
   - BUG: Logic errors, incorrect implementations, type mismatches
   - SECURITY: Injection vulnerabilities, auth issues, data exposure, insecure practices
   - PERFORMANCE: Inefficient algorithms, unnecessary operations, memory leaks
   - STYLE: Readability issues, naming conventions, code organization
   - LOGIC: Flawed logic, missing edge cases, incorrect assumptions

## IMPORTANT RULES:

- Only comment on ADDED or MODIFIED lines (lines starting with +)
- Do NOT comment on DELETED lines (lines starting with -)
- Line numbers must be from the NEW file (right side of diff)
- Skip trivial changes (whitespace, imports reorganization)
- Be constructive, not critical
- If code is good, say so in the summary but don't force issues

## Output Format:

You MUST respond with valid JSON matching this exact schema:

{
  "reviews": [
    {
      "file": "path/to/file.py",
      "line": 42,
      "severity": "low" | "medium" | "high",
      "category": "bug" | "security" | "performance" | "style" | "logic",
      "issue": "Clear description of the issue (minimum 10 characters)",
      "suggestion": "Specific suggestion for improvement (minimum 10 characters)"
    }
  ],
  "summary": "Overall assessment of the changes (minimum 20 characters)"
}

If no issues are found, return an empty reviews array with a positive summary."""

    def __init__(self):
        """Initialize the AI review engine."""
        self.settings = get_settings()
        self.client = AsyncOpenAI(api_key=self.settings.openai_api_key)
        self.diff_parser = get_diff_parser()
        
        # Rate limiter for OpenAI API
        self._rate_limiter = AsyncLimiter(
            max_rate=self.settings.openai_rate_limit_rpm,
            time_period=60
        )
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type(Exception),
        reraise=True
    )
    async def review_changes(
        self,
        parsed_diffs: List[ParsedDiff],
        pr_title: Optional[str] = None,
        pr_body: Optional[str] = None
    ) -> AIReviewResult:
        """
        Review code changes using AI.
        
        Args:
            parsed_diffs: List of parsed diff objects
            pr_title: Optional PR title for context
            pr_body: Optional PR description for context
            
        Returns:
            AIReviewResult with issues and summary
            
        Raises:
            AIReviewError: If the review fails
        """
        if not parsed_diffs:
            return AIReviewResult(
                reviews=[],
                summary="No code changes to review."
            )
        
        # Format diffs for LLM
        formatted_diffs = self.diff_parser.format_for_llm(
            parsed_diffs,
            max_tokens=self.settings.openai_max_tokens // 2  # Leave room for response
        )
        
        # Build user prompt
        user_prompt = self._build_user_prompt(formatted_diffs, pr_title, pr_body)
        
        logger.info(
            "Sending code review request to AI",
            num_files=len(parsed_diffs),
            prompt_length=len(user_prompt)
        )
        
        async with self._rate_limiter:
            try:
                response = await self.client.chat.completions.create(
                    model=self.settings.openai_model,
                    messages=[
                        {"role": "system", "content": self.SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=self.settings.openai_temperature,
                    max_tokens=self.settings.openai_max_tokens,
                    response_format={"type": "json_object"}
                )
                
                # Extract and parse response
                content = response.choices[0].message.content
                
                if not content:
                    raise AIReviewError("Empty response from AI")
                
                logger.debug(
                    "Received AI response",
                    response_length=len(content),
                    usage=response.usage.model_dump() if response.usage else None
                )
                
                # Parse and validate JSON response
                result = self._parse_response(content, parsed_diffs)
                
                logger.info(
                    "AI review completed",
                    num_issues=len(result.reviews),
                    high_severity=sum(1 for r in result.reviews if r.severity == "high"),
                    medium_severity=sum(1 for r in result.reviews if r.severity == "medium"),
                    low_severity=sum(1 for r in result.reviews if r.severity == "low")
                )
                
                return result
                
            except Exception as e:
                logger.error(
                    "AI review failed",
                    error=str(e),
                    error_type=type(e).__name__
                )
                raise AIReviewError(f"AI review failed: {e}") from e
    
    def _build_user_prompt(
        self,
        formatted_diffs: str,
        pr_title: Optional[str],
        pr_body: Optional[str]
    ) -> str:
        """Build the user prompt for the AI."""
        prompt_parts = ["# Code Review Request\n"]
        
        if pr_title:
            prompt_parts.append(f"## PR Title: {pr_title}\n")
        
        if pr_body:
            # Truncate long PR bodies
            body = pr_body[:1000] + "..." if len(pr_body) > 1000 else pr_body
            prompt_parts.append(f"## PR Description:\n{body}\n")
        
        prompt_parts.append("## Code Changes:\n")
        prompt_parts.append(formatted_diffs)
        prompt_parts.append("\n\n## Your Review:\n")
        prompt_parts.append("Please analyze the above code changes and provide your review in JSON format.")
        
        return "\n".join(prompt_parts)
    
    def _parse_response(
        self,
        content: str,
        parsed_diffs: List[ParsedDiff]
    ) -> AIReviewResult:
        """
        Parse and validate the AI response.
        
        Args:
            content: Raw JSON response from AI
            parsed_diffs: Original parsed diffs for validation
            
        Returns:
            Validated AIReviewResult
            
        Raises:
            AIReviewError: If response is invalid
        """
        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            logger.error("Failed to parse AI response as JSON", error=str(e))
            raise AIReviewError(f"Invalid JSON response: {e}") from e
        
        # Build set of valid files
        valid_files = {d.filename for d in parsed_diffs}
        
        # Build set of valid line numbers per file
        valid_lines: Dict[str, set] = {}
        for diff in parsed_diffs:
            valid_lines[diff.filename] = {
                line.new_line_number
                for line in diff.lines
                if line.new_line_number is not None
            }
        
        # Validate and filter reviews
        validated_reviews: List[ReviewIssue] = []
        
        for review_data in data.get("reviews", []):
            try:
                # Basic validation
                review = self._validate_review_issue(review_data)
                
                # Check file exists in diff
                if review.file not in valid_files:
                    logger.warning(
                        "AI referenced non-existent file",
                        file=review.file,
                        valid_files=list(valid_files)
                    )
                    continue
                
                # Check line number is valid
                file_lines = valid_lines.get(review.file, set())
                if review.line not in file_lines:
                    logger.warning(
                        "AI referenced invalid line number",
                        file=review.file,
                        line=review.line,
                        valid_range=f"{min(file_lines) if file_lines else 0}-{max(file_lines) if file_lines else 0}"
                    )
                    # Try to find nearest valid line
                    nearest = self._find_nearest_valid_line(review.line, file_lines)
                    if nearest:
                        review.line = nearest
                        logger.info(
                            "Adjusted line number to nearest valid",
                            original=review_data.get("line"),
                            adjusted=nearest
                        )
                    else:
                        continue
                
                validated_reviews.append(review)
                
            except (ValidationError, ValueError) as e:
                logger.warning(
                    "Skipping invalid review issue",
                    error=str(e),
                    data=review_data
                )
                continue
        
        # Validate summary
        summary = data.get("summary", "")
        if not summary or len(summary) < 20:
            summary = "AI code review completed. See inline comments for details."
        
        return AIReviewResult(
            reviews=validated_reviews,
            summary=summary
        )
    
    def _validate_review_issue(self, data: Dict[str, Any]) -> ReviewIssue:
        """
        Validate a single review issue.
        
        Args:
            data: Raw issue data from AI
            
        Returns:
            Validated ReviewIssue
            
        Raises:
            ValueError: If data is invalid
        """
        # Validate required fields
        required_fields = ["file", "line", "severity", "category", "issue", "suggestion"]
        for field in required_fields:
            if field not in data:
                raise ValueError(f"Missing required field: {field}")
        
        # Normalize severity
        severity = str(data["severity"]).lower()
        if severity not in ["low", "medium", "high"]:
            severity = "low"
        
        # Normalize category
        category = str(data["category"]).lower()
        if category not in ["bug", "security", "performance", "style", "logic"]:
            category = "style"
        
        # Validate line number
        line = int(data["line"])
        if line < 1:
            raise ValueError(f"Invalid line number: {line}")
        
        # Validate issue and suggestion length
        issue = str(data["issue"])
        suggestion = str(data["suggestion"])
        
        if len(issue) < 10:
            raise ValueError(f"Issue description too short: {issue}")
        if len(suggestion) < 10:
            raise ValueError(f"Suggestion too short: {suggestion}")
        
        return ReviewIssue(
            file=str(data["file"]),
            line=line,
            severity=severity,
            category=category,
            issue=issue,
            suggestion=suggestion
        )
    
    def _find_nearest_valid_line(
        self,
        target: int,
        valid_lines: set,
        max_distance: int = 5
    ) -> Optional[int]:
        """
        Find the nearest valid line number.
        
        Args:
            target: Target line number from AI
            valid_lines: Set of valid line numbers
            max_distance: Maximum distance to search
            
        Returns:
            Nearest valid line number or None
        """
        if not valid_lines:
            return None
        
        for distance in range(1, max_distance + 1):
            # Check above
            if target - distance in valid_lines:
                return target - distance
            # Check below
            if target + distance in valid_lines:
                return target + distance
        
        return None


# Singleton instance
_engine_instance: Optional[AIReviewEngine] = None


def get_ai_engine() -> AIReviewEngine:
    """Get the singleton AIReviewEngine instance."""
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = AIReviewEngine()
    return _engine_instance
