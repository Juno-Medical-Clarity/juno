import pytest


def test_care_plan_route_requires_authorization_header(client):
    response = client.post("/care_plan")

    assert response.status_code == 401
    body = response.get_json()
    assert body["status"] == "error"
    assert body["error"]["code"] == "MISSING_AUTH_HEADER"


@pytest.mark.parametrize("path", ["/simplify", "/simplify/v1", "/simplify/v1-1", "/simplify/v1-2"])
def test_old_simplify_endpoints_do_not_exist(path, client):
    """All /simplify* paths are hard-cut — unconditional 404."""
    response = client.post(path)

    assert response.status_code == 404
