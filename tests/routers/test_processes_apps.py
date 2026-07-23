import pytest

from app.auth import create_access_token
from app.domain.processes import InstalledApplication, InstalledApplicationList
from app.services import processes as processes_service


@pytest.mark.anyio
async def test_list_applications_endpoint(monkeypatch, async_client):
    token = create_access_token({"sub": "admin"})
    monkeypatch.setattr(
        processes_service,
        "list_installed_applications",
        lambda filter_text=None: InstalledApplicationList(
            applications=[
                InstalledApplication(
                    id="google-chrome.desktop",
                    name="Google Chrome",
                    exec_command="google-chrome-stable %U",
                    exec_binary="google-chrome-stable",
                )
            ]
        ),
    )

    response = await async_client.get(
        "/processes/apps",
        params={"filter": "chrome"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["applications"][0]["name"] == "Google Chrome"


@pytest.mark.anyio
async def test_open_application_endpoint_resolves_desktop_entry(monkeypatch, async_client):
    token = create_access_token({"sub": "admin"})
    monkeypatch.setattr(
        processes_service,
        "open_installed_application",
        lambda name, args=None: processes_service.LaunchResult(
            pid=999,
            message="Opened Google Chrome.",
            detached=True,
            application_id="google-chrome.desktop",
            application_name="Google Chrome",
        ),
    )

    response = await async_client.post(
        "/processes/app/open",
        json={"name": "chrome"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["application_id"] == "google-chrome.desktop"
    assert payload["application_name"] == "Google Chrome"
