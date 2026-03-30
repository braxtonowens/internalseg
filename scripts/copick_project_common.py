#!/usr/bin/env python3

import json
import re
from pathlib import Path


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_json_if_exists(path: Path) -> dict:
    if not path.exists():
        return {}
    return load_json(path)


def save_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")


def sanitize_token(value: str) -> str:
    token = re.sub(r"[^A-Za-z0-9-]+", "-", value.strip()).strip("-")
    return token or "segmentation"


def bacteria_pickable_objects() -> list[dict]:
    return [
        {"name": "periplasm", "is_particle": False, "label": 1, "color": [214, 134, 174, 255], "radius": 10.0, "metadata": {"source_names": ["membrane"]}},
        {"name": "cytoplasm", "is_particle": False, "label": 2, "color": [88, 166, 255, 255], "radius": 10.0, "metadata": {"source_names": ["cytoplasm"]}},
        {"name": "flagella", "is_particle": False, "label": 3, "color": [255, 184, 108, 255], "radius": 10.0, "metadata": {"source_names": ["flagella"]}},
        {"name": "storage-granule", "is_particle": False, "label": 4, "color": [120, 220, 140, 255], "radius": 10.0, "metadata": {"source_names": ["storage_granule"]}},
        {"name": "carbon-film", "is_particle": False, "label": 5, "color": [200, 200, 200, 255], "radius": 10.0, "metadata": {"source_names": ["carbon_film"]}},
        {"name": "chemosensory-array", "is_particle": False, "label": 6, "color": [230, 90, 170, 255], "radius": 10.0, "metadata": {"source_names": ["chemosensory_array", "chemosensory-array"]}},
    ]


def yeast_pickable_objects() -> list[dict]:
    return [
        {"name": "plasma-membrane", "is_particle": False, "label": 1, "color": [214, 134, 174, 255], "radius": 10.0, "metadata": {"source_names": ["plasma_membrane"]}},
        {"name": "cell-wall", "is_particle": False, "label": 2, "color": [212, 175, 55, 255], "radius": 10.0, "metadata": {"source_names": ["cell_wall"]}},
        {"name": "cytoplasm", "is_particle": False, "label": 3, "color": [88, 166, 255, 255], "radius": 10.0, "metadata": {"source_names": ["cytoplasm"]}},
        {"name": "nucleus", "is_particle": False, "label": 4, "color": [255, 122, 69, 255], "radius": 10.0, "metadata": {"source_names": ["nucleus"]}},
        {"name": "vacuole", "is_particle": False, "label": 5, "color": [120, 220, 140, 255], "radius": 10.0, "metadata": {"source_names": ["vacuole"]}},
        {"name": "mitochondria", "is_particle": False, "label": 6, "color": [255, 184, 108, 255], "radius": 10.0, "metadata": {"source_names": ["mitochondria"]}},
        {"name": "lipid-droplet", "is_particle": False, "label": 7, "color": [245, 229, 99, 255], "radius": 10.0, "metadata": {"source_names": ["lipid_droplet"]}},
        {"name": "endoplasmic-reticulum", "is_particle": False, "label": 8, "color": [186, 104, 200, 255], "radius": 10.0, "metadata": {"source_names": ["endoplasmic_reticulum", "er"]}},
    ]


def hela_stress_pickable_objects() -> list[dict]:
    return [
        {"name": "mitochondria", "is_particle": False, "label": 1, "color": [255, 184, 108, 255], "radius": 10.0, "metadata": {"source_names": ["mitochondria", "mitochondrion"]}},
        {"name": "cytoplasm", "is_particle": False, "label": 2, "color": [88, 166, 255, 255], "radius": 10.0, "metadata": {"source_names": ["cytoplasm"]}},
        {"name": "nucleus", "is_particle": False, "label": 3, "color": [255, 122, 69, 255], "radius": 10.0, "metadata": {"source_names": ["nucleus"]}},
        {"name": "endoplasmic-reticulum", "is_particle": False, "label": 4, "color": [186, 104, 200, 255], "radius": 10.0, "metadata": {"source_names": ["endoplasmic_reticulum", "er"]}},
        {"name": "golgi", "is_particle": False, "label": 5, "color": [212, 175, 55, 255], "radius": 10.0, "metadata": {"source_names": ["golgi", "golgi_apparatus"]}},
        {"name": "lysosome", "is_particle": False, "label": 6, "color": [120, 220, 140, 255], "radius": 10.0, "metadata": {"source_names": ["lysosome", "lysosomes"]}},
        {"name": "lipid-droplet", "is_particle": False, "label": 7, "color": [245, 229, 99, 255], "radius": 10.0, "metadata": {"source_names": ["lipid_droplet"]}},
        {"name": "plasma-membrane", "is_particle": False, "label": 8, "color": [214, 134, 174, 255], "radius": 10.0, "metadata": {"source_names": ["plasma_membrane", "cell_membrane"]}},
    ]


def preset_objects(preset: str) -> list[dict]:
    if preset == "bacteria":
        return bacteria_pickable_objects()
    if preset == "yeast":
        return yeast_pickable_objects()
    if preset == "hela-stress":
        return hela_stress_pickable_objects()
    raise ValueError(f"unsupported preset: {preset}")


def preset_default_object(preset: str) -> str:
    if preset == "bacteria":
        return "periplasm"
    if preset == "yeast":
        return "plasma-membrane"
    if preset == "hela-stress":
        return "mitochondria"
    raise ValueError(f"unsupported preset: {preset}")


def object_names_from_copick_config(copick_config_path: Path) -> list[str]:
    configured = []
    for obj in load_json(copick_config_path).get("pickable_objects", []):
        name = str(obj.get("name", "")).strip()
        if name and name not in configured:
            configured.append(name)
    return configured


def infer_object_name_from_path(path: Path) -> str | None:
    parts = path.stem.split("_")
    if len(parts) < 4:
        return None
    return "_".join(parts[3:]).replace("_", "-")


def latest_segmentation_records(seg_dir: Path) -> dict[str, dict]:
    records: dict[str, dict] = {}
    if not seg_dir.exists():
        return records
    for path in sorted(seg_dir.glob("*.zarr")):
        metadata = load_json_if_exists(path / ".zattrs")
        object_name = metadata.get("object_name") or infer_object_name_from_path(path)
        if not object_name:
            continue
        created_at = str(metadata.get("created_at", ""))
        previous = records.get(str(object_name))
        if previous is None or created_at >= previous["created_at"]:
            records[str(object_name)] = {
                "path": path,
                "created_at": created_at,
                "metadata": metadata,
            }
    return records


def run_object_statuses(overlay_root: Path, run_name: str, object_names: list[str]) -> dict[str, dict]:
    seg_dir = overlay_root / "ExperimentRuns" / run_name / "Segmentations"
    absence_dir = overlay_root / "ExperimentRuns" / run_name / "Absences"
    latest_segmentations = latest_segmentation_records(seg_dir)
    statuses: dict[str, dict] = {}
    for object_name in object_names:
        object_token = sanitize_token(object_name)
        absence_path = absence_dir / f"{object_token}.json"
        record = latest_segmentations.get(object_name)
        if record is not None:
            statuses[object_name] = {"status": "segmented", "path": record["path"], "metadata": record["metadata"]}
        elif absence_path.exists():
            statuses[object_name] = {"status": "absent", "path": absence_path, "metadata": load_json_if_exists(absence_path)}
        else:
            statuses[object_name] = {"status": "missing", "path": None, "metadata": {}}
    return statuses


def annotation_summary_lines(overlay_root: Path, run_name: str, object_names: list[str]) -> list[str]:
    statuses = run_object_statuses(overlay_root, run_name, object_names)
    lines = [f"Run annotation status: {run_name}"]
    for object_name in object_names:
        status = statuses[object_name]
        if status["status"] == "segmented":
            lines.append(f"saved: {object_name} ({status['path'].name})")
        elif status["status"] == "absent":
            lines.append(f"absent: {object_name}")
        else:
            lines.append(f"missing: {object_name}")

    latest_segmentations = latest_segmentation_records(overlay_root / "ExperimentRuns" / run_name / "Segmentations")
    for extra in sorted(name for name in latest_segmentations if name not in statuses):
        lines.append(f"other save: {extra} ({latest_segmentations[extra]['path'].name})")
    return lines
