"""
Minimal Garmin FIT structured workout file generator.

No external dependencies — writes the binary FIT format directly.
Reference: Garmin FIT SDK protocol document (fitprotocol.pdf).
"""
import re
import struct
import io
from datetime import datetime, timezone
from typing import Optional

# Garmin FIT epoch: December 31 1989 00:00:00 UTC
_FIT_EPOCH = datetime(1989, 12, 31, 0, 0, 0, tzinfo=timezone.utc)

# Garmin CRC-16 lookup table
_CRC_TABLE = [
    0x0000, 0xCC01, 0xD801, 0x1400, 0xF001, 0x3C00, 0x2800, 0xE401,
    0xA001, 0x6C00, 0x7800, 0xB401, 0x5000, 0x9C01, 0x8801, 0x4400,
]

# ── FIT base types ────────────────────────────────────────────────────────────
_T_ENUM   = 0x00   # 1 byte, invalid = 0xFF
_T_UINT8  = 0x02   # 1 byte, invalid = 0xFF
_T_UINT16 = 0x84   # 2 bytes LE, invalid = 0xFFFF
_T_UINT32 = 0x86   # 4 bytes LE, invalid = 0xFFFFFFFF
_T_STR    = 0x07   # null-terminated UTF-8

# ── Global message numbers ────────────────────────────────────────────────────
_MSG_FILE_ID      = 0
_MSG_WORKOUT      = 26
_MSG_WORKOUT_STEP = 27

# ── Duration types (workout step field 2) ─────────────────────────────────────
DUR_TIME     = 0   # duration_value in milliseconds
DUR_DISTANCE = 1   # duration_value in centimetres
DUR_OPEN     = 5   # user ends step manually (lap button)

# ── Target types (workout step field 4) ──────────────────────────────────────
TGT_HEART_RATE = 1
TGT_OPEN       = 2   # no target

# ── Intensity values (workout step field 8) ───────────────────────────────────
INT_ACTIVE   = 0
INT_REST     = 1
INT_WARMUP   = 2
INT_COOLDOWN = 3
INT_RECOVERY = 4

# ── Garmin HR zones (used as target_value when target_type = HEART_RATE) ─────
# These match Garmin Connect's default zone numbering
HR_ZONE_1 = 1   # very light / warmup    ~50-60% max HR
HR_ZONE_2 = 2   # easy / aerobic         ~60-70% max HR
HR_ZONE_3 = 3   # aerobic / moderate     ~70-80% max HR
HR_ZONE_4 = 4   # threshold / tempo      ~80-90% max HR
HR_ZONE_5 = 5   # VO2 max / intervals    ~90-100% max HR

_INVALID_U32 = 0xFFFF_FFFF   # sentinel for "not set"


# ─────────────────────────────────────────────────────────────────────────────
# Low-level CRC and string helpers
# ─────────────────────────────────────────────────────────────────────────────

def _crc16(data: bytes, crc: int = 0) -> int:
    for byte in data:
        tmp = _CRC_TABLE[crc & 0xF]
        crc = (crc >> 4) & 0x0FFF
        crc ^= tmp ^ _CRC_TABLE[byte & 0xF]
        tmp = _CRC_TABLE[crc & 0xF]
        crc = (crc >> 4) & 0x0FFF
        crc ^= tmp ^ _CRC_TABLE[(byte >> 4) & 0xF]
    return crc


def _fit_str(s: str, size: int) -> bytes:
    """Encode a string as a fixed-size null-terminated FIT string field."""
    b = s.encode("utf-8")[:size - 1]
    return b + b"\x00" * (size - len(b))


def _fit_now() -> int:
    """Current time as seconds since FIT epoch."""
    return int((datetime.now(timezone.utc) - _FIT_EPOCH).total_seconds())


# ─────────────────────────────────────────────────────────────────────────────
# FIT binary record builder
# ─────────────────────────────────────────────────────────────────────────────

class _FitBuilder:
    """Assembles FIT definition + data record pairs into a byte buffer."""

    def __init__(self):
        self._buf = io.BytesIO()
        self._step_def_done = False

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _definition(self, local_type: int, global_msg: int, fields: list[tuple]):
        """Write a definition message. fields = [(field_def_num, size, base_type), ...]"""
        hdr = 0x40 | (local_type & 0x0F)   # bit 6 = 1 → definition message
        self._buf.write(struct.pack("B", hdr))
        self._buf.write(b"\x00")                         # reserved
        self._buf.write(b"\x00")                         # architecture: little-endian
        self._buf.write(struct.pack("<H", global_msg))
        self._buf.write(struct.pack("B", len(fields)))
        for fnum, fsize, ftype in fields:
            self._buf.write(struct.pack("BBB", fnum, fsize, ftype))

    def _data(self, local_type: int):
        """Write a data record header byte."""
        self._buf.write(struct.pack("B", local_type & 0x0F))

    # ── FIT messages ─────────────────────────────────────────────────────────

    def write_file_id(self):
        """file_id message: type=workout, time_created=now"""
        self._definition(0, _MSG_FILE_ID, [
            (0, 1, _T_ENUM),   # type
            (4, 4, _T_UINT32), # time_created
        ])
        self._data(0)
        self._buf.write(struct.pack("B", 5))             # 5 = workout
        self._buf.write(struct.pack("<I", _fit_now()))

    def write_workout(self, name: str, num_steps: int):
        """workout message: sport=running, num_valid_steps, name"""
        self._definition(1, _MSG_WORKOUT, [
            (4, 1,  _T_ENUM),   # sport
            (6, 2,  _T_UINT16), # num_valid_steps
            (8, 16, _T_STR),    # wkt_name
        ])
        self._data(1)
        self._buf.write(struct.pack("B", 1))             # sport = running
        self._buf.write(struct.pack("<H", num_steps))
        self._buf.write(_fit_str(name, 16))

    def write_step(
        self,
        index: int,
        name: str,
        dur_type: int,
        dur_val: int,
        tgt_type: int,
        tgt_val: int,
        tgt_low: int  = _INVALID_U32,
        tgt_high: int = _INVALID_U32,
        intensity: int = INT_ACTIVE,
    ):
        """workout_step message. Definition is written once on first step."""
        if not self._step_def_done:
            self._definition(2, _MSG_WORKOUT_STEP, [
                (0, 2,  _T_UINT16), # message_index
                (1, 16, _T_STR),    # wkt_step_name
                (2, 1,  _T_ENUM),   # duration_type
                (3, 4,  _T_UINT32), # duration_value
                (4, 1,  _T_ENUM),   # target_type
                (5, 4,  _T_UINT32), # target_value
                (6, 4,  _T_UINT32), # custom_target_value_low
                (7, 4,  _T_UINT32), # custom_target_value_high
                (8, 1,  _T_ENUM),   # intensity
            ])
            self._step_def_done = True
        self._data(2)
        self._buf.write(struct.pack("<H", index))
        self._buf.write(_fit_str(name, 16))
        self._buf.write(struct.pack("B",  dur_type))
        self._buf.write(struct.pack("<I", dur_val))
        self._buf.write(struct.pack("B",  tgt_type))
        self._buf.write(struct.pack("<I", tgt_val))
        self._buf.write(struct.pack("<I", tgt_low))
        self._buf.write(struct.pack("<I", tgt_high))
        self._buf.write(struct.pack("B",  intensity))

    def build(self) -> bytes:
        """Assemble the complete FIT file bytes (header + records + CRC)."""
        data = self._buf.getvalue()
        # 14-byte header: size(1) + protocol(1) + profile(2) + data_size(4) + ".FIT"(4) + crc(2)
        hdr = struct.pack("<BBHI4s", 14, 0x10, 2132, len(data), b".FIT")
        hdr = hdr + struct.pack("<H", _crc16(hdr))
        return hdr + data + struct.pack("<H", _crc16(data))


# ─────────────────────────────────────────────────────────────────────────────
# Step building helpers
# ─────────────────────────────────────────────────────────────────────────────

def _ms(minutes: float) -> int:
    """Minutes → milliseconds."""
    return max(1000, int(minutes * 60 * 1000))


def _cm(km: float) -> int:
    """Kilometres → centimetres."""
    return max(100, int(km * 100_000))


def _step(name, dur_type, dur_val, tgt_type, tgt_val, intensity,
          tgt_low=_INVALID_U32, tgt_high=_INVALID_U32):
    return (name, dur_type, dur_val, tgt_type, tgt_val, tgt_low, tgt_high, intensity)


def _parse_intervals(title: str, description: str) -> tuple[int, int]:
    """Extract (reps, interval_metres) from text. Defaults: 4 × 1000 m."""
    text = (title + " " + description).lower()
    # Match "4×1km", "4x800m", "5 x 1000m", "6 × 400 m"
    m = re.search(r"(\d+)\s*[×x]\s*([\d.]+)\s*(km|m)\b", text)
    if m:
        reps = int(m.group(1))
        dist = float(m.group(2))
        dist_m = int(dist * 1000) if m.group(3) == "km" else int(dist)
        return min(max(reps, 1), 20), max(dist_m, 100)
    # Match "4 reps" or "4 repeats"
    m = re.search(r"(\d+)\s*rep", text)
    if m:
        return min(max(int(m.group(1)), 1), 20), 1000
    return 4, 1000


# ─────────────────────────────────────────────────────────────────────────────
# Workout-type step generators
# ─────────────────────────────────────────────────────────────────────────────

def _steps_easy(distance_km: float, duration_min: float) -> list:
    wu, cd = 5.0, 5.0
    steps = [_step("Warm Up", DUR_TIME, _ms(wu), TGT_OPEN, 0, INT_WARMUP)]
    if distance_km > 0:
        main_km = max(distance_km - 1.0, 1.0)
        steps.append(_step("Easy Run", DUR_DISTANCE, _cm(main_km), TGT_HEART_RATE, HR_ZONE_2, INT_ACTIVE))
    elif duration_min > 0:
        steps.append(_step("Easy Run", DUR_TIME, _ms(max(duration_min - wu - cd, 5.0)), TGT_HEART_RATE, HR_ZONE_2, INT_ACTIVE))
    else:
        steps.append(_step("Easy Run", DUR_OPEN, 0, TGT_HEART_RATE, HR_ZONE_2, INT_ACTIVE))
    steps.append(_step("Cool Down", DUR_TIME, _ms(cd), TGT_OPEN, 0, INT_COOLDOWN))
    return steps


def _steps_long(distance_km: float, duration_min: float) -> list:
    wu, cd = 10.0, 10.0
    steps = [_step("Warm Up", DUR_TIME, _ms(wu), TGT_OPEN, 0, INT_WARMUP)]
    if distance_km > 0:
        steps.append(_step("Long Run", DUR_DISTANCE, _cm(max(distance_km - 2.0, 1.0)), TGT_HEART_RATE, HR_ZONE_2, INT_ACTIVE))
    elif duration_min > 0:
        steps.append(_step("Long Run", DUR_TIME, _ms(max(duration_min - wu - cd, 10.0)), TGT_HEART_RATE, HR_ZONE_2, INT_ACTIVE))
    else:
        steps.append(_step("Long Run", DUR_OPEN, 0, TGT_HEART_RATE, HR_ZONE_2, INT_ACTIVE))
    steps.append(_step("Cool Down", DUR_TIME, _ms(cd), TGT_OPEN, 0, INT_COOLDOWN))
    return steps


def _steps_tempo(distance_km: float, duration_min: float) -> list:
    wu, cd = 10.0, 10.0
    steps = [_step("Warm Up", DUR_TIME, _ms(wu), TGT_OPEN, 0, INT_WARMUP)]
    if duration_min > (wu + cd + 5):
        steps.append(_step("Tempo", DUR_TIME, _ms(duration_min - wu - cd), TGT_HEART_RATE, HR_ZONE_4, INT_ACTIVE))
    elif distance_km > 3.0:
        steps.append(_step("Tempo", DUR_DISTANCE, _cm(max(distance_km - 4.0, 2.0)), TGT_HEART_RATE, HR_ZONE_4, INT_ACTIVE))
    else:
        steps.append(_step("Tempo", DUR_TIME, _ms(20), TGT_HEART_RATE, HR_ZONE_4, INT_ACTIVE))
    steps.append(_step("Cool Down", DUR_TIME, _ms(cd), TGT_OPEN, 0, INT_COOLDOWN))
    return steps


def _steps_intervals(day: dict) -> list:
    reps, interval_m = _parse_intervals(day.get("title", ""), day.get("description", ""))
    recovery_ms = _ms(2.0)   # 2 min recovery between reps
    steps = [_step("Warm Up", DUR_TIME, _ms(10), TGT_OPEN, 0, INT_WARMUP)]
    for _ in range(reps):
        steps.append(_step("Work",     DUR_DISTANCE, _cm(interval_m / 1000), TGT_HEART_RATE, HR_ZONE_5, INT_ACTIVE))
        steps.append(_step("Recovery", DUR_TIME, recovery_ms,                TGT_OPEN, 0,              INT_RECOVERY))
    steps.append(_step("Cool Down", DUR_TIME, _ms(10), TGT_OPEN, 0, INT_COOLDOWN))
    return steps


def _steps_cross_training(duration_min: float) -> list:
    dur = _ms(duration_min) if duration_min > 0 else _ms(30)
    return [_step("Cross Training", DUR_TIME, dur, TGT_HEART_RATE, HR_ZONE_3, INT_ACTIVE)]


def _steps_recovery(duration_min: float) -> list:
    dur = _ms(duration_min) if duration_min > 0 else _ms(30)
    return [_step("Active Recovery", DUR_TIME, dur, TGT_HEART_RATE, HR_ZONE_1, INT_ACTIVE)]


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def build_fit_workout(day: dict) -> bytes:
    """Generate a Garmin FIT structured workout file from a training plan day dict.

    The day dict must have at least: workout_type, title.
    Optional: distance_km, duration_min, description.
    Returns raw .fit file bytes ready to serve as a download.
    """
    workout_type = day.get("workout_type", "Run")
    title        = (day.get("title") or workout_type)[:15]
    distance_km  = float(day.get("distance_km") or 0)
    duration_min = float(day.get("duration_min") or 0)
    wt = workout_type.lower()

    if "rest" in wt:
        steps = [_step("Rest Day", DUR_OPEN, 0, TGT_OPEN, 0, INT_REST)]
    elif "interval" in wt or "repeat" in wt or "hill" in wt:
        steps = _steps_intervals(day)
    elif "tempo" in wt or "threshold" in wt:
        steps = _steps_tempo(distance_km, duration_min)
    elif "long" in wt:
        steps = _steps_long(distance_km, duration_min)
    elif "cross" in wt:
        steps = _steps_cross_training(duration_min)
    elif "recovery" in wt:
        steps = _steps_recovery(duration_min)
    else:
        steps = _steps_easy(distance_km, duration_min)

    builder = _FitBuilder()
    builder.write_file_id()
    builder.write_workout(title, len(steps))
    for i, s in enumerate(steps):
        builder.write_step(i, *s)

    return builder.build()
