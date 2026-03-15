import os

import httpx
import pytest

from docuware import DocuwareClientException, connect, default_credentials_file


@pytest.fixture(scope="session")
def dw_client():
    cred_file = default_credentials_file()
    if not cred_file.exists():
        pytest.skip("No credentials file — set up .credentials to run integration tests")
    try:
        return connect(credentials_file=cred_file, verify_certificate=False)
    except (DocuwareClientException, httpx.TransportError) as e:
        pytest.skip(f"Cannot connect to DocuWare: {e}")


@pytest.fixture(scope="session")
def dw_org(dw_client):
    return next(iter(dw_client.organizations))


@pytest.fixture(scope="session")
def dw_file_cabinet(dw_org):
    name = os.environ.get("DW_TEST_CABINET")
    if not name:
        pytest.skip("Set DW_TEST_CABINET to run integration tests")
    fc = dw_org.file_cabinet(name)
    if fc is None:
        pytest.skip(f"File cabinet '{name}' not found")
    return fc


@pytest.fixture(scope="session")
def dw_search_dialog(dw_file_cabinet):
    dlg = dw_file_cabinet.search_dialog()
    if dlg is None:
        pytest.skip("No search dialog available")
    return dlg
