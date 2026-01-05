#!/usr/bin/env python3
"""
json_to_csv.py

Convert JSON to CSV.
- Works with:
  1) a list of objects:          [{...}, {...}]
  2) an object with a list key:  {"Report_Entry": [{...}, {...}]}
  3) nested objects (flattened to dot keys)
  4) lists inside fields (joined with ';' by default)

Usage:
  python3 json_to_csv.py input.json output.csv
  python3 json_to_csv.py input.json output.csv --records-key Report_Entry
  python3 json_to_csv.py input.json output.csv --delimiter "," --list-sep ";"
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union


Json = Union[Dict[str, Any], List[Any]]


def flatten(obj: Any, parent_key: str = "", sep: str = ".") -> Dict[str, Any]:
    """
    Flatten nested dicts into a single dict with dotted keys.
    Lists are kept as lists (handled later), unless they contain dicts,
    in which case we JSON-serialize them to preserve structure.
    """
    items: List[Tuple[str, Any]] = []

    if isinstance(obj, dict):
        for k, v in obj.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else str(k)
            items.extend(flatten(v, new_key, sep=sep).items())
        return dict(items)

    if isinstance(obj, list):
        # If list contains dicts/lists, keep it structured as JSON string to avoid column explosion
        if any(isinstance(x, (dict, list)) for x in obj):
            return {parent_key: json.dumps(obj, ensure_ascii=False)}
        return {parent_key: obj}

    return {parent_key: obj}


def find_records(data: Json, records_key: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Decide which list of dicts to treat as CSV rows.
    """
    if isinstance(data, list):
        if all(isinstance(x, dict) for x in data):
            return data  # type: ignore[return-value]
        raise ValueError("Top-level JSON is a list but does not contain objects (dicts).")

    if not isinstance(data, dict):
        raise ValueError("Top-level JSON must be an object or an array.")

    if records_key:
        val = data.get(records_key)
        if isinstance(val, list) and all(isinstance(x, dict) for x in val):
            return val  # type: ignore[return-value]
        raise ValueError(f'Key "{records_key}" was provided but is not a list of objects.')

    # Auto-detect: find first list-of-dicts value
    for k, v in data.items():
        if isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
            return v  # type: ignore[return-value]

    # If dict itself is a single record, write a 1-row CSV
    return [data]


def normalize_value(v: Any, list_sep: str = ";") -> Any:
    """
    Convert values to CSV-friendly forms.
    """
    if isinstance(v, list):
        return list_sep.join("" if x is None else str(x) for x in v)
    if isinstance(v, (dict, tuple, set)):
        return json.dumps(v, ensure_ascii=False)
    return v


def main() -> None:
    ap = argparse.ArgumentParser(description="Convert JSON to CSV (with flattening).")
    ap.add_argument("input_json", type=Path)
    ap.add_argument("output_csv", type=Path)
    ap.add_argument("--records-key", default=None, help="Key that contains the list of records (rows).")
    ap.add_argument("--delimiter", default=",", help="CSV delimiter (default: ,).")
    ap.add_argument("--list-sep", default=";", help="Separator for lists in fields (default: ;).")
    ap.add_argument("--flatten-sep", default=".", help="Separator for flattened keys (default: .).")
    ap.add_argument("--sort-alphabetically", action="store_true", help="Sort CSV columns alphabetically (default: preserve JSON order).")
    args = ap.parse_args()

    raw = args.input_json.read_text(encoding="utf-8")
    
    records: List[Dict[str, Any]] = []
    decoder = json.JSONDecoder()
    pos = 0
    raw_len = len(raw)

    while pos < raw_len:
        # Skip leading whitespace
        while pos < raw_len and raw[pos].isspace():
            pos += 1
        if pos >= raw_len:
            break

        try:
            obj, next_pos = decoder.raw_decode(raw, pos)
            records.extend(find_records(obj, records_key=args.records_key))
            pos = next_pos
        except json.JSONDecodeError as e:
            if not records:
                # If we haven't found any records yet, the file might just be invalid JSON
                raise e
            # Otherwise, maybe there is just trailing junk
            break

    flat_rows: List[Dict[str, Any]] = []
    fieldnames: List[str] = []

    # Flatten and collect all columns across all rows (preserving insertion order)
    fieldnames: List[str] = []
    seen_cols: set = set()
    for rec in records:
        flat = flatten(rec, sep=args.flatten_sep)
        flat_rows.append(flat)
        for key in flat.keys():
            if key not in seen_cols:
                seen_cols.add(key)
                fieldnames.append(key)

    if args.sort_alphabetically:
        fieldnames = sorted(fieldnames)

    with args.output_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=args.delimiter, extrasaction="ignore")
        writer.writeheader()
        for row in flat_rows:
            out_row = {k: normalize_value(row.get(k), list_sep=args.list_sep) for k in fieldnames}
            writer.writerow(out_row)

    print(f"Wrote {len(records)} row(s) to {args.output_csv}")


if __name__ == "__main__":
    main()