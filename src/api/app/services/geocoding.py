import asyncio
import time

import structlog
from geopy.exc import GeocoderTimedOut, GeocoderUnavailable
from geopy.geocoders import Nominatim

from app.config import settings

log = structlog.get_logger(__name__)


class GeocodingService:
    def __init__(self) -> None:
        self.geocoder = Nominatim(user_agent=settings.NOMINATIM_USER_AGENT)
        self._last_call: float = 0.0

    async def geocode_address(self, address: str) -> tuple[float, float] | None:
        """Returns (lat, lon) or None. Respects 1.1s rate limit and retries up to 3 times."""
        max_retries = 3
        last_error: Exception | None = None

        for attempt in range(max_retries):
            try:
                # Enforce rate limit
                elapsed = time.monotonic() - self._last_call
                if elapsed < settings.NOMINATIM_RATE_LIMIT_DELAY:
                    await asyncio.sleep(settings.NOMINATIM_RATE_LIMIT_DELAY - elapsed)

                loop = asyncio.get_event_loop()
                location = await loop.run_in_executor(
                    None,
                    lambda: self.geocoder.geocode(address, timeout=10),
                )
                self._last_call = time.monotonic()

                if location is None:
                    log.warning("geocode_no_result", address=address)
                    return None

                lat: float = float(location.latitude)
                lon: float = float(location.longitude)
                log.info("geocode_success", address=address, lat=lat, lon=lon)
                return lat, lon

            except GeocoderTimedOut as exc:
                last_error = exc
                log.warning(
                    "geocode_timeout",
                    address=address,
                    attempt=attempt + 1,
                    max_retries=max_retries,
                )
                await asyncio.sleep(2 ** attempt)
            except GeocoderUnavailable as exc:
                last_error = exc
                log.warning("geocode_unavailable", address=address, attempt=attempt + 1)
                await asyncio.sleep(2 ** attempt)
            except Exception as exc:
                log.error("geocode_error", address=address, error=str(exc))
                return None

        log.error("geocode_all_retries_failed", address=address, last_error=str(last_error))
        return None


geocoding_service = GeocodingService()
