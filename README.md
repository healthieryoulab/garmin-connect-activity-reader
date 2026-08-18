# Garmin Connect Activity Reader

An unofficial Codex Skill that reads and normalizes Garmin Connect activity data without relying on the map-based activity-detail page.

[Latest release: v1.0.0](https://github.com/healthieryoulab/garmin-connect-activity-reader/releases/tag/v1.0.0) · [MIT License](LICENSE)

## Why this exists

Garmin's activity-detail page can become blank or unusable when its map component fails, even while the underlying activity services remain available. This Skill retrieves those resources independently, so Codex can still work with heart-rate zones, training effect, training load, splits, charts, weather, gear, and other recorded metrics.

It does not scrape the rendered activity page or use its DOM as the source of record.

## What it retrieves

- Activity summary, timing, distance, pace, heart rate, training effect, and training load
- Heart-rate and power-zone distributions
- Chart descriptors and sampled activity details
- Splits, typed splits, and split summaries
- Weather and associated gear when Garmin provides them
- Running dynamics, cadence, power, and elevation fields when available
- Exercise sets for supported strength-training activities

The collector preserves Garmin's raw responses for provenance and adds a normalized convenience layer. It never invents missing Garmin-calculated metrics.

## Privacy defaults

- Route polyline collection is disabled by default with `maxPolylineSize=0`.
- Garmin tokens stay in `~/.garminconnect`; the directory uses mode `0700` and the token file uses mode `0600`.
- Output files are created with mode `0600`.
- Passwords and MFA codes are prompted locally and should never be pasted into chat or passed on the command line.
- `coverage` and `errors` distinguish unavailable data from failed endpoint requests.

Raw activity details may still contain location samples even when route polyline collection is disabled. Keep raw outputs local and outside the repository.

## Requirements

- Python 3.12
- A Garmin Connect account
- A macOS or Linux shell environment
- Network access for dependency installation and Garmin Connect requests

This project uses the unofficial [`python-garminconnect`](https://github.com/cyberjunky/python-garminconnect) client and Garmin's private web services. Those services can change without notice.

## Install as a Codex Skill

Ask Codex to install the tagged release:

```text
Install the Skill from healthieryoulab/garmin-connect-activity-reader using
ref v1.0.0, path ., and the name garmin-connect-activity-reader.
```

Or install it manually:

```bash
git clone --branch v1.0.0 --depth 1 \
  https://github.com/healthieryoulab/garmin-connect-activity-reader.git \
  ~/.codex/skills/garmin-connect-activity-reader

cd ~/.codex/skills/garmin-connect-activity-reader
./scripts/bootstrap.sh
```

After installation, invoke it in Codex as `$garmin-connect-activity-reader`.

## Quick start

Set up the local Python environment once:

```bash
./scripts/bootstrap.sh
```

Read the latest running activity:

```bash
.venv/bin/python scripts/read_garmin_activity.py \
  --latest --activity-type running \
  --output /tmp/garmin-latest-run.json
```

Read a known activity:

```bash
.venv/bin/python scripts/read_garmin_activity.py \
  --activity-id ACTIVITY_ID \
  --output /tmp/garmin-activity.json
```

Read the most recent matching activity on a date and render a compact Markdown report:

```bash
.venv/bin/python scripts/read_garmin_activity.py \
  --date YYYY-MM-DD --activity-type running --format markdown
```

On first use, run the collector in an interactive terminal. It will try cached tokens first and otherwise prompt locally for Garmin credentials and MFA.

## Check completeness

Always inspect these top-level fields before treating a result as complete:

- `coverage.summary` must be `true` for summary metrics.
- `coverage.heart_rate_zones` must be `true` for heart-rate-zone analysis.
- `errors` identifies endpoints that could not be obtained.
- A null value in a successfully fetched response means Garmin did not provide that metric.

See [`references/data-contract.md`](references/data-contract.md) for normalized-field provenance and completeness rules.

## Test

Run the offline test suite:

```bash
./scripts/test.sh
```

The tests use synthetic fixtures and do not contact Garmin or read account tokens.

## Disclaimer

This project is unofficial and is not affiliated with or endorsed by Garmin. Use it only with accounts and activity data you are authorized to access. Garmin authentication flows and private service schemas may change at any time.

## License

[MIT](LICENSE)
