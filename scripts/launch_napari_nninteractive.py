#!/usr/bin/env python3

import argparse
import importlib.util
import json
from datetime import datetime, timezone
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import zarr

from copick_project_common import annotation_summary_lines as shared_annotation_summary_lines
from copick_project_common import object_names_from_copick_config, run_object_statuses


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_json_if_exists(path: Path) -> dict:
    if not path.exists():
        return {}
    return load_json(path)


def have_module(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def find_tomograms(static_root: Path) -> list[Path]:
    return sorted(static_root.glob("ExperimentRuns/*/VoxelSpacing*/*.zarr"))


def absence_marker_path(overlay_root: Path, tomogram: Path, object_name: str) -> Path:
    run_name = infer_run_name(tomogram)
    object_token = sanitize_token(object_name)
    return overlay_root / "ExperimentRuns" / run_name / "Absences" / f"{object_token}.json"


def has_existing_object_record(overlay_root: Path, tomogram: Path, object_name: str) -> bool:
    run_name = infer_run_name(tomogram)
    status = run_object_statuses(overlay_root, run_name, [object_name])[object_name]["status"]
    return status in {"segmented", "absent"}


def choose_tomogram(
    static_root: Path,
    overlay_root: Path,
    run_filter: str | None,
    tomogram_path: str | None,
    object_name: str,
) -> Path:
    if tomogram_path:
        path = Path(tomogram_path).expanduser()
        if not path.exists():
            raise FileNotFoundError(f"tomogram path does not exist: {path}")
        return path

    candidates = find_tomograms(static_root)
    if not candidates:
        raise FileNotFoundError(f"no tomogram zarrs found under: {static_root}")

    if run_filter:
        filtered = [p for p in candidates if run_filter in p.as_posix()]
        if not filtered:
            raise FileNotFoundError(f"no tomograms matched run filter: {run_filter}")
        return filtered[0]

    for candidate in candidates:
        if not has_existing_object_record(overlay_root, candidate, object_name):
            return candidate

    return candidates[0]


def open_level0_and_scale(tomogram: Path) -> tuple[np.ndarray, tuple[float, float, float]]:
    group = zarr.open(str(tomogram), mode="r")
    arr = np.asarray(group["0"])
    scale = (1.0, 1.0, 1.0)
    attrs = getattr(group, "attrs", {})
    multiscales = attrs.get("multiscales", []) if hasattr(attrs, "get") else []
    if multiscales:
        datasets = multiscales[0].get("datasets", [])
        if datasets:
            transforms = datasets[0].get("coordinateTransformations", [])
            for transform in transforms:
                if transform.get("type") == "scale":
                    scale_values = transform.get("scale", [])
                    if len(scale_values) == 3:
                        scale = tuple(float(v) for v in scale_values)
                        break
    return arr, scale


def robust_contrast_limits(tomogram: Path) -> tuple[float, float]:
    arr, _ = open_level0_and_scale(tomogram)
    z0 = max(0, arr.shape[0] // 2 - 8)
    z1 = min(arr.shape[0], z0 + 16)
    sample = arr[z0:z1]
    low = float(np.quantile(sample, 0.01))
    high = float(np.quantile(sample, 0.999))
    if not np.isfinite(low) or not np.isfinite(high) or low >= high:
        low = float(sample.min())
        high = float(sample.max())
    return low, high


def sanitize_token(value: str) -> str:
    token = re.sub(r"[^A-Za-z0-9-]+", "-", value.strip()).strip("-")
    return token or "segmentation"


def infer_run_name(tomogram: Path) -> str:
    return tomogram.parent.parent.name


def infer_voxel_spacing(tomogram: Path) -> str:
    name = tomogram.parent.name
    if name.startswith("VoxelSpacing"):
        return name.removeprefix("VoxelSpacing")
    return "unknown"


def segmentation_output_path(
    overlay_root: Path,
    tomogram: Path,
    user_id: str,
    session_id: str,
    object_name: str,
) -> Path:
    run_name = infer_run_name(tomogram)
    voxel_spacing = infer_voxel_spacing(tomogram)
    user_token = sanitize_token(user_id)
    session_token = sanitize_token(session_id)
    object_token = sanitize_token(object_name)
    filename = f"{voxel_spacing}_{user_token}_{session_token}_{object_token}.zarr"
    return overlay_root / "ExperimentRuns" / run_name / "Segmentations" / filename


def napari_object_layers(viewer, tomogram: Path):
    run_stem = tomogram.stem
    object_prefix = "object "
    object_layers = []
    for layer in viewer.layers:
        name = getattr(layer, "name", "")
        if name.startswith(object_prefix) and name.endswith(f" - {run_stem}"):
            try:
                index = int(name.split(" - ", 1)[0].split()[1])
            except Exception:
                continue
            display_name = name[: -len(f" - {run_stem}")]
            object_layers.append((index, display_name, layer))
    object_layers.sort(key=lambda item: item[0])
    return object_layers


def multilabel_from_viewer(viewer, tomogram: Path):
    run_stem = tomogram.stem
    semantic_name = f"semantic map - {run_stem}"
    if semantic_name in viewer.layers:
        layer = viewer.layers[semantic_name]
        return np.asarray(layer.data), semantic_name

    object_layers = napari_object_layers(viewer, tomogram)
    if object_layers:
        combined = np.zeros_like(np.asarray(object_layers[0][2].data), dtype=np.uint16)
        for index, _display_name, layer in object_layers:
            data = np.asarray(layer.data)
            combined[data != 0] = index
        return combined, "combined nnInteractive objects"

    layer = viewer.layers.selection.active
    if layer is None or getattr(layer, "_type_string", None) != "labels":
        return None, None
    return np.asarray(layer.data), getattr(layer, "name", "active labels")


def instance_choices_from_data(data: np.ndarray | None, object_layers) -> list[tuple[str, int | None]]:
    choices = [("All instances", None)]

    if object_layers:
        for index, display_name, _layer in object_layers:
            choices.append((display_name, index))
        return choices

    for instance_id in available_instance_ids(data):
        choices.append((f"Label {instance_id}", instance_id))
    return choices


def save_labels_layer_to_zarr(data: np.ndarray, export_path: Path, metadata: dict) -> None:
    if export_path.exists():
        shutil.rmtree(export_path)
    export_path.parent.mkdir(parents=True, exist_ok=True)

    shape = tuple(int(dim) for dim in data.shape)
    if len(shape) != 3:
        raise ValueError(f"unsupported label array rank: {len(shape)}")
    chunks = tuple(max(1, min(dim, target)) for dim, target in zip(shape, (1, 256, 256), strict=True))
    store = zarr.open_array(str(export_path), mode="w", shape=shape, chunks=chunks, dtype=np.uint16)

    for z0 in range(0, shape[0], chunks[0]):
        z1 = min(z0 + chunks[0], shape[0])
        for y0 in range(0, shape[1], chunks[1]):
            y1 = min(y0 + chunks[1], shape[1])
            for x0 in range(0, shape[2], chunks[2]):
                x1 = min(x0 + chunks[2], shape[2])
                store[z0:z1, y0:y1, x0:x1] = np.asarray(data[z0:z1, y0:y1, x0:x1], dtype=np.uint16)

    attrs_path = export_path / ".zattrs"
    with attrs_path.open("w", encoding="utf-8") as handle:
        json.dump(metadata, handle, indent=2)
        handle.write("\n")


def build_segmentation_metadata(tomogram: Path, export_path: Path, user_id: str, session_id: str, object_name: str) -> dict:
    return {
        "copick_segment_type": "labels",
        "run_name": infer_run_name(tomogram),
        "voxel_spacing": infer_voxel_spacing(tomogram),
        "user_id": sanitize_token(user_id),
        "session_id": sanitize_token(session_id),
        "object_name": sanitize_token(object_name),
        "source_tomogram": str(tomogram),
        "export_path": str(export_path),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def configured_object_names(copick_config_path: Path, preferred_object: str) -> list[str]:
    configured = object_names_from_copick_config(copick_config_path)
    if preferred_object not in configured:
        configured.insert(0, preferred_object)
    return configured


def annotation_summary_lines(overlay_root: Path, tomogram: Path, object_names: list[str]) -> list[str]:
    return shared_annotation_summary_lines(overlay_root, infer_run_name(tomogram), object_names)


def next_tomogram_command(selected_object_name: str) -> list[str]:
    value_flags = {"--project-config", "--copick-config", "--run", "--tomogram", "--user-id", "--session-id", "--object-name", "--plugin"}
    skip_value_flags = {"--run", "--tomogram", "--session-id", "--object-name"}
    passthrough: list[str] = []
    argv = sys.argv[1:]
    index = 0
    while index < len(argv):
        arg = argv[index]
        if "=" in arg and arg.startswith("--"):
            flag, value = arg.split("=", 1)
            if flag not in skip_value_flags:
                passthrough.append(arg)
            index += 1
            continue
        if arg in value_flags:
            if arg not in skip_value_flags:
                passthrough.append(arg)
                if index + 1 < len(argv):
                    passthrough.append(argv[index + 1])
            index += 2
            continue
        passthrough.append(arg)
        index += 1
    passthrough.extend(["--object-name", selected_object_name])
    return [sys.executable, str(Path(__file__).resolve()), *passthrough]


def available_instance_ids(data: np.ndarray | None) -> list[int]:
    if data is None:
        return []
    labels = np.unique(data)
    return [int(value) for value in labels.tolist() if int(value) != 0]


def append_single_instance(existing_data: np.ndarray | None, source_data: np.ndarray, source_instance_id: int) -> tuple[np.ndarray, int]:
    mask = source_data == source_instance_id
    if not np.any(mask):
        raise ValueError(f"instance {source_instance_id} is empty and cannot be exported")

    if existing_data is None:
        assigned_instance_id = 1
        merged = np.zeros_like(source_data, dtype=np.uint16)
    else:
        if existing_data.shape != source_data.shape:
            raise ValueError(
                f"existing export shape {existing_data.shape} does not match current labels shape {source_data.shape}"
            )
        merged = existing_data.astype(np.uint16, copy=True)
        existing_nonzero = merged[merged != 0]
        assigned_instance_id = int(existing_nonzero.max()) + 1 if existing_nonzero.size else 1

    merged[mask] = assigned_instance_id
    return merged, assigned_instance_id


def write_absence_marker(marker_path: Path, metadata: dict) -> None:
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(metadata)
    payload["record_type"] = "absence"
    payload["marked_absent"] = True
    with marker_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")


def install_save_helper(
    viewer,
    overlay_root: Path,
    tomogram: Path,
    user_id: str,
    session_id: str,
    default_object_name: str,
    object_names: list[str],
) -> None:
    from qtpy.QtWidgets import QComboBox, QLabel, QPushButton, QSizePolicy, QTextEdit, QVBoxLayout, QWidget

    panel = QWidget()
    panel.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(8, 8, 8, 8)
    layout.setSpacing(6)

    object_label = QLabel("Object class")
    layout.addWidget(object_label)

    object_combo = QComboBox()
    object_combo.addItems(object_names)
    object_combo.setCurrentText(default_object_name)
    layout.addWidget(object_combo)

    instance_label = QLabel("Instance selection")
    layout.addWidget(instance_label)

    instance_combo = QComboBox()
    layout.addWidget(instance_combo)

    refresh_button = QPushButton("Refresh Instance List")
    layout.addWidget(refresh_button)

    target_label = QLabel("")
    target_label.setWordWrap(True)
    layout.addWidget(target_label)

    summary_label = QLabel("Existing annotations for this tomogram")
    layout.addWidget(summary_label)

    summary_text = QTextEdit()
    summary_text.setReadOnly(True)
    summary_text.setMinimumHeight(160)
    layout.addWidget(summary_text)

    status_label = QLabel(
        "Default behavior is unchanged: save all instances for the selected class. "
        "Choose a single instance to append just that object into the class file."
    )
    status_label.setWordWrap(True)
    layout.addWidget(status_label)

    save_button = QPushButton("Save Selection To Copick Overlay")
    layout.addWidget(save_button)

    absent_button = QPushButton("Mark Object Absent For This Run")
    layout.addWidget(absent_button)

    next_button = QPushButton("Next Tomogram")
    layout.addWidget(next_button)

    def current_object_name() -> str:
        return object_combo.currentText().strip() or default_object_name

    def current_export_path() -> Path:
        return segmentation_output_path(overlay_root, tomogram, user_id, session_id, current_object_name())

    def current_absence_path() -> Path:
        return absence_marker_path(overlay_root, tomogram, current_object_name())

    def current_metadata(export_path: Path) -> dict:
        return build_segmentation_metadata(tomogram, export_path, user_id, session_id, current_object_name())

    def update_target_label() -> None:
        target_label.setText(
            f"Export path:\n{current_export_path()}\n\nAbsent marker:\n{current_absence_path()}"
        )

    def update_annotation_summary() -> None:
        summary_text.setPlainText("\n".join(annotation_summary_lines(overlay_root, tomogram, object_names)))

    def refresh_instance_choices() -> None:
        previous_value = instance_combo.currentData()
        object_layers = napari_object_layers(viewer, tomogram)
        data, source_name = multilabel_from_viewer(viewer, tomogram)
        choices = instance_choices_from_data(data, object_layers)

        instance_combo.blockSignals(True)
        instance_combo.clear()
        for label, value in choices:
            instance_combo.addItem(label, value)
        match_index = instance_combo.findData(previous_value)
        instance_combo.setCurrentIndex(match_index if match_index >= 0 else 0)
        instance_combo.blockSignals(False)

        if data is None:
            status_label.setText("No nnInteractive semantic/object labels layer was found to inspect.")
        else:
            count = len(object_layers) if object_layers else len(available_instance_ids(data))
            plural = "s" if count != 1 else ""
            status_label.setText(f"Ready to export from {source_name}. Found {count} labeled instance{plural}.")
        update_target_label()
        update_annotation_summary()

    def save_active_labels(event=None) -> None:
        data, source_name = multilabel_from_viewer(viewer, tomogram)
        if data is None:
            message = "No nnInteractive semantic/object labels layer was found to save."
            viewer.status = message
            status_label.setText(message)
            return

        export_path = current_export_path()
        export_path.parent.mkdir(parents=True, exist_ok=True)
        payload = current_metadata(export_path)
        payload["source_layer"] = source_name

        selected_instance_id = instance_combo.currentData()
        if selected_instance_id is None:
            export_data = np.asarray(data, dtype=np.uint16)
            payload["export_selection"] = "all-instances"
            payload["labels_present"] = available_instance_ids(export_data)
            message = f"Saved all instances from {source_name} to {export_path}"
        else:
            existing_data = None
            existing_metadata = {}
            if export_path.exists():
                existing_data = np.asarray(zarr.open_array(str(export_path), mode="r"))
                existing_metadata = load_json_if_exists(export_path / ".zattrs")
            try:
                export_data, assigned_instance_id = append_single_instance(existing_data, np.asarray(data), int(selected_instance_id))
            except ValueError as exc:
                message = str(exc)
                viewer.status = message
                status_label.setText(message)
                return

            instance_records = list(existing_metadata.get("instance_records", []))
            instance_records.append(
                {
                    "source_instance_id": int(selected_instance_id),
                    "assigned_instance_id": int(assigned_instance_id),
                    "saved_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            payload["export_selection"] = "single-instance"
            payload["source_instance_id"] = int(selected_instance_id)
            payload["assigned_instance_id"] = int(assigned_instance_id)
            payload["instance_records"] = instance_records
            payload["labels_present"] = available_instance_ids(export_data)
            message = (
                f"Appended instance {selected_instance_id} from {source_name} "
                f"as instance {assigned_instance_id} in {export_path}"
            )

        save_labels_layer_to_zarr(export_data, export_path, payload)
        viewer.status = message
        status_label.setText(message)
        refresh_instance_choices()

    def mark_object_absent(event=None) -> None:
        absence_path = current_absence_path()
        absence_path.parent.mkdir(parents=True, exist_ok=True)
        write_absence_marker(absence_path, current_metadata(current_export_path()))
        message = f"Marked object absent at {absence_path}"
        viewer.status = message
        status_label.setText(message)
        update_annotation_summary()

    def open_next_tomogram(event=None) -> None:
        command = next_tomogram_command(current_object_name())
        viewer.status = f"Opening next tomogram for {current_object_name()}"
        status_label.setText(f"Opening next tomogram for {current_object_name()}...")
        subprocess.Popen(command, cwd=str(Path.cwd()))
        viewer.close()

    object_combo.currentTextChanged.connect(lambda _: update_target_label())
    refresh_button.clicked.connect(refresh_instance_choices)
    save_button.clicked.connect(save_active_labels)
    absent_button.clicked.connect(mark_object_absent)
    next_button.clicked.connect(open_next_tomogram)
    viewer.bind_key("Ctrl-Shift-S", save_active_labels, overwrite=True)
    viewer.bind_key("Ctrl-Shift-A", mark_object_absent, overwrite=True)
    viewer.bind_key("Ctrl-Shift-N", open_next_tomogram, overwrite=True)
    viewer.window.add_dock_widget(panel, area="right", name="Copick Export")
    refresh_instance_choices()
    update_annotation_summary()
    viewer.status = f"Copick export ready: {current_export_path()}"


def default_session_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def parse_args() -> argparse.Namespace:
    cwd = Path.cwd()
    parser = argparse.ArgumentParser(description="Launch napari for a local copick project intended for nninteractive.")
    parser.add_argument(
        "--project-config",
        default=str(cwd / "project_config.json"),
        help="Path to project settings JSON.",
    )
    parser.add_argument(
        "--copick-config",
        default=None,
        help="Override path to copick_config.json.",
    )
    parser.add_argument(
        "--regen-config",
        action="store_true",
        help="Regenerate copick_config.json with setup_copick_project.py before launching.",
    )
    parser.add_argument(
        "--run",
        default=None,
        help="Substring to match in the run path, for example 10202-mba2012-04-23-12.",
    )
    parser.add_argument(
        "--tomogram",
        default=None,
        help="Explicit path to a tomogram .zarr store.",
    )
    parser.add_argument(
        "--user-id",
        default="braxton",
        help="User identifier to embed in the suggested copick segmentation filename.",
    )
    parser.add_argument(
        "--session-id",
        default=default_session_id(),
        help="Session identifier to embed in the suggested copick segmentation filename.",
    )
    parser.add_argument(
        "--object-name",
        default=None,
        help="Object or label name to embed in the suggested copick segmentation filename.",
    )
    parser.add_argument(
        "--plugin",
        default=None,
        help="Optional napari reader plugin name override.",
    )
    parser.add_argument(
        "--raw-display",
        action="store_true",
        help="Open the tomogram without applying robust contrast limits.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the resolved paths and checks without launching napari.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_config_path = Path(args.project_config).expanduser()
    if not project_config_path.exists():
        print(f"error: project config not found: {project_config_path}", file=sys.stderr)
        return 2

    project_config = load_json(project_config_path)
    if args.user_id == "braxton":
        args.user_id = project_config.get("default_user_id", args.user_id)
    if args.object_name is None:
        args.object_name = project_config.get("default_object_name", "periplasm")
    copick_config_path = Path(
        args.copick_config or project_config.get("config_path", Path.cwd() / "copick_config.json")
    ).expanduser()
    static_root = Path(project_config["static_root"]).expanduser()
    overlay_root = Path(project_config["overlay_root"]).expanduser()

    if args.regen_config:
        setup_script = Path(__file__).resolve().parent / "setup_copick_project.py"
        result = subprocess.run([sys.executable, str(setup_script)], check=False)
        if result.returncode != 0:
            return result.returncode

    print(f"copick config: {copick_config_path}")
    print(f"static root: {static_root}")
    print(f"overlay root: {overlay_root}")

    if not static_root.exists():
        print(f"error: static root does not exist: {static_root}", file=sys.stderr)
        return 2
    if not copick_config_path.exists():
        print(
            "error: copick config does not exist. Run `conda run -n napari-env python scripts/setup_copick_project.py` first.",
            file=sys.stderr,
        )
        return 2

    required_modules = {"napari": "napari", "nninteractive": "nnInteractive", "copick": "copick"}
    missing = [label for label, module_name in required_modules.items() if not have_module(module_name)]
    if missing:
        print("missing packages:", ", ".join(missing), file=sys.stderr)
        print("hint: install them into the same environment, then rerun this launcher.", file=sys.stderr)
        return 2

    try:
        tomogram = choose_tomogram(static_root, overlay_root, args.run, args.tomogram, args.object_name)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(f"tomogram: {tomogram}")
    export_path = segmentation_output_path(overlay_root, tomogram, args.user_id, args.session_id, args.object_name)
    export_path.parent.mkdir(parents=True, exist_ok=True)
    absence_path = absence_marker_path(overlay_root, tomogram, args.object_name)
    absence_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"segmentation export: {export_path}")
    print(f"absence marker: {absence_path}")

    os.environ["COPICK_CONFIG_PATH"] = str(copick_config_path)
    os.environ["COPICK_STATIC_ROOT"] = str(static_root)
    os.environ["COPICK_OVERLAY_ROOT"] = str(overlay_root)

    if args.dry_run:
        print("dry-run: environment checks passed, not launching napari.")
        return 0

    import napari

    viewer = napari.Viewer()
    image, voxel_scale = open_level0_and_scale(tomogram)
    image_layer = viewer.add_image(image, name=tomogram.stem, scale=voxel_scale)

    if not args.raw_display:
        low, high = robust_contrast_limits(tomogram)
        image_layer.contrast_limits = (low, high)
        print(f"contrast limits: ({low:.3f}, {high:.3f})")

    object_names = configured_object_names(copick_config_path, args.object_name)
    viewer.window.add_plugin_dock_widget("napari-nninteractive", "nnInteractive")
    install_save_helper(
        viewer,
        overlay_root=overlay_root,
        tomogram=tomogram,
        user_id=args.user_id,
        session_id=args.session_id,
        default_object_name=args.object_name,
        object_names=object_names,
    )

    napari.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
