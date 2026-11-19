"""Temporary: prints where the time of a browser request goes, from the files of SKAT_E2E_TIMING_DIR (item 712)."""

import json
import sys
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlsplit


def percentile(values: list[float], share: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(share * len(ordered)))] if ordered else float("nan")


def summary(label: str, values: list[float]) -> None:
    print(f"{label:55s} n={len(values):6d} p50={percentile(values, .5):7.0f} p95={percentile(values, .95):7.0f} p99={percentile(values, .99):7.0f} max={max(values, default=float('nan')):7.0f}")


def main(directory: Path) -> None:
    rows = [json.loads(line) for path in directory.glob("*.jsonl") for line in path.read_text().splitlines()]
    app_by_target = defaultdict(list)
    routes = defaultdict(list)
    for row in rows:
        if row["kind"] == "app":
            app_by_target[(row["pid"], row["target"], row["method"])].append(row)
        elif row["kind"] == "route":
            routes[(row["pid"], row["url"])].append(row)
    gaps = defaultdict(lambda: defaultdict(list))
    for row in rows:
        if row["kind"] != "browser":
            continue
        parts = urlsplit(row["url"])
        target = parts.path + (f"?{parts.query}" if parts.query else "")
        candidates = app_by_target[(row["pid"], target, row["method"])]
        routed = routes[(row["pid"], row["url"])]
        group = "app-asset" if parts.path.startswith("/_app/") else "routed"
        for app in candidates:
            if row["sent"] / 1000 - 0.05 <= app["entry"] <= row["first_byte"] / 1000:
                gaps[group]["browser send -> app entry"].append((app["entry"] - row["sent"] / 1000) * 1000)
                gaps[group]["app entry -> app response start"].append((app["start"] - app["entry"]) * 1000)
                gaps[group]["app response start -> browser first byte"].append(row["first_byte"] - app["start"] * 1000)
                candidates.remove(app)
                break
        for route in routed:
            if route["entry"] <= row["first_byte"] / 1000:
                gaps[group]["route duration"].append((route["exit"] - route["entry"]) * 1000)
                gaps[group]["browser send -> route entry"].append((route["entry"] - row["sent"] / 1000) * 1000)
                routed.remove(route)
                break
        gaps[group]["browser send -> first byte"].append(row["first_byte"] - row["sent"])
    for group, measures in sorted(gaps.items()):
        print(f"== {group} (ms)")
        for label, values in measures.items():
            summary(label, values)
    summary("server loop lag over 50 ms (ms)", [row["lag_ms"] for row in rows if row["kind"] == "loop_lag"])
    stalls = [row for row in rows if row["kind"] == "stall"]
    print(f"stalls over 300 ms: {len(stalls)}")
    for row in stalls[:12]:
        print(json.dumps({key: row[key] for key in ("stale_ms", "loop_cpu_ms_since_beat", "watchdog_tick_ms", "main_cpu_ms_in_tick")}))
    summary("stalls: stale ms", [row["stale_ms"] for row in stalls])
    summary("stalls: main thread cpu ms in the stalled tick", [row["main_cpu_ms_in_tick"] for row in stalls])
    summary("stalls: loop thread cpu ms since beat", [row["loop_cpu_ms_since_beat"] for row in stalls])
    summary("stalls: watchdog tick ms", [row["watchdog_tick_ms"] for row in stalls])
    garbage = [row for row in rows if row["kind"] == "gc"]
    summary("gc over 50 ms (ms)", [row["ms"] for row in garbage])
    print("gc generations over 50 ms:", {generation: sum(row["generation"] == generation for row in garbage) for generation in (0, 1, 2)})
    print(f"lag events: {sum(row['kind'] == 'loop_lag' for row in rows)}; browser requests: {sum(row['kind'] == 'browser' for row in rows)}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
