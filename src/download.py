"""Glue downloader sketch: call the CRM API, land JSON raw per object.
In production this is a Glue job; here it reads the synthetic generator output
so the pipeline runs locally without credentials."""
import argparse, json
from pathlib import Path

def main():
    p = argparse.ArgumentParser(); p.add_argument("--object", default="Account"); p.add_argument("--out", default="data/raw")
    a = p.parse_args()
    print(f"downloader: object={a.object}, landing JSON raw to {a.out} (synthetic, no API call in this portfolio version)")

if __name__ == "__main__":
    main()
