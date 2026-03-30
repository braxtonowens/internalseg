#!/usr/bin/env python3

import argparse
import re
import subprocess
import sys
from pathlib import Path

from chunk_registry_common import build_registry
from copick_project_common import preset_default_object, preset_objects, save_json


def prompt_if_missing(value: str | None, prompt: str) -> str:
    if value:
        return value.strip()
    entered = input(prompt).strip()
    if not entered:
        raise SystemExit("error: a value is required")
    return entered


def run_command(cmd: list[str], dry_run: bool = False) -> int:
    print("command:", " ".join(cmd))
    if dry_run:
        return 0
    return subprocess.run(cmd, check=False).returncode


def sanitize_portal_name(value: str) -> str:
    sanitized = re.sub(r'[<>:"/\\|?*\x00-\x1F\x7F\s_]+', '-', value).strip('-')
    if not sanitized:
        raise SystemExit(f"error: invalid empty name after sanitizing {value!r}")
    return sanitized


def portal_runs(dataset_id: int):
    try:
        import cryoet_data_portal as cdp
    except ImportError as exc:
        raise SystemExit("error: cryoet_data_portal is not installed in the active Python environment") from exc
    client = cdp.Client()
    return sorted(cdp.Run.find(client, [cdp.Run.dataset_id == dataset_id]), key=lambda run: run.name)


def dataset_project_name(dataset_id: str, preset: str, chunk_index: int, chunk_count: int) -> str:
    base = f"dataset-{dataset_id}-{preset}"
    if chunk_count == 1:
        return base
    return f"{base}-chunk-{chunk_index:03d}-of-{chunk_count:03d}"


def write_local_project(
    project_root: Path,
    dataset_id: str,
    preset: str,
    user_id: str,
    remote_host: str,
    remote_projects_root: str,
    selected_source_runs: list[str],
    selected_copick_runs: list[str],
    chunk_size: int,
    chunk_index: int,
    chunk_count: int,
) -> tuple[Path, Path, Path, Path, Path]:
    source_cache_root = project_root / "source_dataset"
    static_root = project_root / "copick_static"
    overlay_root = project_root / "copick_overlay"
    project_config_path = project_root / "project_config.json"
    copick_config_path = project_root / "copick_config.json"
    manifest_path = project_root / "annotation_project.json"

    project_root.mkdir(parents=True, exist_ok=True)
    source_cache_root.mkdir(parents=True, exist_ok=True)
    static_root.mkdir(parents=True, exist_ok=True)
    overlay_root.mkdir(parents=True, exist_ok=True)

    project_label = f"Dataset {dataset_id} {preset.title()} Project"
    if chunk_count > 1:
        project_label = f"{project_label} Chunk {chunk_index}/{chunk_count}"

    project_config = {
        "static_backend": "local",
        "static_root": str(static_root),
        "overlay_root": str(overlay_root),
        "config_path": str(copick_config_path),
        "project_name": project_label,
        "description": f"Local annotation project for dataset {dataset_id} using the {preset} class preset.",
        "skip_validation": True,
        "default_object_name": preset_default_object(preset),
        "default_user_id": user_id,
    }
    save_json(project_config_path, project_config)

    copick_config = {
        "config_type": "filesystem",
        "name": project_config["project_name"],
        "description": project_config["description"],
        "version": "1.20.0",
        "pickable_objects": preset_objects(preset),
        "overlay_root": f"local://{overlay_root}",
        "overlay_fs_args": {"auto_mkdir": True},
        "static_root": f"local://{static_root}",
        "static_fs_args": {"auto_mkdir": False},
    }
    save_json(copick_config_path, copick_config)

    manifest = {
        "dataset_id": str(dataset_id),
        "preset": preset,
        "user_id": user_id,
        "remote_host": remote_host,
        "remote_projects_root": remote_projects_root,
        "object_names": [obj["name"] for obj in preset_objects(preset)],
        "source_cache_root": str(source_cache_root),
        "project_root": str(project_root),
        "project_config_path": str(project_config_path),
        "selected_runs": selected_source_runs,
        "selected_copick_runs": selected_copick_runs,
        "chunk_size": chunk_size,
        "chunk_index": chunk_index,
        "chunk_count": chunk_count,
        "registry_path": None,
    }
    save_json(manifest_path, manifest)
    return source_cache_root, static_root, overlay_root, project_config_path, manifest_path


def download_run_via_portal(run, source_cache_root: Path, dataset_id: str, dry_run: bool) -> None:
    destination = source_cache_root / str(dataset_id)
    if dry_run:
        print(f"portal download: dataset {dataset_id} run {run.name} -> {destination}")
        return
    print(f"downloading portal run: {run.name}")
    run.download_everything(dest_path=str(destination))


def download_run_via_aws_sync(run, source_cache_root: Path, dataset_id: str, dry_run: bool) -> int:
    destination = source_cache_root / str(dataset_id) / run.name
    command = [
        "aws",
        "s3",
        "sync",
        run.s3_prefix,
        str(destination),
        "--no-sign-request",
        "--exclude",
        "*",
        "--include",
        "Reconstructions/*/Tomograms/*",
        "--include",
        "Reconstructions/*/Tomograms/**",
        "--include",
        "Reconstructions/*/Annotations/*",
        "--include",
        "Reconstructions/*/Annotations/**",
        "--exclude",
        "*.mrc",
    ]
    return run_command(command, dry_run=dry_run)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download a chunk of runs directly from the CryoET Portal and create a local copick annotation project.")
    parser.add_argument("--dataset-id", required=True, help="Portal dataset id, for example 10274.")
    parser.add_argument("--preset", choices=["bacteria", "yeast", "hela-stress"], required=True, help="Class preset to apply.")
    parser.add_argument("--chunk-size", type=int, required=True, help="Number of runs to include in one local chunk.")
    parser.add_argument("--chunk-index", type=int, default=1, help="1-based chunk index to download.")
    parser.add_argument("--projects-dir", default=str(Path.cwd() / "projects"), help="Parent directory where the local project folder will be created.")
    parser.add_argument("--remote-host", default="ssh.rc.byu.edu", help="Remote host used later during finalize/upload.")
    parser.add_argument("--remote-projects-root", default="/grphome/grp_tomo/nobackup/archive/copick_projects", help="Remote parent directory used later during finalize/upload.")
    parser.add_argument("--user-id", default=None, help="Annotation user id to store in metadata. If omitted, prompt interactively.")
    parser.add_argument("--link-mode", choices=["symlink", "copy"], default="symlink", help="How to materialize downloaded raw data into the local copick static tree.")
    parser.add_argument("--download-method", choices=["portal", "aws-sync"], default="aws-sync", help="How to fetch run data from the CryoET Portal.")
    parser.add_argument("--dry-run", action="store_true", help="Print commands without executing them.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(__file__).resolve().parent.parent
    scripts_dir = root / "scripts"
    user_id = prompt_if_missing(args.user_id, "Annotation user id: ")

    runs = portal_runs(int(args.dataset_id))
    if not runs:
        print(f"error: no runs found for dataset {args.dataset_id}", file=sys.stderr)
        return 2
    source_run_names = [run.name for run in runs]
    registry_preview = build_registry(args.dataset_id, args.preset, source_run_names, args.chunk_size)

    chunk_count = int(registry_preview["chunk_count"])
    chunk_index = int(args.chunk_index)
    if chunk_index < 1 or chunk_index > chunk_count:
        print(f"error: --chunk-index must be between 1 and {chunk_count}", file=sys.stderr)
        return 2

    selected_source_runs = next(chunk["selected_runs"] for chunk in registry_preview["chunks"] if int(chunk["chunk_index"]) == chunk_index)
    selected_names = set(selected_source_runs)
    selected_run_objects = [run for run in runs if run.name in selected_names]
    selected_copick_runs = [sanitize_portal_name(f"{args.dataset_id}-{run.name}") for run in selected_run_objects]

    project_name = dataset_project_name(args.dataset_id, args.preset, chunk_index, chunk_count)
    project_root = Path(args.projects_dir).expanduser() / project_name
    source_cache_root, static_root, _overlay_root, project_config_path, manifest_path = write_local_project(
        project_root=project_root,
        dataset_id=args.dataset_id,
        preset=args.preset,
        user_id=user_id,
        remote_host=args.remote_host,
        remote_projects_root=args.remote_projects_root,
        selected_source_runs=selected_source_runs,
        selected_copick_runs=selected_copick_runs,
        chunk_size=args.chunk_size,
        chunk_index=chunk_index,
        chunk_count=chunk_count,
    )

    conversion_config_path = project_root / "conversion_config.json"
    conversion_config = {
        "source_root": str(source_cache_root),
        "dataset_ids": [int(args.dataset_id)],
        "author_contains": [],
        "output_static_root": str(static_root),
        "link_mode": args.link_mode,
        "portal_user_id": "portal",
        "project_config_path": str(project_config_path),
        "default_particle_radius": 60.0,
        "default_segmentation_radius": 10.0,
    }
    save_json(conversion_config_path, conversion_config)

    for run in selected_run_objects:
        if args.download_method == "aws-sync":
            rc = download_run_via_aws_sync(run, source_cache_root, args.dataset_id, args.dry_run)
            if rc != 0:
                return rc
        else:
            download_run_via_portal(run, source_cache_root, args.dataset_id, args.dry_run)

    rc = run_command([sys.executable, str(scripts_dir / "build_copick_static.py"), "--conversion-config", str(conversion_config_path)], dry_run=args.dry_run)
    if rc != 0:
        return rc

    rc = run_command([sys.executable, str(scripts_dir / "setup_copick_project.py"), "--project-config", str(project_config_path), "--skip-validation"], dry_run=args.dry_run)
    if rc != 0:
        return rc

    print(f"project root: {project_root}")
    print(f"project config: {project_config_path}")
    print(f"manifest: {manifest_path}")
    print(f"download method: {args.download_method}")
    print(f"chunk: {chunk_index}/{chunk_count}")
    print(f"runs in chunk: {len(selected_source_runs)}")
    print(f"first run: {selected_source_runs[0]}")
    print(f"last run: {selected_source_runs[-1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
