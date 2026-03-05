def test_upload_invalid_document_type(client):
    res = client.post(
        "/api/documents/upload",
        params={"document_type": "unknown_type"},
        files={"file": ("test.txt", b"hello", "text/plain")},
    )
    assert res.status_code == 400


def test_upload_list_get_delete_document(client):
    upload = client.post(
        "/api/documents/upload",
        params={"document_type": "strategy_checklist"},
        files={"file": ("test.txt", b"hello", "text/plain")},
    )
    assert upload.status_code == 200
    doc = upload.json()

    listing = client.get("/api/documents")
    assert listing.status_code == 200
    data = listing.json()
    assert data["total"] == 1
    assert data["items"][0]["id"] == doc["id"]

    fetched = client.get(f"/api/documents/{doc['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == doc["id"]

    deleted = client.delete(f"/api/documents/{doc['id']}")
    assert deleted.status_code == 200
    assert deleted.json() == {"status": "ok"}

    missing = client.get(f"/api/documents/{doc['id']}")
    assert missing.status_code == 404


def test_submit_document_checklist_saves_json(client):
    upload = client.post(
        "/api/documents/upload",
        params={"document_type": "strategy_checklist"},
        files={"file": ("checklist.txt", b"content", "text/plain")},
    )
    doc_id = upload.json()["id"]

    submit = client.post(
        f"/api/documents/{doc_id}/submit-checklist",
        json={"parsed_json": {"items": [{"id": "1", "text": "X"}]}},
    )
    assert submit.status_code == 200

    fetched = client.get(f"/api/documents/{doc_id}")
    body = fetched.json()
    assert body["preprocessed"] is True
    assert body["parsed_json"]["items"][0]["text"] == "X"
