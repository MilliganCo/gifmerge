# Changelog

## 2026-07-07 — repository audit

- Confirmed inspected current files contain no observed secrets or API configuration.
- Classified project as a small public utility candidate after full-history scan.
- Documented optional ffmpeg/imageio fallback behavior.

## Current version

- Folder picker for GIF inputs.
- GIF merge with shuffled order and reduced adjacent duplicates.
- Preserves frame durations where possible.
- Falls back to ffmpeg when Pillow cannot decode a GIF.
