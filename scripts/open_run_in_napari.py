#!/usr/bin/env python3

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import zarr


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_json_if_exists(path: Path) -> dict:
    if not path.exists():
        return {}
    return load_json(path)


def latest_overlay_segmentations(seg_dir: Path) -> list[Path]:
    latest: dict[str, tuple[str, Path]] = {}
    if not seg_dir.exists():
        return []

    for path in sorted(seg_dir.glob("*.zarr")):
        metadata = load_json_if_exists(path / ".zattrs")
        object_name = metadata.get("object_name")
        created_at = str(metadata.get("created_at", ""))
        if not object_name:
            parts = path.stem.split("_")
            if len(parts) >= 4:
                object_name = "_".join(parts[3:]).replace("_", "-")
        if not object_name:
            continue

        previous = latest.get(str(object_name))
        if previous is None or created_at >= previous[0]:
            latest[str(object_name)] = (created_at, path)

    return [item[1] for item in sorted(latest.values(), key=lambda item: item[1].name)]


def open_level0_and_scale(path: Path) -> tuple[np.ndarray, tuple[float, float, float]]:
    root = zarr.open(str(path), mode="r")
    try:
        data = np.asarray(root["0"])
        scale = level0_scale_from_attrs(getattr(root, "attrs", {}))
        return data, scale
    except Exception:
        array = np.asarray(zarr.open_array(str(path), mode="r"))
        return array, (1.0, 1.0, 1.0)


def robust_contrast_limits(data: np.ndarray) -> tuple[float, float]:
    z0 = max(0, data.shape[0] // 2 - 8)
    z1 = min(data.shape[0], z0 + 16)
    sample = data[z0:z1]
    low = float(np.quantile(sample, 0.01))
    high = float(np.quantile(sample, 0.999))
    if not np.isfinite(low) or not np.isfinite(high) or low >= high:
        low = float(sample.min())
        high = float(sample.max())
    return low, high


def level0_scale_from_attrs(attrs) -> tuple[float, float, float]:
    scale = (1.0, 1.0, 1.0)
    multiscales = attrs.get("multiscales", []) if hasattr(attrs, "get") else []
    if multiscales:
        datasets = multiscales[0].get("datasets", [])
        if datasets:
            transforms = datasets[0].get("coordinateTransformations", [])
            for transform in transforms:
                if transform.get("type") == "scale":
                    values = transform.get("scale", [])
                    if len(values) == 3:
                        scale = tuple(float(v) for v in values)
                        break
    return scale


def load_segmentation_data_and_scale(path: Path) -> tuple[np.ndarray, tuple[float, float, float]]:
    root = zarr.open(str(path), mode="r")
    try:
        return np.asarray(root["0"], dtype=np.uint16), level0_scale_from_attrs(getattr(root, "attrs", {}))
    except Exception:
        return np.asarray(zarr.open_array(str(path), mode="r"), dtype=np.uint16), (1.0, 1.0, 1.0)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Open one run's tomogram and segmentations in Napari.")
    parser.add_argument("run", help="Run id key, for example 10476-12345")
    parser.add_argument(
        "--project-config",
        default=str(Path.cwd() / "project_config.json"),
        help="Path to project settings JSON.",
    )
    parser.add_argument(
        "--all-overlay-versions",
        action="store_true",
        help="Open every overlay segmentation version instead of only the latest one per object.",
    )
    parser.add_argument(
        "--include-static-segmentations",
        action="store_true",
        help="Also open static portal segmentations from copick_static.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_config = load_json(Path(args.project_config).expanduser())
    static_root = Path(project_config["static_root"]).expanduser()
    overlay_root = Path(project_config["overlay_root"]).expanduser()

    run_static_root = static_root / "ExperimentRuns" / args.run
    run_overlay_root = overlay_root / "ExperimentRuns" / args.run
    if not run_static_root.exists():
        print(f"error: run not found under static tree: {run_static_root}", file=sys.stderr)
        return 2

    tomograms = sorted(run_static_root.glob("VoxelSpacing*/*.zarr"))
    if not tomograms:
        print(f"error: no tomograms found for run id: {args.run}", file=sys.stderr)
        return 2

    overlay_seg_dir = run_overlay_root / "Segmentations"
    overlay_paths = sorted(overlay_seg_dir.glob("*.zarr")) if args.all_overlay_versions else latest_overlay_segmentations(overlay_seg_dir)
    static_seg_paths = sorted((run_static_root / "Segmentations").glob("*.zarr")) if args.include_static_segmentations else []

    print(f"run id: {args.run}")
    print(tomograms[0])
    for path in static_seg_paths:
        print(path)
    for path in overlay_paths:
        print(path)

    import napari

    viewer = napari.Viewer()
    image_data, image_scale = open_level0_and_scale(tomograms[0])
    image_layer = viewer.add_image(image_data, name=tomograms[0].stem, scale=image_scale)
    image_layer.contrast_limits = robust_contrast_limits(image_data)

    for path in static_seg_paths:
        data, seg_scale = load_segmentation_data_and_scale(path)
        viewer.add_labels(data, name=path.stem, opacity=0.5, scale=seg_scale if seg_scale != (1.0, 1.0, 1.0) else image_scale)
    for path in overlay_paths:
        data, seg_scale = load_segmentation_data_and_scale(path)
        viewer.add_labels(data, name=path.stem, opacity=0.5, scale=seg_scale if seg_scale != (1.0, 1.0, 1.0) else image_scale)

    napari.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
