import unittest
from unittest.mock import MagicMock

from docuware.dialogs import Dialog, InfoDialog, ResultListDialog, ResultTree, SearchDialog, StoreDialog, TaskListDialog
from docuware.filecabinet import FileCabinet
from docuware.types import OrganizationP


def _make_fc(dialogs_response):
    mock_client = MagicMock()
    mock_conn = MagicMock()
    mock_client.conn = mock_conn
    mock_conn.get_json.return_value = dialogs_response

    mock_org = MagicMock(spec=OrganizationP)
    mock_org.client = mock_client

    fc = FileCabinet(
        {"Id": "fc1", "Name": "Archive", "Links": [{"rel": "dialogs", "href": "/dialogs"}]},
        mock_org,
    )
    return fc


def _dialog_info(id_, type_, is_default=False):
    return {
        "$type": "DialogInfo",
        "Id": id_,
        "Type": type_,
        "DisplayName": f"Dialog {id_}",
        "IsDefault": is_default,
        "Links": [{"rel": "self", "href": f"/dialogs/{id_}"}],
    }


class TestFromConfig(unittest.TestCase):
    def _fc(self):
        mock_org = MagicMock(spec=OrganizationP)
        mock_org.client = MagicMock()
        return FileCabinet({"Id": "fc1", "Links": []}, mock_org)

    def test_search_dialog_type(self):
        fc = self._fc()
        dlg = Dialog.from_config(_dialog_info("d1", "Search"), fc)
        self.assertIsInstance(dlg, SearchDialog)

    def test_store_dialog_type(self):
        fc = self._fc()
        dlg = Dialog.from_config(_dialog_info("d1", "Store"), fc)
        self.assertIsInstance(dlg, StoreDialog)

    def test_info_dialog_type(self):
        fc = self._fc()
        dlg = Dialog.from_config(_dialog_info("d1", "InfoDialog"), fc)
        self.assertIsInstance(dlg, InfoDialog)

    def test_result_tree_type(self):
        fc = self._fc()
        dlg = Dialog.from_config(_dialog_info("d1", "ResultTree"), fc)
        self.assertIsInstance(dlg, ResultTree)

    def test_task_list_type(self):
        fc = self._fc()
        dlg = Dialog.from_config(_dialog_info("d1", "TaskList"), fc)
        self.assertIsInstance(dlg, TaskListDialog)

    def test_unknown_type_falls_back_to_dialog(self):
        fc = self._fc()
        dlg = Dialog.from_config(_dialog_info("d1", "Unknown"), fc)
        self.assertIs(type(dlg), Dialog)


class TestIsDefaultFallback(unittest.TestCase):
    def test_is_default_dialog_preferred(self):
        fc = _make_fc({
            "Dialog": [
                _dialog_info("SearchFirst", "Search", is_default=False),
                _dialog_info("SearchDefault", "Search", is_default=True),
            ]
        })
        result = fc.search_dialog()
        self.assertIsNotNone(result)
        self.assertEqual(result.id, "SearchDefault")

    def test_first_dialog_used_when_no_default(self):
        fc = _make_fc({
            "Dialog": [
                _dialog_info("SearchA", "Search", is_default=False),
                _dialog_info("SearchB", "Search", is_default=False),
            ]
        })
        result = fc.search_dialog()
        self.assertIsNotNone(result)
        self.assertEqual(result.id, "SearchA")

    def test_returns_none_when_no_search_dialog(self):
        fc = _make_fc({"Dialog": [_dialog_info("StoreA", "Store")]})
        result = fc.search_dialog()
        self.assertIsNone(result)

    def test_required_raises_when_missing(self):
        fc = _make_fc({"Dialog": []})
        with self.assertRaises(KeyError):
            fc.search_dialog(required=True)


class TestUnderscoreIdFilter(unittest.TestCase):
    def test_underscore_ids_excluded(self):
        fc = _make_fc({
            "Dialog": [
                _dialog_info("SearchNormal", "Search"),          # no "_": kept
                _dialog_info("SearchMobile_copy", "Search"),     # has "_": excluded
            ]
        })
        ids = [d.id for d in fc.dialogs]
        self.assertIn("SearchNormal", ids)
        self.assertNotIn("SearchMobile_copy", ids)

    def test_missing_id_does_not_raise(self):
        fc = _make_fc({
            "Dialog": [
                {"$type": "DialogInfo", "Type": "Search", "Links": []},  # no "Id" key
                _dialog_info("dlg1", "Search"),
            ]
        })
        # Should not raise; entry without Id is excluded (empty string has no "_")
        ids = [d.id for d in fc.dialogs]
        self.assertIn("dlg1", ids)


class TestDisplayNameFallback(unittest.TestCase):
    def test_display_name_used_when_present(self):
        mock_org = MagicMock(spec=OrganizationP)
        mock_org.client = MagicMock()
        fc = FileCabinet({"Id": "fc1", "Links": []}, mock_org)
        dlg = Dialog.from_config(
            {"$type": "DialogInfo", "Id": "d1", "Type": "Search", "DisplayName": "My Search", "Links": []},
            fc,
        )
        self.assertEqual(dlg.name, "My Search")

    def test_id_used_as_fallback_when_no_display_name(self):
        mock_org = MagicMock(spec=OrganizationP)
        mock_org.client = MagicMock()
        fc = FileCabinet({"Id": "fc1", "Links": []}, mock_org)
        dlg = Dialog.from_config(
            {"$type": "DialogInfo", "Id": "d1", "Type": "Search", "Links": []},
            fc,
        )
        self.assertEqual(dlg.name, "d1")

    def test_empty_display_name_falls_back_to_id(self):
        mock_org = MagicMock(spec=OrganizationP)
        mock_org.client = MagicMock()
        fc = FileCabinet({"Id": "fc1", "Links": []}, mock_org)
        dlg = Dialog.from_config(
            {"$type": "DialogInfo", "Id": "d1", "Type": "Search", "DisplayName": "", "Links": []},
            fc,
        )
        self.assertEqual(dlg.name, "d1")


class TestAssociatedDialog(unittest.TestCase):
    def _make_fc_with_dialogs(self, dialog_list):
        mock_client = MagicMock()
        mock_conn = MagicMock()
        mock_client.conn = mock_conn
        mock_conn.get_json.return_value = {"Dialog": dialog_list}

        mock_org = MagicMock(spec=OrganizationP)
        mock_org.client = mock_client

        return FileCabinet(
            {"Id": "fc1", "Name": "Archive", "Links": [{"rel": "dialogs", "href": "/dialogs"}]},
            mock_org,
        )

    def test_associated_dialog_id_stored(self):
        mock_org = MagicMock(spec=OrganizationP)
        mock_org.client = MagicMock()
        fc = FileCabinet({"Id": "fc1", "Links": []}, mock_org)
        dlg = Dialog.from_config(
            {
                "$type": "DialogInfo", "Id": "SearchA", "Type": "Search",
                "AssignedDialogId": "ResultsB", "Links": [],
            },
            fc,
        )
        self.assertEqual(dlg.associated_dialog_id, "ResultsB")

    def test_associated_dialog_none_when_empty(self):
        mock_org = MagicMock(spec=OrganizationP)
        mock_org.client = MagicMock()
        fc = FileCabinet({"Id": "fc1", "Links": []}, mock_org)
        dlg = Dialog.from_config(_dialog_info("SearchA", "Search"), fc)
        self.assertIsNone(dlg.associated_dialog)

    def test_associated_dialog_resolves_to_correct_type(self):
        fc = self._make_fc_with_dialogs([
            {
                "$type": "DialogInfo", "Id": "SearchA", "Type": "Search",
                "AssignedDialogId": "ResultsB",
                "Links": [{"rel": "self", "href": "/dialogs/SearchA"}],
            },
            {
                "$type": "DialogInfo", "Id": "ResultsB", "Type": "ResultList",
                "AssignedDialogId": "",
                "Links": [{"rel": "self", "href": "/dialogs/ResultsB"}],
            },
        ])
        search_dlg = fc.dialog("SearchA")
        associated = search_dlg.associated_dialog
        self.assertIsNotNone(associated)
        self.assertIsInstance(associated, ResultListDialog)
        self.assertEqual(associated.id, "ResultsB")


class TestStoreDialogFields(unittest.TestCase):
    def test_store_dialog_fields_loaded(self):
        mock_org = MagicMock(spec=OrganizationP)
        mock_client = MagicMock()
        mock_conn = MagicMock()
        mock_client.conn = mock_conn
        mock_org.client = mock_client
        mock_conn.get_json.return_value = {
            "Fields": [
                {"DBFieldName": "COMPANY", "DlgLabel": "Company", "DWFieldType": "String"},
                {"DBFieldName": "DATE", "DlgLabel": "Date", "DWFieldType": "Date"},
            ]
        }

        fc = FileCabinet({"Id": "fc1", "Links": []}, mock_org)
        dlg = Dialog.from_config(
            {
                "$type": "DialogInfo", "Id": "StoreA", "Type": "Store",
                "Links": [{"rel": "self", "href": "/dialogs/StoreA"}],
            },
            fc,
        )
        self.assertIsInstance(dlg, StoreDialog)
        fields = dlg.fields
        self.assertIn("COMPANY", fields)
        self.assertIn("DATE", fields)
        self.assertEqual(fields["COMPANY"].name, "Company")

    def test_store_dialog_fields_cached(self):
        mock_org = MagicMock(spec=OrganizationP)
        mock_client = MagicMock()
        mock_conn = MagicMock()
        mock_client.conn = mock_conn
        mock_org.client = mock_client
        mock_conn.get_json.return_value = {"Fields": []}

        fc = FileCabinet({"Id": "fc1", "Links": []}, mock_org)
        dlg = Dialog.from_config(
            {
                "$type": "DialogInfo", "Id": "StoreA", "Type": "Store",
                "Links": [{"rel": "self", "href": "/dialogs/StoreA"}],
            },
            fc,
        )
        _ = dlg.fields
        _ = dlg.fields
        mock_conn.get_json.assert_called_once()


if __name__ == "__main__":
    unittest.main()
