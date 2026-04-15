# Legacy Quarantine

This directory contains files that were intentionally isolated from the project root because they are not part of the official ARIS runtime anymore.

## Why These Files Were Isolated

The official ARIS runtime currently starts at `main.py` and runs on top of `src/aris`.

The files moved here belong to older experiments, wake word tooling, daemon attempts, backups, or historical support material that do not participate in the current supported execution flow.

Keeping them in quarantine improves the structural readability of the repository without deleting historical material that may still be useful in the future.

## What This Means

- files in `legacy/wake/` do not belong to the current runtime path
- files in `legacy/experiments/` are not part of the supported application base
- files in `docs/legacy/` describe historical or alternative flows, not the official runtime

## Reuse Policy

These files may be reused later only as:

- separate subsystems
- migration reference
- historical documentation
- recovery material for future redesign work

They should not be treated as active runtime components unless they are deliberately reintroduced through a future scoped change.
