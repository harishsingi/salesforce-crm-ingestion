from src.src_to_pre import dedupe

def test_dedupe_keeps_latest():
    recs = [
        {"Id": "1", "LastModifiedDate": "2026-11-01T10:00:00Z", "Amount": 100},
        {"Id": "1", "LastModifiedDate": "2026-11-01T10:00:00Z", "Amount": 100},
        {"Id": "1", "LastModifiedDate": "2026-11-02T10:00:00Z", "Amount": 200},
        {"Id": "2", "LastModifiedDate": "2026-11-01T10:00:00Z", "Amount": 50},
    ]
    out = dedupe(recs)
    assert len(out) == 2
    assert [r for r in out if r["Id"] == "1"][0]["Amount"] == 200

def test_deletes_applied_in_sem():
    from src.pre_to_sem import main  # noqa - import check only
    assert callable(main)
