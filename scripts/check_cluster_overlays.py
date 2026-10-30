#!/usr/bin/env python3
"""Guard the ignoreMissingValueFiles footgun.

Argo renders with values/clusters/<cluster>/<chart-basename>.yaml and silently
skips a missing overlay file. A typo'd overlay name therefore *looks* applied
but never is. This check fails CI when any overlay does not match a chart
directory basename, or when a chart directory is malformed.
"""
import pathlib
import sys


def main() -> int:
    root = pathlib.Path(".")
    charts = {p.parent.name for p in root.glob("charts/*/*/Chart.yaml")}
    if not charts:
        print("error: no charts found under charts/<tier>/<name>/", file=sys.stderr)
        return 1

    errors: list[str] = []
    checked = 0

    clusters_dir = root / "values" / "clusters"
    if clusters_dir.is_dir():
        for cluster in sorted(p for p in clusters_dir.iterdir() if p.is_dir()):
            overlays = sorted(cluster.glob("*.yaml"))
            if not overlays:
                print(f"warning: values/clusters/{cluster.name}/ is empty", file=sys.stderr)
            for overlay in overlays:
                checked += 1
                if overlay.stem not in charts:
                    errors.append(
                        f"{overlay}: no chart named '{overlay.stem}' "
                        f"(charts: {', '.join(sorted(charts))}) — overlay would be SILENTLY IGNORED"
                    )

    for tier in sorted(p for p in (root / "charts").iterdir() if p.is_dir()):
        for chart in sorted(p for p in tier.iterdir() if p.is_dir()):
            if not (chart / "Chart.yaml").exists():
                errors.append(f"{chart}: directory under charts/ without Chart.yaml")

    for e in errors:
        print(f"error: {e}", file=sys.stderr)
    if errors:
        return 1

    print(f"ok: {checked} overlay(s) match charts {sorted(charts)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
