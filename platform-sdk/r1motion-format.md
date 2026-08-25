# `.r1motion` v1

An `.r1motion` file is a ZIP archive containing exactly five root-level files: `manifest.json`, `motion-design.json`, `trajectory.json`, `cloud-simulation-report.json`, and `preview-animation.json`. The manifest records SHA256 and byte length for every payload file. The archive itself receives a SHA256 when imported.

SHA256 detects accidental or malicious modification but does not authenticate who created the package. Teacher Bridge therefore displays: “SHA256 integrity verified; source identity is not cryptographically authenticated.” Platform approval metadata is evidence, not a cryptographic signature and not robot authorization.

The public platform may compile, simulate, preview and export this file. It has no Teacher Bridge, robot-LAN, Gateway or DDS API. Transfer to the teacher computer is manual.
