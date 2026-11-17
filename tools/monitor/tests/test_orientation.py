import math
import time
import unittest

from pc_monitor.orientation import (
    TiltEstimator, angle_between, gravity_for_tilt, rotation_matrix, transform,
    quaternion_matrix, shortest_rotation,
)
from pc_monitor.stream import CsvRecorder, DemoWorker, Mailbox, Sample


def sample(i, xyz, *, gap=False):
    return Sample(i, i / 800, 0, *xyz, gap_before=gap)


class TiltTests(unittest.TestCase):
    def assertVectorClose(self, actual, expected, places=7):
        for a, b in zip(actual, expected):
            self.assertAlmostEqual(a, b, places=places)

    def test_known_static_poses_and_axis_signs(self):
        # Expected angles are independently known from these elementary poses.
        cases = [((0, 0, 1), 0, 0, 0),
                 ((0, 0.5, math.sqrt(3) / 2), 30, 0, 30),
                 ((-0.5, 0, math.sqrt(3) / 2), 0, 30, 30),
                 ((0.5, 0, math.sqrt(3) / 2), 0, -30, 30),
                 ((0, 0, -1), 180, 0, 180)]
        for xyz, roll, pitch, tilt in cases:
            with self.subTest(xyz=xyz):
                estimator = TiltEstimator()
                estimator.update(sample(0, xyz))
                state = estimator.snapshot()
                self.assertEqual(state.quality, "gravity")
                self.assertAlmostEqual(state.roll_deg, roll)
                self.assertAlmostEqual(state.pitch_deg, pitch)
                self.assertAlmostEqual(state.tilt_deg, tilt)
                self.assertVectorClose(transform(state.matrix, state.unit_g), (0, 0, 1))

    def test_combined_pose_rotation_places_measured_gravity_vertically(self):
        for roll in (-175, -45, 0, 35, 150):
            for pitch in (-75, -20, 0, 50, 85):
                estimator = TiltEstimator()
                estimator.update(sample(0, gravity_for_tilt(math.radians(roll), math.radians(pitch))))
                state = estimator.snapshot()
                self.assertAlmostEqual(state.roll_deg, roll)
                self.assertAlmostEqual(state.pitch_deg, pitch)
                self.assertVectorClose(transform(state.matrix, state.unit_g), (0, 0, 1))

    def test_vertical_x_does_not_invent_a_roll_angle(self):
        estimator = TiltEstimator()
        estimator.update(sample(0, (1, 0, 0)))
        state = estimator.snapshot()
        self.assertFalse(state.roll_defined)
        self.assertIsNone(state.roll_deg)
        self.assertAlmostEqual(state.pitch_deg, -90)
        self.assertVectorClose(transform(state.matrix, state.unit_g), (0, 0, 1))

    def test_filter_does_not_interpolate_through_zero_at_angle_wrap(self):
        estimator = TiltEstimator()
        estimator.update(sample(0, gravity_for_tilt(math.radians(179), 0)))
        for i in range(1, 201):
            estimator.update(sample(i, gravity_for_tilt(math.radians(-179), 0)))
        self.assertGreater(abs(estimator.snapshot().roll_deg), 178)

    def test_filter_uses_elapsed_time_and_gap_resets_it(self):
        estimator = TiltEstimator(tau=0.25)
        estimator.update(sample(0, (0, 0, 1)))
        target = (0, 0.5, math.sqrt(3) / 2)
        for i in range(1, 801):
            estimator.update(sample(i, target))
        decay = math.exp(-1 / 0.25)
        self.assertVectorClose(estimator.filtered, (0, (1 - decay) * target[1],
                                                    decay + (1 - decay) * target[2]))
        estimator.update(sample(801, (0, -0.5, math.sqrt(3) / 2), gap=True))
        self.assertAlmostEqual(estimator.snapshot().roll_deg, -30)

    def test_freefall_and_strong_acceleration_hold_last_model(self):
        estimator = TiltEstimator()
        estimator.update(sample(0, (0, 0, 1)))
        initial_matrix = estimator.snapshot().matrix
        estimator.update(sample(1, (0, 0, 0)))
        self.assertEqual(estimator.snapshot().quality, "undefined")
        self.assertIsNone(estimator.snapshot().pitch_deg)
        self.assertEqual(estimator.snapshot().matrix, initial_matrix)
        estimator.update(sample(2, (3, 0, 0)))
        self.assertEqual(estimator.snapshot().quality, "dynamic")
        self.assertEqual(estimator.snapshot().matrix, initial_matrix)
        estimator.update(sample(3, (0, 0.5, math.sqrt(3) / 2)))
        self.assertGreater(estimator.snapshot().roll_deg, 0)
        self.assertLess(estimator.snapshot().roll_deg, 1)
        for i in range(4, 804):
            estimator.update(sample(i, (0, 0.5, math.sqrt(3) / 2)))
        self.assertGreater(estimator.snapshot().roll_deg, 29)
        self.assertLess(estimator.snapshot().roll_deg, 30)

    def test_model_continuity_through_vertical_x_and_full_pitch_turn(self):
        estimator = TiltEstimator(tau=0)
        previous = initial = None
        largest = 0
        for i in range(3601):
            estimator.update(sample(i, gravity_for_tilt(0, math.radians(i * 0.1))))
            state = estimator.snapshot()
            self.assertVectorClose(transform(state.matrix, state.unit_g), (0, 0, 1))
            if previous is not None:
                trace = sum(previous[r][c] * state.matrix[r][c] for r in range(3) for c in range(3))
                step = math.degrees(math.acos(max(-1, min(1, (trace - 1) / 2))))
                largest = max(largest, step)
            else:
                initial = state.matrix
            previous = state.matrix
        self.assertLess(largest, 0.101)
        for actual, expected in zip(previous, initial):
            self.assertVectorClose(actual, expected)

    def test_shortest_rotation_handles_exactly_opposite_gravity(self):
        for a in ((1, 0, 0), (0, 1, 0), (0, 0, 1)):
            b = tuple(-v for v in a)
            self.assertVectorClose(transform(quaternion_matrix(shortest_rotation(a, b)), a), b)

    def test_combined_motion_keeps_gravity_vertical_and_matrix_orthonormal(self):
        estimator = TiltEstimator(tau=0.08)
        for i in range(2000):
            roll = math.radians(70) * math.sin(i * 0.011)
            pitch = math.radians(85) * math.sin(i * 0.008)
            estimator.update(sample(i, gravity_for_tilt(roll, pitch)))
            state = estimator.snapshot()
            self.assertVectorClose(transform(state.matrix, state.unit_g), (0, 0, 1))
            for a in range(3):
                for b in range(3):
                    self.assertAlmostEqual(sum(x * y for x, y in zip(state.matrix[a], state.matrix[b])),
                                           1 if a == b else 0, places=7)

    def test_reference_delta_is_angle_between_gravity_directions(self):
        self.assertAlmostEqual(angle_between((0, 0, 1), (0, 0, 2)), 0)
        self.assertAlmostEqual(angle_between((0, 0, 1), (0, 1, 0)), 90)
        self.assertAlmostEqual(angle_between((0, 0, 1), (0, 0, -1)), 180)
        with self.assertRaises(ValueError):
            angle_between((0, 0, 0), (0, 0, 1))

    def test_world_yaw_rotations_are_unobservable_from_gravity(self):
        body_to_world = rotation_matrix(math.radians(25), math.radians(-30))
        for yaw in (0, 45, 90, 180):
            # Rz(yaw) leaves world vertical unchanged, so every such pose
            # produces the identical accelerometer vector R^T @ (0, 0, 1).
            c, s = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
            rz = ((c, -s, 0), (s, c, 0), (0, 0, 1))
            full = tuple(tuple(sum(rz[r][k] * body_to_world[k][col] for k in range(3))
                               for col in range(3)) for r in range(3))
            self.assertVectorClose(full[2], body_to_world[2])

    def test_demo_is_a_changing_gravity_vector_with_near_unit_magnitude(self):
        mailbox = Mailbox()
        worker = DemoWorker(mailbox, CsvRecorder())
        worker.start()
        try:
            time.sleep(0.25)
        finally:
            worker.stop_event.set()
            worker.join(timeout=1)
        values, _, stats = mailbox.take()
        self.assertGreater(stats.received, 50)
        for value in values:
            self.assertLess(abs(math.sqrt(value.x ** 2 + value.y ** 2 + value.z ** 2) - 1), 0.004)
        self.assertGreater(max(v.y for v in values) - min(v.y for v in values), 0.01)


if __name__ == "__main__":
    unittest.main()
