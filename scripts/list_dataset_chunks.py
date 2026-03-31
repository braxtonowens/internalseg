#!/usr/bin/env python3

import argparse

from bootstrap_local_annotation_project import portal_runs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="List available runs for a Portal dataset.")
    parser.add_argument("--dataset-id", required=True, help="Portal dataset id, for example 10476.")
    parser.add_argument("--preset", choices=["bacteria", "yeast", "hela"], required=False, help="Optional class preset label to print alongside the run list.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    runs = portal_runs(int(args.dataset_id))
    run_names = [run.name for run in runs]
    if not run_names:
        print(f"error: no runs found for dataset {args.dataset_id}")
        return 2

    print(f"dataset: {args.dataset_id}")
    if args.preset:
        print(f"preset: {args.preset}")
    print(f"run count: {len(run_names)}")
    print("source: CryoET Portal")
    print()
    for index, run_name in enumerate(run_names, start=1):
        print(f"{index:03d} {run_name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
