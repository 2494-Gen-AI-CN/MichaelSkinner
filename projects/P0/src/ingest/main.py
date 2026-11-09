"""Run the configured files through cleaning, BigQuery loading, and logging."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import uuid4

from .clean import clean_source, read_source
from .config import load_config, source_fingerprint
from .load import BigQueryStore, should_skip


def process_source(settings, source, run_id, store=None, force=False):
    """Clean and optionally upload one source, then record its result."""
    log = {
        "run_id": run_id, "source": source["name"], "started_at": datetime.now(timezone.utc),
        "finished_at": None, "file_sha256": "", "fingerprint": "", "status": "failed",
        "rows_read": 0, "rows_loaded": 0, "rows_rejected": 0,
        "duplicates_removed": 0, "destination_etag": "", "error": "",
    }
    rejects = []
    try:
        # Skip only successful, unchanged sources. Missing tables must be loaded again.
        path = settings["root"] / source["path"]
        log["file_sha256"], log["fingerprint"] = source_fingerprint(path, source)
        skip = False
        if store is not None and not force:
            table = store.get_table(source["name"])
            skip = should_skip(store.last_load(source["name"]), log["fingerprint"], table)
        if skip:
            log["status"] = "skipped"
            log["destination_etag"] = table.etag
        else:
            # A dry run performs the same cleaning but has no BigQuery connection.
            raw = read_source(path, source)
            log["rows_read"] = len(raw)
            result = clean_source(raw, source)
            log["rows_rejected"] = len(result["rejects"])
            log["duplicates_removed"] = result["duplicates_removed"]
            for row in result["rejects"]:
                rejects.append(dict(row, run_id=run_id, source=source["name"],
                                    rejected_at=datetime.now(timezone.utc)))
            if store is None:
                log["status"] = "validated"
                log["rows_ready"] = len(result["clean"])
            else:
                store.append_rejects(rejects)
                table = store.replace_source(source, result["clean"])
                log["status"] = "loaded"
                log["rows_loaded"] = len(result["clean"])
                log["destination_etag"] = table.etag
    except Exception as error:
        # Keep processing other source files even if this one fails.
        log["error"] = str(error)

    log["finished_at"] = datetime.now(timezone.utc)
    if store is not None:
        try:
            store.append_log(log)
        except Exception as error:
            log["status"] = "failed"
            log["error"] += f" Unable to save load log: {error}"
    return log, rejects


def run_ingestion(settings, dry_run=False, force=False, store=None):
    """Process every source and save a local copy of the run results."""
    run_id = uuid4().hex
    if dry_run:
        store = None
    else:
        store = store or BigQueryStore(settings["bigquery"])
        store.prepare()

    logs = []
    rejects = []
    for source in settings["sources"]:
        log, source_rejects = process_source(settings, source, run_id, store, force)
        logs.append(log)
        rejects.extend(source_rejects)
        print(f"{source['name']}: {log['status']} | read={log['rows_read']:,} "
              f"clean={log.get('rows_ready', log['rows_loaded']):,} "
              f"rejected={log['rows_rejected']:,}", flush=True)
        if log["error"]:
            print(log["error"])

    # Local reports are useful for inspection and are excluded from Git.
    output = settings["root"] / "data" / "runs" / run_id
    output.mkdir(parents=True)
    (output / "load_log.json").write_text(json.dumps(logs, default=str, indent=2))
    (output / "rejects.json").write_text(json.dumps(rejects, default=str, indent=2, ensure_ascii=False))
    print(f"Local report: {output}")
    return logs


def main():
    """Read command options and report whether the ingestion succeeded."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/config.yaml", type=Path)
    parser.add_argument("--dry-run", action="store_true", help="Clean locally without uploading.")
    parser.add_argument("--force", action="store_true", help="Reload unchanged files too.")
    args = parser.parse_args()
    try:
        logs = run_ingestion(load_config(args.config), dry_run=args.dry_run, force=args.force)
        return int(any(log["status"] == "failed" for log in logs))
    except Exception as error:
        print(f"Ingestion failed: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
