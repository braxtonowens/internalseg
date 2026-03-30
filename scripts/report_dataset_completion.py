#!/usr/bin/env python3

import argparse
import csv
import json
import sys
from pathlib import Path

from copick_project_common import load_json, object_names_from_copick_config, run_object_statuses


def find_runs(static_root: Path) -> list[str]:
    return sorted(path.name for path in (static_root / "ExperimentRuns").iterdir() if path.is_dir())


def build_report(project_config_path: Path) -> dict:
    project_config = load_json(project_config_path)
    copick_config_path = Path(project_config["config_path"]).expanduser()
    static_root = Path(project_config["static_root"]).expanduser()
    overlay_root = Path(project_config["overlay_root"]).expanduser()
    object_names = object_names_from_copick_config(copick_config_path)
    runs = find_runs(static_root)

    run_records = []
    segmented = 0
    absent = 0
    missing = 0
    missing_pairs = []

    for run_name in runs:
        statuses = run_object_statuses(overlay_root, run_name, object_names)
        row = {"run_name": run_name, "objects": {}}
        for object_name in object_names:
            status = statuses[object_name]["status"]
            row["objects"][object_name] = status
            if status == "segmented":
                segmented += 1
            elif status == "absent":
                absent += 1
            else:
                missing += 1
                missing_pairs.append({"run_name": run_name, "object_name": object_name})
        run_records.append(row)

    total_cells = len(runs) * len(object_names)
    completed_cells = segmented + absent
    return {
        "project_config": str(project_config_path),
        "run_count": len(runs),
        "object_count": len(object_names),
        "total_cells": total_cells,
        "completed_cells": completed_cells,
        "completion_fraction": (completed_cells / total_cells) if total_cells else 0.0,
        "segmented": segmented,
        "absent": absent,
        "missing": missing,
        "object_names": object_names,
        "runs": run_records,
        "missing_pairs": missing_pairs,
    }


def print_report(report: dict) -> None:
    print(f"runs: {report['run_count']}")
    print(f"objects: {report['object_count']}")
    print(f"completed cells: {report['completed_cells']}/{report['total_cells']} ({report['completion_fraction'] * 100:.1f}%)")
    print(f"segmented: {report['segmented']}")
    print(f"absent: {report['absent']}")
    print(f"missing: {report['missing']}")
    for run in report["runs"]:
        missing_objects = [name for name, status in run["objects"].items() if status == "missing"]
        if missing_objects:
            print(f"{run['run_name']}: missing {', '.join(missing_objects)}")
        else:
            print(f"{run['run_name']}: complete")


def write_csv(report: dict, path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["run_name", *report["object_names"]])
        for run in report["runs"]:
            writer.writerow([run["run_name"], *[run["objects"][name] for name in report["object_names"]]])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Report per-run, per-object dataset completion from a copick project overlay.")
    parser.add_argument("--project-config", default=str(Path.cwd() / "project_config.json"), help="Path to project settings JSON.")
    parser.add_argument("--json", dest="json_output", default=None, help="Optional path to write a JSON report.")
    parser.add_argument("--csv", dest="csv_output", default=None, help="Optional path to write a CSV matrix.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_config_path = Path(args.project_config).expanduser()
    if not project_config_path.exists():
        print(f"error: project config not found: {project_config_path}", file=sys.stderr)
        return 2

    report = build_report(project_config_path)
    print_report(report)

    if args.json_output:
        output_path = Path(args.json_output).expanduser()
        output_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"json: {output_path}")
    if args.csv_output:
        output_path = Path(args.csv_output).expanduser()
        write_csv(report, output_path)
        print(f"csv: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
