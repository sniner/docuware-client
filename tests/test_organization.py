from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from docuware import users as users_module
from docuware.organization import Organization
from docuware.types import DocuwareClientP

_ORG_CONFIG = {
    "Name": "Test Org",
    "Id": "org1",
    "Links": [
        {"rel": "filecabinets", "href": "/DocuWare/Platform/Organizations/org1/FileCabinets"},
        {"rel": "dialogs",      "href": "/DocuWare/Platform/Organizations/org1/Dialogs"},
        {"rel": "users",        "href": "/DocuWare/Platform/Organizations/org1/Users"},
        {"rel": "groups",       "href": "/DocuWare/Platform/Organizations/org1/Groups"},
        {"rel": "userInfo",     "href": "/DocuWare/Platform/Organizations/org1/UserInfo"},
        {"rel": "self",         "href": "/DocuWare/Platform/Organizations/org1"},
    ],
}

_FC_RESPONSE = {
    "FileCabinet": [
        {"Id": "fc1", "Name": "Archive", "IsBasket": False, "Links": []},
        {"Id": "bk1", "Name": "Inbox",   "IsBasket": True,  "Links": []},
    ]
}


def _make_org(side_effects=None, return_value=None):
    mock_client = MagicMock(spec=DocuwareClientP)
    mock_conn = MagicMock()
    mock_client.conn = mock_conn
    if side_effects is not None:
        mock_conn.get_json.side_effect = side_effects
    elif return_value is not None:
        mock_conn.get_json.return_value = return_value
    org = Organization(_ORG_CONFIG, mock_client)
    return org, mock_conn


# --- conn property ---

def test_organization_conn_property():
    org, mock_conn = _make_org()
    assert org.conn is mock_conn


# --- all_cabinets ---

def test_organization_all_cabinets_returns_both():
    org, _ = _make_org(return_value=_FC_RESPONSE)
    assert len(org.all_cabinets) == 2


def test_organization_all_cabinets_cached():
    org, mock_conn = _make_org(return_value=_FC_RESPONSE)
    _ = org.all_cabinets
    _ = org.all_cabinets
    mock_conn.get_json.assert_called_once()


# --- basket() ---

def test_organization_basket_by_name():
    org, _ = _make_org(return_value=_FC_RESPONSE)
    bk = org.basket("Inbox")
    assert bk is not None
    assert bk.id == "bk1"


def test_organization_basket_not_found_returns_none():
    org, _ = _make_org(return_value=_FC_RESPONSE)
    assert org.basket("Nonexistent") is None


# --- my_tasks ---

def test_organization_my_tasks_raises_not_implemented():
    org, _ = _make_org()
    with pytest.raises(NotImplementedError):
        _ = org.my_tasks


# --- dialogs ---

def test_organization_dialogs_filtered_by_known_fc():
    fc_resp = {"FileCabinet": [{"Id": "fc1", "Name": "Archive", "IsBasket": False, "Links": []}]}
    dlg_resp = {
        "Dialog": [
            {"$type": "DialogInfo", "Id": "dlg1", "Type": "Search",
             "FileCabinetId": "fc1", "DisplayName": "Search", "Links": []},
            {"$type": "DialogInfo", "Id": "dlg2", "Type": "Search",
             "FileCabinetId": "unknown_fc", "DisplayName": "Orphan", "Links": []},
        ]
    }
    org, _ = _make_org(side_effects=[fc_resp, dlg_resp])
    dlgs = org.dialogs
    assert len(dlgs) == 1
    assert dlgs[0].id == "dlg1"


def test_organization_dialogs_cached():
    fc_resp = {"FileCabinet": [{"Id": "fc1", "Name": "Archive", "IsBasket": False, "Links": []}]}
    dlg_resp = {"Dialog": [
        {"$type": "DialogInfo", "Id": "dlg1", "Type": "Search",
         "FileCabinetId": "fc1", "DisplayName": "Search", "Links": []}
    ]}
    org, mock_conn = _make_org(side_effects=[fc_resp, dlg_resp])
    _ = org.dialogs
    _ = org.dialogs
    assert mock_conn.get_json.call_count == 2  # fc + dialogs, not more


# --- dialog() ---

def test_organization_dialog_by_name():
    fc_resp = {"FileCabinet": [{"Id": "fc1", "Name": "Archive", "IsBasket": False, "Links": []}]}
    dlg_resp = {"Dialog": [
        {"$type": "DialogInfo", "Id": "dlg1", "Type": "Search",
         "FileCabinetId": "fc1", "DisplayName": "My Search", "Links": []}
    ]}
    org, _ = _make_org(side_effects=[fc_resp, dlg_resp])
    d = org.dialog("My Search")
    assert d is not None
    assert d.id == "dlg1"


# --- info ---

def test_organization_info_strips_empty_lines():
    info_resp = {
        "Name": "Test Org", "Id": "org1",
        "Links": [{"rel": "self", "href": "/DocuWare/Platform/Organizations/org1"}],
        "AdditionalInfo": {
            "CompanyNames": ["Test Org", "", ""],
            "AddressLines": ["Main St 1", "", "12345 City"],
        },
    }
    org, _ = _make_org(return_value=info_resp)
    info = org.info
    assert info["CompanyNames"] == ["Test Org"]
    assert "" not in info["AddressLines"]


def test_organization_info_falls_back_to_org_name_when_all_empty():
    info_resp = {
        "Name": "Test Org", "Id": "org1",
        "Links": [],
        "AdditionalInfo": {"CompanyNames": ["", ""], "AddressLines": []},
    }
    org, _ = _make_org(return_value=info_resp)
    assert org.info["CompanyNames"] == ["Test Org"]


def test_organization_info_cached():
    info_resp = {
        "Name": "Test Org", "Id": "org1", "Links": [],
        "AdditionalInfo": {"CompanyNames": ["Test Org"], "AddressLines": []},
    }
    org, mock_conn = _make_org(return_value=info_resp)
    _ = org.info
    _ = org.info
    mock_conn.get_json.assert_called_once()


# --- users / groups ---

def test_organization_users_returns_users_object():
    org, _ = _make_org()
    assert isinstance(org.users, users_module.Users)


def test_organization_groups_returns_groups_object():
    org, _ = _make_org()
    assert isinstance(org.groups, users_module.Groups)


# --- __str__ ---

def test_organization_str():
    org, _ = _make_org()
    s = str(org)
    assert "Test Org" in s
    assert "org1" in s
