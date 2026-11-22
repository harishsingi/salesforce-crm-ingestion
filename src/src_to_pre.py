"""SRC to PRE: dedupe on record Id, keep latest timestamp, load each Id once."""
import json
from pathlib import Path

def dedupe(records):
    best = {}
    for r in records:
        key = r["Id"]
        if key not in best or r["LastModifiedDate"] >= best[key]["LastModifiedDate"]:
            best[key] = r
    return sorted(best.values(), key=lambda r: r["Id"])

def main():
    src = json.loads(Path("data/raw/account.json").read_text())
    pre = dedupe(src)
    Path("data/pre").mkdir(parents=True, exist_ok=True)
    Path("data/pre/account.json").write_text(json.dumps(pre, indent=2))
    print(f"SRC {len(src)} -> PRE {len(pre)} unique records")

if __name__ == "__main__":
    main()
