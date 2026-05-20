# Mariya Polkovnikova
# 2026.04.20
#
# Centralized HTTP Client for External Data Requests
#
# This module provides a unified HTTP client interface for all external
# data requests (historical archives, CMMS, weather, etc). Abstracts away the details of
# AsyncClient management and error handling.

from typing import Dict, Any, Optional, List, Callable
from json import dumps
import logging
from os import getenv

from httpx import AsyncClient
from fastapi.responses import JSONResponse

from api import (
    HEADERS,
    CLIENT_TIMEOUT_ONE,
    CLIENT_TIMEOUT_ALL,
    HTTPMessages
)

logger = logging.getLogger(__name__)

# Test mode for synthetic data
TEST_MODE = getenv("TEST_MODE", "false").lower() == "true"


class HTTPClient:
    """
    Centralized HTTP client for making requests to external services.
    
    Handles:
    - Connection pooling with AsyncClient
    - Multiple URL failover (primary/secondary endpoints)
    - Error handling and logging
    - Request/response validation
    - Timeout management
    """
    
    def __init__(
        self,
        urls: List[str] | str,
        headers: Optional[Dict[str, str]] = None,
        timeout_one: int = CLIENT_TIMEOUT_ONE,
        timeout_all: int = CLIENT_TIMEOUT_ALL
    ):
        """
        Initialize HTTP client.
        
        :param List[str] | str urls: Single URL or list of URLs (for failover)
        :param Optional[Dict[str, str]] headers: HTTP headers (defaults to HEADERS)
        :param int timeout_one: Single request timeout in seconds
        :param int timeout_all: Total timeout for all retries in seconds
        """
        self.urls = urls if isinstance(urls, list) else [urls]
        self.headers = headers or HEADERS
        self.timeout_one = timeout_one
        self.timeout_all = timeout_all
    
    async def post_json(
        self,
        request_data: Dict[str, Any] | str,
        error_handler: Optional[Callable[[str], JSONResponse]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Send POST request with JSON payload to primary/backup URLs.
        
        Tries each URL in sequence until one succeeds.
        
        :param Dict[str, Any] | str request_data: Request body (dict or JSON string)
        :param Optional[Callable] error_handler: Function to handle errors
        :return: Parsed JSON response or None on failure
        """
        
        if isinstance(request_data, dict):
            request_data = dumps(request_data)
        
        last_error = None
        
        try:
            async with AsyncClient(timeout=self.timeout_all) as client:
                for url in self.urls:
                    try:
                        logger.debug(f"Attempting POST to {url}")
                        
                        response = await client.post(
                            url=url,
                            headers=self.headers,
                            data=request_data,
                            timeout=self.timeout_one
                        )
                        
                        if 200 <= response.status_code < 300:
                            logger.debug(f"Success: HTTP {response.status_code} from {url}")
                            return response.json()
                        else:
                            logger.debug(f"Failed: HTTP {response.status_code} from {url}")
                            last_error = f"HTTP {response.status_code}"
                            continue
                    
                    except Exception as e:
                        logger.debug(f"Exception from {url}: {e}")
                        last_error = str(e)
                        continue
        
        except Exception as e:
            logger.warning(f"Fatal error in HTTP client: {e}")
            last_error = str(e)
        
        logger.warning(f"All URLs failed. Last error: {last_error}")
        
        if error_handler:
            return error_handler(last_error)
        
        return None
    
    async def post_with_callback(
        self,
        request_data: Dict[str, Any] | str,
        callback: Callable[[Dict[str, Any]], Any],
        error_handler: Optional[Callable[[str], JSONResponse]] = None
    ) -> Any:
        """
        Send POST request and apply callback to successful response.
        
        :param Dict[str, Any] | str request_data: Request body
        :param Callable callback: Function to process response
        :param Optional[Callable] error_handler: Error handler
        :return: Result of callback or error response
        """
        
        response_data = await self.post_json(request_data, error_handler)
        
        if response_data is None:
            return error_handler(None) if error_handler else None
        
        try:
            return callback(response_data)
        except Exception as e:
            logger.error(f"Error in callback: {e}")
            if error_handler:
                return error_handler(str(e))
            return None


# Singleton instances for predefined endpoints
_cmms_client = None
_weather_client = None

# CMMS client is separate since it may have different URLs and headers (e.g. API keys)
def get_cmms_client() -> HTTPClient:
    """Get or create CMMS (external data) HTTP client."""
    global _cmms_client
    
    if _cmms_client is None:
        from api import RZ_URL
        
        if not RZ_URL:
            logger.warning("RZ_URL not configured")
            _cmms_client = HTTPClient(
                urls=[""],  # Empty URL - will fail safely
                timeout_one=CLIENT_TIMEOUT_ONE,
                timeout_all=CLIENT_TIMEOUT_ALL
            )
        else:
            _cmms_client = HTTPClient(
                urls=[RZ_URL],
                timeout_one=CLIENT_TIMEOUT_ONE,
                timeout_all=CLIENT_TIMEOUT_ALL
            )
    
    return _cmms_client

# Weather client is separate since it may have different URLs and headers (e.g. API keys)
def get_weather_client() -> HTTPClient:
    """Get or create Weather API HTTP client."""
    global _weather_client
    
    if _weather_client is None:
        from api import WEATHER_URL
        
        if not WEATHER_URL:
            logger.warning("WEATHER_URL not configured")
            _weather_client = HTTPClient(
                urls=[""],  # Empty URL - will fail safely
                timeout_one=CLIENT_TIMEOUT_ONE,
                timeout_all=CLIENT_TIMEOUT_ALL
            )
        else:
            _weather_client = HTTPClient(
                urls=[WEATHER_URL],
                timeout_one=CLIENT_TIMEOUT_ONE,
                timeout_all=CLIENT_TIMEOUT_ALL
            )
    
    return _weather_client

def create_custom_client(
    urls: List[str] | str,
    headers: Optional[Dict[str, str]] = None,
    timeout_one: int = CLIENT_TIMEOUT_ONE,
    timeout_all: int = CLIENT_TIMEOUT_ALL
) -> HTTPClient:
    """
    Create a custom HTTP client for specific use cases.
    
    :param List[str] | str urls: Service URL(s)
    :param Optional[Dict[str, str]] headers: Custom headers
    :param int timeout_one: Request timeout
    :param int timeout_all: Total timeout
    :return: Configured HTTPClient instance
    """
    return HTTPClient(
        urls=urls,
        headers=headers,
        timeout_one=timeout_one,
        timeout_all=timeout_all
    )
