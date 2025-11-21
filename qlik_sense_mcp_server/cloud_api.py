"""Qlik Cloud REST API v1 client."""

import json
from typing import Dict, List, Any, Optional
import httpx
import logging
import os
import time
from .config import QlikSenseConfig

logger = logging.getLogger(__name__)


class QlikCloudAPI:
    """Client for Qlik Cloud REST API v1 using httpx."""

    def __init__(self, config: QlikSenseConfig):
        self.config = config
        self.base_url = config.server_url.rstrip('/')
        
        # Validate authentication method
        if not config.uses_oauth() and not config.uses_api_key():
            raise ValueError(
                "Either OAuth2 M2M credentials or API key is required for Qlik Cloud authentication"
            )
        
        # Setup SSL verification (Qlik Cloud uses standard SSL)
        verify_ssl = config.verify_ssl

        # Timeouts from env (seconds)
        http_timeout_env = os.getenv("QLIK_HTTP_TIMEOUT")
        try:
            timeout_val = float(http_timeout_env) if http_timeout_env else 30.0
        except ValueError:
            timeout_val = 30.0

        # OAuth token caching
        self._oauth_token: Optional[str] = None
        self._oauth_token_expires_at: float = 0.0
        
        # Setup headers - will be updated dynamically based on auth method
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        # Create httpx client (headers will be updated per request if using OAuth)
        self.client = httpx.Client(
            verify=verify_ssl,
            timeout=timeout_val,
            headers=headers,
        )
        
        # Log authentication method
        if config.uses_oauth():
            logger.info("Using OAuth2 M2M authentication for Qlik Cloud")
        else:
            logger.info("Using API key authentication for Qlik Cloud")
            # Set API key header immediately if using API key
            self.client.headers["Authorization"] = f"Bearer {config.api_key}"
    
    def _get_oauth_token(self) -> str:
        """
        Get OAuth2 access token using client credentials flow.
        Implements token caching with automatic renewal.
        
        Returns:
            Access token string
            
        Raises:
            ValueError: If OAuth credentials are not configured
            Exception: If token request fails
        """
        if not self.config.uses_oauth():
            raise ValueError("OAuth2 credentials not configured")
        
        # Check if cached token is still valid (with 60 second buffer)
        current_time = time.time()
        if self._oauth_token and current_time < (self._oauth_token_expires_at - 60):
            return self._oauth_token
        
        # Request new token
        token_url = f"{self.base_url}/oauth/token"
        
        # Prepare form data for client credentials flow
        data = {
            "grant_type": "client_credentials",
            "client_id": self.config.oauth_client_id,
            "client_secret": self.config.oauth_client_secret,
        }
        
        try:
            # Use a separate client for token request (no auth header needed)
            token_client = httpx.Client(
                verify=self.config.verify_ssl,
                timeout=30.0,
            )
            
            response = token_client.post(
                token_url,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            response.raise_for_status()
            
            token_data = response.json()
            access_token = token_data.get("access_token")
            expires_in = token_data.get("expires_in", 3600)  # Default to 1 hour
            
            if not access_token:
                raise ValueError("No access_token in OAuth response")
            
            # Cache token with expiration time
            self._oauth_token = access_token
            self._oauth_token_expires_at = current_time + expires_in
            
            logger.debug(f"OAuth token obtained, expires in {expires_in} seconds")
            
            token_client.close()
            return access_token
            
        except httpx.HTTPStatusError as e:
            logger.error(f"OAuth token request failed: {e.response.status_code} - {e.response.text}")
            raise Exception(f"Failed to obtain OAuth token: HTTP {e.response.status_code}")
        except Exception as e:
            logger.error(f"OAuth token request error: {str(e)}")
            raise

    def _get_api_url(self, endpoint: str) -> str:
        """Get full API URL for endpoint."""
        # Remove leading slash if present
        endpoint = endpoint.lstrip('/')
        # Ensure it starts with /api/v1
        if not endpoint.startswith('api/v1'):
            endpoint = f"api/v1/{endpoint}"
        return f"{self.base_url}/{endpoint}"

    def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make HTTP request to Qlik Cloud REST API."""
        try:
            url = self._get_api_url(endpoint)
            
            # Update Authorization header if using OAuth (token may have been refreshed)
            if self.config.uses_oauth():
                try:
                    token = self._get_oauth_token()
                    # Update headers for this request
                    request_headers = kwargs.get("headers", {}).copy()
                    request_headers["Authorization"] = f"Bearer {token}"
                    kwargs["headers"] = request_headers
                except Exception as e:
                    logger.error(f"Failed to get OAuth token: {str(e)}")
                    return {"error": f"OAuth authentication failed: {str(e)}"}
            
            response = self.client.request(method, url, **kwargs)
            response.raise_for_status()

            if response.headers.get("content-type", "").startswith("application/json"):
                return response.json()
            else:
                return {"raw_response": response.text}

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error {e.response.status_code}: {e.response.text}")
            try:
                error_detail = e.response.json()
            except:
                error_detail = {"error": e.response.text}
            return {"error": f"HTTP {e.response.status_code}", "details": error_detail}
        except Exception as e:
            logger.error(f"Request error: {str(e)}")
            return {"error": str(e)}

    # Data Assets (Datasets)
    def get_data_assets(self, limit: int = 100, offset: int = 0, 
                       space_id: Optional[str] = None) -> Dict[str, Any]:
        """Get list of data assets (datasets)."""
        params = {"limit": limit, "offset": offset}
        if space_id:
            params["spaceId"] = space_id
        return self._make_request("GET", "data-assets", params=params)

    def get_data_asset(self, asset_id: str) -> Dict[str, Any]:
        """Get specific data asset by ID."""
        return self._make_request("GET", f"data-assets/{asset_id}")

    def get_data_asset_data(self, asset_id: str, limit: int = 1000, 
                           offset: int = 0) -> Dict[str, Any]:
        """Get data from a data asset."""
        params = {"limit": limit, "offset": offset}
        return self._make_request("GET", f"data-assets/{asset_id}/data", params=params)

    # Apps
    def get_apps(self, limit: int = 100, offset: int = 0,
                space_id: Optional[str] = None,
                name: Optional[str] = None) -> Dict[str, Any]:
        """Get list of apps."""
        params = {"limit": limit, "offset": offset}
        if space_id:
            params["spaceId"] = space_id
        if name:
            params["name"] = name
        return self._make_request("GET", "items", params=params)

    def get_app(self, app_id: str) -> Dict[str, Any]:
        """Get specific app by ID."""
        return self._make_request("GET", f"items/{app_id}")

    def get_app_metadata(self, app_id: str) -> Dict[str, Any]:
        """Get app metadata including data model."""
        return self._make_request("GET", f"apps/{app_id}/data/metadata")

    def get_app_connections(self, app_id: str) -> Dict[str, Any]:
        """Get app data connections."""
        return self._make_request("GET", f"apps/{app_id}/data/connections")

    # Spaces
    def get_spaces(self, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        """Get list of spaces."""
        params = {"limit": limit, "offset": offset}
        return self._make_request("GET", "spaces", params=params)

    def get_space(self, space_id: str) -> Dict[str, Any]:
        """Get specific space by ID."""
        return self._make_request("GET", f"spaces/{space_id}")

    # Items (generic)
    def get_items(self, limit: int = 100, offset: int = 0,
                 space_id: Optional[str] = None,
                 resource_type: Optional[str] = None) -> Dict[str, Any]:
        """Get list of items (apps, datasets, etc.)."""
        params = {"limit": limit, "offset": offset}
        if space_id:
            params["spaceId"] = space_id
        if resource_type:
            params["resourceType"] = resource_type
        return self._make_request("GET", "items", params=params)

