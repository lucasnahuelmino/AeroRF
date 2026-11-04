"""
tests/test_map_objects.py
-------------------------
CRUD for map objects, RF payloads, notes, history and states
(spec §52: CRUD de objetos, CRUD de RF, CRUD de antenas).

The theme of these tests is that the *record* survives: an object's whole
life — creation, edits, state changes, notes — must be reconstructable
afterwards, and destructive operations must not be able to destroy part of
an investigation by accident.
"""

from __future__ import annotations

import pytest

from app.models.constants import (
    SESSION_RECORDING,
    SESSION_STOPPED,
    STATE_ACTIVE,
    STATE_OFF,
)
from app.services import flight_service as fsvc
from app.services import map_service as svc
from app.services.map_service import MapServiceError

EZE = (-34.8222, -58.5358)


# ─── Create ──────────────────────────────────────────────────────────────────

class TestCreate:
    def test_create_point(self, db):
        obj = svc.create_object(
            db, "point", name="Punto", latitude=EZE[0], longitude=EZE[1]
        )
        assert obj.id is not None
        assert obj.type == "point"
        assert obj.status == STATE_ACTIVE
        assert obj.visible is True
        assert obj.locked is False

    def test_defaults_are_applied(self, db):
        obj = svc.create_object(db, "rf_source", latitude=EZE[0], longitude=EZE[1])
        assert obj.color == "#f97316"       # type default
        assert obj.icon == "emitter"
        assert obj.opacity == 1.0

    def test_layer_assigned_by_type(self, db):
        obj = svc.create_object(db, "circle", latitude=EZE[0], longitude=EZE[1],
                                radius=10, radius_unit="nm")
        assert obj.layer is not None
        assert obj.layer.key == "circles"

    def test_explicit_layer_wins(self, db):
        from app.models.layer import Layer

        custom = Layer(key="mi_capa", name="Mi capa", order_index=900)
        db.add(custom)
        db.commit()

        obj = svc.create_object(
            db, "point", latitude=EZE[0], longitude=EZE[1], layer_id=custom.id
        )
        assert obj.layer.key == "mi_capa"

    def test_creation_is_historised(self, db):
        obj = svc.create_object(db, "point", latitude=EZE[0], longitude=EZE[1])
        history = svc.list_history(db, obj.id)
        assert len(history) == 1
        assert history[0].field == "__created__"
        assert history[0].new_value == "point"

    def test_initial_notes_recorded(self, db):
        obj = svc.create_object(
            db, "point", latitude=EZE[0], longitude=EZE[1],
            notes=["Medición en sitio", "Fuente apagada"],
        )
        notes = svc.list_notes(db, obj.id)
        assert [n.text for n in notes] == ["Medición en sitio", "Fuente apagada"]

    def test_invalid_type_rejected(self, db):
        with pytest.raises(MapServiceError) as exc:
            svc.create_object(db, "unicorn", latitude=EZE[0], longitude=EZE[1])
        # El mensaje identifica el tipo inválido (en español: la regla
        # del proyecto pone el texto del operador en su idioma).
        assert "Tipo de objeto desconocido" in str(exc.value)

    def test_invalid_coordinate_rejected(self, db):
        with pytest.raises(MapServiceError):
            svc.create_object(db, "point", latitude=91, longitude=0)

    def test_invalid_status_rejected(self, db):
        with pytest.raises(MapServiceError):
            svc.create_object(
                db, "point", latitude=EZE[0], longitude=EZE[1], status="Inventado"
            )

    def test_unit_is_normalised_on_write(self, db):
        obj = svc.create_object(
            db, "circle", latitude=EZE[0], longitude=EZE[1],
            radius=5, radius_unit="Millas Náuticas",
        )
        # The database only ever stores the canonical id.
        assert obj.radius_unit == "nm"
        assert obj.radius == 5

    def test_rf_payload_attached(self, db):
        obj = svc.create_object(
            db, "rf_source", name="Fuente", latitude=EZE[0], longitude=EZE[1],
            rf={"kind": "FM", "frequency_mhz": 98.1, "power_dbm": -55},
        )
        db.refresh(obj)
        assert obj.rf_source is not None
        assert obj.rf_source.kind == "FM"
        assert obj.rf_source.frequency_mhz == pytest.approx(98.1)

    def test_antenna_azimuth_promoted_to_object(self, db):
        """The map's radial line must match the recorded pointing angle."""
        obj = svc.create_object(
            db, "antenna", latitude=EZE[0], longitude=EZE[1],
            antenna={"kind": "Direccional", "azimuth_deg": 90, "sector_deg": 60},
        )
        db.refresh(obj)
        assert obj.azimuth == 90
        assert obj.antenna.sector_deg == 60

    def test_reference_radius_promoted_to_object(self, db):
        obj = svc.create_object(
            db, "reference", latitude=EZE[0], longitude=EZE[1],
            reference={"radius": 10, "radius_unit": "nm"},
        )
        db.refresh(obj)
        assert obj.radius == 10
        assert obj.radius_unit == "nm"


# ─── Read ────────────────────────────────────────────────────────────────────

class TestRead:
    def test_get_and_list(self, db):
        a = svc.create_object(db, "point", name="A", latitude=EZE[0], longitude=EZE[1])
        b = svc.create_object(db, "point", name="B", latitude=EZE[1], longitude=EZE[0])
        assert svc.get_object(db, a.id).id == a.id
        assert len(svc.list_objects(db)) == 2
        assert len(svc.list_objects(db, types=["point"])) == 2
        assert len(svc.list_objects(db, types=["circle"])) == 0
        assert len(svc.list_objects(db, search="A")) == 1
        assert svc.get_object(db, 99999) is None

    def test_filter_by_bbox(self, db):
        svc.create_object(db, "point", name="Cerca", latitude=-34.6, longitude=-58.4)
        svc.create_object(db, "point", name="Lejos", latitude=-20.0, longitude=-50.0)
        near = svc.list_objects(db, bbox=(-35.0, -59.0, -34.0, -58.0))
        assert [o.name for o in near] == ["Cerca"]

    def test_filter_by_expediente(self, db):
        from app.models.expediente import Expediente

        exp = Expediente(numero_expediente="E-1", freq_mhz=118.3, aeropuerto="EZE")
        db.add(exp)
        db.commit()

        svc.create_object(db, "point", name="A", latitude=EZE[0], longitude=EZE[1],
                         expediente_id=exp.id)
        svc.create_object(db, "point", name="B", latitude=EZE[0], longitude=EZE[1])
        found = svc.list_objects(db, expediente_id=exp.id)
        assert [o.name for o in found] == ["A"]

    def test_stats(self, db):
        svc.create_object(db, "point", latitude=EZE[0], longitude=EZE[1])
        svc.create_object(db, "circle", latitude=EZE[0], longitude=EZE[1],
                          radius=5, radius_unit="nm")
        stats = svc.object_stats(db)
        assert stats["total"] == 2
        assert stats["by_type"] == {"point": 1, "circle": 1}
        assert stats["by_status"][STATE_ACTIVE] == 2
        assert "circles" in stats["by_layer"]


# ─── Update ──────────────────────────────────────────────────────────────────

class TestUpdate:
    def test_partial_update(self, db):
        obj = svc.create_object(db, "point", name="Antes",
                                latitude=EZE[0], longitude=EZE[1])
        svc.update_object(db, obj.id, {"name": "Despues"})
        assert svc.get_object(db, obj.id).name == "Despues"

    def test_every_changed_field_is_historised(self, db):
        obj = svc.create_object(db, "point", name="Antes",
                                latitude=EZE[0], longitude=EZE[1])
        svc.update_object(db, obj.id, {"name": "Despues", "description": "Nota"})
        fields = {h.field for h in svc.list_history(db, obj.id)}
        assert {"name", "description"} <= fields

    def test_unchanged_fields_are_not_historised(self, db):
        obj = svc.create_object(db, "point", name="Igual",
                                latitude=EZE[0], longitude=EZE[1])
        before = len(svc.list_history(db, obj.id))
        svc.update_object(db, obj.id, {"name": "Igual"})
        assert len(svc.list_history(db, obj.id)) == before

    def test_old_value_is_preserved(self, db):
        obj = svc.create_object(db, "point", name="V1", latitude=EZE[0],
                                longitude=EZE[1])
        svc.update_object(db, obj.id, {"name": "V2"})
        row = next(h for h in svc.list_history(db, obj.id) if h.field == "name")
        assert row.old_value == "V1"
        assert row.new_value == "V2"

    def test_unknown_field_rejected(self, db):
        obj = svc.create_object(db, "point", latitude=EZE[0], longitude=EZE[1])
        with pytest.raises(MapServiceError) as exc:
            svc.update_object(db, obj.id, {"nope": 1})
        # El mensaje nombra el campo rechazado (en español, como todo
        # lo que lee el operador).
        assert "campo(s) desconocido(s)" in str(exc.value).lower()

    def test_invalid_status_rejected(self, db):
        obj = svc.create_object(db, "point", latitude=EZE[0], longitude=EZE[1])
        with pytest.raises(MapServiceError):
            svc.update_object(db, obj.id, {"status": "Inventado"})

    def test_invalid_coordinate_rejected(self, db):
        obj = svc.create_object(db, "point", latitude=EZE[0], longitude=EZE[1])
        with pytest.raises(MapServiceError):
            svc.update_object(db, obj.id, {"latitude": 200})

    def test_move(self, db):
        obj = svc.create_object(db, "point", latitude=EZE[0], longitude=EZE[1])
        svc.move_object(db, obj.id, -34.5, -58.3)
        moved = svc.get_object(db, obj.id)
        assert moved.latitude == pytest.approx(-34.5)
        rows = [h for h in svc.list_history(db, obj.id)
                if h.field in ("latitude", "longitude")]
        assert len(rows) == 2

    def test_duplicate(self, db):
        obj = svc.create_object(
            db, "point", name="Original", latitude=EZE[0], longitude=EZE[1]
        )
        copy = svc.duplicate_object(db, obj.id, offset_lat=0.01)
        assert copy.id != obj.id
        assert copy.name == "Original (copia)"
        assert copy.latitude == pytest.approx(EZE[0] + 0.01)

    def test_duplicate_copies_the_rf_payload(self, db):
        obj = svc.create_object(
            db, "rf_source", name="Fuente", latitude=EZE[0], longitude=EZE[1],
            rf={"kind": "FM", "frequency_mhz": 98.1},
        )
        copy = svc.duplicate_object(db, obj.id)
        db.refresh(copy)
        assert copy.rf_source is not None
        assert copy.rf_source.frequency_mhz == pytest.approx(98.1)

    def test_locked_object_refuses_edits(self, db):
        obj = svc.create_object(db, "point", latitude=EZE[0], longitude=EZE[1])
        svc.update_object(db, obj.id, {"locked": True})
        with pytest.raises(MapServiceError) as exc:
            svc.update_object(db, obj.id, {"name": "No"})
        # Este texto llega al operador tal cual (`client.js` prefiere el
        # `detail` del backend): buscaba la palabra inglesa «locked», que al
        # pasar a español dejó de existir. Lo que se guarda es que el motivo
        # sea el candado, y que esté en el idioma del operador.
        assert "bloqueado" in str(exc.value).lower()

    def test_locked_object_can_be_unlocked(self, db):
        """A lock must never be a one-way trap."""
        obj = svc.create_object(db, "point", latitude=EZE[0], longitude=EZE[1])
        svc.update_object(db, obj.id, {"locked": True})
        svc.update_object(db, obj.id, {"locked": False})
        assert svc.get_object(db, obj.id).locked is False


# ─── States and history (spec §15, §40, §41) ────────────────────────────────

class TestStateMachine:
    def test_transitions_historised_in_order(self, db):
        obj = svc.create_object(db, "rf_source", latitude=EZE[0], longitude=EZE[1],
                                status=STATE_ACTIVE)
        for state in (STATE_OFF, STATE_ACTIVE, "Cerrado"):
            svc.set_status(db, obj.id, state, user="inspector")

        rows = [h for h in svc.list_history(db, obj.id) if h.field == "status"]
        assert [h.new_value for h in rows] == [STATE_OFF, STATE_ACTIVE, "Cerrado"]
        assert [h.old_value for h in rows] == [STATE_ACTIVE, STATE_OFF, STATE_ACTIVE]

    def test_comment_attached_to_transition(self, db):
        obj = svc.create_object(db, "rf_source", latitude=EZE[0], longitude=EZE[1])
        svc.set_status(db, obj.id, STATE_OFF, user="inspector",
                       comment="Fuente apagada.")
        row = next(h for h in svc.list_history(db, obj.id) if h.field == "status")
        assert row.comment == "Fuente apagada."
        assert row.user == "inspector"

    def test_final_state_is_readable(self, db):
        obj = svc.create_object(db, "rf_source", latitude=EZE[0], longitude=EZE[1])
        svc.set_status(db, obj.id, STATE_OFF)
        assert svc.get_object(db, obj.id).status == STATE_OFF

    def test_all_seven_states_accepted(self, db):
        from app.models.constants import OBJECT_STATES

        assert len(OBJECT_STATES) == 7
        obj = svc.create_object(db, "point", latitude=EZE[0], longitude=EZE[1])
        for state in OBJECT_STATES:
            svc.set_status(db, obj.id, state)
        assert svc.get_object(db, obj.id).status == OBJECT_STATES[-1]

    def test_history_filterable_by_field(self, db):
        obj = svc.create_object(db, "point", latitude=EZE[0], longitude=EZE[1])
        svc.update_object(db, obj.id, {"name": "A"})
        svc.set_status(db, obj.id, STATE_OFF)
        assert len(svc.list_history(db, obj.id, field="status")) == 1


# ─── Notes (spec §14, §42) ──────────────────────────────────────────────────

class TestNotes:
    def test_append_only(self, db):
        obj = svc.create_object(db, "point", latitude=EZE[0], longitude=EZE[1])
        for text in ("Se detectó emisión el 12/09/2026.",
                     "Se volvió a medir el 14/09/2026.",
                     "Fuente apagada."):
            svc.add_note(db, obj.id, text, user="inspector")

        notes = svc.list_notes(db, obj.id)
        assert len(notes) == 3
        assert notes[0].text.startswith("Se detectó")
        assert notes[-1].text == "Fuente apagada."

    def test_notes_survive_edits(self, db):
        obj = svc.create_object(db, "point", latitude=EZE[0], longitude=EZE[1])
        svc.add_note(db, obj.id, "Nota")
        svc.update_object(db, obj.id, {"name": "Cambiado"})
        svc.set_status(db, obj.id, STATE_OFF)
        assert len(svc.list_notes(db, obj.id)) == 1

    def test_no_update_or_delete_api(self, db):
        """Append-only is a property of the service surface, not a promise."""
        forbidden = {"update_note", "delete_note", "edit_note"}
        assert not forbidden & set(dir(svc))

    def test_empty_note_rejected(self, db):
        obj = svc.create_object(db, "point", latitude=EZE[0], longitude=EZE[1])
        with pytest.raises(MapServiceError):
            svc.add_note(db, obj.id, "   ")

    def test_note_on_missing_object(self, db):
        with pytest.raises(MapServiceError):
            svc.add_note(db, 99999, "Nota")

    def test_timestamp_recorded(self, db):
        obj = svc.create_object(db, "point", latitude=EZE[0], longitude=EZE[1])
        note = svc.add_note(db, obj.id, "Nota")
        assert note.timestamp is not None


# ─── Delete ──────────────────────────────────────────────────────────────────

class TestDelete:
    def test_delete_removes_object(self, db):
        obj = svc.create_object(db, "point", latitude=EZE[0], longitude=EZE[1])
        svc.delete_object(db, obj.id)
        assert svc.get_object(db, obj.id) is None

    def test_delete_cascades_notes_and_history(self, db):
        obj = svc.create_object(db, "point", latitude=EZE[0], longitude=EZE[1])
        svc.add_note(db, obj.id, "Nota")
        svc.set_status(db, obj.id, STATE_OFF)
        svc.delete_object(db, obj.id)
        assert svc.list_notes(db, obj.id) == []
        assert svc.list_history(db, obj.id) == []

    def test_delete_refused_when_linked_to_expediente(self, db):
        from app.models.expediente import Expediente

        exp = Expediente(numero_expediente="E-1", freq_mhz=118.3, aeropuerto="EZE")
        db.add(exp)
        db.commit()
        obj = svc.create_object(db, "point", latitude=EZE[0], longitude=EZE[1],
                                expediente_id=exp.id)
        with pytest.raises(MapServiceError) as exc:
            svc.delete_object(db, obj.id)
        assert "expediente" in str(exc.value)

    def test_cascade_overrides_the_refusal(self, db):
        from app.models.expediente import Expediente

        exp = Expediente(numero_expediente="E-1", freq_mhz=118.3, aeropuerto="EZE")
        db.add(exp)
        db.commit()
        obj = svc.create_object(db, "point", latitude=EZE[0], longitude=EZE[1],
                                expediente_id=exp.id)
        svc.delete_object(db, obj.id, cascade=True)
        assert svc.get_object(db, obj.id) is None

    def test_delete_missing_object_is_a_noop(self, db):
        svc.delete_object(db, 99999)

    def test_clear_layer_requires_cascade(self, db):
        obj = svc.create_object(db, "point", latitude=EZE[0], longitude=EZE[1])
        with pytest.raises(MapServiceError):
            svc.clear_layer(db, obj.layer_id)
        assert svc.get_object(db, obj.id) is not None
        assert svc.clear_layer(db, obj.layer_id, cascade=True) == 1


# ─── Spatial queries (spec §30) ─────────────────────────────────────────────

class TestSpatial:
    def test_objects_near_sorted_by_distance(self, db):
        near = svc.create_object(db, "rf_source", name="Cerca",
                                 latitude=-34.60, longitude=-58.40)
        far = svc.create_object(db, "rf_source", name="Lejos",
                                latitude=-34.80, longitude=-58.40)
        rows = svc.objects_near(db, -34.60, -58.40, 20)
        assert [r["object"].id for r in rows] == [near.id, far.id]
        assert rows[0]["distance_m"] < rows[1]["distance_m"]

    def test_objects_near_respects_the_radius(self, db):
        svc.create_object(db, "rf_source", latitude=-34.60, longitude=-58.40)
        svc.create_object(db, "rf_source", latitude=-35.00, longitude=-58.40)
        # 0.40 deg of latitude is about 24 NM, so it is outside 20 NM.
        assert len(svc.objects_near(db, -34.60, -58.40, 20)) == 1
        assert len(svc.objects_near(db, -34.60, -58.40, 40)) == 2

    def test_distances_report_km_and_nm(self, db):
        svc.create_object(db, "rf_source", latitude=-34.60, longitude=-58.40)
        rows = svc.distances_from(db, -34.60, -58.40)
        assert len(rows) == 1
        assert rows[0]["distance_m"] == pytest.approx(0.0, abs=1)
        assert rows[0]["distance_km"] == pytest.approx(0.0, abs=0.001)
        assert rows[0]["distance_nm"] == pytest.approx(0.0, abs=0.001)

    def test_20nm_in_nm_and_km_agree(self, db):
        from app.core.geo import destination_point

        lat, lon = destination_point(-34.6, -58.4, 90, 37_040)
        svc.create_object(db, "rf_source", latitude=lat, longitude=lon)
        row = svc.distances_from(db, -34.6, -58.4)[0]
        assert row["distance_nm"] == pytest.approx(20.0, rel=1e-4)
        assert row["distance_km"] == pytest.approx(37.04, rel=1e-4)

    def test_positionless_object_reports_none(self, db):
        from app.models.map_object import MapObject

        db.add(MapObject(type="point", name="Sin posición"))
        db.commit()
        rows = svc.distances_from(db, -34.6, -58.4)
        assert rows[0]["distance_m"] is None
        assert rows[0]["distance_nm"] is None

    def test_filter_by_type(self, db):
        svc.create_object(db, "rf_source", latitude=-34.6, longitude=-58.4)
        svc.create_object(db, "antenna", latitude=-34.6, longitude=-58.4)
        rows = svc.distances_from(db, -34.6, -58.4, types=["rf_source"])
        assert len(rows) == 1
        assert rows[0]["type"] == "rf_source"


# ─── Flight recording (spec §24, §26, §52) ─────────────────────────────────

class TestFlightRecording:
    def _state(self, ts, lat=-34.6, lon=-58.4):
        return {
            "icao24": "abc123", "callsign": "ARG1234",
            "time_position": ts, "latitude": lat, "longitude": lon,
            "altitude": 10_000.0, "heading": 90.0, "velocity": 240.0,
            "on_ground": False, "vertical_rate": 0.0,
        }

    def test_create_session(self, db):
        s = fsvc.create_session(db, "abc123", "ARG1234", interval_s=10)
        assert s.id is not None
        assert s.status == SESSION_RECORDING
        assert s.icao24 == "abc123"

    def test_duplicate_session_refused(self, db):
        fsvc.create_session(db, "abc123")
        with pytest.raises(fsvc.FlightServiceError):
            fsvc.create_session(db, "abc123")

    def test_invalid_icao24_refused(self, db):
        with pytest.raises(fsvc.FlightServiceError):
            fsvc.create_session(db, "not-hex!")

    def test_samples_recorded(self, db):
        s = fsvc.create_session(db, "abc123", "ARG1234")
        for i, ts in enumerate([1_758_000_000, 1_758_000_010, 1_758_000_020]):
            fsvc.record_sample(db, s.id, self._state(ts, -34.6 + i * 0.01))

        detail = fsvc.get_session_detail(db, s.id)
        assert len(detail["positions"]) == 3
        assert detail["session"]["sample_count"] == 3
        assert detail["positions"][0]["provenance"] == "aerorf"

    def test_missing_fields_stay_none(self, db):
        """A state vector without velocity records None, not 0.0 (spec §56)."""
        s = fsvc.create_session(db, "abc123")
        state = self._state(1_758_000_000)
        state["velocity"] = None
        state["altitude"] = None
        p = fsvc.record_sample(db, s.id, state)
        assert p.velocity is None
        assert p.altitude is None

    def test_positionless_sample_is_still_recorded(self, db):
        s = fsvc.create_session(db, "abc123")
        state = self._state(1_758_000_000)
        state["latitude"] = state["longitude"] = None
        p = fsvc.record_sample(db, s.id, state)
        assert p is not None
        assert p.latitude is None

    def test_stop_session_closes_and_builds_a_track(self, db):
        from app.models.flight import AircraftTrack

        s = fsvc.create_session(db, "abc123", "ARG1234")
        for i, ts in enumerate([1_758_000_000, 1_758_000_600, 1_758_001_200]):
            fsvc.record_sample(db, s.id, self._state(ts, -34.6 + i * 0.05))

        fsvc.stop_session(db, s.id, notes="Fin de la observación")
        track = db.query(AircraftTrack).filter(
            AircraftTrack.session_id == s.id
        ).first()
        assert track is not None
        # The track must be linked to its session, or replay finds nothing.
        assert track.session_id == s.id
        assert track.source == "aerorf"
        assert track.point_count == 3
        assert track.geometry["type"] == "LineString"

        refreshed = db.get(type(s), s.id)
        assert refreshed.status == SESSION_STOPPED
        assert refreshed.ended_at is not None
        assert refreshed.notes == "Fin de la observación"

    def test_session_detail_exposes_the_track(self, db):
        s = fsvc.create_session(db, "abc123", "ARG1234")
        for i, ts in enumerate([1_758_000_000, 1_758_000_600]):
            fsvc.record_sample(db, s.id, self._state(ts, -34.6 + i * 0.05))
        fsvc.stop_session(db, s.id)

        detail = fsvc.get_session_detail(db, s.id)
        assert len(detail["tracks"]) == 1
        assert detail["tracks"][0]["point_count"] == 2
        assert detail["tracks"][0]["source"] == "aerorf"
        assert len(detail["positions"]) == 2

    def test_stopping_twice_refused(self, db):
        s = fsvc.create_session(db, "abc123")
        fsvc.stop_session(db, s.id)
        with pytest.raises(fsvc.FlightServiceError):
            fsvc.stop_session(db, s.id)

    def test_recording_into_a_stopped_session_is_ignored(self, db):
        s = fsvc.create_session(db, "abc123")
        fsvc.stop_session(db, s.id)
        assert fsvc.record_sample(db, s.id, self._state(1_758_000_000)) is None

    def test_session_with_no_usable_positions_still_stops(self, db):
        s = fsvc.create_session(db, "abc123")
        state = self._state(1_758_000_000)
        state["latitude"] = state["longitude"] = None
        fsvc.record_sample(db, s.id, state)
        fsvc.stop_session(db, s.id)
        assert db.get(type(s), s.id).status == SESSION_STOPPED


# ─── Watchlist (spec §25) ───────────────────────────────────────────────────

class TestWatchlist:
    def test_add_assigns_slot_and_colour(self, db):
        row = fsvc.add_selection(db, "abc001", "ARG1")
        assert row.slot == 0
        assert row.color == fsvc.SLOT_COLORS[0]

    def test_five_allowed(self, db):
        for i in range(5):
            fsvc.add_selection(db, f"abc00{i}")
        assert len(fsvc.list_selections(db)) == 5

    def test_sixth_refused(self, db):
        for i in range(5):
            fsvc.add_selection(db, f"abc00{i}")
        with pytest.raises(fsvc.FlightServiceError) as exc:
            fsvc.add_selection(db, "abc005")
        assert "5" in str(exc.value)

    def test_duplicate_refused(self, db):
        fsvc.add_selection(db, "abc001")
        with pytest.raises(fsvc.FlightServiceError):
            fsvc.add_selection(db, "abc001")

    def test_removing_frees_a_slot(self, db):
        for i in range(5):
            fsvc.add_selection(db, f"abc00{i}")
        fsvc.remove_selection(db, "abc002")
        row = fsvc.add_selection(db, "abc005")
        assert row.slot == 2

    def test_colours_are_distinct(self, db):
        for i in range(5):
            fsvc.add_selection(db, f"abc00{i}")
        colors = [r["color"] for r in fsvc.list_selections(db)]
        assert len(set(colors)) == 5

    def test_invalid_icao24_refused(self, db):
        with pytest.raises(fsvc.FlightServiceError):
            fsvc.add_selection(db, "XYZ")
