#!/usr/bin/env python3

import argparse

from bootstrap_local_annotation_project import portal_runs
from chunk_registry_common import build_registry


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="List chunk boundaries for a Portal dataset without contacting the remote server.")
    parser.add_argument("--dataset-id", required=True, help="Portal dataset id, for example 10274.")
    parser.add_argument("--preset", choices=["bacteria", "yeast", "hela"], required=True, help="Class preset to inspect.")
    parser.add_argument("--chunk-size", type=int, required=True, help="Number of runs per chunk.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    runs = portal_runs(int(args.dataset_id))
    run_names = [run.name for run in runs]
    if not run_names:
        print(f"error: no runs found for dataset {args.dataset_id}")
        return 2

    registry = build_registry(args.dataset_id, args.preset, run_names, args.chunk_size)

    print(f"dataset: {args.dataset_id}")
    print(f"preset: {args.preset}")
    print(f"run count: {len(run_names)}")
    print(f"chunk size: {args.chunk_size}")
    print(f"chunk count: {registry['chunk_count']}")
    print("source: CryoET Portal")
    print()

    for chunk in registry["chunks"]:
        selected_runs = chunk["selected_runs"]
        print(
            "chunk {chunk_index:03d}: runs={count:<3} first={first} last={last}".format(
                chunk_index=int(chunk["chunk_index"]),
                count=len(selected_runs),
                first=selected_runs[0],
                last=selected_runs[-1],
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
