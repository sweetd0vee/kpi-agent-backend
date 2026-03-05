def test_create_update_context_and_delete_collection(client):
    created = client.post("/api/collections", json={"name": "Коллекция A", "department": "IT"})
    assert created.status_code == 200
    collection = created.json()

    listing = client.get("/api/collections")
    assert listing.status_code == 200
    assert any(c["id"] == collection["id"] for c in listing.json())

    updated = client.patch(
        f"/api/collections/{collection['id']}",
        json={"name": "Коллекция B", "summary": "Описание"},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Коллекция B"

    upload = client.post(
        "/api/documents/upload",
        params={"document_type": "business_plan_checklist", "collection_id": collection["id"]},
        files={"file": ("plan.txt", b"hello world", "text/plain")},
    )
    assert upload.status_code == 200

    context = client.get(f"/api/collections/{collection['id']}/context")
    assert context.status_code == 200
    ctx = context.json()
    assert ctx["document_count"] == 1
    assert ctx["included_count"] == 1
    assert "hello world" in ctx["content"]

    deleted = client.delete(f"/api/collections/{collection['id']}")
    assert deleted.status_code == 200

    missing = client.get(f"/api/collections/{collection['id']}")
    assert missing.status_code == 404
