#!/usr/bin/env python3

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from bootstrap_local_annotation_project import portal_runs
from chunk_registry_common import (
    build_registry,
    ensure_registry_matches,
    load_remote_registry,
    now_utc,
    registry_path,
    save_remote_registry,
    ssh_target,
)
from copick_project_common import (
    load_json,
    preset_default_object,
    preset_objects,
    run_object_statuses,
    save_json,
)


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


def remote_exists(remote_user: str, remote_host: str, path: str, dry_run: bool = False) -> bool:
    cmd = ["ssh", ssh_target(remote_user, remote_host), f"test -e {path}"]
    print("command:", " ".join(cmd))
    if dry_run:
        return False
    return subprocess.run(cmd, check=False).returncode == 0


def ensure_remote_project(manifest: dict, dry_run: bool = False) -> int:
    remote_user = manifest["remote_user"]
    remote_host = manifest["remote_host"]
    remote_projects_root = manifest["remote_projects_root"].rstrip("/")
    dataset_id = manifest["dataset_id"]
    preset = manifest["preset"]
    remote_project_root = f"{remote_projects_root}/dataset-{dataset_id}-{preset}"
    remote_overlay_root = f"{remote_project_root}/copick_overlay"
    remote_project_config_path = f"{remote_project_root}/project_config.json"
    remote_copick_config_path = f"{remote_project_root}/copick_config.json"

    rc = run_command(
        ["ssh", ssh_target(remote_user, remote_host), f"mkdir -p {remote_project_root} {remote_overlay_root}"],
        dry_run=dry_run,
    )
    if rc != 0:
        return rc

    local_temp_dir = Path(manifest["project_root"]) / ".remote_finalize"
    local_temp_dir.mkdir(parents=True, exist_ok=True)
    local_project_config_path = local_temp_dir / "project_config.json"
    local_copick_config_path = local_temp_dir / "copick_config.json"

    project_config = {
        "config_path": remote_copick_config_path,
        "overlay_root": remote_overlay_root,
        "dataset_ids": [int(dataset_id)],
        "project_name": f"Dataset {dataset_id} {preset.title()} Project",
        "description": f"Remote shared portal-backed copick project for dataset {dataset_id} using the {preset} class preset.",
        "skip_validation": True,
        "default_object_name": preset_default_object(preset),
    }
    save_json(local_project_config_path, project_config)

    copick_config = {
        "config_type": "cryoet_data_portal",
        "name": project_config["project_name"],
        "description": project_config["description"],
        "version": "1.20.0",
        "pickable_objects": preset_objects(preset),
        "overlay_root": f"local://{remote_overlay_root}",
        "overlay_fs_args": {"auto_mkdir": True},
        "dataset_ids": [int(dataset_id)],
        "user_id": manifest["user_id"],
        "session_id": "remote-master",
    }
    save_json(local_copick_config_path, copick_config)

    rc = run_command(
        ["scp", str(local_project_config_path), f"{ssh_target(remote_user, remote_host)}:{remote_project_config_path}"],
        dry_run=dry_run,
    )
    if rc != 0:
        return rc
    return run_command(
        ["scp", str(local_copick_config_path), f"{ssh_target(remote_user, remote_host)}:{remote_copick_config_path}"],
        dry_run=dry_run,
    )


def verify_remote_overlay(manifest: dict, relative_paths: list[Path], dry_run: bool = False) -> int:
    remote_user = manifest["remote_user"]
    remote_host = manifest["remote_host"]
    remote_projects_root = manifest["remote_projects_root"].rstrip("/")
    remote_overlay_root = f"{remote_projects_root}/dataset-{manifest['dataset_id']}-{manifest['preset']}/copick_overlay"
    if dry_run:
        return 0
    for relative_path in relative_paths:
        remote_path = f"{remote_overlay_root}/{relative_path.as_posix()}"
        if not remote_exists(remote_user, remote_host, remote_path, dry_run=False):
            print(f"error: uploaded file not found remotely: {remote_path}", file=sys.stderr)
            return 1
    return 0


def chunk_missing_pairs(project_config_path: Path, selected_copick_runs: list[str], object_names: list[str]) -> list[dict]:
    project_config = load_json(project_config_path)
    overlay_root = Path(project_config["overlay_root"]).expanduser()
    missing = []
    for run_name in selected_copick_runs:
        statuses = run_object_statuses(overlay_root, run_name, object_names)
        for object_name in object_names:
            if statuses[object_name]["status"] == "missing":
                missing.append({"run_name": run_name, "object_name": object_name})
    return missing


def update_registry_after_finalize(manifest: dict, missing_pairs: list[dict], dry_run: bool = False) -> int:
    remote_user = manifest["remote_user"]
    remote_host = manifest["remote_host"]
    dataset_id = manifest["dataset_id"]
    preset = manifest["preset"]
    chunk_size = int(manifest["chunk_size"])
    registry_file = manifest.get("registry_path") or registry_path(manifest["remote_projects_root"], dataset_id, preset)

    run_names = [run.name for run in portal_runs(int(dataset_id))]
    if not run_names:
        print(f"error: no runs found for dataset {dataset_id}", file=sys.stderr)
        return 2

    existing_registry = load_remote_registry(remote_user, remote_host, registry_file)
    if existing_registry is None:
        registry = build_registry(dataset_id, preset, run_names, chunk_size)
    else:
        registry = ensure_registry_matches(existing_registry, dataset_id, preset, run_names, chunk_size)

    chunk_index = int(manifest["chunk_index"])
    target = None
    for chunk in registry.get("chunks", []):
        if int(chunk.get("chunk_index", 0)) == chunk_index:
            target = chunk
            break
    if target is None:
        print(f"error: chunk {chunk_index} was not found in the registry", file=sys.stderr)
        return 2

    target["assigned_user"] = manifest["user_id"]
    target["started_at"] = target.get("started_at") or now_utc()
    if missing_pairs:
        target["status"] = "in_progress"
        target["completed_at"] = None
    else:
        target["status"] = "complete"
        target["completed_at"] = now_utc()
    registry["updated_at"] = now_utc()
    return save_remote_registry(remote_user, remote_host, registry_file, registry, dry_run=dry_run)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Upload a local annotation project into the shared remote copick project and optionally delete it."
    )
    parser.add_argument(
        "--project-config",
        default=str(Path.cwd() / "project_config.json"),
        help="Path to the local project_config.json.",
    )
    parser.add_argument("--remote-user", default=None, help="Remote username. If omitted, prompt interactively.")
    parser.add_argument("--keep-local-project", action="store_true", help="Keep the local project after successful upload.")
    parser.add_argument("--dry-run", action="store_true", help="Print commands without executing them.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_config_path = Path(args.project_config).expanduser()
    project_root = project_config_path.parent
    manifest_path = project_root / "annotation_project.json"
    if not manifest_path.exists():
        print(f"error: annotation project manifest not found: {manifest_path}", file=sys.stderr)
        return 2

    manifest = load_json(manifest_path)
    manifest["remote_user"] = prompt_if_missing(args.remote_user or manifest.get("remote_user"), "Remote username: ")

    rc = ensure_remote_project(manifest, dry_run=args.dry_run)
    if rc != 0:
        return rc

    overlay_root = Path(load_json(project_config_path)["overlay_root"]).expanduser()
    remote_overlay_root = (
        f"{manifest['remote_projects_root'].rstrip('/')}/dataset-{manifest['dataset_id']}-{manifest['preset']}/copick_overlay/"
    )
    relative_paths = sorted(path.relative_to(overlay_root) for path in overlay_root.rglob("*") if path.is_file())
    if not relative_paths:
        print("warning: no local overlay files were found to upload.")

    rc = run_command(
        [
            "rsync",
            "-av",
            "--ignore-existing",
            f"{overlay_root}/",
            f"{ssh_target(manifest['remote_user'], manifest['remote_host'])}:{remote_overlay_root}",
        ],
        dry_run=args.dry_run,
    )
    if rc != 0:
        return rc

    rc = verify_remote_overlay(manifest, relative_paths, dry_run=args.dry_run)
    if rc != 0:
        return rc

    missing_pairs = chunk_missing_pairs(
        project_config_path,
        manifest.get("selected_copick_runs", []),
        manifest.get("object_names", []),
    )
    rc = update_registry_after_finalize(manifest, missing_pairs, dry_run=args.dry_run)
    if rc != 0:
        return rc
    if missing_pairs:
        print(f"chunk remains in_progress: {len(missing_pairs)} run/object pairs are still missing")
    else:
        print("chunk marked complete in remote registry")

    if not args.keep_local_project and not args.dry_run:
        shutil.rmtree(project_root)
        print(f"deleted local project: {project_root}")
    else:
        print(f"kept local project: {project_root}")
    print(f"remote project: {manifest['remote_projects_root'].rstrip('/')}/dataset-{manifest['dataset_id']}-{manifest['preset']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
