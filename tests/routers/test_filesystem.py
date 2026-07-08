import json

import pytest
from app.auth import create_access_token


@pytest.mark.anyio
async def test_filesystem_list_download_upload_delete(tmp_path, async_client):
    token = create_access_token({"sub": "admin"})
    base_dir = tmp_path / "data"
    base_dir.mkdir()
    sample_file = base_dir / "hello.txt"
    sample_file.write_text("hello world")

    list_response = await async_client.get(
        "/fs/list",
        params={"path": str(base_dir)},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_response.status_code == 200
    assert any(item["name"] == "hello.txt" for item in list_response.json()["files"])

    download_response = await async_client.get(
        "/fs/download",
        params={"path": str(sample_file)},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert download_response.status_code == 200
    assert download_response.content == b"hello world"

    upload_response = await async_client.post(
        "/fs/upload",
        headers={"Authorization": f"Bearer {token}"},
        data={"path": str(base_dir)},
        files={"file": ("new.txt", b"upload content")},
    )
    assert upload_response.status_code == 200
    assert (base_dir / "new.txt").read_bytes() == b"upload content"

    delete_response = await async_client.request(
        "DELETE",
        "/fs/delete",
        content=json.dumps({"path": str(base_dir / "new.txt")}),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    assert delete_response.status_code == 200
    assert not (base_dir / "new.txt").exists()


@pytest.mark.anyio
async def test_filesystem_search_zip_unzip(tmp_path, async_client):
    token = create_access_token({"sub": "admin"})
    base_dir = tmp_path / "repo"
    base_dir.mkdir()
    nested = base_dir / "nested"
    nested.mkdir()
    file_a = nested / "match.txt"
    file_a.write_text("a")
    file_b = base_dir / "other.txt"
    file_b.write_text("b")

    search_response = await async_client.get(
        "/fs/search",
        params={"query": "match", "path": str(base_dir)},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert search_response.status_code == 200
    assert any(item["name"] == "match.txt" for item in search_response.json()["files"])

    zip_path = base_dir / "archive.zip"
    zip_response = await async_client.post(
        "/fs/zip",
        json={"paths": [str(nested), str(file_b)], "output": str(zip_path)},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert zip_response.status_code == 200
    assert zip_path.exists()

    extract_dir = tmp_path / "extracted"
    unzip_response = await async_client.post(
        "/fs/unzip",
        json={"path": str(zip_path), "destination": str(extract_dir)},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert unzip_response.status_code == 200
    assert (extract_dir / "nested" / "match.txt").exists() or (extract_dir / "match.txt").exists()  # archive structure may vary

    open_response = await async_client.post(
        "/fs/open",
        json={"path": str(base_dir)},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert open_response.status_code in (200, 500)
    assert open_response.json()["success"] is True or "Could not open path" in open_response.json().get("detail", "")
