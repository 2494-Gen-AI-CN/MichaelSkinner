"""Read the YAML configuration and calculate fingerprints for safe reruns."""

import hashlib
import json
import os
from pathlib import Path
import re

from dotenv import load_dotenv
import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]
# Increase this after changing cleaning behavior so unchanged files are reprocessed.
CLEANING_VERSION = "2"


def load_config(path):
    """Load local settings and check the source names, schemas, and keys."""
    # The real project ID belongs in the ignored .env file, not in shared code.
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    with open(path, encoding="utf-8") as file:
        settings = yaml.safe_load(file)
    cloud = settings["bigquery"]
    cloud["project"] = os.path.expandvars(cloud["project"])
    if not re.fullmatch(r"[a-z][a-z0-9-]{4,61}[a-z0-9]", cloud["project"]):
        raise ValueError("Set GCP_PROJECT to your Google Cloud project ID.")
    for field in ("staging_dataset", "warehouse_dataset"):
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", cloud[field]):
            raise ValueError(f"Invalid dataset name: {cloud[field]}")
    cloud.setdefault("location", "US")

    # These checks catch configuration mistakes before any files are uploaded.
    names = {"rejects", "load_log"}
    for source in settings["sources"]:
        name = source["name"]
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) or name in names:
            raise ValueError(f"Invalid, duplicate, or reserved source name: {name}")
        names.add(name)
        if source["format"] not in ("csv", "json"):
            raise ValueError(f"Unsupported format for {name}")
        if not source["key"] or not set(source["key"]).issubset(source["schema"]):
            raise ValueError(f"Source keys must appear in the schema: {name}")
        for kind in source["schema"].values():
            if kind not in ("string", "int", "float", "numeric", "datetime", "timestamp"):
                raise ValueError(f"Unsupported type for {name}: {kind}")
    settings["root"] = PROJECT_ROOT
    return settings


def source_fingerprint(path, source):
    """Identify file contents and cleaning settings so unchanged inputs can be skipped."""
    file_hash = hashlib.sha256()
    with open(path, "rb") as file:
        chunk = file.read(1024 * 1024)
        while chunk:
            file_hash.update(chunk)
            chunk = file.read(1024 * 1024)
    file_hash = file_hash.hexdigest()
    settings_text = json.dumps(source, sort_keys=True, separators=(",", ":"))
    fingerprint = hashlib.sha256(f"{CLEANING_VERSION}:{file_hash}:{settings_text}".encode()).hexdigest()
    return file_hash, fingerprint
