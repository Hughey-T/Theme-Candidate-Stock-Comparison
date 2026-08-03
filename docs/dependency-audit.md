# TestClient dependency audit

The collection failure was reproduced in the pre-existing global Python 3.12 environment. It contained FastAPI 0.141.1 and Starlette 1.3.1 but neither `httpx` nor `httpx2`. Starlette 1.3.1 first attempts `httpx2`, then the established `httpx` package, and emits the misleading `httpx2` installation message only when both imports fail. `httpx2` is not a dependency declared by this repository and is not needed by the supported dependency set.

The repository already declared `httpx>=0.27,<1` in the development extra and pinned `httpx==0.28.1` in CI constraints. Thus the original exception was caused by an incomplete ambient environment after the editable installation had failed at build-isolation download, not by TestClient application code. A full run with the available httpx 0.28.1 installation collected all API tests and passed.

To keep future resolution away from the unrelated Starlette 1.x transition, contract 2.0 now declares the tested TestClient window `starlette>=0.46,<0.47` and `httpx>=0.27,<0.29`; reproducible constraints pin Starlette 0.46.2 and httpx 0.28.1. The `build` frontend is also a declared development dependency. Production continues to resolve Starlette through FastAPI and does not install test-only clients.

Fresh-environment installation could not be completed in this workspace because every package-index request was rejected by its CONNECT proxy with HTTP 403, including pip itself and the PEP 517 hatchling build dependency. This is distinct from dependency resolution: CI installs the same constrained declarations on Python 3.11–3.13 and now performs `python -m build`, forced wheel installation, an out-of-tree package import, and packaged-v2-schema import.
