"""PRE to SEM: apply deletes via IsDeleted at promotion, keep history in PRE."""
import json
from pathlib import Path

def main():
    pre = json.loads(Path("data/pre/account.json").read_text())
    sem = [r for r in pre if r.get("IsDeleted") != "true"]
    Path("data/sem").mkdir(parents=True, exist_ok=True)
    Path("data/sem/account.json").write_text(json.dumps(sem, indent=2))
    print(f"PRE {len(pre)} -> SEM {len(sem)} active records, deletes applied, history kept in PRE")

if __name__ == "__main__":
    main()
