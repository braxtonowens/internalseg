#!/usr/bin/env python3

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from chunk_registry_common import ssh_target
from copick_project_common import load_json, preset_default_object, preset_objects, preset_project_name, preset_template, run_object_statuses, save_json


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

    rc = run_command(["ssh", ssh_target(remote_user, remote_host), f"mkdir -p {remote_project_root} {remote_overlay_root}"], dry_run=dry_run)
    if rc != 0:
        return rc

    local_temp_dir = Path(manifest["project_root"]) / ".remote_finalize"
    local_temp_dir.mkdir(parents=True, exist_ok=True)
    local_project_config_path = local_temp_dir / "project_config.json"
    local_copick_config_path = local_temp_dir / "copick_config.json"

    template = preset_template(preset)
    project_config = {
        "config_path": remote_copick_config_path,
        "overlay_root": remote_overlay_root,
        "dataset_ids": [int(dataset_id)],
        "project_name": preset_project_name(preset),
        "description": str(template.get("description", f"Remote shared portal-backed copick project for dataset {dataset_id}.")),
        "skip_validation": True,
        "default_object_name": preset_default_object(preset),
    }
    save_json(local_project_config_path, project_config)

    copick_config = dict(template)
    for key in ["config_type", "overlay_root", "overlay_fs_args", "static_root", "static_fs_args"]:
        copick_config.pop(key, None)
    copick_config.update({
        "config_type": "cryoet_data_portal",
        "name": project_config["project_name"],
        "description": project_config["description"],
        "version": str(template.get("version", "1.20.0")),
        "pickable_objects": preset_objects(preset),
        "overlay_root": f"local://{remote_overlay_root}",
        "overlay_fs_args": {"auto_mkdir": True},
        "dataset_ids": [int(dataset_id)],
        "user_id": manifest["user_id"],
        "session_id": "remote-master",
    })
    save_json(local_copick_config_path, copick_config)

    rc = run_command(["scp", str(local_project_config_path), f"{ssh_target(remote_user, remote_host)}:{remote_project_config_path}"], dry_run=dry_run)
    if rc != 0:
        return rc
    return run_command(["scp", str(local_copick_config_path), f"{ssh_target(remote_user, remote_host)}:{remote_copick_config_path}"], dry_run=dry_run)


def verify_remote_overlay(manifest: dict, relative_paths: list[Path], dry_run: bool = False) -> int:
    remote_user = manifest["remote_user"]
    remote_host = manifest["remote_host"]
    remote_projects_root = manifest["remote_projects_root"].rstrip("/")
    run_name = manifest["selected_copick_run"]
    remote_run_root = f"{remote_projects_root}/dataset-{manifest['dataset_id']}-{manifest['preset']}/copick_overlay/ExperimentRuns/{run_name}"
    if dry_run:
        return 0
    for relative_path in relative_paths:
        remote_path = f"{remote_run_root}/{relative_path.as_posix()}"
        if not remote_exists(remote_user, remote_host, remote_path, dry_run=False):
            print(f"error: uploaded file not found remotely: {remote_path}", file=sys.stderr)
            return 1
    return 0


def run_missing_pairs(project_config_path: Path, run_name: str, object_names: list[str]) -> list[dict]:
    project_config = load_json(project_config_path)
    overlay_root = Path(project_config["overlay_root"]).expanduser()
    statuses = run_object_statuses(overlay_root, run_name, object_names)
    missing = []
    for object_name in object_names:
        if statuses[object_name]["status"] == "missing":
            missing.append({"run_name": run_name, "object_name": object_name})
    return missing


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Upload a local single-run annotation project into the shared remote copick project and optionally delete it.")
    parser.add_argument("--project-config", default=str(Path.cwd() / "project_config.json"), help="Path to the local project_config.json.")
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
    local_run_root = overlay_root / "ExperimentRuns" / manifest["selected_copick_run"]
    remote_run_root = f"{manifest['remote_projects_root'].rstrip('/')}/dataset-{manifest['dataset_id']}-{manifest['preset']}/copick_overlay/ExperimentRuns/{manifest['selected_copick_run']}/"
    if not local_run_root.exists():
        print(f"warning: no local overlay directory was found for run {manifest['selected_copick_run']}")
        relative_paths: list[Path] = []
    else:
        relative_paths = sorted(path.relative_to(local_run_root) for path in local_run_root.rglob('*') if path.is_file())
        rc = run_command([
            "rsync",
            "-av",
            "--delete",
            f"{local_run_root}/",
            f"{ssh_target(manifest['remote_user'], manifest['remote_host'])}:{remote_run_root}",
        ], dry_run=args.dry_run)
        if rc != 0:
            return rc

        rc = verify_remote_overlay(manifest, relative_paths, dry_run=args.dry_run)
        if rc != 0:
            return rc

    missing_pairs = run_missing_pairs(project_config_path, manifest["selected_copick_run"], manifest.get("object_names", []))
    if missing_pairs:
        print(f"run remains incomplete: {len(missing_pairs)} object classes are still missing")
    else:
        print("run is complete: every configured object has a segmentation or absence record")

    if not args.keep_local_project and not args.dry_run:
        shutil.rmtree(project_root)
        print(f"deleted local project: {project_root}")
    else:
        print(f"kept local project: {project_root}")
    print(f"remote project: {manifest['remote_projects_root'].rstrip('/')}/dataset-{manifest['dataset_id']}-{manifest['preset']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
