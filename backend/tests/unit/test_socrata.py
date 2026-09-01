"""The Socrata wrapper must turn every failure mode into SocrataError."""

import httpx
import pytest
import respx

from app.services.socrata import SocrataClient, SocrataError

URL = "https://data.cityofchicago.org/resource/abcd-1234.json"


@respx.mock
def test_success_returns_rows():
    respx.get(URL).mock(return_value=httpx.Response(200, json=[{"a": 1}]))
    assert SocrataClient().get_rows("abcd-1234", {"$limit": "1"}) == [{"a": 1}]


@respx.mock
@pytest.mark.parametrize("status", [429, 500, 503, 404])
def test_http_errors_become_socrata_error(status):
    respx.get(URL).mock(return_value=httpx.Response(status, json=[]))
    with pytest.raises(SocrataError):
        SocrataClient().get_rows("abcd-1234", {})


@respx.mock
def test_non_json_becomes_socrata_error():
    respx.get(URL).mock(return_value=httpx.Response(200, text="<html>nope</html>"))
    with pytest.raises(SocrataError):
        SocrataClient().get_rows("abcd-1234", {})


@respx.mock
def test_wrong_shape_becomes_socrata_error():
    respx.get(URL).mock(return_value=httpx.Response(200, json={"error": "not a list"}))
    with pytest.raises(SocrataError):
        SocrataClient().get_rows("abcd-1234", {})


@respx.mock
def test_timeout_becomes_socrata_error():
    respx.get(URL).mock(side_effect=httpx.TimeoutException("slow"))
    with pytest.raises(SocrataError):
        SocrataClient().get_rows("abcd-1234", {})
