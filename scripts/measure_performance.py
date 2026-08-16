import argparse
import csv
from datetime import date, timedelta
from pathlib import Path
import statistics
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from campus_lost_found import Store


def main() -> None:
    parser = argparse.ArgumentParser(description="Measure real SQLite search/filter timings")
    parser.add_argument("--runs", type=int, default=100)
    parser.add_argument("--rows", type=int, default=1000)
    parser.add_argument("--output", default=str(ROOT / "evidence" / "performance" / "PERF_Search_Filter_Timing.csv"))
    args = parser.parse_args()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as temp_dir:
        store = Store(Path(temp_dir) / "performance.db")
        store.init_db()
        user = store.register("Performance Fixture", "performance@example.edu", "Benchmark1!")
        categories = ["Electronics", "Bag", "Books", "Bottle"]
        locations = ["Main Library", "Building A", "Cafeteria", "Sports Hall"]
        base_date = date(2026, 1, 1)
        now = "2026-08-16T00:00:00+00:00"
        with store.connect() as connection:
            connection.executemany(
                """INSERT INTO reports(report_type,item_name,category,location,event_date,description,status,owner_id,created_at)
                   VALUES(?,?,?,?,?,?,'Active',?,?)""",
                [
                    (
                        "LOST" if index % 2 == 0 else "FOUND",
                        f"Demo item {index}",
                        categories[index % len(categories)],
                        locations[index % len(locations)],
                        (base_date + timedelta(days=index % 220)).isoformat(),
                        f"Searchable benchmark description {index}",
                        user["id"],
                        now,
                    )
                    for index in range(args.rows)
                ],
            )

        measurements = []
        for run in range(1, args.runs + 1):
            started = time.perf_counter()
            results = store.list_reports(
                keyword="benchmark",
                category="Electronics",
                location="Main Library",
                start_date="2026-01-01",
                end_date="2026-08-08",
            )
            elapsed_ms = (time.perf_counter() - started) * 1000
            measurements.append((run, elapsed_ms, len(results)))

    sorted_times = sorted(row[1] for row in measurements)
    p95 = sorted_times[max(0, int(len(sorted_times) * 0.95) - 1)]
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["environment", "local SQLite demo benchmark"])
        writer.writerow(["dataset_rows", args.rows])
        writer.writerow(["runs", args.runs])
        writer.writerow(["nfr_target_ms", 3000])
        writer.writerow(["average_ms", f"{statistics.mean(sorted_times):.3f}"])
        writer.writerow(["p95_ms", f"{p95:.3f}"])
        writer.writerow([])
        writer.writerow(["run", "elapsed_ms", "result_count"])
        for run, elapsed_ms, count in measurements:
            writer.writerow([run, f"{elapsed_ms:.3f}", count])
    print(f"Performance evidence written: {output}")
    print(f"Average {statistics.mean(sorted_times):.3f} ms; p95 {p95:.3f} ms; target <= 3000 ms")


if __name__ == "__main__":
    main()

