#!/usr/bin/env python3

import copy
import json
import re
from pathlib import Path


HELA_STRESS_TEMPLATE = {'dataset_ids': [10473, 10474, 10475, 10476],
 'description': 'This copick project contains data from datasets (10476,).',
 'name': 'CZ cryoET Data Portal Dataset',
 'pickable_objects': [{'color': [255, 225, 25, 255],
                       'emdb_id': None,
                       'identifier': 'CDPO:0000001',
                       'is_particle': False,
                       'label': 1,
                       'map_threshold': None,
                       'name': 'sample',
                       'pdb_id': None,
                       'radius': 50.0},
                      {'color': [0, 255, 0, 255],
                       'emdb_id': None,
                       'identifier': 'GO:0016020',
                       'is_particle': False,
                       'label': 2,
                       'map_threshold': None,
                       'name': 'membrane',
                       'pdb_id': None,
                       'radius': 50.0},
                      {'color': [60, 180, 75, 255],
                       'emdb_id': None,
                       'identifier': 'GO:0048475',
                       'is_particle': False,
                       'label': 3,
                       'map_threshold': None,
                       'name': 'coated-membrane',
                       'pdb_id': None,
                       'radius': 50.0},
                      {'color': [0, 210, 140, 255],
                       'emdb_id': None,
                       'identifier': 'GO:0031974',
                       'is_particle': False,
                       'label': 4,
                       'map_threshold': None,
                       'name': 'membrane-tubule',
                       'pdb_id': None,
                       'radius': 50.0},
                      {'color': [170, 110, 40, 255],
                       'emdb_id': None,
                       'identifier': 'GO:0005618',
                       'is_particle': False,
                       'label': 5,
                       'map_threshold': None,
                       'name': 'cell-wall',
                       'pdb_id': None,
                       'radius': 50.0},
                      {'color': [255, 165, 0, 255],
                       'emdb_id': None,
                       'identifier': 'GO:0031982',
                       'is_particle': False,
                       'label': 6,
                       'map_threshold': None,
                       'name': 'vesicle',
                       'pdb_id': None,
                       'radius': 50.0},
                      {'color': [255, 69, 0, 255],
                       'emdb_id': None,
                       'identifier': 'coated-vesicle',
                       'is_particle': False,
                       'label': 7,
                       'map_threshold': None,
                       'name': 'coated-vesicle',
                       'pdb_id': None,
                       'radius': 50.0},
                      {'color': [210, 105, 30, 255],
                       'emdb_id': None,
                       'identifier': None,
                       'is_particle': False,
                       'label': 8,
                       'map_threshold': None,
                       'name': 'dense-vesicle',
                       'pdb_id': None,
                       'radius': 50.0},
                      {'color': [245, 130, 48, 255],
                       'emdb_id': None,
                       'identifier': 'GO:0030133',
                       'is_particle': False,
                       'label': 9,
                       'map_threshold': None,
                       'name': 'transport-vesicle',
                       'pdb_id': None,
                       'radius': 50.0},
                      {'color': [230, 190, 50, 255],
                       'emdb_id': None,
                       'identifier': None,
                       'is_particle': False,
                       'label': 10,
                       'map_threshold': None,
                       'name': 'multilamellar-vesicle',
                       'pdb_id': None,
                       'radius': 50.0},
                      {'color': [50, 205, 50, 255],
                       'emdb_id': None,
                       'identifier': 'GO:0005776',
                       'is_particle': False,
                       'label': 11,
                       'map_threshold': None,
                       'name': 'autophagosome',
                       'pdb_id': None,
                       'radius': 50.0},
                      {'color': [255, 0, 0, 255],
                       'emdb_id': None,
                       'identifier': 'GO:0005739',
                       'is_particle': False,
                       'label': 12,
                       'map_threshold': None,
                       'name': 'mitochondrion',
                       'pdb_id': None,
                       'radius': 50.0},
                      {'color': [220, 20, 60, 255],
                       'emdb_id': None,
                       'identifier': 'GO:0030061',
                       'is_particle': False,
                       'label': 13,
                       'map_threshold': None,
                       'name': 'mitochondrial-cristae',
                       'pdb_id': None,
                       'radius': 50.0},
                      {'color': [178, 34, 34, 255],
                       'emdb_id': None,
                       'identifier': 'GO:0005759',
                       'is_particle': False,
                       'label': 14,
                       'map_threshold': None,
                       'name': 'mitochondrial-matrix',
                       'pdb_id': None,
                       'radius': 50.0},
                      {'color': [255, 99, 71, 255],
                       'emdb_id': None,
                       'identifier': None,
                       'is_particle': False,
                       'label': 15,
                       'map_threshold': None,
                       'name': 'mitochondrial-crystal',
                       'pdb_id': None,
                       'radius': 50.0},
                      {'color': [138, 43, 226, 255],
                       'emdb_id': None,
                       'identifier': 'GO:0005791',
                       'is_particle': False,
                       'label': 16,
                       'map_threshold': None,
                       'name': 'rough-er',
                       'pdb_id': None,
                       'radius': 50.0},
                      {'color': [186, 85, 211, 255],
                       'emdb_id': None,
                       'identifier': 'GO:0071782',
                       'is_particle': False,
                       'label': 17,
                       'map_threshold': None,
                       'name': 'endoplasmic-reticulum-tubular-network',
                       'pdb_id': None,
                       'radius': 50.0},
                      {'color': [75, 0, 130, 255],
                       'emdb_id': None,
                       'identifier': 'GO:0005635',
                       'is_particle': False,
                       'label': 18,
                       'map_threshold': None,
                       'name': 'nuclear-envelope',
                       'pdb_id': None,
                       'radius': 50.0},
                      {'color': [123, 104, 238, 255],
                       'emdb_id': None,
                       'identifier': 'GO:0031981',
                       'is_particle': False,
                       'label': 19,
                       'map_threshold': None,
                       'name': 'nuclear-lumen',
                       'pdb_id': None,
                       'radius': 50.0},
                      {'color': [148, 103, 189, 255],
                       'emdb_id': None,
                       'identifier': 'GO:0005643',
                       'is_particle': False,
                       'label': 20,
                       'map_threshold': None,
                       'name': 'nuclear-pore',
                       'pdb_id': None,
                       'radius': 50.0},
                      {'color': [0, 0, 255, 255],
                       'emdb_id': None,
                       'identifier': 'GO:0005874',
                       'is_particle': False,
                       'label': 21,
                       'map_threshold': None,
                       'name': 'microtubules',
                       'pdb_id': None,
                       'radius': 50.0},
                      {'color': [255, 20, 147, 255],
                       'emdb_id': None,
                       'identifier': 'CDPO:0000020',
                       'is_particle': False,
                       'label': 22,
                       'map_threshold': None,
                       'name': 'protein-aggregate',
                       'pdb_id': None,
                       'radius': 50.0},
                      {'color': [0, 191, 255, 255],
                       'emdb_id': None,
                       'identifier': 'CDPO:0000014',
                       'is_particle': False,
                       'label': 23,
                       'map_threshold': None,
                       'name': 'ice-contamination',
                       'pdb_id': None,
                       'radius': 50.0},
                      {'color': [230, 25, 75, 255],
                       'emdb_id': None,
                       'identifier': 'CDPO:0000015',
                       'is_particle': False,
                       'label': 24,
                       'map_threshold': None,
                       'name': 'sputter-particle',
                       'pdb_id': None,
                       'radius': 50.0}],
 'version': '1.19.0'}


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


def bacteria_template() -> dict:
    return {
        "name": "Bacteria Annotation Project",
        "description": "Local annotation project using the bacteria class preset.",
        "version": "1.20.0",
        "pickable_objects": bacteria_pickable_objects(),
    }


def yeast_template() -> dict:
    return {
        "name": "Yeast Annotation Project",
        "description": "Local annotation project using the yeast class preset.",
        "version": "1.20.0",
        "pickable_objects": yeast_pickable_objects(),
    }


def hela_stress_template() -> dict:
    return copy.deepcopy(HELA_STRESS_TEMPLATE)


def preset_template(preset: str) -> dict:
    if preset == "bacteria":
        return bacteria_template()
    if preset == "yeast":
        return yeast_template()
    if preset == "hela":
        return hela_stress_template()
    raise ValueError(f"unsupported preset: {preset}")


def preset_objects(preset: str) -> list[dict]:
    return list(preset_template(preset).get("pickable_objects", []))


def preset_default_object(preset: str) -> str:
    if preset == "bacteria":
        return "periplasm"
    if preset == "yeast":
        return "plasma-membrane"
    if preset == "hela":
        return "mitochondrion"
    raise ValueError(f"unsupported preset: {preset}")


def preset_project_name(preset: str) -> str:
    return str(preset_template(preset).get("name", f"{preset.title()} Annotation Project"))


def preset_description(preset: str) -> str:
    return str(preset_template(preset).get("description", f"Local annotation project using the {preset} class preset."))


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
