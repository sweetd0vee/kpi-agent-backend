def test_kpi_replace_dedupes_rows(client):
    payload = {
        "rows": [
            {"id": "1", "lastName": "First"},
            {"id": "1", "lastName": "Second"},
        ]
    }
    res = client.put("/api/kpi", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert len(data["rows"]) == 1
    assert data["rows"][0]["lastName"] == "Second"


def test_ppr_replace_requires_id(client):
    res = client.put("/api/ppr", json={"rows": [{"id": ""}]})
    assert res.status_code == 400
