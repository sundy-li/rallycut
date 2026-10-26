# BlurBall vendored source

- Source: https://github.com/cogsys-tuebingen/blurball
- Commit: `2f0f5496f7ba4b5b1a36790749935121b2ce972d`
- `network.py` is the unmodified upstream `src/models/blurball.py`.
- `config.json` is a JSON transcription of upstream `src/configs/model/blurball.yaml` (architecture fields only).
- Upstream `LICENSE.md` (MIT, Copyright 2023 NTT Communications Corporation) is retained verbatim.
- The network source also retains Microsoft / HRNet author notices. See `HRNET-LICENSE` for the referenced HRNet project's MIT license.
- Citation: Gossard, Radovic, Ziegler, Zell. *BlurBall: Joint Ball and Motion Blur Estimation for Table Tennis Ball Tracking*, CVSports / CVPRW 2026. https://arxiv.org/abs/2509.18387

## MPS pipeline adaptation

RallyCut's adapter (`pretrained.py`, `inference_pipeline.py`, `neural_analysis.py`) incorporates streaming/batching/pipeline ideas and code structure from sundyli's local BlurBall fork, base commit `108e4f3902d3665a8cdb6ab637c1b3946e929b4e` plus the inspected uncommitted working tree. At final verification these exact working-tree files had been committed by their author as `f895ffdce459bf9ae0bfb5a0cb4ef5d1746ee5fc`; the file hashes remained unchanged. Exact input file hashes are recorded in RallyCut's `models/manifest.json`. The local checkout is not modified and is not a runtime dependency. `network.py` and the checkpoint architecture remain identical. RGB/affine coordinates and safe checkpoint loading are deliberately retained rather than copying the fork's BGR shortcut / unrestricted checkpoint loading. FP16 is opt-in, not an unverified default.

## Weights are separate

Official `blurball_best` was downloaded locally from the authors' Nextcloud link in their README. The file is **not vendored, embedded or committed**. SHA-256: `3545206c7155194ea654899d33579c88c9fd8e82c632cbdbae3b0c0ec3f2985f`.

The MIT source license does not by itself establish explicit independent weight / dataset redistribution terms. No such terms were visible in the official shared weight directory at review time. This integration permits explicit local installation for evaluation, not a claim of cleared commercial redistribution. Confirm permission / terms with the authors before a bundled release.
