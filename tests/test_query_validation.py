"""
Tests for WeatherQueryCreate / WeatherQueryUpdate date-range validation.

Design decision: these run against the Pydantic schema directly, not
through the API/DB. The validator rejects a bad date range before
FastAPI ever calls the route handler, so unit-testing the schema is both
faster and more precise than spinning up the full stack to prove the
same thing -- no network call to the geocoding service, no database
needed. The one API-level test below confirms that contract holds at
the HTTP boundary too.
"""
from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from app.schemas.schemas import WeatherQueryCreate, WeatherQueryUpdate


def test_create_rejects_end_before_start():
    with pytest.raises(ValidationError, match="end_date must be on or after start_date"):
        WeatherQueryCreate(
            location_query="Tokyo",
            start_date=date(2026, 6, 20),
            end_date=date(2026, 6, 19),
        )


def test_create_rejects_range_over_365_days():
    start = date(2026, 1, 1)
    end = start + timedelta(days=366)
    with pytest.raises(ValidationError, match="cannot exceed 365 days"):
        WeatherQueryCreate(location_query="Tokyo", start_date=start, end_date=end)


def test_create_accepts_same_day_range():
    """start_date == end_date is a valid single-day query, not an error."""
    q = WeatherQueryCreate(
        location_query="Tokyo",
        start_date=date(2026, 6, 20),
        end_date=date(2026, 6, 20),
    )
    assert q.start_date == q.end_date


def test_create_accepts_exactly_365_days():
    """365 days is the inclusive boundary -- should pass, not just <365."""
    start = date(2026, 1, 1)
    end = start + timedelta(days=365)
    q = WeatherQueryCreate(location_query="Tokyo", start_date=start, end_date=end)
    assert (q.end_date - q.start_date).days == 365


def test_update_rejects_end_before_start_when_both_provided():
    with pytest.raises(ValidationError, match="end_date must be on or after start_date"):
        WeatherQueryUpdate(start_date=date(2026, 6, 20), end_date=date(2026, 6, 1))


def test_update_allows_partial_fields_without_triggering_validation():
    """Updating only one of the two dates shouldn't require the other,
    and shouldn't accidentally compare a real date against None."""
    q = WeatherQueryUpdate(end_date=date(2026, 6, 30))
    assert q.start_date is None
    assert q.end_date == date(2026, 6, 30)


def test_api_rejects_bad_date_range_before_touching_geocoding(client):
    """
    End-to-end check: POSTing an invalid range returns 422 from request
    validation. If this ever silently passed and called the geocoding
    service for an invalid range, this test would hang/fail on a real
    network call instead of asserting fast -- so a passing 422 here is
    also a guardrail against that regression.
    """
    response = client.post(
        "/queries",
        json={
            "location_query": "Tokyo",
            "start_date": "2026-06-20",
            "end_date": "2026-06-01",
        },
    )
    assert response.status_code == 422
