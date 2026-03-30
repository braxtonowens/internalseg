#!/usr/bin/env python3

import argparse
import importlib.metadata
import importlib.util
import json
import sys
from pathlib import Path


def local_uri(path: Path) -> str:
    return f"local://{path.resolve()}"


def load_project_config(path: Path) -> dict:
    with path.open("r", encoding="ascii") as handle:
        return json.load(handle)


def detect_copick_static_layout(static_root: Path) -> tuple[bool, list[str]]:
    required = ["Objects", "ExperimentRuns"]
    missing = [name for name in required if not (static_root / name).exists()]
    return len(missing) == 0, missing


def copick_version() -> str:
    try:
        return importlib.metadata.version("copick")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def load_static_seed_config(static_root: Path) -> dict:
    seed_path = static_root / "copick_config.json"
    if not seed_path.exists():
        return {}
    with seed_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def build_config(static_root: Path, overlay_root: Path, name: str, description: str, seed_config: dict | None = None) -> dict:
    seed_config = seed_config or {}
    return {
        "config_type": "filesystem",
        "name": seed_config.get("name", name),
        "description": seed_config.get("description", description),
        "version": seed_config.get("version", copick_version()),
        "pickable_objects": seed_config.get("pickable_objects", []),
        "overlay_root": local_uri(overlay_root),
        "overlay_fs_args": {"auto_mkdir": True},
        "static_root": local_uri(static_root),
        "static_fs_args": {"auto_mkdir": False},
    }


def validate_with_copick(config_path: Path) -> tuple[bool, str]:
    if importlib.util.find_spec("copick") is None:
        return False, "copick is not installed in the active Python environment; skipped runtime validation."

    import copick

    root = copick.from_file(str(config_path))
    return True, f"copick opened the config successfully ({len(root.runs)} runs, {len(root.pickable_objects)} objects)."


def parse_args() -> argparse.Namespace:
    cwd = Path.cwd()
    parser = argparse.ArgumentParser(description="Create a local filesystem-backed copick config from a local static tree and writable overlay.")
    parser.add_argument("--project-config", default=str(cwd / "project_config.json"), help="Path to workspace project settings JSON.")
    parser.add_argument("--static-root", default=None, help="Absolute path to the local static data tree.")
    parser.add_argument("--overlay-root", default=None, help="Absolute path for local writable overlay data.")
    parser.add_argument("--config-path", default=None, help="Path to write the copick config JSON.")
    parser.add_argument("--project-name", default=None)
    parser.add_argument("--description", default=None)
    parser.add_argument("--skip-validation", action="store_true", help="Write the config without attempting to open it with copick.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_config_path = Path(args.project_config).expanduser()

    project_config = {}
    if project_config_path.exists():
        try:
            project_config = load_project_config(project_config_path)
        except json.JSONDecodeError as exc:
            print(f"error: could not parse project config: {exc}", file=sys.stderr)
            return 2

    static_root = Path(args.static_root or project_config.get("static_root", "")).expanduser()
    overlay_root = Path(args.overlay_root or project_config.get("overlay_root", Path.cwd() / "copick_overlay")).expanduser()
    config_path = Path(args.config_path or project_config.get("config_path", Path.cwd() / "copick_config.json")).expanduser()
    project_name = args.project_name or project_config.get("project_name", "Local Copick Project")
    description = args.description or project_config.get("description", "Filesystem-backed copick project with a local static tree and writable overlay.")
    skip_validation = args.skip_validation or bool(project_config.get("skip_validation", False))

    if not str(static_root):
        print("error: static root is not set. Update project_config.json or pass --static-root.", file=sys.stderr)
        return 2
    if not static_root.exists():
        print(f"error: static root does not exist: {static_root}", file=sys.stderr)
        return 2

    is_layout_ok, missing = detect_copick_static_layout(static_root)
    if not is_layout_ok:
        print(
            "error: static root is not in copick filesystem layout. "
            f"Missing required top-level entries: {', '.join(missing)}.",
            file=sys.stderr,
        )
        return 3

    seed_config = load_static_seed_config(static_root)
    overlay_root.mkdir(parents=True, exist_ok=True)
    config_path.parent.mkdir(parents=True, exist_ok=True)

    config = build_config(static_root, overlay_root, project_name, description, seed_config=seed_config)
    with config_path.open("w", encoding="ascii") as handle:
        json.dump(config, handle, indent=2)
        handle.write("\n")

    print(f"wrote config: {config_path}")
    print(f"static root: {static_root}")
    print(f"overlay root: {overlay_root.resolve()}")

    if skip_validation:
        print("warning: runtime validation skipped.")
        return 0

    ok, message = validate_with_copick(config_path)
    if ok:
        print(message)
        return 0

    print(f"warning: {message}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
