"""Configuration for Qlik Cloud MCP Server."""

import os
from typing import Optional
from pydantic import BaseModel, Field


class QlikSenseConfig(BaseModel):
    """
    Configuration model for Qlik Cloud server connection.

    Handles server connection details with OAuth2 M2M authentication.
    """

    server_url: str = Field(..., description="Qlik Cloud server URL (e.g., https://tenant.qlikcloud.com)")
    oauth_client_id: str = Field(..., description="OAuth2 M2M client ID (required)")
    oauth_client_secret: str = Field(..., description="OAuth2 M2M client secret (required)")
    verify_ssl: bool = Field(True, description="Verify SSL certificates")
    
    # Optional fields for Engine API compatibility / Enterprise support
    api_key: Optional[str] = Field(None, description="API Key for authentication")
    user_directory: Optional[str] = Field(None, description="User Directory for certificate auth")
    user_id: Optional[str] = Field(None, description="User ID for certificate auth")
    client_cert_path: Optional[str] = Field(None, description="Path to client certificate")
    client_key_path: Optional[str] = Field(None, description="Path to client key")
    ca_cert_path: Optional[str] = Field(None, description="Path to CA certificate")
    engine_port: int = Field(443, description="Qlik Engine port")

    @classmethod
    def from_env(cls) -> "QlikSenseConfig":
        """
        Create configuration instance from environment variables.

        Reads required configuration values from environment variables with QLIK_ prefix.
        Requires OAuth2 M2M authentication.

        Returns:
            Configured QlikSenseConfig instance
            
        Raises:
            ValueError: If OAuth2 M2M credentials are not provided
        """
        server_url = os.getenv("QLIK_SERVER_URL", "")
        oauth_client_id = os.getenv("QLIK_OAUTH_CLIENT_ID")
        oauth_client_secret = os.getenv("QLIK_OAUTH_CLIENT_SECRET")
        
        if not oauth_client_id:
            raise ValueError("QLIK_OAUTH_CLIENT_ID environment variable is required for Qlik Cloud")
        
        if not oauth_client_secret:
            raise ValueError("QLIK_OAUTH_CLIENT_SECRET environment variable is required for Qlik Cloud")
        
        return cls(
            server_url=server_url,
            oauth_client_id=oauth_client_id,
            oauth_client_secret=oauth_client_secret,
            verify_ssl=os.getenv("QLIK_VERIFY_SSL", "true").lower() == "true",
            api_key=os.getenv("QLIK_API_KEY"),
            user_directory=os.getenv("QLIK_USER_DIRECTORY"),
            user_id=os.getenv("QLIK_USER_ID"),
            client_cert_path=os.getenv("QLIK_CLIENT_CERT_PATH"),
            client_key_path=os.getenv("QLIK_CLIENT_KEY_PATH"),
            ca_cert_path=os.getenv("QLIK_CA_CERT_PATH"),
            engine_port=int(os.getenv("QLIK_ENGINE_PORT", "443"))
        )
