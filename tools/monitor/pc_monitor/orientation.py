"""Gravity-based tilt estimation. Heading/yaw is deliberately not estimated."""

from __future__ import annotations

import math
from dataclasses import dataclass

from pc_monitor.stream import Sample

Vector = tuple[float, float, float]
Matrix = tuple[Vector, Vector, Vector]
Quaternion = tuple[float, float, float, float]


def norm(v: Vector) -> float:
    return math.sqrt(sum(x * x for x in v))


def unit_vector(v: Vector) -> Vector | None:
    length = norm(v)
    return tuple(x / length for x in v) if length > 1e-9 else None


def angle_between(a: Vector, b: Vector) -> float:
    ua, ub = unit_vector(a), unit_vector(b)
    if ua is None or ub is None:
        raise ValueError("A zero vector has no direction")
    return math.degrees(math.acos(max(-1.0, min(1.0, sum(x * y for x, y in zip(ua, ub))))))


def rotation_matrix(roll: float, pitch: float) -> Matrix:
    """Body to world: Ry(pitch) Rx(roll), with the unobservable yaw fixed to zero.

    Angles are in radians. For a static sensor, R @ measured_unit_g = world +Z.
    The matrix represents one compatible pose, not a measured full 3D attitude.
    """
    cr, sr, cp, sp = math.cos(roll), math.sin(roll), math.cos(pitch), math.sin(pitch)
    return ((cp, sp * sr, sp * cr), (0.0, cr, -sr), (-sp, cp * sr, cp * cr))


def transform(matrix: Matrix, point: Vector) -> Vector:
    return tuple(sum(a * b for a, b in zip(row, point)) for row in matrix)


def gravity_for_tilt(roll: float, pitch: float) -> Vector:
    """Ideal static sensor readings for the given roll/pitch in radians."""
    return (-math.sin(pitch), math.cos(pitch) * math.sin(roll),
            math.cos(pitch) * math.cos(roll))


def quaternion_normalized(q: Quaternion) -> Quaternion:
    length = math.sqrt(sum(value * value for value in q))
    return tuple(value / length for value in q)


def quaternion_product(a: Quaternion, b: Quaternion) -> Quaternion:
    w, x, y, z = a
    v, i, j, k = b
    return (w * v - x * i - y * j - z * k,
            w * i + x * v + y * k - z * j,
            w * j - x * k + y * v + z * i,
            w * k + x * j - y * i + z * v)


def shortest_rotation(a: Vector, b: Vector) -> Quaternion:
    """Unit quaternion mapping unit vector a to b, including opposite vectors."""
    dot = max(-1.0, min(1.0, sum(x * y for x, y in zip(a, b))))
    if dot < -1.0 + 1e-10:
        basis = tuple(float(i == min(range(3), key=lambda k: abs(a[k]))) for i in range(3))
        cross = (a[1] * basis[2] - a[2] * basis[1],
                 a[2] * basis[0] - a[0] * basis[2],
                 a[0] * basis[1] - a[1] * basis[0])
        return (0.0, *unit_vector(cross))
    cross = (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])
    return quaternion_normalized((1.0 + dot, *cross))


def quaternion_matrix(q: Quaternion) -> Matrix:
    w, x, y, z = q
    return ((1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)),
            (2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)),
            (2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)))


@dataclass(frozen=True, slots=True)
class TiltState:
    unit_g: Vector | None
    matrix: Matrix | None
    roll_deg: float | None
    pitch_deg: float | None
    tilt_deg: float | None
    magnitude_g: float
    quality: str  # waiting / gravity / dynamic / undefined
    roll_defined: bool = True


class TiltEstimator:
    """Filter acceleration vectors before converting them to angles.

    This avoids smoothing angles across the +180/-180 discontinuity. Large
    accelerations/free fall hold the last pose instead of producing a fake tilt.
    A plausible 1 g magnitude does not prove the absence of linear acceleration.
    The displayed pose uses the smallest compatible rotation between successive
    gravity directions, avoiding Euler branch flips. This is a continuity choice
    for an unobservable heading; it does not measure yaw or angular velocity.
    """

    def __init__(self, tau: float = 0.25):
        self.tau = tau
        self.reset()

    def reset(self):
        self.filtered: Vector | None = None
        self.last_t: float | None = None
        self.raw: Vector | None = None
        self.raw_magnitude = 0.0
        self.residual = 0.0
        self.held_roll = 0.0
        self.accepted = False
        self.pose_q: Quaternion | None = None
        self.pose_g: Vector | None = None

    def update(self, sample: Sample):
        raw = (sample.x, sample.y, sample.z)
        self.raw = raw
        self.raw_magnitude = norm(raw)
        restart = (sample.gap_before or self.last_t is None or
                   sample.t <= self.last_t or sample.t - self.last_t > 0.1)
        dt = sample.t - self.last_t if self.last_t is not None else 0.0
        self.last_t = sample.t
        self.accepted = all(math.isfinite(v) for v in raw) and 0.75 <= self.raw_magnitude <= 1.25
        if not self.accepted:
            # Do not feed strong linear acceleration or free fall into the tilt filter.
            # Keep the sample clock and last filtered value. The first valid sample
            # must resume smoothing rather than snap directly to a new raw angle.
            return
        if restart or self.filtered is None or self.tau <= 0:
            self.filtered = raw
        else:
            alpha = -math.expm1(-dt / self.tau)
            self.filtered = tuple(old + alpha * (new - old) for old, new in zip(self.filtered, raw))
        self.residual = norm(tuple(a - b for a, b in zip(raw, self.filtered)))
        self._update_pose()

    def _update_pose(self):
        if self.filtered is None or norm(self.filtered) < 0.25:
            return
        direction = unit_vector(self.filtered)
        if self.pose_q is None:
            x, y, z = direction
            roll = math.atan2(y, z) if math.hypot(y, z) > 1e-9 else 0.0
            pitch = math.atan2(-x, math.hypot(y, z))
            cr, sr = math.cos(roll / 2), math.sin(roll / 2)
            cp, sp = math.cos(pitch / 2), math.sin(pitch / 2)
            self.pose_q = (cp * cr, cp * sr, sp * cr, -sp * sr)
        else:
            # Right multiplication maps the new body gravity into the previous
            # body gravity, so the resulting pose still maps it to world +Z.
            delta = shortest_rotation(direction, self.pose_g)
            self.pose_q = quaternion_normalized(quaternion_product(self.pose_q, delta))
        self.pose_g = direction

    def snapshot(self) -> TiltState:
        if self.raw is None:
            return TiltState(None, None, None, None, None, 0.0, "waiting")
        direction = unit_vector(self.filtered) if self.filtered is not None else None
        undefined = self.raw_magnitude < 0.15 or direction is None or norm(self.filtered) < 0.25
        if direction is None:
            return TiltState(None, None, None, None, None, self.raw_magnitude,
                             "undefined" if undefined else "dynamic")
        x, y, z = direction
        roll_defined = math.hypot(y, z) >= 0.02
        if roll_defined:
            self.held_roll = math.atan2(y, z)
        pitch = math.atan2(-x, math.hypot(y, z))
        matrix = quaternion_matrix(self.pose_q) if self.pose_q is not None else None
        dynamic = not self.accepted or abs(self.raw_magnitude - 1.0) > 0.12 or self.residual > 0.18
        quality = "undefined" if undefined else ("dynamic" if dynamic else "gravity")
        return TiltState(direction, matrix,
                         math.degrees(self.held_roll) if roll_defined and not undefined else None,
                         math.degrees(pitch) if not undefined else None,
                         math.degrees(math.acos(max(-1.0, min(1.0, z)))) if not undefined else None,
                         self.raw_magnitude, quality, roll_defined)
