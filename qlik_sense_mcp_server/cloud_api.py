"""Qlik Cloud REST API v1 client."""

import json
from typing import Dict, List, Any, Optional
import httpx
import logging
import os
from .config import QlikSenseConfig

logger = logging.getLogger(__name__)


class QlikCloudAPI:
    """Client for Qlik Cloud REST API v1 using httpx."""

    def __init__(self, config: QlikSenseConfig):
        self.config = config
        self.base_url = config.server_url.rstrip('/')
        
        if not config.api_key:
            raise ValueError("API key is required for Qlik Cloud authentication")
        
        # Setup SSL verification (Qlik Cloud uses standard SSL)
        verify_ssl = config.verify_ssl

        # Timeouts from env (seconds)
        http_timeout_env = os.getenv("QLIK_HTTP_TIMEOUT")
        try:
            timeout_val = float(http_timeout_env) if http_timeout_env else 30.0
        except ValueError:
            timeout_val = 30.0

        # Setup headers - Qlik Cloud uses Bearer token authentication
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {config.api_key}"
        }

        # Create httpx client
        self.client = httpx.Client(
            verify=verify_ssl,
            timeout=timeout_val,
            headers=headers,
        )

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

