from __future__ import annotations
import logging
from typing import Dict, List, Literal, Optional, Union, overload

from docuware import structs, types, dialogs

log = logging.getLogger(__name__)


class FileCabinet(types.FileCabinetP):
    def __init__(self, config: Dict, organization: types.OrganizationP):
        self.organization = organization
        self.name = config.get("Name", "")
        self.id = config.get("Id", "")
        self.endpoints = structs.Endpoints(config)
        self._dialogs: Optional[List[types.DialogP]] = None

    @property
    def dialogs(self) -> List[types.DialogP]:
        if self._dialogs is None:
            result = self.organization.client.conn.get_json(self.endpoints["dialogs"])
            self._dialogs = [
                dialogs.Dialog.from_config(dlg, self) for dlg in result.get("Dialog", [])
                if dlg.get("$type") == "DialogInfo" and ("_" not in dlg.get("Id"))
                # and (dlg.get("IsDefault") or dlg.get("IsForMobile"))
            ]
        return self._dialogs or []

    @overload
    def dialog(self, key: str, *, required: Literal[True]) -> types.DialogP: ...

    @overload
    def dialog(self, key: str, *, required: Literal[False]) -> Optional[types.DialogP]: ...

    def dialog(self, key: str, *, required: bool = False) -> Optional[types.DialogP]:
        return structs.first_item_by_id_or_name(self.dialogs, key, required=required)

    @overload
    def search_dialog(self, key: Optional[str], *, required: Literal[True]) -> types.SearchDialogP: ...

    @overload
    def search_dialog(self, key: Optional[str], *, required: Literal[False]) -> Optional[types.SearchDialogP]: ...

    def search_dialog(self, key: Optional[str] = None, *, required: bool = False) -> Optional[types.SearchDialogP]:
        # TODO: Is there a default search dialog?
        search_dlgs = (dlg for dlg in self.dialogs if isinstance(dlg, dialogs.SearchDialog))
        if key:
            return structs.first_item_by_id_or_name(
                search_dlgs,
                key,
                required=required,
            )
        else:
            return structs.first_item_by_class(
                search_dlgs,
                dialogs.SearchDialog,
                required=required
            )

    # This method from PR#4 needs a complete rewrite
    def create_data_entry(self, data: Dict) -> Union[str, Literal[False]]:
        """
        The function `create_data_entry` creates a data entry in a document management system using XML
        payload.

        :param data: The `data` parameter is a dictionary that contains the field names and their
        corresponding values for creating a data entry. Each key-value pair in the dictionary represents
        a field name and its value
        :type data: dict
        :return: the result of the data entry creation. If the data entry creation is successful, it
        will return the result. If there is a problem creating the data entry, it will return False.
        """

        xml_head = """<Document xmlns='http://dev.docuware.com/schema/public/services/platform' Id='1'>
<Fields>"""

        xml_middle = ""
        for key, value in data.items():
            xml_field = f"""<Field FieldName='{key}'>
<String>{value}</String>
</Field>"""
            xml_middle += xml_field

        xml_foot = """</Fields>
</Document>"""

        xml_payload = xml_head + xml_middle + xml_foot

        headers = {
            "Content-Type": "application/xml",
            "Accept": "application/xml"
        }

        try:
            result = self.organization.client.conn.post_text(f"{self.endpoints['documents']}", headers=headers,
                                                             data=str.encode(xml_payload))
        except Exception as e:
            log.debug(f"Problem creating data entry:\n\n{e}")
            return False
        return result

    # This method from PR#4 needs a complete rewrite
    def update_data_entry(self, query: List = [], data: Dict = {}) -> Union[Response, Literal[False]]:
        """
        The `update_data_entry` function updates the fields of a document in a file cabinet based on a
        search query and a dictionary of field-value pairs.

        :param query: The `query` parameter is a list that represents the search query used to find the
        document to be updated. It is optional and can be left empty if you want to update all documents
        in the file cabinet
        :type query: list
        :param data: The `data` parameter is a dictionary that contains the key-value pairs of the
        fields and their corresponding values that you want to update in the document. Each key
        represents the field name, and the corresponding value represents the new value for that field
        :type data: dict
        :return: the result of the update request. If the update request is successful, it will return
        the result of the request. If there is an error during the update, it will return False.
        """

        fc_fields = []
        # Retrieve and extract file cabinet fields and types
        dlg = self.search_dialog()
        for field in dlg.fields.values():
            fc_field: Dict[str, Any] = {}
            fc_field["id"] = field.id
            fc_field["length"] = field.length
            fc_field["name"] = field.name
            fc_field["type"] = field.type
            fc_fields.append(fc_field)

        # The above code is performing a search query using a search dialog. It then checks the count
        # of the search results. If there is only one result, it retrieves the document ID of that
        # result. If there are no results, it logs a debug message and returns False. If there are
        # more than one result, it logs a debug message and returns False, indicating that the update
        # request can only be executed for one document and the user needs to specify their search
        # query.
        dlg = self.search_dialog()
        fc_search = dlg.search(query)
        if fc_search.count == 1:
            for result in fc_search:
                document_id = result.document.id
        elif fc_search.count < 1:
            log.debug('Update search query returned no results, update request will not be executed.')
            return False
        else:
            log.debug(
                'Update search query returned more than 1 result, update request can only be executed for one document. Please specify your search query.')
            return False

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json"
        }

        body = {
            "Field": []
        }

        # The above code is iterating over the items in the `data` dictionary. For each key-value
        # pair, it creates a list called `item_element_name` using a list comprehension.
        for key, value in data.items():
            # The above code is creating a list called `item_element_name` using a list comprehension.
            # It checks each element `x` in the list `fc_fields` and checks if the value of the `type`
            # key in `x` is equal to 'Decimal'. If it is, the corresponding element in
            # `item_element_name` is set to 'Float'. If not, it checks if the value of the `type` key
            # is equal to 'Numeric'. If it is, the corresponding element in `item_element_name` is set
            # to 'Integer'. If neither condition is met, the corresponding element
            item_element_name = ['Decimal' if x['type'] == 'Decimal' else 'String' for x in fc_fields if
                                 x['id'] == key.upper()]
            field = {
                "FieldName": key,
                "Item": value,
                "ItemElementName": item_element_name[0]
            }
            body["Field"].append(field)

        try:
            # result = self.client.conn.put(f"{self.endpoints['filecabinets']}/{fc.id}/Documents/{document_id}/Fields", headers=headers, json=body)
            result = self.organization.client.conn.put(
                f"{self.endpoints['documents']}/{document_id}/Fields",
                headers=headers, json=body
            )
        except Exception as e:
            log.debug(f'Error updating document data fields:\n\n{e}')
            return False
        return result

    def __str__(self) -> str:
        return f"{self.__class__.__name__} '{self.name}' [{self.id}]"
