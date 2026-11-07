"""Common event envelope and per-type payload schemas (spec §4).

Owner: Shangran. Changes must be agreed with all producer owners.

Every producer sends one `Event`. The hub validates the envelope *and* the
payload for the declared `type`, so a malformed payload is rejected at the
door instead of breaking the UI later.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

SCHEMA_VERSION = 1

Mode = Literal["live", "replay", "simulated", "configured"]
Source = Literal["aircraft", "audio", "acoustics", "wifi", "pressure", "hub", "demo", "mock"]


class _Payload(BaseModel):
    # Required fields are enforced; extra diagnostic fields are allowed so
    # owners can add debugging info without a schema meeting.
    model_config = ConfigDict(extra="allow")


# ---------------------------------------------------------------- payloads

class SourceStatus(_Payload):
    component: str
    state: Literal["starting", "ok", "calibrating", "stale", "offline", "error"]
    detail: str = ""
    last_sample_age_ms: Optional[float] = None


class AircraftSignature(_Payload):
    event_id: str
    start_utc: str
    end_utc: str
    # [[receive_time_unix_s, frequency_hz], ...] — observed ridge
    frequency_trace: List[List[float]]
    quality_score: float
    # Optional: matched aircraft and its predicted curve at the *estimate*
    # (or at a known location for the required experiment).
    aircraft_id: Optional[str] = None
    callsign: Optional[str] = None
    predicted_trace: Optional[List[List[float]]] = None
    predicted_at: Optional[Literal["estimate", "known_location", "configured"]] = None


class CandidateRegion(_Payload):
    latitude: float
    longitude: float
    radius_m: float
    fit_score: float


class LocationEstimate(_Payload):
    status: Literal["listening", "candidate", "supported", "ambiguous", "no_match"]
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    search_bounds: Dict[str, float]  # lat_min, lat_max, lon_min, lon_max
    candidate_regions: List[CandidateRegion] = Field(default_factory=list)
    fit_score: Optional[float] = None
    supporting_event_ids: List[str] = Field(default_factory=list)
    method: str


class AircraftTracks(_Payload):
    """Addition proposed for the Sky view (not in spec table — agree at hour 1)."""
    # [{id, callsign, type, points: [[unix_s, lat, lon, alt_m], ...]}]
    aircraft: List[Dict[str, Any]]
    collection_region: Dict[str, float]


class PressureSample(_Payload):
    pressure_pa: Optional[float]  # null if the source only reports altitude
    sensor_timestamp: Optional[Union[float, str]] = None
    relative_height_m: Optional[float] = None


class FloorEstimate(_Payload):
    floor_id: Optional[str]
    reference_floor: Optional[str]
    calibration_id: Optional[str]
    status: Literal["settled", "transition", "uncertain", "uncalibrated", "configured"]


class WifiFeatures(_Payload):
    motion_score: float
    csi_trace: List[float]          # reduced trace for display (not raw CSI)
    packet_rate_hz: float
    sample_age_ms: float


class GestureDetected(_Payload):
    gesture: str
    score: float  # detector score, NOT a probability
    model_version: str
    window_ms: int


class AcousticMeasurement(_Payload):
    """One echolocation sweep at one position in a room (Anna)."""
    measurement_id: str
    position_label: Optional[str] = None          # e.g. "P1 table centre"
    rt60_s: Optional[float] = None                # reverberation time
    reflection_distances_m: List[float] = Field(default_factory=list)  # strongest early reflections
    snr_db: Optional[float] = None
    impulse_response_preview: Optional[List[float]] = None  # downsampled, for display only


class RoomCandidate(_Payload):
    room_id: str
    label: Optional[str] = None
    score: float  # match score, NOT a probability


class RoomEstimate(_Payload):
    """Ranked rooms on the current floor (Anna). Same status vocabulary as location."""
    status: Literal["listening", "candidate", "supported", "ambiguous", "no_match"]
    floor_id: Optional[str] = None
    floor_source: Literal["measured", "configured", "manual"] = "measured"
    estimated_dims_m: Optional[Dict[str, float]] = None  # length, width, height
    candidates: List[RoomCandidate] = Field(default_factory=list)
    method: str
    supporting_measurement_ids: List[str] = Field(default_factory=list)


class DemoState(_Payload):
    current_view: str  # slide id; the list of slides lives in config demo.views
    selected_building: Optional[str] = None
    selected_room: Optional[str] = None
    selection_source: Literal["measured", "configured", "manual"] = "configured"
    gesture_armed: bool = False
    last_trigger: Optional[str] = None


class ReplayProgress(_Payload):
    replay_of: str
    position: int
    total: int
    finished: bool = False


PAYLOAD_MODELS: Dict[str, type] = {
    "source.status": SourceStatus,
    "aircraft.signature": AircraftSignature,
    "aircraft.tracks": AircraftTracks,
    "location.estimate": LocationEstimate,
    "pressure.sample": PressureSample,
    "floor.estimate": FloorEstimate,
    "acoustic.measurement": AcousticMeasurement,
    "room.estimate": RoomEstimate,
    "wifi.features": WifiFeatures,
    "gesture.detected": GestureDetected,
    "demo.state": DemoState,
    "replay.progress": ReplayProgress,
}


# ---------------------------------------------------------------- envelope

class Event(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = SCHEMA_VERSION
    session_id: str = Field(min_length=1)
    source: Source
    type: str
    timestamp_utc: str
    sequence: int = Field(ge=0)
    mode: Mode
    payload: Dict[str, Any]

    @field_validator("type")
    @classmethod
    def _known_type(cls, v: str) -> str:
        if v not in PAYLOAD_MODELS:
            raise ValueError(f"unknown event type {v!r}")
        return v

    @field_validator("timestamp_utc")
    @classmethod
    def _iso_utc(cls, v: str) -> str:
        parse_utc(v)  # raises on malformed
        return v

    def validated_payload(self) -> BaseModel:
        return PAYLOAD_MODELS[self.type].model_validate(self.payload)


def validate_event(data: Dict[str, Any]) -> Event:
    """Validate envelope + payload. Raises ValidationError / ValueError."""
    ev = Event.model_validate(data)
    ev.validated_payload()
    return ev


# ---------------------------------------------------------------- time utils

def utc_now_iso() -> str:
    return iso_from_unix(datetime.now(timezone.utc).timestamp())


def iso_from_unix(t: float) -> str:
    dt = datetime.fromtimestamp(t, tz=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def parse_utc(s: str) -> float:
    """ISO-8601 UTC string -> unix seconds. Requires an explicit zone."""
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        raise ValueError("timestamp must include a UTC offset or 'Z'")
    return dt.timestamp()


__all__ = [
    "Event", "validate_event", "PAYLOAD_MODELS", "ValidationError",
    "utc_now_iso", "iso_from_unix", "parse_utc", "SCHEMA_VERSION",
]
