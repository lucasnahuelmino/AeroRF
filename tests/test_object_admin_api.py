from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


_API = "/api/v1"


def test_object_listing_includes_hidden_records_and_admin_filters(db):
    with TestClient(app) as client:
        hidden = client.post(
            f"{_API}/map/objects",
            json={
                "type": "rf_source",
                "name": "Fuente reservada",
                "category": "Fuente interferente",
                "source": "user",
                "visible": False,
                "latitude": -34.6,
                "longitude": -58.4,
            },
        )
        shown = client.post(
            f"{_API}/map/objects",
            json={
                "type": "point",
                "name": "Punto visible",
                "category": "Referencia",
                "source": "user",
                "visible": True,
                "latitude": -34.6,
                "longitude": -58.4,
            },
        )
        assert hidden.status_code == 201, hidden.text
        assert shown.status_code == 201, shown.text

        all_objects = client.get(f"{_API}/map/objects", params={"limit": 1})
        assert all_objects.status_code == 200, all_objects.text
        assert all_objects.json()["count"] == 1
        assert all_objects.json()["total"] == 2

        hidden_object = client.get(
            f"{_API}/map/objects",
            params={
                "visible": "false",
                "category": "Fuente interferente",
                "source": "user",
                "search": str(hidden.json()["id"]),
            },
        )
        assert hidden_object.status_code == 200, hidden_object.text
        result = hidden_object.json()
        assert result["total"] == 1
        assert len(result["objects"]) == 1
        assert result["objects"][0]["id"] == hidden.json()["id"]
        assert result["objects"][0]["visible"] is False

        unlayered = client.put(
            f"{_API}/map/objects/{shown.json()['id']}",
            json={"layer_id": None},
        )
        assert unlayered.status_code == 200, unlayered.text
        orphaned_objects = client.get(
            f"{_API}/map/objects",
            params={"layer_missing": "true"},
        )
        assert orphaned_objects.json()["total"] == 1
        assert orphaned_objects.json()["objects"][0]["id"] == shown.json()["id"]

        updated = client.put(
            f"{_API}/map/objects/{hidden.json()['id']}",
            json={"name": "Fuente editada mientras está oculta"},
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["visible"] is False
        assert updated.json()["name"] == "Fuente editada mientras está oculta"

        deleted = client.delete(f"{_API}/map/objects/{hidden.json()['id']}")
        assert deleted.status_code == 200, deleted.text
        remaining = client.get(f"{_API}/map/objects")
        assert remaining.json()["total"] == 1
