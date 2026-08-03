# Sample catalogue

These compact scenario descriptors are intentionally small. The executable payload construction and mutation for every descriptor lives in `tests/`; this prevents a large, fragile duplicate corpus. `test_sample_catalogue` guarantees that every required descriptor remains present and that invalid descriptors are marked invalid.

`valid/v2-blind-session.json` is the preferred 2.0 pipeline intake. It deliberately contains no upstream rank in the blind projection; reconciliation data is sealed until the independent-AI freeze.
