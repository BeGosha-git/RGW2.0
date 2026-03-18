"""
Upgrade system entry point.

Delegates to update.py which contains the full implementation.

Usage:
    python3 upgrade.py                     # normal update (version-gated)
    python3 upgrade.py --force             # force update, ignore version
    python3 upgrade.py --force --ip <IP>   # force update from specific IP
"""

from __future__ import annotations

from update import check_and_update_version, update_system

__all__ = ["check_and_update_version", "update_system"]


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="RGW2 system updater")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Ignore version comparison and force update from remote robot",
    )
    parser.add_argument(
        "--ip",
        default=None,
        metavar="IP",
        help="Force update from this specific IP address (implies --force)",
    )
    args = parser.parse_args()
    force = args.force or bool(args.ip)
    update_system(force=force, source_ip=args.ip)
