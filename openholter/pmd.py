"""Polar Measurement Data (PMD) protocol for the Polar H10.

Reference: Polar BLE SDK, technical_documentation/Polar_Measurement_Data_Specification.pdf
(github.com/polarofficial/polar-ble-sdk). Summary of what is used here:

Control point (write + indicate):
    request:  [op_code, measurement_type, (setting_type, count, value_u16_le * count)...]
    response: [0xF0, op_code, measurement_type, error_code, more_frames, params...]
    op codes: 0x01 get settings, 0x02 start measurement, 0x03 stop measurement
    reading the characteristic returns the feature bitmask: [0x0F, b1, b2]

Data (notify):
    [measurement_type, timestamp_u64_le (ns, last sample in frame), frame_type, samples...]
    ECG  frame type 0x00: int24 LE per sample, microvolts
    ACC  frame type 0x00/0x01/0x02: x,y,z as int8/int16/int24 LE, milli-G
    frame types with bit 0x80 set are delta-compressed (not used by H10).
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

PMD_SERVICE = "fb005c80-02e7-f387-1cad-8acd2d8df0c8"
PMD_CONTROL = "fb005c81-02e7-f387-1cad-8acd2d8df0c8"
PMD_DATA = "fb005c82-02e7-f387-1cad-8acd2d8df0c8"

HR_SERVICE = "0000180d-0000-1000-8000-00805f9b34fb"
HR_MEASUREMENT = "00002a37-0000-1000-8000-00805f9b34fb"
BATTERY_LEVEL = "00002a19-0000-1000-8000-00805f9b34fb"

# measurement types
ECG = 0x00
PPG = 0x01
ACC = 0x02
PPI = 0x03
GYRO = 0x05
MAG = 0x06

MEASUREMENT_NAMES = {ECG: "ecg", PPG: "ppg", ACC: "acc", PPI: "ppi", GYRO: "gyro", MAG: "mag"}

# op codes
OP_GET_SETTINGS = 0x01
OP_START = 0x02
OP_STOP = 0x03

# setting types
SETTING_SAMPLE_RATE = 0x00
SETTING_RESOLUTION = 0x01
SETTING_RANGE = 0x02
SETTING_CHANNELS = 0x04
SETTING_NAMES = {
    SETTING_SAMPLE_RATE: "sample_rate",
    SETTING_RESOLUTION: "resolution",
    SETTING_RANGE: "range",
    0x03: "range_milliunit",
    SETTING_CHANNELS: "channels",
    0x05: "conversion_factor",
}

ERRORS = {
    0: "success",
    1: "invalid op code",
    2: "invalid measurement type",
    3: "not supported",
    4: "invalid length",
    5: "invalid parameter",
    6: "already in state",
    7: "invalid resolution",
    8: "invalid sample rate",
    9: "invalid range",
    10: "invalid MTU",
    11: "invalid number of channels",
    12: "invalid state",
    13: "device in charger",
}

# 2000-01-01T00:00:00Z in Unix ns; PMD timestamps count from this epoch.
PMD_EPOCH_UNIX_NS = 946_684_800 * 1_000_000_000


def _setting(kind: int, value: int) -> bytes:
    return bytes([kind, 1]) + struct.pack("<H", value)


def start_ecg_command(sample_rate: int = 130, resolution: int = 14) -> bytes:
    return bytes([OP_START, ECG]) + _setting(SETTING_SAMPLE_RATE, sample_rate) + _setting(SETTING_RESOLUTION, resolution)


def start_acc_command(sample_rate: int = 50, resolution: int = 16, range_g: int = 4) -> bytes:
    return (
        bytes([OP_START, ACC])
        + _setting(SETTING_SAMPLE_RATE, sample_rate)
        + _setting(SETTING_RESOLUTION, resolution)
        + _setting(SETTING_RANGE, range_g)
    )


def stop_command(measurement: int) -> bytes:
    return bytes([OP_STOP, measurement])


def get_settings_command(measurement: int) -> bytes:
    return bytes([OP_GET_SETTINGS, measurement])


def parse_features(data: bytes) -> List[str]:
    """Parse the control point read value into a list of supported measurement names."""
    if len(data) < 2 or data[0] != 0x0F:
        return []
    bits = data[1] | ((data[2] << 8) if len(data) > 2 else 0)
    return [name for code, name in MEASUREMENT_NAMES.items() if bits & (1 << code)]


@dataclass
class ControlResponse:
    op_code: int
    measurement: int
    error: int
    more: bool
    params: bytes

    @property
    def ok(self) -> bool:
        return self.error == 0

    @property
    def error_text(self) -> str:
        return ERRORS.get(self.error, f"unknown error {self.error}")


def parse_control_response(data: bytes) -> Optional[ControlResponse]:
    if len(data) < 4 or data[0] != 0xF0:
        return None
    more = bool(data[4]) if len(data) > 4 else False
    return ControlResponse(data[1], data[2], data[3], more, bytes(data[5:]))


def parse_settings(params: bytes) -> Dict[str, List[float]]:
    """Parse a get-settings response body: repeated (type, count, values)."""
    out: Dict[str, List[float]] = {}
    i = 0
    while i + 2 <= len(params):
        kind, count = params[i], params[i + 1]
        i += 2
        width = 4 if kind == 0x05 else (1 if kind == SETTING_CHANNELS else 2)
        values: List[float] = []
        for _ in range(count):
            if i + width > len(params):
                return out
            chunk = params[i:i + width]
            if width == 4:
                values.append(struct.unpack("<f", chunk)[0])
            elif width == 2:
                values.append(struct.unpack("<H", chunk)[0])
            else:
                values.append(chunk[0])
            i += width
        out[SETTING_NAMES.get(kind, f"setting_{kind}")] = values
    return out


@dataclass
class Frame:
    measurement: int
    sensor_ts_ns: int  # timestamp of the last sample, PMD epoch
    frame_type: int
    samples: np.ndarray = field(repr=False)  # ECG: (n,) int32 µV, ACC: (n, 3) int32 mG


def _int24(raw: np.ndarray) -> np.ndarray:
    """Decode little-endian signed 24-bit integers from an (n, 3) uint8 array."""
    v = raw[:, 0].astype(np.int32) | (raw[:, 1].astype(np.int32) << 8) | (raw[:, 2].astype(np.int32) << 16)
    return np.where(v & 0x800000, v - 0x1000000, v).astype(np.int32)


def decode_samples(measurement: int, frame_type: int, body: bytes) -> np.ndarray:
    buf = np.frombuffer(body, dtype=np.uint8)
    if frame_type & 0x80:
        raise ValueError("delta-compressed frames are not supported (not used by H10)")
    if measurement == ECG:
        if frame_type != 0x00:
            raise ValueError(f"unexpected ECG frame type {frame_type}")
        n = len(buf) // 3
        return _int24(buf[: n * 3].reshape(n, 3))
    if measurement == ACC:
        width = {0x00: 1, 0x01: 2, 0x02: 3}.get(frame_type)
        if width is None:
            raise ValueError(f"unexpected ACC frame type {frame_type}")
        n = len(buf) // (3 * width)
        buf = buf[: n * 3 * width]
        if width == 1:
            vals = buf.view(np.int8).astype(np.int32)
        elif width == 2:
            vals = buf.view("<i2").astype(np.int32)
        else:
            vals = _int24(buf.reshape(-1, 3))
        return vals.reshape(n, 3)
    raise ValueError(f"unsupported measurement type {measurement}")


def parse_frame(data: bytes) -> Frame:
    if len(data) < 10:
        raise ValueError(f"PMD frame too short ({len(data)} bytes)")
    measurement = data[0]
    (ts,) = struct.unpack_from("<Q", data, 1)
    frame_type = data[9]
    return Frame(measurement, ts, frame_type, decode_samples(measurement, frame_type, bytes(data[10:])))


def encode_frame(measurement: int, sensor_ts_ns: int, samples: np.ndarray) -> bytes:
    """Encode a frame exactly like the H10 does. Used by the simulator and tests."""
    if measurement == ECG:
        v = np.asarray(samples, dtype=np.int32) & 0xFFFFFF
        raw = np.stack([v & 0xFF, (v >> 8) & 0xFF, (v >> 16) & 0xFF], axis=1).astype(np.uint8)
        frame_type = 0x00
        body = raw.tobytes()
    elif measurement == ACC:
        frame_type = 0x01
        body = np.asarray(samples, dtype="<i2").reshape(-1, 3).tobytes()
    else:
        raise ValueError(f"cannot encode measurement {measurement}")
    return bytes([measurement]) + struct.pack("<Q", sensor_ts_ns) + bytes([frame_type]) + body


@dataclass
class HeartRate:
    bpm: int
    rr_ms: List[float]
    contact: Optional[bool]


def parse_heart_rate(data: bytes) -> HeartRate:
    """Parse a standard BLE Heart Rate Measurement (0x2A37) notification."""
    flags = data[0]
    i = 1
    if flags & 0x01:
        (bpm,) = struct.unpack_from("<H", data, i)
        i += 2
    else:
        bpm = data[i]
        i += 1
    contact: Optional[bool] = None
    if flags & 0x04:  # contact detection supported
        contact = bool(flags & 0x02)
    if flags & 0x08:  # energy expended present
        i += 2
    rr: List[float] = []
    if flags & 0x10:
        while i + 2 <= len(data):
            (raw,) = struct.unpack_from("<H", data, i)
            rr.append(raw * 1000.0 / 1024.0)
            i += 2
    return HeartRate(bpm, rr, contact)


def encode_heart_rate(bpm: int, rr_ms: List[float], contact: bool = True) -> bytes:
    flags = 0x10 | 0x04 | (0x02 if contact else 0)
    out = bytes([flags, max(0, min(255, int(round(bpm))))])
    for r in rr_ms:
        out += struct.pack("<H", int(round(r * 1024.0 / 1000.0)))
    return out
