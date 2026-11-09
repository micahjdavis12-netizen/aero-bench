# Aero Bench

A GitHub-hosted wind-tunnel interface connected to your native Apple Silicon Mac engine. Car meshes and simulation results stay on the Mac. No scan-derived baseline assets or private access keys are published in this repository.

## Use it

Open the GitHub Pages site at https://micahjdavis12-netizen.github.io/aero-bench/.
To load cars or run new calculations, keep the full **AeroBench.app** already installed in Applications. Download the small **AeroBench Connect** launcher from the repository file `AeroBench-Connect-Mac.zip`, unzip it and put it in Applications alongside the full app. Open Connect for normal use. It reuses the existing runtime and native solver; no Python, Docker, Homebrew or Git installation is needed.

On first use macOS may require app-specific approval under Privacy & Security. Connect has ad-hoc integrity signatures but is not Apple-notarized. The Mac app opens the GitHub site with a private temporary HTTPS connection to your engine. Pair a phone through **Computer settings → Pair phone with QR**. Keep that QR/link private and keep your Mac awake.

## Small updates

Connect checks `updates/stable.json` every time it opens. Each update refers to one immutable commit and lists exact SHA-256 checksums for the allowed app-code files. An update is staged and verified before it becomes current. If a later download fails, the verified cached code remains available. Private keys, uploaded scans and run folders are not update targets.

Pushing backend or interface changes to `main` runs **Publish small Mac update**, which validates the updater and promotes a commit-pinned manifest. Normal code updates are around a hundred kilobytes. The large solver/runtime remains installed locally; replacing those native components can still require a larger release.

The one-time Connect bootstrap trusts code published to this specific repository over verified HTTPS. Protect repository write access. It does not fetch arbitrary source URLs from update metadata or disable macOS security protections.

## Hosting

The Pages workflow installs the locked JavaScript dependencies and builds the interface. It does not upload car scans, results or keys, and does not run CFD. The offline site displays a connection prompt until paired with a Mac. Model files and solved fields are fetched from authenticated backend routes.

## Native engine

The existing Mac bundle supplies OpenFOAM2412.app 2.1.2, portable arm64 Python and its model/field-processing libraries. `desktop/mac_main.py` starts that installed engine and updates the private working copy in `~/Library/AeroBench/app`. The native meshing generator uses the required `minMedialAxisAngle` setting and four solver workers. New jobs perform real meshing, solving and field export. Edited geometry does not instantly recalculate displayed forces.

The prepared GTV6 model is approximate. Ride height uses provisional source-model stance, cooling paths and wheel faces are closed, and its earlier force-stable baseline did not meet the strict residual criterion. These exploratory results are not validated engineering predictions. The native Mac engine differs from the Linux build used for that saved baseline; compare matched settings/builds and validate numerical sensitivity before relying on small aero changes.

## Development

- `web/`: responsive Three.js interface and authenticated backend transport.
- `cfd.py`, `runner.py`, `postprocess.py`: case generation, meshing, solving and solved-field export.
- `models.py`, `mesh_exports.py`: closed STL/OBJ import and GLB output.
- `server.py`, `auth.py`: protected API and one-job-at-a-time execution.
- `desktop/`: native Mac controller and fixed-repository bootstrap.
- `updates/`: small desktop update channel; `release_manifest.py` generates its pinned manifest.
- `tests/`: updater validation and rollback checks.

Run `python3 -m unittest discover -s tests`. Build the public site with `npm ci` and `python3 build_site.py`. Native execution must be checked on a real Mac; cloud-side packaging and integrity checks do not establish CFD accuracy.

The OpenFOAM engine and its source/license notices remain in the installed full Mac bundle. The app's browser dependencies retain their MIT notices. This source repository contains no redistributed solver binaries or user scan payloads.
