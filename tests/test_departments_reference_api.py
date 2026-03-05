def test_departments_create_and_list(client):
    first = client.post("/api/departments", json={"name": "IT"})
    assert first.status_code == 200
    first_id = first.json()["id"]

    second = client.post("/api/departments", json={"name": "IT"})
    assert second.status_code == 200
    assert second.json()["id"] == first_id

    listing = client.get("/api/departments")
    assert listing.status_code == 200
    assert len(listing.json()["items"]) == 1


def test_reference_responsibles_unique(client):
    client.put("/api/kpi", json={"rows": [{"id": "1", "lastName": "Иванов"}]})
    client.put(
        "/api/ppr",
        json={"rows": [{"id": "2", "lastName": "Петров"}, {"id": "3", "lastName": "Иванов"}]},
    )

    res = client.get("/api/reference/responsibles")
    assert res.status_code == 200
    assert res.json()["items"] == ["Иванов", "Петров"]
