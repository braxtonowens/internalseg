# Segment SAM Workflow

Small-script workflow for cryoET annotation in Napari with `nnInteractive`.

Raw data comes from the CryoET Portal. Local projects are built as filesystem-backed copick projects. Finished annotations are uploaded into a shared remote overlay and tracked by chunk.

## Status

This repository is usable for:
- listing Portal dataset chunks
- bootstrapping a local chunk project
- opening tomograms in Napari
- exporting annotations and absences to a local overlay
- finalizing local work into the shared remote project

Current limitation:
- saving a single selected instance in the export dock still needs more testing on large tomograms
- saving `All instances` is the safer path right now

## Repository layout

- `scripts/bootstrap_local_annotation_project.py`: bootstrap one local project chunk from the CryoET Portal
- `scripts/list_dataset_chunks.py`: show chunk boundaries for a dataset
- `scripts/launch_napari_nninteractive.py`: open the next tomogram in Napari with the export dock
- `scripts/open_run_in_napari.py`: open a specific run for inspection
- `scripts/report_dataset_completion.py`: report segmented/absent/missing status for a local project
- `scripts/finalize_annotation_project.py`: upload overlay files and update the remote chunk registry
- `scripts/build_copick_static.py`: convert downloaded Portal-style data into local `copick_static`
- `scripts/setup_copick_project.py`: regenerate local `copick_config.json`
- `scripts/copick_project_common.py`: shared preset and overlay-status helpers
- `scripts/chunk_registry_common.py`: shared chunk-registry helpers
- `scripts/sync_remote_worktree.sh`: sync this repo to the shared remote checkout

## Presets

Current built-in presets:
- `bacteria`
- `yeast`
- `hela-stress`

The `hela-stress` preset is just a starting guess and is expected to change.

## Environment

Create the Conda environment:

```bash
conda env create -f environment.yml
conda activate segment-sam
```

Install AWS CLI separately and make sure `aws` is on your `PATH`.

Check the key tools:

```bash
python --version
aws --version
```

## Workflow

List chunks:

```bash
python scripts/list_dataset_chunks.py --dataset-id 10475 --preset hela-stress --chunk-size 5
```

Bootstrap one chunk locally:

```bash
python scripts/bootstrap_local_annotation_project.py --dataset-id 10475 --preset hela-stress --chunk-size 5 --chunk-index 1 --user-id <annotator_id>
```

Open the annotation launcher:

```bash
python scripts/launch_napari_nninteractive.py --project-config /path/to/projects/dataset-10475-hela-stress-chunk-001-of-043/project_config.json
```

Open a specific run directly:

```bash
python scripts/open_run_in_napari.py 10475-20221005_P1_ts_002 --project-config /path/to/projects/dataset-10475-hela-stress-chunk-001-of-043/project_config.json
```

Check local completion:

```bash
python scripts/report_dataset_completion.py --project-config /path/to/projects/dataset-10475-hela-stress-chunk-001-of-043/project_config.json
```

Finalize and upload:

```bash
python scripts/finalize_annotation_project.py --project-config /path/to/projects/dataset-10475-hela-stress-chunk-001-of-043/project_config.json
```

## Remote paths

Default shared remote locations:
- remote code checkout: `/grphome/grp_tomo/nobackup/archive/segment_sam_remote`
- remote shared projects: `/grphome/grp_tomo/nobackup/archive/copick_projects`

Sync the code to the shared remote checkout:

```bash
bash scripts/sync_remote_worktree.sh
```
