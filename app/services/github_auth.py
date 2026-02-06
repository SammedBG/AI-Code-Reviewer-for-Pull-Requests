"""
GitHub App Authentication Service

This module handles GitHub App authentication including:
- JWT generation for App authentication
- Installation access token generation
- Automatic token refresh when expired

Design Decisions:
- Use RS256 algorithm for JWT signing (GitHub requirement)
- Cache tokens to minimize API calls
- Automatically refresh tokens before they expire
- Thread-safe token management
"""

import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

import httpx
import jwt
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import get_settings
from app.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class CachedToken:
    """Cached installation access token with expiration."""
    token: str
    expires_at: datetime
    
    @property
    def is_expired(self) -> bool:
        """Check if token is expired or will expire within 5 minutes."""
        buffer = timedelta(minutes=5)
        return datetime.now(timezone.utc) >= (self.expires_at - buffer)


class GitHubAuthError(Exception):
    """Custom exception for GitHub authentication errors."""
    pass


class GitHubAppAuth:
    """
    GitHub App Authentication Manager.
    
    Handles JWT generation and installation access token management
    for GitHub App authentication.
    
    Usage:
        auth = GitHubAppAuth()
        token = await auth.get_installation_token(installation_id)
        # Use token for API requests
    """
    
    # GitHub API endpoints
    GITHUB_API_BASE = "https://api.github.com"
    
    def __init__(self):
        """Initialize the auth manager."""
        self.settings = get_settings()
        self._private_key: Optional[str] = None
        # Cache tokens by installation_id
        self._token_cache: Dict[int, CachedToken] = {}
    
    @property
    def private_key(self) -> str:
        """Lazy load and cache the private key."""
        if self._private_key is None:
            self._private_key = self.settings.get_private_key()
            logger.debug("Loaded GitHub App private key")
        return self._private_key
    
    def generate_jwt(self) -> str:
        """
        Generate a JWT for GitHub App authentication.
        
        The JWT is used to authenticate as the GitHub App itself,
        not as an installation. It's valid for up to 10 minutes.
        
        Returns:
            Signed JWT string
            
        Raises:
            GitHubAuthError: If JWT generation fails
        """
        try:
            now = int(time.time())
            
            payload = {
                # Issued at time (60 seconds in the past for clock drift)
                "iat": now - 60,
                # Expiration time (10 minute maximum)
                "exp": now + (9 * 60),
                # GitHub App ID
                "iss": self.settings.github_app_id,
            }
            
            token = jwt.encode(
                payload,
                self.private_key,
                algorithm="RS256"
            )
            
            logger.debug("Generated GitHub App JWT", app_id=self.settings.github_app_id)
            return token
            
        except Exception as e:
            logger.error("Failed to generate JWT", error=str(e))
            raise GitHubAuthError(f"Failed to generate JWT: {e}") from e
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(httpx.HTTPError),
        reraise=True
    )
    async def _fetch_installation_token(self, installation_id: int) -> CachedToken:
        """
        Fetch a new installation access token from GitHub.
        
        This method is called when we don't have a cached token
        or the cached token is expired.
        
        Args:
            installation_id: GitHub App installation ID
            
        Returns:
            CachedToken with the access token and expiration
            
        Raises:
            GitHubAuthError: If token fetch fails
        """
        jwt_token = self.generate_jwt()
        
        url = f"{self.GITHUB_API_BASE}/app/installations/{installation_id}/access_tokens"
        
        headers = {
            "Authorization": f"Bearer {jwt_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(url, headers=headers)
                response.raise_for_status()
                
                data = response.json()
                token = data["token"]
                # Parse expiration time from GitHub response
                expires_at = datetime.fromisoformat(
                    data["expires_at"].replace("Z", "+00:00")
                )
                
                logger.info(
                    "Obtained installation access token",
                    installation_id=installation_id,
                    expires_at=expires_at.isoformat()
                )
                
                return CachedToken(token=token, expires_at=expires_at)
                
            except httpx.HTTPStatusError as e:
                error_body = e.response.text
                logger.error(
                    "Failed to get installation token",
                    installation_id=installation_id,
                    status_code=e.response.status_code,
                    error=error_body
                )
                raise GitHubAuthError(
                    f"Failed to get installation token: {e.response.status_code} - {error_body}"
                ) from e
    
    async def get_installation_token(self, installation_id: int) -> str:
        """
        Get an installation access token, using cache when possible.
        
        This is the main method to call for getting authentication tokens.
        It handles caching and automatic refresh of expired tokens.
        
        Args:
            installation_id: GitHub App installation ID
            
        Returns:
            Valid installation access token
            
        Raises:
            GitHubAuthError: If authentication fails
        """
        # Check cache first
        cached = self._token_cache.get(installation_id)
        
        if cached and not cached.is_expired:
            logger.debug(
                "Using cached installation token",
                installation_id=installation_id
            )
            return cached.token
        
        # Fetch new token
        logger.debug(
            "Fetching new installation token",
            installation_id=installation_id,
            reason="expired" if cached else "not_cached"
        )
        
        new_token = await self._fetch_installation_token(installation_id)
        self._token_cache[installation_id] = new_token
        
        return new_token.token
    
    def invalidate_token(self, installation_id: int) -> None:
        """
        Invalidate a cached token.
        
        Call this if an API request fails with 401 Unauthorized,
        indicating the token may have been revoked.
        
        Args:
            installation_id: GitHub App installation ID to invalidate
        """
        if installation_id in self._token_cache:
            del self._token_cache[installation_id]
            logger.info(
                "Invalidated cached token",
                installation_id=installation_id
            )


# Singleton instance for the application
_auth_instance: Optional[GitHubAppAuth] = None


def get_github_auth() -> GitHubAppAuth:
    """
    Get the singleton GitHubAppAuth instance.
    
    Returns:
        GitHubAppAuth instance
    """
    global _auth_instance
    if _auth_instance is None:
        _auth_instance = GitHubAppAuth()
    return _auth_instance
