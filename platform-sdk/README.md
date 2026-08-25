# Platform SDK

This directory is the complete handoff to the existing public teaching platform: JSON Schema 2020-12 contracts, simulation OpenAPI, Python and TypeScript clients, preview format and `.r1motion` reference packaging.

Regenerate derived contracts with `python platform-sdk/generate.py`. Public clients intentionally expose only compile/simulate/report/preview operations. No robot-LAN, Teacher Bridge, Gateway, RPC or DDS access exists in either SDK.
