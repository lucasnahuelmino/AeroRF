from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.database.database import SessionLocal
from app.models.map_object import MapObject
from app.models.rf import RFEvent

_API = "/api/v1"


def _client(db):
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


def test_recent_measurements_are_bounded_and_newest_first(db):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    with SessionLocal() as session:
        for index, created_at in enumerate(
            [now - timedelta(days=2), now, now - timedelta(days=1)],
            start=1,
        ):
            session.add(
                MapObject(
                    type="measurement",
                    name=f"Medición {index}",
                    geometry_type="Point",
                    geometry={"type": "Point", "coordinates": [-58.4, -34.6]},
                    latitude=-34.6,
                    longitude=-58.4,
                    fecha_creacion=created_at,
                    fecha_actualizacion=created_at,
                )
            )
        session.commit()

    with _client(db) as client:
        response = client.get(
            f"{_API}/map/objects",
            params={"type": "measurement", "limit": 2, "order_by": "recent"},
        )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["count"] == 2
    assert data["total"] == 3
    assert [row["name"] for row in data["objects"]] == ["Medición 2", "Medición 3"]


def test_recent_rf_events_are_bounded_and_ordered_by_event_time(db):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    with SessionLocal() as session:
        for index, event_at in enumerate(
            [now - timedelta(days=2), now, now - timedelta(days=1)],
            start=1,
        ):
            obj = MapObject(
                type="rf_event",
                name=f"Alerta RF {index}",
                geometry_type="Point",
                geometry={"type": "Point", "coordinates": [-58.4, -34.6]},
                latitude=-34.6,
                longitude=-58.4,
                fecha_creacion=now - timedelta(days=10),
                fecha_actualizacion=now - timedelta(days=10),
            )
            session.add(obj)
            session.flush()
            session.add(
                RFEvent(
                    object_id=obj.id,
                    event_at=event_at,
                    frequency_mhz=121.5,
                    classification="interferencia",
                )
            )
        session.commit()

    with _client(db) as client:
        response = client.get(f"{_API}/rf/events", params={"limit": 2})

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["count"] == 2
    assert [row["name"] for row in data["events"]] == ["Alerta RF 2", "Alerta RF 3"]
