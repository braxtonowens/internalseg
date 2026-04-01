# Dataset 10476 Annotation Workflow

Filesystem-backed copick workflow for annotating CryoET Portal data in Napari with `nnInteractive`.

This repository is centered on the shared mammalian segmentation project used for dataset `10476`, with the same `hela` object catalog also usable for related datasets such as `10475`. Raw data is downloaded directly from the CryoET Portal, converted into a local `copick_static` tree, and annotated locally.

## Dataset 10476 Project

The built-in `hela` preset is the dataset-10476 project definition. It preserves the dataset-specific metadata and object catalog from the client config, including:

- `sample`
- `membrane`
- `coated-membrane`
- `membrane-tubule`
- `cell-wall`
- `vesicle`
- `coated-vesicle`
- `dense-vesicle`
- `transport-vesicle`
- `multilamellar-vesicle`
- `autophagosome`
- `mitochondrion`
- `mitochondrial-cristae`
- `mitochondrial-matrix`
- `mitochondrial-crystal`
- `rough-er`
- `endoplasmic-reticulum-tubular-network`
- `nuclear-envelope`
- `nuclear-lumen`
- `nuclear-pore`
- `microtubules`
- `protein-aggregate`
- `ice-contamination`
- `sputter-particle`

The default annotation target is `mitochondrion`.

## Status

This repository is usable for:
- listing Portal runs for a dataset
- bootstrapping one local single-run project
- opening tomograms in Napari
- exporting annotations and absences to a local overlay

Current limitation:
- saving a single selected instance in the export dock still needs more testing on large tomograms
- saving `All instances` is the safer path right now

## Repository Layout

- `scripts/bootstrap_local_annotation_project.py`: bootstrap one local project for a single Portal run
- `scripts/list_dataset_chunks.py`: list available Portal runs for a dataset
- `scripts/launch_napari_nninteractive.py`: open the next tomogram in Napari with the export dock
- `scripts/open_run_in_napari.py`: open a specific run for inspection
- `scripts/report_dataset_completion.py`: report segmented/absent/missing status for a local project
- `scripts/build_copick_static.py`: convert downloaded Portal-style data into local `copick_static`
- `scripts/setup_copick_project.py`: regenerate local `copick_config.json`
- `scripts/copick_project_common.py`: shared presets and overlay-status helpers
- `scripts/sync_remote_worktree.sh`: sync this repo to the shared remote checkout

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

List available runs for dataset `10476`:

```bash
python scripts/list_dataset_chunks.py --dataset-id 10476 --preset hela
```

Bootstrap one run locally:

```bash
python scripts/bootstrap_local_annotation_project.py --dataset-id 10476 --preset hela --run-id <run_id> --user-id <annotator_id>
```

Open the annotation launcher:

```bash
python scripts/launch_napari_nninteractive.py --project-config projects/dataset-10476-hela-run-<run_id>/project_config.json
```

Open the run directly:

```bash
python scripts/open_run_in_napari.py 10476-<run_id> --project-config projects/dataset-10476-hela-run-<run_id>/project_config.json
```

Check local completion:

```bash
python scripts/report_dataset_completion.py --project-config projects/dataset-10476-hela-run-<run_id>/project_config.json
```

Copy one run overlay to the remote server:

```bash
scp -r /path/to/projects/dataset-10476-hela-run-<run_id>/copick_overlay/ExperimentRuns/10476-<run_id> <remote_user>@ssh.rc.byu.edu:/grphome/grp_tomo/nobackup/archive/copick_projects/dataset-10476-hela/copick_overlay/ExperimentRuns/
```

This copies the local run overlay directory to the shared remote project.

## Remote Paths

Default shared remote locations:
- remote code checkout: `/grphome/grp_tomo/nobackup/archive/segment_sam_remote`
- remote shared projects: `/grphome/grp_tomo/nobackup/archive/copick_projects`

Sync the code to the shared remote checkout:

```bash
bash scripts/sync_remote_worktree.sh
```
