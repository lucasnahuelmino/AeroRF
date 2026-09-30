"""Asking twice for the same flight must not put the trajectory in twice.

The operator reported that yesterday's recordings "no se guardaron
correctamente". They had been saved — every one of them — and the problem was
that each one was saved two or three times over.

Measured in the database, before this change: 34 rows in ``aircraft_tracks``
holding 8 groups of exact duplicates. Same aerodrome, same start, same end,
same number of points. One flight from 09-28 appeared three times with 308
points each; the merged track for e02659 on 09-29 appeared three times with
165 points each.

The cause was in ``_store_track``: it built a row and inserted it, every time,
without ever asking whether the trajectory was already there. Nothing about the
insert was wrong in isolation. It simply had no memory of the previous request,
and several parts of the application ask for the same flight more than once —
the operator reloading the panel, a retry after a timeout, the per-aircraft
trajectory cache starting empty on each page load.

What is deliberately *not* deduplicated: a sparser trajectory over the same
window. That is different data, not a repeat — it is how a partial live
recording stays visible next to the full one. Only an identical window with an
identical point count is treated as the same trajectory.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.database import Base
from app.models.flight import AircraftTrack
from app.services.flight_service import _store_track


def _points(n: int, start: float = -34.5):
    """n positions marching north, so the geometry is not degenerate."""
    return [
        {"latitude": start + i * 0.01, "longitude": -58.4 + i * 0.01, "time": 1_700_000_000 + i * 10}
        for i in range(n)
    ]


def _payload(n: int):
    return {
        "source": "opensky",
        "start_time": 1_700_000_000,
        "end_time": 1_700_000_000 + n * 10,
        "span_s": float(n * 10),
        "provenance_counts": {"opensky": n},
    }


@pytest.fixture
def db():
    engine = create_engine("sqlite://", future=True)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, future=True)()
    try:
        yield session
    finally:
        session.close()


def _count(db) -> int:
    return db.query(AircraftTrack).count()


def test_the_same_flight_twice_is_stored_once(db):
    first = _store_track(db, "a101c3", "AAL3139", _points(120), _payload(120))
    second = _store_track(db, "a101c3", "AAL3139", _points(120), _payload(120))
    assert first.id == second.id, "la segunda peticion debe devolver la fila existente"
    assert _count(db) == 1


def test_three_requests_still_leave_one_row(db):
    for _ in range(3):
        _store_track(db, "e02659", "ARG1763", _points(165), _payload(165))
    assert _count(db) == 1


def test_a_sparser_trajectory_over_the_same_window_is_kept(db):
    # Not a repeat: fewer points over the same window is a different
    # trajectory, and hiding it would lose the partial live recording.
    _store_track(db, "e06491", "ARG1775", _points(10), _payload(10))
    _store_track(db, "e06491", "ARG1775", _points(5), _payload(5))
    assert _count(db) == 2


def test_another_aerodrome_is_never_mistaken_for_a_repeat(db):
    _store_track(db, "a101c3", "AAL3139", _points(120), _payload(120))
    _store_track(db, "a101c3", "AAL1107", _points(120), _payload(120))
    assert _count(db) == 2


def test_a_different_window_for_the_same_aerodrome_is_kept(db):
    _store_track(db, "a101c3", "AAL3139", _points(120), _payload(120))
    later = dict(_payload(120))
    later["start_time"] += 86_400
    later["end_time"] += 86_400
    _store_track(db, "a101c3", "AAL3139", _points(120), later)
    assert _count(db) == 2


def test_the_session_link_survives_on_the_row_that_is_kept(db):
    session_id = 7
    _store_track(db, "e02659", "ARG1763", _points(9), _payload(9), session_id=session_id)
    again = _store_track(db, "e02659", "ARG1763", _points(9), _payload(9))
    assert again.session_id == session_id, (
        "la sesion de grabacion debe seguir enlazada a la trayectoria"
    )
