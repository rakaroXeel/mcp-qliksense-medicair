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
        
        # Setup headers - Authorization will be added per request via OAuth token
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        # Create httpx client (headers will be updated per request with OAuth token)
        self.client = httpx.Client(
            verify=verify_ssl,
            timeout=timeout_val,
            headers=headers,
        )
        
        logger.info("Using OAuth2 M2M authentication for Qlik Cloud")
    
    def _get_oauth_token(self) -> str:
        """
        Get OAuth2 access token using client credentials flow.
        Implements token caching with automatic renewal.
        
        Returns:
            Access token string
            
        Raises:
            Exception: If token request fails
        """
        
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
            
            # Get OAuth token (may be cached or refreshed)
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
                data = response.json()
                # Log response for debugging
                logger.info(f"API Response for {endpoint}:\n{json.dumps(data, indent=2)}")
                return data
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

    def get_app_tables(self, app_id: str) -> Dict[str, Any]:
        """Get list of tables in the app from metadata."""
        metadata = self.get_app_metadata(app_id)
        if "error" in metadata:
            return metadata
        
        # Extract tables from metadata
        tables = []
        if isinstance(metadata, dict):
            # Metadata structure may vary, try common paths
            qv_tables = metadata.get("qvTables", [])
            if qv_tables:
                for table in qv_tables:
                    table_info = {
                        "name": table.get("qName", ""),
                        "fields": len(table.get("qFields", [])),
                        "rows": table.get("qNoOfRows", 0)
                    }
                    tables.append(table_info)
            else:
                # Try alternative structure
                tables_data = metadata.get("tables", [])
                if tables_data:
                    tables = tables_data
        
        return {
            "app_id": app_id,
            "tables": tables,
            "total_tables": len(tables)
        }

    def get_app_fields(self, app_id: str, table_name: Optional[str] = None) -> Dict[str, Any]:
        """Get list of fields in the app, optionally filtered by table."""
        metadata = self.get_app_metadata(app_id)
        if "error" in metadata:
            return metadata
        
        fields = []
        if isinstance(metadata, dict):
            # Try multiple possible structures for metadata
            # Structure 1: qvTables -> qFields
            qv_tables = metadata.get("qvTables", [])
            if qv_tables:
                logger.debug(f"Found {len(qv_tables)} tables in qvTables")
                for table in qv_tables:
                    table_name_meta = table.get("qName", "")
                    table_fields = table.get("qFields", [])
                    if not table_fields:
                        # Try alternative field structure
                        table_fields = table.get("fields", [])
                    
                    for field in table_fields:
                        # Handle different field structures
                        if isinstance(field, dict):
                            field_name = field.get("qName") or field.get("name") or field.get("field")
                            field_type = field.get("qType") or field.get("type") or "unknown"
                        elif isinstance(field, str):
                            field_name = field
                            field_type = "unknown"
                        else:
                            continue
                        
                        if field_name:
                            field_info = {
                                "name": field_name,
                                "table": table_name_meta,
                                "type": field_type
                            }
                            if not table_name or field_info["table"] == table_name:
                                fields.append(field_info)
            
            # Structure 2: Direct fields array (if qvTables didn't work)
            if not fields:
                direct_fields = metadata.get("fields", [])
                if direct_fields:
                    logger.debug(f"Found {len(direct_fields)} fields in direct fields array")
                    for field in direct_fields:
                        if isinstance(field, dict):
                            field_name = field.get("qName") or field.get("name") or field.get("field")
                            field_type = field.get("qType") or field.get("type") or "unknown"
                            table_name_meta = field.get("table") or field.get("tableName") or "Unknown"
                        elif isinstance(field, str):
                            field_name = field
                            field_type = "unknown"
                            table_name_meta = "Unknown"
                        else:
                            continue
                        
                        if field_name:
                            field_info = {
                                "name": field_name,
                                "table": table_name_meta,
                                "type": field_type
                            }
                            if not table_name or field_info["table"] == table_name:
                                fields.append(field_info)
            
            # Structure 3: tables array with fields
            if not fields:
                tables_array = metadata.get("tables", [])
                if tables_array:
                    logger.debug(f"Found {len(tables_array)} tables in tables array")
                    for table in tables_array:
                        table_name_meta = table.get("name") or table.get("qName") or ""
                        table_fields = table.get("fields", []) or table.get("qFields", [])
                        for field in table_fields:
                            if isinstance(field, dict):
                                field_name = field.get("qName") or field.get("name") or field.get("field")
                                field_type = field.get("qType") or field.get("type") or "unknown"
                            elif isinstance(field, str):
                                field_name = field
                                field_type = "unknown"
                            else:
                                continue
                            
                            if field_name:
                                field_info = {
                                    "name": field_name,
                                    "table": table_name_meta,
                                    "type": field_type
                                }
                                if not table_name or field_info["table"] == table_name:
                                    fields.append(field_info)
            
            # Log metadata structure for debugging if no fields found
            if not fields:
                logger.warning(f"No fields found in metadata. Metadata keys: {list(metadata.keys())}")
                logger.debug(f"Metadata structure sample: {json.dumps(metadata, indent=2)[:1000]}")
        
        result = {
            "app_id": app_id,
            "fields": fields,
            "total_fields": len(fields)
        }
        if table_name:
            result["table_name"] = table_name
        
        return result

    def create_hypercube(self, app_id: str, dimensions: List[str], 
                        measures: List[str], filters: Optional[List[Dict[str, Any]]] = None,
                        max_rows: int = 1000) -> Dict[str, Any]:
        """
        Create hypercube and get data from app.
        
        Args:
            app_id: Application ID
            dimensions: List of dimension field names
            measures: List of measure expressions
            filters: Optional list of filter objects
            max_rows: Maximum number of rows to return
        
        Returns:
            Hypercube data
        """
        # Build hypercube definition
        hypercube_def = {
            "qDimensions": [
                {
                    "qDef": {
                        "qFieldDefs": [dim]
                    },
                    "qNullSuppression": False
                }
                for dim in dimensions
            ],
            "qMeasures": [
                {
                    "qDef": {
                        "qDef": measure
                    }
                }
                for measure in measures
            ],
            "qInitialDataFetch": [
                {
                    "qTop": 0,
                    "qLeft": 0,
                    "qHeight": max_rows,
                    "qWidth": len(dimensions) + len(measures)
                }
            ],
            "qMode": "S"
        }
        
        # Add filters if provided
        if filters:
            hypercube_def["qInterColumnSortOrder"] = []
            # Filters would be applied here if supported
        
        payload = {
            "method": "CreateHyperCube",
            "params": [hypercube_def]
        }
        
        # Try POST to hypercube endpoint
        return self._make_request("POST", f"apps/{app_id}/data/hypercube", json=payload)

    def get_field_values(self, app_id: str, field_name: str, limit: int = 100) -> Dict[str, Any]:
        """
        Get distinct values of a field.
        
        Args:
            app_id: Application ID
            field_name: Name of the field
            limit: Maximum number of values to return
        
        Returns:
            List of distinct field values
        """
        # Create a simple hypercube with one dimension to get field values
        hypercube_def = {
            "qDimensions": [
                {
                    "qDef": {
                        "qFieldDefs": [field_name]
                    },
                    "qNullSuppression": False
                }
            ],
            "qMeasures": [],
            "qInitialDataFetch": [
                {
                    "qTop": 0,
                    "qLeft": 0,
                    "qHeight": limit,
                    "qWidth": 1
                }
            ],
            "qMode": "S"
        }
        
        payload = {
            "method": "CreateHyperCube",
            "params": [hypercube_def]
        }
        
        result = self._make_request("POST", f"apps/{app_id}/data/hypercube", json=payload)
        
        # Extract values from hypercube response
        if "error" not in result:
            values = []
            # Parse hypercube response to extract values
            # Structure may vary, try common paths
            if isinstance(result, dict):
                q_data_pages = result.get("qDataPages", [])
                if q_data_pages:
                    for page in q_data_pages:
                        q_matrix = page.get("qMatrix", [])
                        for row in q_matrix:
                            if row:
                                cell = row[0] if row else None
                                if cell:
                                    value = cell.get("qText") or cell.get("qNum")
                                    if value is not None:
                                        values.append(value)
            
            return {
                "app_id": app_id,
                "field_name": field_name,
                "values": values,
                "count": len(values)
            }
        
        return result

    def get_table_data(self, app_id: str, table_name: str, limit: int = 1000, 
                      offset: int = 0) -> Dict[str, Any]:
        """
        Get data from a specific table.
        
        Args:
            app_id: Application ID
            table_name: Name of the table
            limit: Maximum number of rows to return
            offset: Number of rows to skip
        
        Returns:
            Table data
        """
        # First get fields for the table
        fields_result = self.get_app_fields(app_id, table_name)
        if "error" in fields_result:
            return fields_result
        
        fields = fields_result.get("fields", [])
        if not fields:
            return {"error": f"Table '{table_name}' not found or has no fields"}
        
        # Get field names
        field_names = [f["name"] for f in fields]
        
        # Limit number of fields to avoid too wide tables
        max_fields = 20
        if len(field_names) > max_fields:
            field_names = field_names[:max_fields]
        
        # Create hypercube with all table fields as dimensions
        hypercube_def = {
            "qDimensions": [
                {
                    "qDef": {
                        "qFieldDefs": [field]
                    },
                    "qNullSuppression": False
                }
                for field in field_names
            ],
            "qMeasures": [],
            "qInitialDataFetch": [
                {
                    "qTop": offset,
                    "qLeft": 0,
                    "qHeight": limit,
                    "qWidth": len(field_names)
                }
            ],
            "qMode": "S"
        }
        
        payload = {
            "method": "CreateHyperCube",
            "params": [hypercube_def]
        }
        
        result = self._make_request("POST", f"apps/{app_id}/data/hypercube", json=payload)
        
        # Transform hypercube data to table format
        if "error" not in result:
            rows = []
            if isinstance(result, dict):
                q_data_pages = result.get("qDataPages", [])
                if q_data_pages:
                    for page in q_data_pages:
                        q_matrix = page.get("qMatrix", [])
                        for row_data in q_matrix:
                            row = {}
                            for i, cell in enumerate(row_data):
                                if i < len(field_names):
                                    field_name = field_names[i]
                                    value = cell.get("qText") or cell.get("qNum")
                                    row[field_name] = value
                            if row:
                                rows.append(row)
            
            return {
                "app_id": app_id,
                "table_name": table_name,
                "fields": field_names,
                "rows": rows,
                "row_count": len(rows),
                "limit": limit,
                "offset": offset
            }
        
        return result

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

