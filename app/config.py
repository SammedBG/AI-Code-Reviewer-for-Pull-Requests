"""
Configuration Management Module

This module handles all application configuration using Pydantic Settings.
Configuration is loaded from environment variables with strong typing and validation.

Design Decisions:
- Use Pydantic Settings for automatic environment variable loading
- Provide sensible defaults for optional settings
- Validate configuration at startup (fail-fast approach)
- Support both file path and direct content for private key (flexibility)
"""

from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    
    All sensitive values are loaded from environment variables only,
    never hardcoded or logged.
    """
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )
    
    # =========================================================================
    # GitHub App Configuration
    # =========================================================================
    github_app_id: str = Field(
        description="GitHub App ID from app settings"
    )
    
    github_private_key_path: Optional[str] = Field(
        default=None,
        description="Path to GitHub App private key .pem file"
    )
    
    github_private_key: Optional[str] = Field(
        default=None,
        description="GitHub App private key content (alternative to path)"
    )
    
    github_webhook_secret: str = Field(
        description="Webhook secret for signature verification"
    )
    
    # =========================================================================
    # OpenAI Configuration
    # =========================================================================
    openai_api_key: str = Field(
        description="OpenAI API key"
    )
    
    openai_model: str = Field(
        default="gpt-4-turbo-preview",
        description="OpenAI model to use for code review"
    )
    
    openai_max_tokens: int = Field(
        default=4096,
        ge=100,
        le=128000,
        description="Maximum tokens for AI response"
    )
    
    openai_temperature: float = Field(
        default=0.3,
        ge=0.0,
        le=1.0,
        description="Temperature for AI responses"
    )
    
    # =========================================================================
    # PR Processing Limits
    # =========================================================================
    max_pr_files: int = Field(
        default=50,
        ge=1,
        le=500,
        description="Maximum number of files to process per PR"
    )
    
    max_diff_lines: int = Field(
        default=500,
        ge=10,
        le=5000,
        description="Maximum diff lines per file"
    )
    
    max_total_diff_lines: int = Field(
        default=3000,
        ge=100,
        le=50000,
        description="Maximum total diff lines for entire PR"
    )
    
    max_file_size_bytes: int = Field(
        default=100000,
        ge=1000,
        description="Maximum file size in bytes"
    )
    
    skip_file_extensions: str = Field(
        default=".min.js,.min.css,.lock,.sum,.map",
        description="Comma-separated file extensions to skip"
    )
    
    skip_paths: str = Field(
        default="vendor/,node_modules/,dist/,build/,__pycache__/",
        description="Comma-separated paths to skip"
    )
    
    # =========================================================================
    # Rate Limiting
    # =========================================================================
    github_rate_limit: int = Field(
        default=5000,
        ge=100,
        description="GitHub API rate limit per hour"
    )
    
    openai_rate_limit_rpm: int = Field(
        default=60,
        ge=1,
        description="OpenAI API rate limit per minute"
    )
    
    # =========================================================================
    # Retry Configuration
    # =========================================================================
    max_retries: int = Field(
        default=3,
        ge=0,
        le=10,
        description="Maximum retry attempts"
    )
    
    retry_base_delay: float = Field(
        default=1.0,
        ge=0.1,
        description="Base delay between retries in seconds"
    )
    
    retry_max_delay: float = Field(
        default=60.0,
        ge=1.0,
        description="Maximum delay between retries in seconds"
    )
    
    # =========================================================================
    # Server Configuration
    # =========================================================================
    host: str = Field(
        default="0.0.0.0",
        description="Host to bind the server"
    )
    
    port: int = Field(
        default=8000,
        ge=1,
        le=65535,
        description="Port to bind the server"
    )
    
    # =========================================================================
    # Logging Configuration
    # =========================================================================
    log_level: str = Field(
        default="INFO",
        description="Logging level"
    )
    
    log_json_format: bool = Field(
        default=True,
        description="Enable JSON logging format"
    )
    
    log_requests: bool = Field(
        default=False,
        description="Enable request/response logging"
    )
    
    # =========================================================================
    # Feature Flags
    # =========================================================================
    enable_github_comments: bool = Field(
        default=True,
        description="Enable posting comments to GitHub"
    )
    
    enable_summary_comment: bool = Field(
        default=True,
        description="Enable summary comment on PR"
    )
    
    enable_inline_comments: bool = Field(
        default=True,
        description="Enable inline comments on specific lines"
    )
    
    min_inline_severity: str = Field(
        default="low",
        description="Minimum severity for inline comments"
    )
    
    # =========================================================================
    # Validators
    # =========================================================================
    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Ensure log level is valid."""
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        v_upper = v.upper()
        if v_upper not in valid_levels:
            raise ValueError(f"Invalid log level: {v}. Must be one of {valid_levels}")
        return v_upper
    
    @field_validator("min_inline_severity")
    @classmethod
    def validate_severity(cls, v: str) -> str:
        """Ensure severity level is valid."""
        valid_severities = {"low", "medium", "high"}
        v_lower = v.lower()
        if v_lower not in valid_severities:
            raise ValueError(f"Invalid severity: {v}. Must be one of {valid_severities}")
        return v_lower
    
    # =========================================================================
    # Computed Properties
    # =========================================================================
    @property
    def skip_extensions_list(self) -> List[str]:
        """Get list of file extensions to skip."""
        return [ext.strip() for ext in self.skip_file_extensions.split(",") if ext.strip()]
    
    @property
    def skip_paths_list(self) -> List[str]:
        """Get list of paths to skip."""
        return [path.strip() for path in self.skip_paths.split(",") if path.strip()]
    
    def get_private_key(self) -> str:
        """
        Get the GitHub App private key content.
        
        Supports two modes:
        1. Direct content via GITHUB_PRIVATE_KEY env var
        2. File path via GITHUB_PRIVATE_KEY_PATH env var
        
        Returns:
            Private key content as string
            
        Raises:
            ValueError: If neither option is configured or file doesn't exist
        """
        # Direct content takes precedence
        if self.github_private_key:
            # Handle newline escaping in env vars
            return self.github_private_key.replace("\\n", "\n")
        
        # Fall back to file path
        if self.github_private_key_path:
            key_path = Path(self.github_private_key_path)
            if not key_path.exists():
                raise ValueError(f"Private key file not found: {key_path}")
            return key_path.read_text()
        
        raise ValueError(
            "GitHub private key not configured. "
            "Set either GITHUB_PRIVATE_KEY or GITHUB_PRIVATE_KEY_PATH"
        )


@lru_cache()
def get_settings() -> Settings:
    """
    Get cached application settings.
    
    Uses lru_cache to ensure settings are only loaded once,
    which is important for performance and consistency.
    
    Returns:
        Settings instance
    """
    return Settings()
