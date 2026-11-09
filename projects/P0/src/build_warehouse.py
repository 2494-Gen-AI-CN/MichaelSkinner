"""Run the warehouse SQL files in order and check the resulting tables."""

import argparse
import csv
from pathlib import Path

from google.cloud import bigquery

from .ingest.config import load_config


def render_sql(sql, cloud):
    """Replace project and dataset placeholders with the local settings."""
    replacements = {"${PROJECT}": cloud["project"], "${STAGING}": cloud["staging_dataset"],
                    "${WAREHOUSE}": cloud["warehouse_dataset"]}
    for placeholder, value in replacements.items():
        sql = sql.replace(placeholder, value)
    return sql


def render_files(settings):
    """Save SQL copies that can be opened directly in the BigQuery console."""
    paths = sorted((settings["root"] / "sql/warehouse").glob("*.sql"))
    if not paths or paths[-1].name != "09_checks.sql":
        raise ValueError("Warehouse SQL files must end with 09_checks.sql.")
    output = settings["root"] / "data/rendered_sql"
    output.mkdir(parents=True, exist_ok=True)
    rendered = []
    for path in paths:
        sql = render_sql(path.read_text(), settings["bigquery"])
        (output / path.name).write_text(sql)
        rendered.append((path.name, sql))
    return rendered


def run_build(settings, render_only=False, client=None):
    """Build the tables and stop if a warehouse validation check fails."""
    rendered = render_files(settings)
    if render_only:
        print("SQL saved in data/rendered_sql. No BigQuery requests were made.")
        return []

    cloud = settings["bigquery"]
    client = client or bigquery.Client(project=cloud["project"], location=cloud["location"])
    # BigQuery cannot join tables across different dataset locations.
    for name in (cloud["staging_dataset"], cloud["warehouse_dataset"]):
        dataset = client.get_dataset(f"{cloud['project']}.{name}")
        if dataset.location.upper() != cloud["location"].upper():
            raise ValueError(f"Dataset {name} must be in {cloud['location']}.")

    # Numbered filenames keep dependencies clear: dimensions are built before the fact.
    checks = []
    for name, sql in rendered:
        print(f"Running {name} ...", flush=True)
        result = client.query(sql, location=cloud["location"]).result()
        if name == "09_checks.sql":
            checks = [dict(row) for row in result]

    # Keep one local check report. SQL checks return their names and pass/fail results.
    report = settings["root"] / "data/warehouse_checks.csv"
    with report.open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["check_name", "observed", "expected", "passed"])
        writer.writeheader()
        writer.writerows(checks)
    failed = [row["check_name"] for row in checks if not row["passed"]]
    if not checks or failed:
        raise RuntimeError("Warehouse checks failed: " + ", ".join(failed))
    print(f"All {len(checks)} warehouse checks passed.")
    return checks


def main():
    """Read the command options and return a failure status if the build fails."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default="config/config.yaml")
    parser.add_argument("--render-only", action="store_true", help="Save SQL without running it.")
    args = parser.parse_args()
    try:
        run_build(load_config(args.config), render_only=args.render_only)
        return 0
    except Exception as error:
        print(f"Warehouse build failed: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
