"""
D2-08 — Unit tests for USGS client, written before implementation (TDD).

Verified against USGS's real FDSN Event Web Service
(earthquake.usgs.gov/fdsnws/event/1/query), which supports an arbitrary
minmagnitude parameter — unlike the fixed-threshold summary feeds
(4.5_week.geojson etc.) the task doc's function signature implies but
which don't actually support a custom min_magnitude value.

Confirmed field mapping:
  - properties.mag -> magnitude
  - properties.place -> place
  - properties.time -> epoch milliseconds, must convert to ISO 8601
  - geometry.coordinates -> [longitude, latitude, depth_km] IN THAT ORDER
    (GeoJSON spec) -- swapping lat/lon is the most common bug here.
No API key required.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.ingestion.usgs.client import UsgsAPIError, fetch_significant_earthquakes


def _mock_client_returning(response: httpx.Response):
    mock_client_instance = AsyncMock()
    mock_client_instance.get = AsyncMock(return_value=response)
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_client_instance)
    mock_cm.__aexit__ = AsyncMock(return_value=False)
    return mock_cm


def _fake_response(status_code: int, json_body: dict | None = None, text: str = "") -> httpx.Response:
    request = httpx.Request("GET", "https://earthquake.usgs.gov/fdsnws/event/1/query")
    if json_body is not None:
        return httpx.Response(status_code=status_code, json=json_body, request=request)
    return httpx.Response(status_code=status_code, text=text, request=request)


def _feature(mag, place, time_ms, lon, lat, depth_km):
    return {
        "type": "Feature",
        "properties": {"mag": mag, "place": place, "time": time_ms, "type": "earthquake"},
        "geometry": {"type": "Point", "coordinates": [lon, lat, depth_km]},
        "id": "us7000abcd",
    }


REAL_SHAPE_RESPONSE = {
    "type": "FeatureCollection",
    "metadata": {"generated": 1751520000000, "count": 2},
    "features": [
        _feature(6.9, "23km SW of Hsinchu, Taiwan", 1751500000000, 120.9, 24.8, 10.5),
        _feature(5.8, "45km N of Tokyo, Japan", 1751490000000, 139.7, 36.2, 35.0),
    ],
}


class TestFetchSignificantEarthquakesSuccess:
    @pytest.mark.asyncio
    async def test_returns_parsed_earthquakes(self):
        response = _fake_response(200, REAL_SHAPE_RESPONSE)
        with patch("app.ingestion.usgs.client.httpx.AsyncClient", return_value=_mock_client_returning(response)):
            results = await fetch_significant_earthquakes(min_magnitude=5.5)

        assert len(results) == 2
        assert results[0]["magnitude"] == 6.9
        assert results[0]["place"] == "23km SW of Hsinchu, Taiwan"

    @pytest.mark.asyncio
    async def test_coordinate_order_not_swapped(self):
        """The most likely bug: GeoJSON is [lon, lat, depth], not [lat, lon].
        Verify latitude/longitude land in the correct output fields."""
        response = _fake_response(200, REAL_SHAPE_RESPONSE)
        with patch("app.ingestion.usgs.client.httpx.AsyncClient", return_value=_mock_client_returning(response)):
            results = await fetch_significant_earthquakes(min_magnitude=5.5)

        # Feature was built with lon=120.9, lat=24.8 (Taiwan) — NOT lat=120.9
        assert results[0]["longitude"] == 120.9
        assert results[0]["latitude"] == 24.8
        assert results[0]["depth_km"] == 10.5

    @pytest.mark.asyncio
    async def test_time_converted_from_epoch_ms_to_iso8601(self):
        response = _fake_response(200, REAL_SHAPE_RESPONSE)
        with patch("app.ingestion.usgs.client.httpx.AsyncClient", return_value=_mock_client_returning(response)):
            results = await fetch_significant_earthquakes(min_magnitude=5.5)

        # 1751500000000 ms -> a real ISO 8601 UTC string, not the raw epoch int
        assert isinstance(results[0]["time"], str)
        assert results[0]["time"].endswith("Z") or "+00:00" in results[0]["time"]

    @pytest.mark.asyncio
    async def test_min_magnitude_passed_as_query_param(self):
        response = _fake_response(200, REAL_SHAPE_RESPONSE)
        mock_client_instance = AsyncMock()
        mock_client_instance.get = AsyncMock(return_value=response)
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("app.ingestion.usgs.client.httpx.AsyncClient", return_value=mock_cm):
            await fetch_significant_earthquakes(min_magnitude=5.5)

        params = mock_client_instance.get.call_args.kwargs.get("params", {})
        assert params.get("minmagnitude") == "5.5"
        assert params.get("format") == "geojson"

    @pytest.mark.asyncio
    async def test_default_time_window_is_seven_days(self):
        """Architecture Spec §6.2.5: 'fetch significant earthquakes from
        last 7 days'."""
        response = _fake_response(200, REAL_SHAPE_RESPONSE)
        mock_client_instance = AsyncMock()
        mock_client_instance.get = AsyncMock(return_value=response)
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("app.ingestion.usgs.client.httpx.AsyncClient", return_value=mock_cm):
            await fetch_significant_earthquakes(min_magnitude=5.5)

        params = mock_client_instance.get.call_args.kwargs.get("params", {})
        assert "starttime" in params
        assert "endtime" in params


class TestFetchSignificantEarthquakesEmptyResults:
    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_quakes_match(self):
        """Done When explicitly allows this: 'may be empty if no recent
        quakes above 5.5'. Must return [], not raise."""
        response = _fake_response(200, {"type": "FeatureCollection", "features": []})
        with patch("app.ingestion.usgs.client.httpx.AsyncClient", return_value=_mock_client_returning(response)):
            results = await fetch_significant_earthquakes(min_magnitude=8.5)

        assert results == []


class TestFetchSignificantEarthquakesFailure:
    @pytest.mark.asyncio
    async def test_raises_usgs_api_error_on_5xx(self):
        response = _fake_response(503, text="Service Unavailable")
        with patch("app.ingestion.usgs.client.httpx.AsyncClient", return_value=_mock_client_returning(response)):
            with pytest.raises(UsgsAPIError):
                await fetch_significant_earthquakes(min_magnitude=5.5)

    @pytest.mark.asyncio
    async def test_raises_usgs_api_error_on_network_failure(self):
        with patch("app.ingestion.usgs.client.httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.side_effect = httpx.ConnectTimeout("timed out")
            with pytest.raises(UsgsAPIError):
                await fetch_significant_earthquakes(min_magnitude=5.5)

    @pytest.mark.asyncio
    async def test_raises_usgs_api_error_on_malformed_json(self):
        response = _fake_response(200, text="not json at all")
        with patch("app.ingestion.usgs.client.httpx.AsyncClient", return_value=_mock_client_returning(response)):
            with pytest.raises(UsgsAPIError):
                await fetch_significant_earthquakes(min_magnitude=5.5)


class TestDoneWhenCheck:
    @pytest.mark.asyncio
    async def test_returns_list_type_regardless_of_result_count(self):
        """Done When: 'Function returns list (may be empty if no recent
        quakes above 5.5)'."""
        response = _fake_response(200, REAL_SHAPE_RESPONSE)
        with patch("app.ingestion.usgs.client.httpx.AsyncClient", return_value=_mock_client_returning(response)):
            results = await fetch_significant_earthquakes(min_magnitude=5.5)
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_min_magnitude_4_returns_results_per_done_when_verification_step(self):
        response = _fake_response(200, REAL_SHAPE_RESPONSE)
        with patch("app.ingestion.usgs.client.httpx.AsyncClient", return_value=_mock_client_returning(response)):
            results = await fetch_significant_earthquakes(min_magnitude=4.0)

        assert isinstance(results, list)
        assert len(results) >= 1
        for eq in results:
            assert set(eq.keys()) == {"magnitude", "place", "time", "latitude", "longitude", "depth_km"}