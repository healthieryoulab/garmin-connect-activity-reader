---
name: garmin-connect-activity-reader
description: Read and normalize one Garmin Connect activity through authenticated read-only service calls without relying on the map-based activity-detail page. Use when Codex needs an activity by ID, date, or latest match; needs heart-rate or power zones, splits, charts, weather, gear, cadence, power, elevation, training effect, or training load; or when the Garmin activity-detail UI is blank or fails while loading its map.
---

# Garmin Connect Activity Reader

## Goal

Read one Garmin activity through authenticated read-only calls. Use `scripts/read_garmin_activity.py` as the collector and normalizer. Do not scrape `/app/activity/<id>` or treat its rendered DOM as the source of record.

Read `references/data-contract.md` when field provenance, endpoint coverage, or completeness matters.

## Set up

Run setup once from this skill directory:

```bash
./scripts/bootstrap.sh
```

The bootstrap script creates a local `.venv` and installs pinned dependencies. It requires Python 3.12 and network access.

## Collect an activity

Use the local environment created by the bootstrap script:

```bash
.venv/bin/python scripts/read_garmin_activity.py \
  --latest --activity-type running \
  --output /private/tmp/garmin-latest-run.json
```

Select a known activity:

```bash
.venv/bin/python scripts/read_garmin_activity.py \
  --activity-id ACTIVITY_ID \
  --output /private/tmp/garmin-activity.json
```

Select the most recent matching activity on a date:

```bash
.venv/bin/python scripts/read_garmin_activity.py \
  --date YYYY-MM-DD --activity-type running --format markdown
```

## Authenticate privately

Use `~/.garminconnect` as the default local token store. On first use, run the collector in an interactive terminal so it can prompt locally for the Garmin email, password, and MFA code.

Never request a password or MFA code in chat, pass a password on the command line, print credentials, inspect token contents, or copy tokens into the skill directory. Treat `garmin_tokens.json` like a password. The collector restricts the token directory to mode `0700` and its token file to mode `0600`.

The collector uses the unofficial `python-garminconnect` client and Garmin's private web services. Those services can change without notice. Stop on CAPTCHA or bot challenges; do not attempt to bypass them.

## Verify completeness

Inspect `errors` and `coverage` before calling the result complete.

- Require `coverage.summary = true` for summary metrics such as maximum heart rate, training effect, and activity training load.
- Require `coverage.heart_rate_zones = true` for heart-rate-zone requests.
- Treat `coverage.<name> = true` as a successful fetch even when the valid payload is empty.
- Treat a null or absent value in a successful response as unavailable.
- Treat an entry in `errors` as an endpoint that was not obtained.
- Never reconstruct a missing Garmin-calculated training effect or training load.

`details`, `splits`, `typed_splits`, `split_summaries`, `power_zones`, `weather`, and `gear` are conditional coverage. Garmin may legitimately omit them for some activity types.

If `summary` fails, stop. If a requested conditional endpoint fails, preserve the usable responses and report the exact missing component.

## Handle failures

- Allow one interactive credential/MFA login when cached tokens are stale or absent.
- Stop and report HTTP 429 rate limiting. Do not retry in a loop.
- Stop on CAPTCHA or bot challenges. Use a user-supplied FIT export or screenshots as a fallback.
- Continue with the collector when the map-based detail page is blank; do not debug the map unless separately requested.

## Protect activity data

Default to JSON for full-fidelity collection and Markdown for a compact review. Output files are created with mode `0600`.

Keep route polyline collection disabled unless coordinates are explicitly required. Add `--include-polyline` only for that case. Even without a polyline, raw chart details can contain location samples, so keep all raw output local and store temporary artifacts outside the repository.

Preserve the activity ID and source date for provenance when extracting normalized metrics for another workflow.
