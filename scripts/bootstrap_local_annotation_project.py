#!/usr/bin/env python3

import argparse
import re
import subprocess
import sys
from pathlib import Path

from copick_project_common import preset_default_object, preset_description, preset_objects, preset_project_name, preset_template, save_json


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
    sanitized = re.sub(r'[<>:"/\|?*\s_]+', '-', value).strip('-')
    if not sanitized:
        raise SystemExit(f"error: invalid empty name after sanitizing {value!r}")
    return sanitized


def portal_runs(dataset_id: int):
    try:
        import cryoet_data_portal as cdp
    except ImportError as exc:
        raise SystemExit("error: cryoet_data_portal is not installed in the active Python environment") from exc
    client = cdp.Client()
    return sorted(cdp.Run.find(client, [cdp.Run.dataset_id == dataset_id]), key=lambda run: int(run.id))


def project_folder_name(dataset_id: str, preset: str, run_id: str) -> str:
    return f"dataset-{dataset_id}-{preset}-run-{sanitize_portal_name(run_id)}"


def write_local_project(
    project_root: Path,
    dataset_id: str,
    preset: str,
    run_id: str,
    user_id: str,
    selected_source_run_name: str,
    selected_source_run_id: str,
    selected_copick_run: str,
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

    project_name = f"{preset_project_name(preset)} run {run_id}"
    description = preset_description(preset)
    template = preset_template(preset)
    pickable_objects = preset_objects(preset)
    default_object_name = preset_default_object(preset)

    project_config = {
        "static_backend": "local",
        "static_root": str(static_root),
        "overlay_root": str(overlay_root),
        "config_path": str(copick_config_path),
        "project_name": project_name,
        "description": description,
        "skip_validation": True,
        "default_object_name": default_object_name,
        "default_user_id": user_id,
    }
    save_json(project_config_path, project_config)

    copick_config = dict(template)
    for key in ["config_type", "overlay_root", "overlay_fs_args", "static_root", "static_fs_args"]:
        copick_config.pop(key, None)
    copick_config.update({
        "config_type": "filesystem",
        "name": project_config["project_name"],
        "description": project_config["description"],
        "version": str(template.get("version", "1.20.0")),
        "pickable_objects": pickable_objects,
        "overlay_root": f"local://{overlay_root}",
        "overlay_fs_args": {"auto_mkdir": True},
        "static_root": f"local://{static_root}",
        "static_fs_args": {"auto_mkdir": False},
    })
    save_json(copick_config_path, copick_config)

    manifest = {
        "dataset_id": str(dataset_id),
        "preset": preset,
        "user_id": user_id,
        "object_names": [str(obj.get("name", "")).strip() for obj in pickable_objects if str(obj.get("name", "")).strip()],
        "source_cache_root": str(source_cache_root),
        "project_root": str(project_root),
        "project_config_path": str(project_config_path),
        "selected_run_id": selected_source_run_id,
        "source_run_name": selected_source_run_name,
        "selected_copick_run": selected_copick_run,
    }
    save_json(manifest_path, manifest)
    return source_cache_root, static_root, overlay_root, project_config_path, manifest_path


def download_run_via_portal(run, source_cache_root: Path, dataset_id: str, dry_run: bool) -> None:
    destination = source_cache_root / str(dataset_id)
    if dry_run:
        print(f"portal download: dataset {dataset_id} run id {run.id} -> {destination}")
        return
    print(f"downloading portal run id: {run.id}")
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
    parser = argparse.ArgumentParser(description="Download a single run directly from the CryoET Portal and create a local copick annotation project.")
    parser.add_argument("--dataset-id", default="10476", help="Portal dataset id. Defaults to 10476.")
    parser.add_argument("--preset", choices=["bacteria", "yeast", "hela"], default="hela", help="Class preset to apply. Defaults to hela.")
    parser.add_argument("--run-id", required=True, help="Exact Portal run id to download.")
    parser.add_argument("--projects-dir", default=str(Path.cwd() / "projects"), help="Parent directory where the local project folder will be created.")
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

    target_run = next((run for run in runs if str(run.id) == str(args.run_id)), None)
    if target_run is None:
        print(f"error: run not found in dataset {args.dataset_id}: {args.run_id}", file=sys.stderr)
        return 2

    run_id = str(target_run.id)
    selected_copick_run = sanitize_portal_name(f"{args.dataset_id}-{run_id}")
    project_root = Path(args.projects_dir).expanduser() / project_folder_name(args.dataset_id, args.preset, run_id)
    source_cache_root, static_root, _overlay_root, project_config_path, manifest_path = write_local_project(
        project_root=project_root,
        dataset_id=args.dataset_id,
        preset=args.preset,
        run_id=run_id,
        user_id=user_id,
        selected_source_run_name=target_run.name,
        selected_source_run_id=run_id,
        selected_copick_run=selected_copick_run,
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
        "selected_runs": [
            {
                "dataset_id": str(args.dataset_id),
                "source_run_name": target_run.name,
                "run_id": run_id,
                "copick_run": selected_copick_run,
            }
        ],
    }
    save_json(conversion_config_path, conversion_config)

    if args.download_method == "aws-sync":
        rc = download_run_via_aws_sync(target_run, source_cache_root, args.dataset_id, args.dry_run)
        if rc != 0:
            return rc
    else:
        download_run_via_portal(target_run, source_cache_root, args.dataset_id, args.dry_run)

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
    print(f"run id: {run_id}")
    print(f"copick run id: {selected_copick_run}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
