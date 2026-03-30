#!/usr/bin/env python3

import json
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from copick_project_common import save_json


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def ssh_target(remote_user: str, remote_host: str) -> str:
    return f"{remote_user}@{remote_host}"


def capture_command(cmd: list[str]) -> str:
    with tempfile.NamedTemporaryFile(mode="w+", encoding="utf-8") as handle:
        subprocess.run(cmd, check=True, stdout=handle, text=True)
        handle.flush()
        handle.seek(0)
        return handle.read()


def registry_path(remote_projects_root: str, dataset_id: str, preset: str) -> str:
    root = remote_projects_root.rstrip("/")
    return f"{root}/dataset-{dataset_id}-{preset}/chunk_registry.json"


def dataset_chunks(run_names: list[str], chunk_size: int) -> list[list[str]]:
    return [run_names[index:index + chunk_size] for index in range(0, len(run_names), chunk_size)]


def load_remote_registry(remote_user: str, remote_host: str, registry_file: str) -> dict | None:
    script = f"if [ -f '{registry_file}' ]; then cat '{registry_file}'; fi"
    output = capture_command(["ssh", ssh_target(remote_user, remote_host), script]).strip()
    if not output:
        return None
    return json.loads(output)


def save_remote_registry(remote_user: str, remote_host: str, registry_file: str, payload: dict, dry_run: bool = False) -> int:
    local_tmp = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".json", delete=False) as handle:
            local_tmp = Path(handle.name)
        save_json(local_tmp, payload)
        cmd = ["scp", str(local_tmp), f"{ssh_target(remote_user, remote_host)}:{registry_file}"]
        print("command:", " ".join(cmd))
        if dry_run:
            return 0
        return subprocess.run(cmd, check=False).returncode
    finally:
        if local_tmp and local_tmp.exists():
            local_tmp.unlink()


def build_registry(dataset_id: str, preset: str, run_names: list[str], chunk_size: int) -> dict:
    chunks = dataset_chunks(run_names, chunk_size)
    return {
        "dataset_id": str(dataset_id),
        "preset": preset,
        "chunk_size": int(chunk_size),
        "chunk_count": len(chunks),
        "run_count": len(run_names),
        "updated_at": now_utc(),
        "chunks": [
            {
                "chunk_index": index,
                "selected_runs": chunk,
                "status": "available",
                "assigned_user": None,
                "started_at": None,
                "completed_at": None,
            }
            for index, chunk in enumerate(chunks, start=1)
        ],
    }


def ensure_registry_matches(existing: dict, dataset_id: str, preset: str, run_names: list[str], chunk_size: int) -> dict:
    expected = build_registry(dataset_id, preset, run_names, chunk_size)
    if str(existing.get("dataset_id")) != str(dataset_id):
        raise SystemExit("error: remote chunk registry dataset_id does not match request")
    if str(existing.get("preset")) != str(preset):
        raise SystemExit("error: remote chunk registry preset does not match request")
    if int(existing.get("chunk_size", 0)) != int(chunk_size):
        raise SystemExit(f"error: remote chunk registry uses chunk_size={existing.get('chunk_size')} not {chunk_size}")
    existing_chunks = existing.get("chunks", [])
    expected_chunks = expected.get("chunks", [])
    if len(existing_chunks) != len(expected_chunks):
        raise SystemExit("error: remote chunk registry no longer matches the dataset run layout")
    for old, new in zip(existing_chunks, expected_chunks, strict=True):
        if old.get("selected_runs") != new.get("selected_runs"):
            raise SystemExit("error: remote chunk registry no longer matches the dataset run layout")
    return existing
