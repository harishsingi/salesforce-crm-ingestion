"""Generate synthetic CRM records. No real customer data."""
import csv, random
from pathlib import Path
random.seed(42)
def main():
    out = Path("data/raw"); out.mkdir(parents=True, exist_ok=True)
    rows = []
    for i in range(1, 101):
        rows.append({"Id": f"001{i:04d}", "Name": f"Account {i}", "LastModifiedDate": f"2026-11-{i%28+1:02d}T10:00:00Z", "IsDeleted": "false", "Amount": random.randint(1000, 90000)})
    # a duplicate re-fetch and an update, to exercise dedupe
    rows.append(dict(rows[0]))
    rows.append({**rows[1], "LastModifiedDate": "2026-11-22T10:00:00Z", "Amount": 91000})
    with open(out / "account.json", "w") as f:
        import json; json.dump(rows, f, indent=2)
    print(f"wrote {len(rows)} synthetic records")
if __name__ == "__main__":
    main()
