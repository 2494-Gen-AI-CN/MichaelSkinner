"""Read source files, clean their values, and separate valid rows from rejects."""

import json

import pandas as pd


def read_source(path, source):
    """Read a configured CSV or JSON file without changing string identifiers."""
    if source["format"] == "csv":
        return pd.read_csv(path, dtype="string", keep_default_na=False, encoding="utf-8-sig")
    with open(path, encoding="utf-8-sig") as file:
        return pd.DataFrame(json.load(file), dtype="string")


def convert_column(values, kind, source):
    """Convert a column to its configured type and leave invalid values empty."""
    if kind == "string":
        return values
    if kind in ("datetime", "timestamp"):
        return pd.to_datetime(
            values, format=source.get("datetime_format", "%Y-%m-%d %H:%M:%S"),
            errors="coerce", utc=(kind == "timestamp"),
        )

    # pandas converts invalid numeric text to a missing value, which we reject below.
    numbers = pd.to_numeric(values, errors="coerce")
    numbers = numbers.replace([float("inf"), float("-inf")], pd.NA)
    if kind == "int":
        whole_numbers = numbers.mod(1).eq(0)
        in_range = numbers.ge(-(2**63)) & numbers.lt(2**63)
        return numbers.where(whole_numbers & in_range).astype("Int64")
    return numbers.astype("Float64")


def add_reason(reasons, invalid, message):
    """Record the first failed check for each invalid row."""
    first_failure = invalid.fillna(False) & reasons.eq("")
    reasons.loc[first_failure] = message


def clean_source(raw, source):
    """Validate rows using the source settings and return clean data and reject counts."""
    raw = raw.reset_index(drop=True).astype("string")
    schema = source["schema"]
    missing = set(schema) - set(raw.columns)
    if missing:
        raise ValueError("Missing columns: " + ", ".join(sorted(missing)))

    clean = raw[list(schema)].copy()
    reasons = pd.Series("", index=raw.index, dtype="string")
    required = set(source["key"] + source.get("required", []))

    # First trim text and convert columns. Optional blank values can remain missing.
    for column, kind in schema.items():
        values = clean[column].str.strip().replace("", pd.NA)
        if column in required:
            add_reason(reasons, values.isna(), f"Missing required field: {column}")
        converted = convert_column(values, kind, source)
        add_reason(reasons, values.notna() & converted.isna(), f"Invalid {kind}: {column}")
        operation = source.get("normalize", {}).get(column)
        if operation == "lower":
            converted = converted.str.lower()
        elif operation == "upper":
            converted = converted.str.upper()
        clean[column] = converted

    # Then apply the business rules listed in YAML, such as score and price limits.
    for column, rules in source.get("rules", {}).items():
        values = clean[column]
        if "min" in rules:
            add_reason(reasons, values < rules["min"], f"{column} below {rules['min']}")
        if "max" in rules:
            add_reason(reasons, values > rules["max"], f"{column} above {rules['max']}")
        if "min_exclusive" in rules:
            add_reason(reasons, values <= rules["min_exclusive"], f"{column} must exceed {rules['min_exclusive']}")
        if "allowed" in rules:
            add_reason(reasons, values.notna() & ~values.isin(rules["allowed"]), f"Unknown value: {column}")
        if "required_when" in rules:
            condition = rules["required_when"]
            applies = clean[condition["column"]].eq(condition["equals"])
            add_reason(reasons, applies & values.isna(), f"Required for {condition['equals']}: {column}")
        if "not_before" in rules:
            other = rules["not_before"]
            add_reason(reasons, values < clean[other], f"{column} before {other}")

    # Remove identical clean rows. If the same key has different values, reject both.
    valid = clean.loc[reasons.eq("")]
    duplicates = valid.duplicated(keep="first")
    unique = valid.loc[~duplicates]
    conflicts = unique.duplicated(subset=source["key"], keep=False)
    reasons.loc[unique.index[conflicts]] = "Conflicting records for source key"
    accepted = unique.loc[~conflicts].reset_index(drop=True)

    # Save the original row, not its converted values, so the problem can be inspected.
    rejects = []
    for index in reasons.index[reasons.ne("")]:
        record = raw.loc[index].fillna("").to_dict()
        rejects.append({
            "row_number": int(index) + 2,
            "reason": reasons.loc[index],
            "raw_record": json.dumps(record, ensure_ascii=False),
        })
    return {"clean": accepted, "rejects": rejects, "duplicates_removed": int(duplicates.sum())}
