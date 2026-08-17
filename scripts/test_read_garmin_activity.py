#!/usr/bin/env python3

import json
import io
import tempfile
import unittest
from argparse import Namespace
from contextlib import redirect_stderr
from pathlib import Path

import read_garmin_activity as reader
from garminconnect import GarminConnectTooManyRequestsError


SYNTHETIC_ACTIVITY_ID = "123456789"
SUMMARY = {
    "activityId": int(SYNTHETIC_ACTIVITY_ID),
    "activityName": "Morning Run",
    "activityTypeDTO": {"typeKey": "running"},
    "startTimeLocal": "2025-01-15 06:30:00",
    "distance": 10000.0,
    "duration": 4200.0,
    "elapsedDuration": 4210.0,
    "movingDuration": 4195.0,
    "averageSpeed": 2.380952,
    "averageHR": 128,
    "maxHR": 151,
    "trainingEffect": 2.7,
    "anaerobicTrainingEffect": 0.1,
    "activityTrainingLoad": 64,
    "trainingEffectLabel": "AEROBIC_BASE",
}

HR_ZONES = [
    {"zoneNumber": 1, "secsInZone": 300, "zoneLowBoundary": 90, "zoneHighBoundary": 110},
    {"zoneNumber": 2, "secsInZone": 3295, "zoneLowBoundary": 111, "zoneHighBoundary": 135},
    {"zoneNumber": 3, "secsInZone": 605, "zoneLowBoundary": 136, "zoneHighBoundary": 155},
]

WRAPPED_SUMMARY = {
    "activityId": int(SYNTHETIC_ACTIVITY_ID),
    "activityName": "Morning Run",
    "activityTypeDTO": {"typeKey": "running"},
    "summaryDTO": {
        "startTimeLocal": "2025-01-15T06:30:00.0",
        "distance": 10000.0,
        "duration": 4200.0,
        "averageHR": 128.0,
        "maxHR": 144.0,
        "trainingEffect": 3.1,
        "anaerobicTrainingEffect": 0.7,
        "activityTrainingLoad": 91.22,
    },
}

LOW_ONLY_HR_ZONES = [
    {"zoneNumber": 1, "secsInZone": 300, "zoneLowBoundary": 58},
    {"zoneNumber": 2, "secsInZone": 3295, "zoneLowBoundary": 128},
    {"zoneNumber": 3, "secsInZone": 605, "zoneLowBoundary": 141},
]


class FakeClient:
    def get_activity(self, activity_id):
        return dict(SUMMARY)

    def get_activity_details(self, activity_id, maxchart, maxpoly):
        return {"metricDescriptors": [], "activityDetailMetrics": []}

    def get_activity_hr_in_timezones(self, activity_id):
        return list(HR_ZONES)

    def get_activity_power_in_timezones(self, activity_id):
        return []

    def get_activity_splits(self, activity_id):
        return {"lapDTOs": []}

    def get_activity_typed_splits(self, activity_id):
        return {"splits": []}

    def get_activity_split_summaries(self, activity_id):
        return {"splitSummaries": []}

    def get_activity_weather(self, activity_id):
        raise RuntimeError("not available")

    def get_activity_gear(self, activity_id):
        return []

    def get_activities(self, start, limit, activitytype):
        return [
            {"activityId": 100, "startTimeLocal": "2025-01-14 06:30:00"},
            {"activityId": 101, "startTimeLocal": "2025-01-15 06:30:00"},
        ]


class RateLimitedClient(FakeClient):
    def get_activity_weather(self, activity_id):
        raise GarminConnectTooManyRequestsError("synthetic rate limit")


class ReaderTests(unittest.TestCase):
    def test_normalized_training_metrics(self):
        normalized = reader.normalize_summary(SUMMARY)
        self.assertEqual(normalized["max_heart_rate_bpm"], 151)
        self.assertEqual(normalized["aerobic_training_effect"], 2.7)
        self.assertEqual(normalized["anaerobic_training_effect"], 0.1)
        self.assertEqual(normalized["activity_training_load"], 64)
        self.assertEqual(normalized["distance_km"], 10.0)
        self.assertEqual(normalized["duration"], "1:10:00")

    def test_normalized_wrapped_summary_dto(self):
        normalized = reader.normalize_summary(WRAPPED_SUMMARY)
        self.assertEqual(normalized["average_heart_rate_bpm"], 128.0)
        self.assertEqual(normalized["max_heart_rate_bpm"], 144.0)
        self.assertEqual(normalized["aerobic_training_effect"], 3.1)
        self.assertEqual(normalized["anaerobic_training_effect"], 0.7)
        self.assertEqual(normalized["activity_training_load"], 91.22)

    def test_zones_derive_percentage(self):
        zones = reader.normalize_zones(HR_ZONES, 4200)
        self.assertEqual(zones[1]["zone"], 2)
        self.assertEqual(zones[1]["duration"], "54:55")
        self.assertTrue(zones[1]["percentage_derived"])
        self.assertAlmostEqual(zones[1]["percentage"], 78.45, places=2)

    def test_zones_derive_upper_boundary_from_next_zone(self):
        zones = reader.normalize_zones(LOW_ONLY_HR_ZONES, 4200)
        self.assertEqual(zones[0]["high_boundary_bpm"], 127)
        self.assertTrue(zones[0]["high_boundary_derived"])
        self.assertEqual(zones[1]["high_boundary_bpm"], 140)
        self.assertTrue(zones[1]["high_boundary_derived"])
        self.assertIsNone(zones[2]["high_boundary_bpm"])
        self.assertFalse(zones[2]["high_boundary_derived"])

    def test_collect_preserves_partial_failure(self):
        data = reader.collect_activity(FakeClient(), SYNTHETIC_ACTIVITY_ID)
        self.assertTrue(data["coverage"]["summary"])
        self.assertTrue(data["coverage"]["heart_rate_zones"])
        self.assertFalse(data["coverage"]["weather"])
        self.assertIn("weather", data["errors"])
        self.assertFalse(data["map_ui_used"])
        self.assertEqual(data["request_options"]["max_polyline_size"], 0)

    def test_collect_does_not_hide_rate_limits(self):
        with self.assertRaises(GarminConnectTooManyRequestsError):
            reader.collect_activity(RateLimitedClient(), SYNTHETIC_ACTIVITY_ID)

    def test_latest_selection_sorts_by_time(self):
        args = Namespace(
            activity_id=None,
            date=None,
            activity_type="running",
            search_limit=20,
        )
        self.assertEqual(reader.resolve_activity_id(FakeClient(), args), "101")

    def test_output_permissions_and_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "activity.json"
            reader.write_output(json.dumps({"ok": True}), str(path))
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(json.loads(path.read_text()), {"ok": True})

    def test_tokenstore_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            tokenstore = Path(directory) / "tokens"
            tokenstore.mkdir(mode=0o755)
            token_file = tokenstore / "garmin_tokens.json"
            token_file.write_text("{}")
            token_file.chmod(0o644)

            reader._secure_tokenstore(tokenstore)

            self.assertEqual(tokenstore.stat().st_mode & 0o777, 0o700)
            self.assertEqual(token_file.stat().st_mode & 0o777, 0o600)

    def test_argument_validation_rejects_invalid_limits(self):
        with redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                reader.parse_args(["--search-limit", "0"])
            with self.assertRaises(SystemExit):
                reader.parse_args(["--max-chart-size", "0"])


if __name__ == "__main__":
    unittest.main()
