"""Configuration for Qlik Cloud MCP Server."""

import os
from typing import Optional
from pydantic import BaseModel, Field


class QlikSenseConfig(BaseModel):
    """
    Configuration model for Qlik Cloud server connection.

    Handles server connection details with OAuth2 M2M or API key authentication.
    """

    server_url: str = Field(..., description="Qlik Cloud server URL (e.g., https://tenant.qlikcloud.com)")
    api_key: Optional[str] = Field(None, description="API key for authentication (optional, fallback)")
    oauth_client_id: Optional[str] = Field(None, description="OAuth2 M2M client ID (optional)")
    oauth_client_secret: Optional[str] = Field(None, description="OAuth2 M2M client secret (optional)")
    verify_ssl: bool = Field(True, description="Verify SSL certificates")

    @classmethod
    def from_env(cls) -> "QlikSenseConfig":
        """
        Create configuration instance from environment variables.

        Reads required configuration values from environment variables with QLIK_ prefix.
        Supports OAuth2 M2M (preferred) or API key authentication.

        Returns:
            Configured QlikSenseConfig instance
            
        Raises:
            ValueError: If neither OAuth2 nor API key credentials are provided
        """
        server_url = os.getenv("QLIK_SERVER_URL", "")
        api_key = os.getenv("QLIK_API_KEY")
        oauth_client_id = os.getenv("QLIK_OAUTH_CLIENT_ID")
        oauth_client_secret = os.getenv("QLIK_OAUTH_CLIENT_SECRET")
        
        # Validate that at least one authentication method is provided
        has_oauth = oauth_client_id and oauth_client_secret
        has_api_key = bool(api_key)
        
        if not has_oauth and not has_api_key:
            raise ValueError(
                "Either OAuth2 M2M credentials (QLIK_OAUTH_CLIENT_ID and QLIK_OAUTH_CLIENT_SECRET) "
                "or API key (QLIK_API_KEY) environment variable is required for Qlik Cloud"
            )
        
        if has_oauth and not oauth_client_secret:
            raise ValueError("QLIK_OAUTH_CLIENT_SECRET is required when QLIK_OAUTH_CLIENT_ID is provided")
        
        if has_oauth and not oauth_client_id:
            raise ValueError("QLIK_OAUTH_CLIENT_ID is required when QLIK_OAUTH_CLIENT_SECRET is provided")
        
        return cls(
            server_url=server_url,
            api_key=api_key,
            oauth_client_id=oauth_client_id,
            oauth_client_secret=oauth_client_secret,
            verify_ssl=os.getenv("QLIK_VERIFY_SSL", "true").lower() == "true"
        )
    
    def uses_oauth(self) -> bool:
        """Check if OAuth2 M2M authentication is configured."""
        return bool(self.oauth_client_id and self.oauth_client_secret)
    
    def uses_api_key(self) -> bool:
        """Check if API key authentication is configured."""
        return bool(self.api_key)
