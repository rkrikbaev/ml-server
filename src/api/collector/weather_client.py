# Mariya Polkovnikova
# 2026.04.20
#
# Weather Client Adapter - Integrates weather service with ML server
#
# This module provides an async-compatible wrapper around the WeatherClient
# and integrates it with the collector's weather data extraction pipeline.

import logging
from typing import Dict, Any, Optional, List, Tuple
from concurrent.futures import ThreadPoolExecutor
import asyncio
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import requests

logger = logging.getLogger(__name__)

# Singleton instances with connection pooling per base URL
_weather_clients: Dict[str, "WeatherClientAsync"] = {}
_executor = ThreadPoolExecutor(max_workers=4)


def normalize_runtime_url(url: str) -> str:
    """Rewrite localhost-style URLs so they can reach host services from Docker."""
    if not url:
        return url

    parsed = urlparse(url)
    if parsed.hostname not in {"127.0.0.1", "localhost"}:
        return url

    if not Path("/.dockerenv").exists():
        return url

    netloc = parsed.netloc.replace(parsed.hostname, "host.docker.internal")
    return urlunparse(parsed._replace(netloc=netloc))


def normalize_weather_base_url(url: str) -> str:
    """Convert a forecast endpoint or bare service URL into the client base URL."""
    normalized_url = normalize_runtime_url(url.rstrip("/"))
    parsed = urlparse(normalized_url)

    if parsed.path.endswith("/forecast"):
        parsed = parsed._replace(path=parsed.path[: -len("/forecast")])
    elif parsed.path.endswith("/weather"):
        parsed = parsed._replace(path=parsed.path[: -len("/weather")])

    return urlunparse(parsed).rstrip("/")

def get_weather_client(
    base_url: Optional[str] = None,
    timeout: int = 10
) -> "WeatherClientAsync":
    """
    Get or create weather client instance.
    
    :param Optional[str] base_url: Weather service base URL
    :param int timeout: Request timeout in seconds
    :return: WeatherClientAsync instance
    """
    global _weather_clients

    from os import getenv

    if base_url is None:
        base_url = getenv("WEATHER_API_URL", "http://localhost:8050/api/v1/weather")

    normalized_base_url = normalize_weather_base_url(base_url)

    if normalized_base_url not in _weather_clients:
        _weather_clients[normalized_base_url] = WeatherClientAsync(
            base_url=normalized_base_url,
            timeout=timeout,
        )
        logger.info("Weather client initialized: %s", normalized_base_url)

    return _weather_clients[normalized_base_url]

class WeatherClientAsync:
    """
    Async wrapper around the synchronous WeatherClient.
    
    Provides async methods for weather data retrieval while maintaining
    compatibility with the blocking WeatherClient library.
    """
    
    def __init__(self, base_url: str, timeout: int = 10):
        """
        Initialize async weather client.
        
        :param str base_url: Weather service base URL
        :param int timeout: Request timeout in seconds
        """
        self.base_url = base_url
        self.timeout = timeout

    def _get(self, path: str, params: Dict[str, Any]) -> Dict[str, Any]:
        response = requests.get(
            f"{self.base_url}{path}",
            params=params,
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def _post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        response = requests.post(
            f"{self.base_url}{path}",
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def _delete(self, path: str) -> Dict[str, Any]:
        response = requests.delete(
            f"{self.base_url}{path}",
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()
    
    async def get_weather(
        self,
        lat: float,
        lon: float,
        units: str = "metric"
    ) -> Dict[str, Any]:
        """
        Get current weather for a location asynchronously.
        
        :param float lat: Latitude
        :param float lon: Longitude
        :param str units: Unit system (metric or imperial)
        :return: Weather data dictionary
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            _executor,
            lambda: self._get("/weather", {"lat": lat, "lon": lon, "units": units})
        )
    
    async def get_forecast(
        self,
        lat: float,
        lon: float,
        hours: int = 24,
        units: str = "metric"
    ) -> Dict[str, Any]:
        """
        Get weather forecast asynchronously.
        
        :param float lat: Latitude
        :param float lon: Longitude
        :param int hours: Forecast hours (default 24)
        :param str units: Unit system
        :return: Forecast data dictionary
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            _executor,
            lambda: self._get("/forecast", {"lat": lat, "lon": lon, "hours": hours, "units": units})
        )
    
    async def get_batch_weather(
        self,
        locations: List[Tuple[float, float]],
        units: str = "metric"
    ) -> Dict[str, Any]:
        """
        Get weather for multiple locations asynchronously.
        
        :param List[Tuple[float, float]] locations: List of (lat, lon) tuples
        :param str units: Unit system
        :return: Batch weather results
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            _executor,
            lambda: self._post(
                "/weather/batch",
                {
                    "locations": [{"lat": lat, "lon": lon} for lat, lon in locations],
                    "units": units,
                },
            )
        )
    
    async def get_providers(self) -> Dict[str, Any]:
        """Get available weather providers."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, lambda: self._get("/providers", {}))
    
    async def get_healthz(self) -> Dict[str, Any]:
        """Get service health status."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, lambda: self._get("/healthz", {}))
    
    async def get_metrics(self) -> Dict[str, Any]:
        """Get performance metrics."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, lambda: self._get("/metrics", {}))
    
    async def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, lambda: self._get("/cache/stats", {}))
    
    async def clear_cache(self) -> Dict[str, Any]:
        """Clear service cache."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, lambda: self._delete("/cache"))
    
    async def reset_metrics(self) -> Dict[str, Any]:
        """Reset performance metrics."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, lambda: self._delete("/cache/metrics"))
    
    async def reset_circuit_breaker(
        self,
        provider: Optional[str] = None
    ) -> Dict[str, Any]:
        """Reset circuit breaker for a provider."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            _executor,
            lambda: requests.post(
                f"{self.base_url}/circuit-breaker/reset",
                json={},
                params={"provider": provider} if provider else {},
                timeout=self.timeout,
            ).json()
        )


async def fetch_weather_timeseries(
    stations_coords: Dict[str, Tuple[float, float]],
    units: str = "metric"
) -> Dict[str, Dict[str, Any]]:
    """
    Fetch weather timeseries data for multiple stations (coordinates).
    
    :param Dict[str, Tuple[float, float]] stations_coords: Dict mapping
        station codes to (lat, lon) tuples
    :param str units: Unit system (metric or imperial)
    :return: Dict mapping station codes to weather data
    """
    client = get_weather_client()
    results = {}
    errors = {}
    
    try:
        # Get batch weather data
        locations = list(stations_coords.values())
        batch_result = await client.get_batch_weather(locations, units)
        
        # Map results back to station codes
        if "results" in batch_result:
            for i, (station_code, _coords) in enumerate(stations_coords.items()):
                if i < len(batch_result["results"]):
                    results[station_code] = batch_result["results"][i]
        
        # Collect errors if any
        if "errors" in batch_result:
            errors = batch_result["errors"]
        
        logger.info(f"Fetched weather for {len(results)} stations")
        
    except Exception as e:
        logger.error(f"Failed to fetch weather data: {e}")
        raise
    
    return results


async def validate_weather_service() -> bool:
    """
    Validate weather service availability.
    
    :return: True if service is available, False otherwise
    """
    try:
        client = get_weather_client()
        health = await client.get_healthz()
        return health.get("status") == "healthy"
    except Exception as e:
        logger.warning(f"Weather service health check failed: {e}")
        return False
