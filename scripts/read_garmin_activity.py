#!/usr/bin/env python3
"""Collect one Garmin Connect activity without loading the map-based detail UI."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

try:
    from garminconnect import (
        Garmin,
        GarminConnectAuthenticationError,
        GarminConnectConnectionError,
        GarminConnectTooManyRequestsError,
    )
except ImportError as exc:  # pragma: no cover - exercised only before bootstrap
    raise SystemExit(
        "Missing garminconnect. Run scripts/bootstrap.sh, then use .venv/bin/python."
    ) from exc


SCHEMA_VERSION = 1
DEFAULT_TOKENSTORE = Path("~/.garminconnect").expanduser()


def nested(data: Any, *paths: str) -> Any:
    """Return the first non-null value found at a dotted path."""
    for path in paths:
        value = data
        found = True
        for part in path.split("."):
            if not isinstance(value, dict) or part not in value:
                found = False
                break
            value = value[part]
        if found and value is not None:
            return value
    return None


def seconds_to_duration(value: Any) -> str | None:
    if not isinstance(value, (int, float)) or value < 0:
        return None
    total = int(round(value))
    hours, remainder = divmod(total, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes}:{seconds:02d}"


def speed_to_pace(value: Any) -> str | None:
    if not isinstance(value, (int, float)) or value <= 0:
        return None
    return seconds_to_duration(1000.0 / float(value))


def normalize_summary(summary: dict[str, Any]) -> dict[str, Any]:
    # Garmin's activity endpoint commonly wraps metrics in summaryDTO while
    # keeping identity fields at the top level. Flatten that wrapper for the
    # convenience mapping below, with top-level values taking precedence.
    summary_dto = summary.get("summaryDTO")
    if isinstance(summary_dto, dict):
        summary = {**summary_dto, **summary}

    distance_m = nested(summary, "distance", "summaryDTO.distance")
    duration_s = nested(summary, "duration", "summaryDTO.duration")
    elapsed_s = nested(summary, "elapsedDuration", "summaryDTO.elapsedDuration")
    moving_s = nested(summary, "movingDuration", "summaryDTO.movingDuration")
    average_speed = nested(summary, "averageSpeed", "summaryDTO.averageSpeed")
    max_speed = nested(summary, "maxSpeed", "summaryDTO.maxSpeed")

    return {
        "activity_id": str(nested(summary, "activityId") or ""),
        "name": nested(summary, "activityName", "name"),
        "activity_type_key": nested(
            summary,
            "activityTypeDTO.typeKey",
            "activityType.typeKey",
            "typeKey",
        ),
        "start_time_local": nested(summary, "startTimeLocal", "summaryDTO.startTimeLocal"),
        "start_time_gmt": nested(summary, "startTimeGMT", "summaryDTO.startTimeGMT"),
        "distance_m": distance_m,
        "distance_km": round(float(distance_m) / 1000.0, 3)
        if isinstance(distance_m, (int, float))
        else None,
        "duration_seconds": duration_s,
        "duration": seconds_to_duration(duration_s),
        "moving_duration_seconds": moving_s,
        "moving_duration": seconds_to_duration(moving_s),
        "elapsed_duration_seconds": elapsed_s,
        "elapsed_duration": seconds_to_duration(elapsed_s),
        "average_speed_mps": average_speed,
        "average_pace_per_km": speed_to_pace(average_speed),
        "max_speed_mps": max_speed,
        "fastest_pace_per_km": speed_to_pace(max_speed),
        "calories_kcal": nested(summary, "calories", "activeCalories"),
        "average_heart_rate_bpm": nested(summary, "averageHR", "averageHeartRate"),
        "max_heart_rate_bpm": nested(summary, "maxHR", "maxHeartRate"),
        "min_heart_rate_bpm": nested(summary, "minHR", "minHeartRate"),
        "aerobic_training_effect": nested(
            summary, "trainingEffect", "aerobicTrainingEffect"
        ),
        "anaerobic_training_effect": nested(summary, "anaerobicTrainingEffect"),
        "activity_training_load": nested(summary, "activityTrainingLoad"),
        "training_effect_label": nested(summary, "trainingEffectLabel"),
        "aerobic_training_effect_message": nested(
            summary, "aerobicTrainingEffectMessage"
        ),
        "anaerobic_training_effect_message": nested(
            summary, "anaerobicTrainingEffectMessage"
        ),
        "average_power_w": nested(summary, "avgPower", "averagePower", "avgWatts"),
        "max_power_w": nested(summary, "maxPower", "maxWatts"),
        "normalized_power_w": nested(summary, "normPower", "normalizedPower"),
        "average_running_cadence_spm": nested(
            summary, "averageRunningCadenceInStepsPerMinute"
        ),
        "max_running_cadence_spm": nested(
            summary, "maxRunningCadenceInStepsPerMinute"
        ),
        "average_stride_length_m": nested(
            summary, "avgStrideLength", "averageStrideLength"
        ),
        "ground_contact_time_ms": nested(summary, "avgGroundContactTime"),
        "vertical_oscillation_cm": nested(summary, "avgVerticalOscillation"),
        "vertical_ratio_percent": nested(summary, "avgVerticalRatio"),
        "elevation_gain_m": nested(summary, "elevationGain"),
        "elevation_loss_m": nested(summary, "elevationLoss"),
        "min_elevation_m": nested(summary, "minElevation"),
        "max_elevation_m": nested(summary, "maxElevation"),
        "aerobic_exercise_time_seconds": nested(summary, "aerobicExerciseTime"),
        "anaerobic_exercise_time_seconds": nested(summary, "anaerobicExerciseTime"),
        "self_evaluation_feel": nested(summary, "selfEvaluation.feel"),
        "self_evaluation_effort": nested(summary, "selfEvaluation.effort"),
    }


def _zone_list(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("zones", "heartRateZones", "hrTimeInZones", "powerTimeInZones"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def normalize_zones(payload: Any, activity_duration: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for index, item in enumerate(_zone_list(payload), start=1):
        seconds = nested(item, "secsInZone", "seconds", "duration")
        percentage = nested(item, "percentage", "percent", "percentInZone")
        derived_percentage = False
        if (
            percentage is None
            and isinstance(seconds, (int, float))
            and isinstance(activity_duration, (int, float))
            and activity_duration > 0
        ):
            percentage = round(100.0 * float(seconds) / float(activity_duration), 2)
            derived_percentage = True
        result.append(
            {
                "zone": nested(item, "zoneNumber", "zone", "zoneIndex") or index,
                "seconds": seconds,
                "duration": seconds_to_duration(seconds),
                "percentage": percentage,
                "percentage_derived": derived_percentage,
                "low_boundary_bpm": nested(
                    item, "zoneLowBoundary", "lowBoundary", "minHeartRate"
                ),
                "high_boundary_bpm": nested(
                    item, "zoneHighBoundary", "highBoundary", "maxHeartRate"
                ),
                "high_boundary_derived": False,
                "raw": item,
            }
        )
    # Garmin's hrTimeInZones endpoint often supplies only each zone's lower
    # boundary. Heart rate is integer-valued, so the next zone's lower bound
    # determines the current zone's inclusive upper bound.
    for index in range(len(result) - 1):
        current = result[index]
        next_low = result[index + 1].get("low_boundary_bpm")
        if current.get("high_boundary_bpm") is None and isinstance(
            next_low, (int, float)
        ):
            current["high_boundary_bpm"] = next_low - 1
            current["high_boundary_derived"] = True
    return result


def _activities_list(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("activities", "activityList", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def resolve_activity_id(client: Any, args: argparse.Namespace) -> str:
    if args.activity_id:
        return str(args.activity_id)

    if args.date:
        activities = client.get_activities_by_date(
            args.date, args.date, activitytype=args.activity_type
        )
    else:
        activities = client.get_activities(
            start=0, limit=args.search_limit, activitytype=args.activity_type
        )

    candidates = _activities_list(activities)
    if not candidates:
        selector = args.date or "latest"
        suffix = f" of type {args.activity_type}" if args.activity_type else ""
        raise LookupError(f"No Garmin activity found for {selector}{suffix}")

    candidates.sort(
        key=lambda item: str(
            nested(item, "startTimeLocal", "startTimeGMT", "summaryDTO.startTimeLocal")
            or ""
        ),
        reverse=True,
    )
    activity_id = nested(candidates[0], "activityId")
    if activity_id is None:
        raise LookupError("Selected Garmin activity has no activityId")
    return str(activity_id)


def _safe_component(
    name: str,
    call: Callable[[], Any],
    raw: dict[str, Any],
    errors: dict[str, str],
    coverage: dict[str, bool],
) -> None:
    try:
        raw[name] = call()
        coverage[name] = True
    except (GarminConnectAuthenticationError, GarminConnectTooManyRequestsError):
        # Authentication failures and rate limits affect the session, not one
        # optional endpoint. Let the CLI stop and report them explicitly.
        raise
    except Exception as exc:  # endpoints legitimately vary by activity type
        raw[name] = None
        coverage[name] = False
        errors[name] = f"{type(exc).__name__}: {exc}"


def collect_activity(
    client: Any,
    activity_id: str,
    *,
    max_chart_size: int = 10000,
    max_polyline_size: int = 0,
) -> dict[str, Any]:
    raw: dict[str, Any] = {}
    errors: dict[str, str] = {}
    coverage: dict[str, bool] = {}

    summary = client.get_activity(activity_id)
    if not isinstance(summary, dict):
        raise GarminConnectConnectionError("Garmin returned a non-object activity summary")
    raw["summary"] = summary
    coverage["summary"] = True

    calls: list[tuple[str, Callable[[], Any]]] = [
        (
            "details",
            lambda: client.get_activity_details(
                activity_id, maxchart=max_chart_size, maxpoly=max_polyline_size
            ),
        ),
        ("heart_rate_zones", lambda: client.get_activity_hr_in_timezones(activity_id)),
        ("power_zones", lambda: client.get_activity_power_in_timezones(activity_id)),
        ("splits", lambda: client.get_activity_splits(activity_id)),
        ("typed_splits", lambda: client.get_activity_typed_splits(activity_id)),
        (
            "split_summaries",
            lambda: client.get_activity_split_summaries(activity_id),
        ),
        ("weather", lambda: client.get_activity_weather(activity_id)),
        ("gear", lambda: client.get_activity_gear(activity_id)),
    ]

    activity_type = nested(
        summary, "activityTypeDTO.typeKey", "activityType.typeKey", "typeKey"
    )
    if activity_type == "strength_training":
        calls.append(
            ("exercise_sets", lambda: client.get_activity_exercise_sets(activity_id))
        )

    for name, call in calls:
        _safe_component(name, call, raw, errors, coverage)

    normalized_activity = normalize_summary(summary)
    duration = normalized_activity.get("duration_seconds")
    normalized = {
        "activity": normalized_activity,
        "heart_rate_zones": normalize_zones(raw.get("heart_rate_zones"), duration),
        "power_zones": normalize_zones(raw.get("power_zones"), duration),
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "activity_id": activity_id,
        "source": "Garmin Connect read-only services via python-garminconnect",
        "map_ui_used": False,
        "request_options": {
            "max_chart_size": max_chart_size,
            "max_polyline_size": max_polyline_size,
        },
        "coverage": coverage,
        "errors": errors,
        "normalized": normalized,
        "raw": raw,
    }


def _secure_tokenstore(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.chmod(0o700)
    token_file = path / "garmin_tokens.json"
    if token_file.exists():
        token_file.chmod(0o600)


def build_client(args: argparse.Namespace) -> Any:
    tokenstore = Path(args.tokenstore).expanduser()
    _secure_tokenstore(tokenstore)

    cached_client = Garmin(is_cn=args.cn)
    try:
        cached_client.login(str(tokenstore))
        _secure_tokenstore(tokenstore)
        return cached_client
    except GarminConnectAuthenticationError:
        if args.non_interactive or not sys.stdin.isatty():
            raise GarminConnectAuthenticationError(
                "No usable Garmin token. Run once in an interactive terminal."
            )

    email = args.email or os.getenv("GARMIN_EMAIL") or input("Garmin email: ").strip()
    if not email:
        raise GarminConnectAuthenticationError("Garmin email is required")
    password = getpass.getpass("Garmin password: ")
    client = Garmin(
        email,
        password,
        is_cn=args.cn,
        prompt_mfa=lambda: getpass.getpass("Garmin MFA code: "),
    )
    client.login(str(tokenstore))
    _secure_tokenstore(tokenstore)
    return client


def render_markdown(data: dict[str, Any]) -> str:
    activity = data["normalized"]["activity"]
    lines = [
        f"# Garmin activity {data['activity_id']}",
        "",
        f"- Name: {activity.get('name') or 'unavailable'}",
        f"- Type: {activity.get('activity_type_key') or 'unavailable'}",
        f"- Start: {activity.get('start_time_local') or 'unavailable'}",
        f"- Distance: {activity.get('distance_km') if activity.get('distance_km') is not None else 'unavailable'} km",
        f"- Duration: {activity.get('duration') or 'unavailable'}",
        f"- Average / max HR: {activity.get('average_heart_rate_bpm') or 'unavailable'} / {activity.get('max_heart_rate_bpm') or 'unavailable'} bpm",
        f"- Aerobic / anaerobic training effect: {activity.get('aerobic_training_effect') if activity.get('aerobic_training_effect') is not None else 'unavailable'} / {activity.get('anaerobic_training_effect') if activity.get('anaerobic_training_effect') is not None else 'unavailable'}",
        f"- Activity training load: {activity.get('activity_training_load') if activity.get('activity_training_load') is not None else 'unavailable'}",
        "",
        "## Heart-rate zones",
        "",
        "| Zone | Duration | Percent | Boundaries |",
        "| --- | ---: | ---: | --- |",
    ]
    zones = data["normalized"]["heart_rate_zones"]
    if zones:
        for zone in zones:
            low = zone.get("low_boundary_bpm")
            high = zone.get("high_boundary_bpm")
            boundaries = f"{low if low is not None else '?'}-{high if high is not None else '?'} bpm"
            percentage = zone.get("percentage")
            marker = " (derived)" if zone.get("percentage_derived") else ""
            lines.append(
                f"| {zone.get('zone')} | {zone.get('duration') or 'unavailable'} | "
                f"{str(percentage) + '%' if percentage is not None else 'unavailable'}{marker} | {boundaries} |"
            )
    else:
        lines.append("| unavailable | unavailable | unavailable | unavailable |")

    lines.extend(["", "## Coverage", ""])
    for name, ok in data["coverage"].items():
        lines.append(f"- {name}: {'ok' if ok else 'missing'}")
    if data["errors"]:
        lines.extend(["", "## Endpoint errors", ""])
        for name, error in data["errors"].items():
            lines.append(f"- {name}: {error}")
    return "\n".join(lines) + "\n"


def write_output(text: str, output: str) -> None:
    if output == "-":
        sys.stdout.write(text)
        return
    path = Path(output).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
        stat.S_IRUSR | stat.S_IWUSR,
    )
    with os.fdopen(file_descriptor, "w", encoding="utf-8") as handle:
        handle.write(text)
    path.chmod(0o600)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read one Garmin activity without loading the map UI."
    )
    selector = parser.add_mutually_exclusive_group()
    selector.add_argument("--activity-id", help="Exact Garmin activity ID")
    selector.add_argument("--date", help="Local activity date in YYYY-MM-DD")
    selector.add_argument(
        "--latest", action="store_true", help="Read the most recent matching activity"
    )
    parser.add_argument(
        "--activity-type",
        help="Garmin parent activity type, for example running or cycling",
    )
    parser.add_argument(
        "--search-limit", type=int, default=20, help="Maximum recent activities to inspect"
    )
    parser.add_argument(
        "--tokenstore", default=str(DEFAULT_TOKENSTORE), help="Local token directory"
    )
    parser.add_argument("--email", help="Garmin email; password is always prompted locally")
    parser.add_argument("--cn", action="store_true", help="Use Garmin China services")
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Fail instead of prompting if cached tokens cannot authenticate",
    )
    parser.add_argument(
        "--max-chart-size", type=int, default=10000, help="Maximum chart samples"
    )
    parser.add_argument(
        "--include-polyline",
        action="store_true",
        help="Request route polyline coordinates; disabled by default",
    )
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    parser.add_argument("--output", default="-", help="Output path or - for stdout")
    args = parser.parse_args(argv)
    if args.search_limit < 1 or args.search_limit > 100:
        parser.error("--search-limit must be between 1 and 100")
    if args.max_chart_size < 1:
        parser.error("--max-chart-size must be positive")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        client = build_client(args)
        activity_id = resolve_activity_id(client, args)
        data = collect_activity(
            client,
            activity_id,
            max_chart_size=args.max_chart_size,
            max_polyline_size=4000 if args.include_polyline else 0,
        )
        if args.format == "json":
            text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
        else:
            text = render_markdown(data)
        write_output(text, args.output)
        if args.output != "-":
            print(
                f"Wrote Garmin activity {activity_id} to "
                f"{Path(args.output).expanduser()}",
                file=sys.stderr,
            )
        return 0
    except GarminConnectTooManyRequestsError as exc:
        print(f"Garmin rate limited the request: {exc}", file=sys.stderr)
        return 3
    except GarminConnectAuthenticationError as exc:
        print(f"Garmin authentication failed: {exc}", file=sys.stderr)
        return 2
    except (GarminConnectConnectionError, OSError) as exc:
        print(f"Garmin connection or output failed: {exc}", file=sys.stderr)
        return 4
    except (LookupError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 5


if __name__ == "__main__":
    raise SystemExit(main())
