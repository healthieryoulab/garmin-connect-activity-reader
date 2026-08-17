# Garmin activity data contract

## Source model

The collector uses read-only methods from `python-garminconnect`. Garmin Connect's private service paths are implementation details and may change; keep them in the collector instead of scraping the activity page.

| Output component | Garmin service resource | Purpose |
| --- | --- | --- |
| `summary` | Activity summary | Identity, type, distance, timing, heart rate, training effect, load, cadence, power, elevation, and metadata |
| `details` | Activity details | Chart descriptors and sampled time-series metrics |
| `heart_rate_zones` | Heart-rate time in zones | Seconds, percentages, and boundaries for activity heart-rate zones |
| `power_zones` | Power time in zones | Activity power-zone distribution |
| `splits` | Activity splits | Laps and split metrics |
| `typed_splits` | Typed activity splits | Sport-specific split records |
| `split_summaries` | Split summaries | Aggregated split types |
| `weather` | Activity weather | Recorded or associated weather |
| `gear` | Activity gear | Associated shoes, bicycle, or other equipment |

## Normalized field provenance

`normalized.activity` is a convenience layer. `raw.summary` remains authoritative. Garmin may wrap metric keys under `summaryDTO`; the collector accepts wrapped and flat summary shapes.

| Normalized field | Common Garmin summary key |
| --- | --- |
| `average_heart_rate_bpm` | `averageHR` or `averageHeartRate` |
| `max_heart_rate_bpm` | `maxHR` or `maxHeartRate` |
| `aerobic_training_effect` | `trainingEffect` or `aerobicTrainingEffect` |
| `anaerobic_training_effect` | `anaerobicTrainingEffect` |
| `activity_training_load` | `activityTrainingLoad` |
| `training_effect_label` | `trainingEffectLabel` |
| `average_power_w` | `avgPower`, `averagePower`, or `avgWatts` |
| `max_power_w` | `maxPower` or `maxWatts` |
| `average_running_cadence_spm` | `averageRunningCadenceInStepsPerMinute` |
| `average_stride_length_m` | `avgStrideLength` or `averageStrideLength` |

Garmin commonly stores speed in metres per second, distance in metres, and duration in seconds. The collector derives kilometres and pace only from valid positive numbers.

## Heart-rate zones

`normalized.heart_rate_zones` accepts a list response or a list nested under `zones`, `heartRateZones`, or `hrTimeInZones`. It preserves every raw zone item and normalizes the zone number, seconds, duration, percentage, and available heart-rate boundaries.

If percentage is absent and activity duration is known, the collector derives it from `seconds / duration` and sets `percentage_derived = true`.

If an upper boundary is absent and the next zone's lower boundary is present, the collector derives the inclusive upper boundary as `next lower boundary - 1 bpm` and sets `high_boundary_derived = true`. It leaves the final upper boundary unavailable unless Garmin supplies it.

## Completeness rules

`coverage` records whether each endpoint returned successfully. A successful empty payload is different from a failed call.

For maximum heart rate, training effect, load, and heart-rate-zone requests:

1. Require `coverage.summary = true`.
2. Require `coverage.heart_rate_zones = true`.
3. Report Garmin-provided null values as unavailable, not zero.
4. Do not independently compute Garmin training effect or training load.
5. Preserve the activity ID, start time, and raw JSON for provenance.

## Dependency boundary

The skill pins the versions in `scripts/requirements.txt` that were used for its tests. `python-garminconnect` calls unofficial Garmin services, so authentication methods and response schemas can change. When updating dependencies, run the unit tests and then perform an opt-in live test against an account-owned activity before changing field mappings.
