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


def test_leaders_create_and_list(client):
    first = client.post("/api/leaders", json={"name": "Иванов Иван Иванович"})
    assert first.status_code == 200
    first_id = first.json()["id"]

    second = client.post("/api/leaders", json={"name": "Петров Петр Петрович"})
    assert second.status_code == 200

    duplicate = client.post("/api/leaders", json={"name": "Иванов Иван Иванович"})
    assert duplicate.status_code == 200
    assert duplicate.json()["id"] == first_id

    listing = client.get("/api/leaders")
    assert listing.status_code == 200
    assert [item["name"] for item in listing.json()["items"]] == [
        "Иванов Иван Иванович",
        "Петров Петр Петрович",
    ]


def test_reference_responsibles_unique(client):
    client.post("/api/leaders", json={"name": "Иванов Иван"})
    client.post("/api/leaders", json={"name": "Петров Петр"})
    client.post("/api/leaders", json={"name": "Иванов Иван"})
    res = client.get("/api/reference/responsibles")
    assert res.status_code == 200
    assert res.json()["items"] == ["Иванов Иван", "Петров Петр"]
