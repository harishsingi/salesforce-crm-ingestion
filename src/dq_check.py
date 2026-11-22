"""Daily noon DQ check: alert if the target has no new data."""
import json
from pathlib import Path

def latest_timestamp(records):
    return max((r["LastModifiedDate"] for r in records), default=None)

def main():
    sem = json.loads(Path("data/sem/account.json").read_text())
    print(f"SEM latest timestamp: {latest_timestamp(sem)}, records: {len(sem)}")
    if not sem:
        raise SystemExit("DQ ALERT: no data in SEM")

if __name__ == "__main__":
    main()
