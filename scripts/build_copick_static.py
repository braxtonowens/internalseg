#!/usr/bin/env python3

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any


def sanitize_name(value: str) -> str:
    sanitized = re.sub(r'[<>:"/\\|?*\x00-\x1F\x7F\s_]+', "-", value).strip("-")
    if not sanitized:
        raise ValueError(f"invalid empty name after sanitizing: {value!r}")
    return sanitized


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="ascii") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")


def iter_strings(obj: Any):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for key, value in obj.items():
            yield str(key)
            yield from iter_strings(value)
    elif isinstance(obj, list):
        for item in obj:
            yield from iter_strings(item)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert portal-style cryoET data into a copick static tree.")
    parser.add_argument(
        "--conversion-config",
        default=str(Path.cwd() / "conversion_config.json"),
        help="Path to conversion settings JSON.",
    )
    return parser.parse_args()


def deterministic_color(name: str) -> list[int]:
    digest = hashlib.sha256(name.encode("utf-8")).digest()
    return [digest[0], digest[1], digest[2], 255]


def parse_voxel_spacing(path: Path) -> float:
    match = re.search(r"VoxelSpacing([0-9]+(?:\.[0-9]+)?)$", path.name)
    if not match:
        raise ValueError(f"could not parse voxel spacing from {path}")
    return round(float(match.group(1)), 3)


def ensure_empty_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def clear_existing(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def materialize_path(src: Path, dst: Path, link_mode: str) -> None:
    clear_existing(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)

    if link_mode == "symlink":
        os.symlink(src, dst, target_is_directory=src.is_dir())
    elif link_mode == "copy":
        if src.is_dir():
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)
    else:
        raise ValueError(f"unsupported link_mode: {link_mode}")


def portal_base_name(path: Path) -> str:
    name = path.name
    suffixes = [
        "_orientedpoint.ndjson",
        "_point.ndjson",
        "_segmentationmask.zarr",
        "_segmentationmask.mrc",
        ".json",
    ]
    for suffix in suffixes:
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break

    if name.endswith("-1.0"):
        name = name[:-4]

    return name


def portal_point_to_copick(entry: dict, voxel_spacing: float) -> dict:
    location = entry["location"]
    transform = [
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]

    if "xyz_rotation_matrix" in entry:
        rotation = entry["xyz_rotation_matrix"]
        for row in range(3):
            for col in range(3):
                transform[row][col] = rotation[row][col]

    return {
        "location": {
            "x": float(location["x"]) * voxel_spacing,
            "y": float(location["y"]) * voxel_spacing,
            "z": float(location["z"]) * voxel_spacing,
        },
        "transformation_": transform,
        "instance_id": int(entry.get("instance_id", 0) or 0),
        "score": float(entry.get("score", 1.0) or 1.0),
    }


def convert_points_file(
    src: Path,
    dst: Path,
    run_name: str,
    object_name: str,
    session_id: str,
    user_id: str,
    voxel_spacing: float,
) -> int:
    points = []
    with src.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            points.append(portal_point_to_copick(json.loads(line), voxel_spacing))

    payload = {
        "pickable_object_name": object_name,
        "user_id": user_id,
        "session_id": session_id,
        "run_name": run_name,
        "voxel_spacing": voxel_spacing,
        "unit": "angstrom",
        "trust_orientation": src.name.endswith("_orientedpoint.ndjson"),
        "points": points,
    }
    save_json(dst, payload)
    return len(points)


def gather_tomogram_sources(voxel_dir: Path) -> list[tuple[str, Path]]:
    tomograms_root = voxel_dir / "Tomograms"
    if not tomograms_root.exists():
        return []

    ret = []
    for tomo_id_dir in sorted(p for p in tomograms_root.iterdir() if p.is_dir()):
        zarrs = sorted(p for p in tomo_id_dir.iterdir() if p.name.endswith(".zarr"))
        for zarr_path in zarrs:
            tomo_type = sanitize_name(zarr_path.stem).lower()
            ret.append((tomo_type, zarr_path))
    return ret


def build_pickable_objects(registry: dict[str, dict], particle_radius: float, segmentation_radius: float) -> list[dict]:
    objects = []
    for index, name in enumerate(sorted(registry), start=1):
        info = registry[name]
        objects.append(
            {
                "name": name,
                "is_particle": info["is_particle"],
                "label": index,
                "color": deterministic_color(name),
                "radius": particle_radius if info["is_particle"] else segmentation_radius,
                "metadata": {
                    "source_names": sorted(info["source_names"]),
                },
            },
        )
    return objects


def update_project_config(path: Path, static_root: str) -> None:
    payload = load_json(path) if path.exists() else {}
    payload["static_backend"] = "local"
    payload["static_root"] = static_root
    if "overlay_root" not in payload:
        payload["overlay_root"] = str(Path.cwd() / "copick_overlay")
    if "config_path" not in payload:
        payload["config_path"] = str(Path.cwd() / "copick_config.json")
    if "project_name" not in payload:
        payload["project_name"] = "Jensen Tomo Local Project"
    if "description" not in payload:
        payload["description"] = "Filesystem-backed copick project for napari/nninteractive with a local writable overlay."
    payload["skip_validation"] = True
    save_json(path, payload)


def dataset_metadata_files(dataset_root: Path) -> list[Path]:
    patterns = [
        "*.json",
        "*/*.json",
        "*/*/*.json",
    ]
    seen = set()
    files = []
    for pattern in patterns:
        for path in dataset_root.glob(pattern):
            if path.is_file() and path not in seen:
                seen.add(path)
                files.append(path)
    return sorted(files)


def dataset_matches_authors(dataset_root: Path, author_filters: list[str]) -> bool:
    if not author_filters:
        return True

    normalized_filters = [item.casefold() for item in author_filters]
    for metadata_file in dataset_metadata_files(dataset_root):
        try:
            payload = load_json(metadata_file)
        except Exception:
            continue

        combined = " ".join(iter_strings(payload)).casefold()
        if "author" not in combined:
            continue
        if all(author.casefold() in combined for author in author_filters):
            return True

    return False


def selected_dataset_ids(source_root: Path, configured_ids: list[str], author_filters: list[str]) -> list[str]:
    candidate_ids = configured_ids
    if not candidate_ids:
        candidate_ids = sorted(path.name for path in source_root.iterdir() if path.is_dir() and path.name.isdigit())

    selected = []
    for dataset_id in candidate_ids:
        dataset_root = source_root / dataset_id
        if not dataset_root.exists():
            continue
        if dataset_matches_authors(dataset_root, author_filters):
            selected.append(dataset_id)
    return selected


def main() -> int:
    args = parse_args()
    config = load_json(Path(args.conversion_config).expanduser())

    source_root = Path(config["source_root"]).expanduser()
    output_static_root = Path(config["output_static_root"]).expanduser()
    dataset_ids = [str(item) for item in config.get("dataset_ids", [])]
    author_filters = [str(item) for item in config.get("author_contains", [])]
    link_mode = config.get("link_mode", "symlink")
    portal_user_id = sanitize_name(config.get("portal_user_id", "portal")).lower()
    project_config_path = Path(config.get("project_config_path", Path.cwd() / "project_config.json")).expanduser()
    particle_radius = float(config.get("default_particle_radius", 60.0))
    segmentation_radius = float(config.get("default_segmentation_radius", 10.0))

    if not source_root.exists():
        print(f"error: source root does not exist: {source_root}", file=sys.stderr)
        return 2
    dataset_ids = selected_dataset_ids(source_root, dataset_ids, author_filters)
    if not dataset_ids:
        print("error: no datasets matched the configured dataset_ids/author_contains filters.", file=sys.stderr)
        return 2

    ensure_empty_dir(output_static_root)
    ensure_empty_dir(output_static_root / "Objects")
    ensure_empty_dir(output_static_root / "ExperimentRuns")

    object_registry: dict[str, dict] = {}
    run_count = 0
    point_count = 0
    segmentation_count = 0
    tomogram_count = 0

    for dataset_id in dataset_ids:
        dataset_root = source_root / dataset_id
        if not dataset_root.exists():
            print(f"warning: dataset root not found, skipping: {dataset_root}")
            continue

        run_dirs = sorted(
            path for path in dataset_root.iterdir() if path.is_dir() and (path / "Reconstructions").exists()
        )
        for run_dir in run_dirs:
            source_run_name = run_dir.name
            run_name = sanitize_name(f"{dataset_id}-{source_run_name}")
            dest_run = output_static_root / "ExperimentRuns" / run_name
            ensure_empty_dir(dest_run)
            ensure_empty_dir(dest_run / "Picks")
            ensure_empty_dir(dest_run / "Segmentations")

            voxel_dirs = sorted(
                path for path in (run_dir / "Reconstructions").iterdir() if path.is_dir() and path.name.startswith("VoxelSpacing")
            )
            if not voxel_dirs:
                continue

            run_count += 1
            for voxel_dir in voxel_dirs:
                voxel_spacing = parse_voxel_spacing(voxel_dir)
                dest_vs = dest_run / f"VoxelSpacing{voxel_spacing:.3f}"
                ensure_empty_dir(dest_vs)

                for tomo_type, src_tomogram in gather_tomogram_sources(voxel_dir):
                    materialize_path(src_tomogram, dest_vs / f"{tomo_type}.zarr", link_mode)
                    tomogram_count += 1

                annotations_root = voxel_dir / "Annotations"
                if not annotations_root.exists():
                    continue

                for ann_dir in sorted(path for path in annotations_root.iterdir() if path.is_dir()):
                    session_id = sanitize_name(ann_dir.name)

                    point_files = sorted(ann_dir.glob("*_orientedpoint.ndjson")) + sorted(ann_dir.glob("*_point.ndjson"))
                    for point_file in point_files:
                        source_object = portal_base_name(point_file)
                        object_name = sanitize_name(source_object).lower()
                        object_registry.setdefault(object_name, {"is_particle": False, "source_names": set()})
                        object_registry[object_name]["is_particle"] = True
                        object_registry[object_name]["source_names"].add(source_object)

                        pick_path = dest_run / "Picks" / f"{portal_user_id}_{session_id}_{object_name}.json"
                        point_count += convert_points_file(
                            src=point_file,
                            dst=pick_path,
                            run_name=run_name,
                            object_name=object_name,
                            session_id=session_id,
                            user_id=portal_user_id,
                            voxel_spacing=voxel_spacing,
                        )

                    for seg_path in sorted(ann_dir.glob("*_segmentationmask.zarr")):
                        source_object = portal_base_name(seg_path)
                        object_name = sanitize_name(source_object).lower()
                        object_registry.setdefault(object_name, {"is_particle": False, "source_names": set()})
                        object_registry[object_name]["source_names"].add(source_object)

                        dest_seg = dest_run / "Segmentations" / f"{voxel_spacing:.3f}_{portal_user_id}_{session_id}_{object_name}.zarr"
                        materialize_path(seg_path, dest_seg, link_mode)
                        segmentation_count += 1

    pickable_objects = build_pickable_objects(object_registry, particle_radius, segmentation_radius)
    static_config = {
        "config_type": "filesystem",
        "name": "Jensen Tomo Converted Static Project",
        "description": "Static copick tree converted from portal-style BYU RC cryoET storage for napari/nninteractive.",
        "version": "1.20.0",
        "pickable_objects": pickable_objects,
        "overlay_root": f"local://{Path.cwd() / 'copick_overlay'}",
        "overlay_fs_args": {"auto_mkdir": True},
        "static_root": f"local://{output_static_root}",
        "static_fs_args": {"auto_mkdir": False},
    }
    save_json(output_static_root / "copick_config.json", static_config)
    update_project_config(project_config_path, str(output_static_root))

    print(f"source root: {source_root}")
    print(f"output static root: {output_static_root}")
    print(f"datasets processed: {len(dataset_ids)}")
    if author_filters:
        print(f"author filters: {author_filters}")
    print(f"runs converted: {run_count}")
    print(f"tomograms linked/copied: {tomogram_count}")
    print(f"point annotations converted: {point_count}")
    print(f"segmentations linked/copied: {segmentation_count}")
    print(f"pickable objects discovered: {len(pickable_objects)}")
    print(f"updated project config: {project_config_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
