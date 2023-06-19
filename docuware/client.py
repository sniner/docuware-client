import re, json

from datetime import datetime, date
from typing import Any, Dict, Iterator, List, Tuple, Type, Union

from docuware import cidict, cijson, conn, errors, parser, structs, utils


def print_json(data):
    cijson.print_json(data)


NOTHING = object()
AND = "And"
OR = "Or"


def _first_item_by_id_or_name(items, key:str, default:Union[Any, None]=NOTHING):
    name = key.casefold()
    for item in items:
        if item.id == key or item.name.casefold() == name:
            return item
    if default != NOTHING:
        return default
    else:
        raise KeyError(key)


def _first_item_by_class(items, cls:Type, default:Union[Any,None]=NOTHING):
    for item in items:
        if isinstance(item, cls):
            return item
    if default != NOTHING:
        return default
    else:
        raise KeyError(cls.__name__)


class DocuwareClient:
    def __init__(self, url:str):
        self.conn = conn.Connection(url, case_insensitive=True)
        self.endpoints = {}
        self.resources = {}
        self.version = None

    @property
    def organizations(self):
        result = self.conn.get_json(self.endpoints["organizations"])
        return (Organization(org, self) for org in result.get("Organization", []))

    def organization(self, key:str, default:Union[Any,None]=NOTHING):
        """Access organization by id or name."""
        return _first_item_by_id_or_name(self.organizations, key, default=default)

    def login(self, username:str, password:str, organization:str=None, cookiejar:dict=None):
        endpoint = "/DocuWare/Platform/Account/Logon"

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        }
        data = {
            "LoginType": "DocuWare",
            "RedirectToMyselfInCaseOfError": "false",
            "RememberMe": "false",
            "Password": password,
            "UserName": username,
        }
        if organization:
            data["Organization"] = organization

        self.conn.cookiejar = cookiejar

        try:
            result = self.conn.post_json(endpoint, headers=headers, data=data)
            self.endpoints = structs.Endpoints(result)
            self.resources = structs.Resources(result)
            # for res in sorted(self.resources.values()):
            #     print(res)
            self.version = result.get("Version")
            return self.conn.cookiejar
        except errors.ResourceError as exc:
            raise errors.AccountError(f"Log in failed with code {exc.status_code}")

    def logoff(self):
        url = self.conn.make_url("/DocuWare/Platform/Account/Logoff")
        self.conn._get(url)


class Organization:
    def __init__(self, config:dict, client:DocuwareClient):
        self.client = client
        self.name = config.get("Name")
        self.id = config.get("Id")
        self.endpoints = structs.Endpoints(config)
        self._info = None
        self._dialogs = None

    @property
    def file_cabinets(self):
        result = self.client.conn.get_json(self.endpoints["filecabinets"])
        return (FileCabinet(fc, self) for fc in result.get("FileCabinet", []))

    def file_cabinet(self, key:str, default:Union[Any,None]=NOTHING):
        return _first_item_by_id_or_name(self.file_cabinets, key, default=default)

    @property
    def my_tasks(self):
        # Sorry, but couldn't figure out how to get "My tasks" list.
        raise NotImplementedError
        # result = self.client.conn.get_json(self.endpoints["workflowRequests"])
        # return MyTasks(result, self)

    @property
    def dialogs(self):
        # It is unclear whether the dialogs here differ from those of FileCabinet or not.
        if self._dialogs is None:
            fc_by_id = {fc.id: fc for fc in self.file_cabinets}
            result = self.client.conn.get_json(self.endpoints["dialogs"])
            self._dialogs = [
                Dialog.from_config(dlg, fc_by_id[dlg.get("FileCabinetId")]) for dlg in result.get("Dialog", [])
                    if dlg.get("$type") == "DialogInfo" and dlg.get("FileCabinetId") in fc_by_id
            ]
        return self._dialogs

    def dialog(self, key:str, default:Union[Any,None]=NOTHING):
        return _first_item_by_id_or_name(self.dialogs, key, default=default)

    @property
    def info(self):
        if self._info is None:
            result = self.client.conn.get_json(self.endpoints["self"])
            self.endpoints = structs.Endpoints(result)
            self._info = cidict.CaseInsensitiveDict(result.get("AdditionalInfo", {}))
            # Remove empty lines
            self._info["CompanyNames"] = [line for line in self._info["CompanyNames"] if line] or [self.name]
            self._info["AddressLines"] = [line for line in self._info["AddressLines"] if line]
        return self._info

    # User functions

    @property
    def users(self):
        """
        This function returns a list of User objects obtained from a JSON response.
        :return: A list of User objects created from the JSON data retrieved from the "users" endpoint.
        """
        result = self.client.conn.get_json(self.endpoints["users"])
        return (User(user, self) for user in result.get("User", []))
    
    def get_user(self, key:str, default:Union[Any,None]=NOTHING):
        """
        This function returns the first item in a list of users that matches a given key, or a default value
        if no match is found.
        
        :param key: The key parameter is a string that represents the unique identifier or name of the user
        that we want to retrieve from the list of users
        :type key: str
        :param default: The default value to return if the user with the specified key is not found in the
        list of users. If no default value is provided, the function will raise a KeyError if the user is
        not found. The default value can be any data type or None
        :type default: Union[Any,None]
        :return: The `get_user` method is returning the first item in the `users` list that matches the
        given `key` (either by `id` or `name`). If no match is found and a `default` value is provided, it
        will return the `default` value. If no `default` value is provided, it will raise a `ValueError`.
        """
        return _first_item_by_id_or_name(self.users, key, default=default)
    
    def get_user_list(self):
        """
        This function retrieves a list of users from a specified endpoint using a client connection and
        returns it.
        :return: The function `get_user_list` is returning a list of dictionaries containing information
        about users. The list is obtained by calling the `get_json` method of the `self.client.conn` object
        with the endpoint URL for users. The `result` variable is a dictionary that contains a key "User"
        whose value is a list of dictionaries. The function returns this list of dictionaries, or an empty
        list
        """
        result = self.client.conn.get_json(self.endpoints["users"])
        return (result.get("User", []))
    
    def create_user(self, user_dict):
        """
        This function creates a new user in a DocuWare platform using a dictionary of user information.
        
        :param userDict: userDict is a dictionary that contains the information needed to create a new user
        in the DocuWare platform. The dictionary should have the following keys and values:
            {
                "Name": "",
                "Email": "",
                "Password": "",
                "DbName": ""
            }
        :return: the result of the API call made to create a new user in a DocuWare organization. If the API
        call is successful, it will return the response from the server as a JSON object. If there is an
        error, it will return False.
        """
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/vnd.docuware.platform.createorganizationuser+json"
        }
        try:
            result = self.client.conn.post_json(self.endpoints['userInfo'], headers=headers, json=user_dict)
        except Exception as e:
            print(f'Error creating user:\n\n{e}')
            return False
        return result

    def add_group_to_user(self, group_name, user_name):
        """
        This function adds a group to a user in a DocuWare organization.
        
        :param groupName: The name of the group that you want to add to the user
        :param userName: The username of the user to whom the group needs to be added
        :return: the result of the API call made to add a group to a user in the DocuWare platform. If the
        API call is successful, it will return the result of the call. If there is an error, it will return
        False.
        """
        # Get group information
        group = self.get_group(group_name)
        # Get user information
        user = self.get_user(user_name)

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json"
        }

        body = {
            "Ids": [
                group.id
            ],
            "OperationType": "Add"
        }

        try:
            result = self.client.conn.put('/DocuWare/Platform/Organization/UserGroups', headers=headers, params={"UserId": user.id}, json=body)
        except Exception as e:
            print(f'Error adding group to user:\n\n{e}')
            return False
        return result
    
    def remove_group_from_user(self, group_name, user_name):
        """
        This function removes a specified group from a specified user in a DocuWare organization.
        
        :param groupName: The name of the group that you want to remove from the user's membership
        :param userName: The username of the user from whom the group needs to be removed
        :return: the result of the API call made to remove a group from a user. If the API call is
        successful, it will return the result of the call. If there is an error, it will return False.
        """
        # Get group information
        group = self.get_group(group_name)
        # Get user information
        user = self.get_user(user_name)

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json"
        }

        body = {
            "Ids": [
                group.id
            ],
            "OperationType": "Remove"
        }
        try:
            result = self.client.conn.put('/DocuWare/Platform/Organization/UserGroups', headers=headers, params={"UserId": user.id}, json=body)
        except Exception as e:
            print(f'Error removing group from user:\n\n{e}')
            return False
        return result

    def deactivate_user(self, user_name):
        """
        This function deactivates a user by sending a POST request to an API endpoint with the user's
        information and setting their "Active" status to False.
        
        :param userName: The username of the user that needs to be deactivated
        :return: the result of the API call made to deactivate the user. If the API call is successful, it
        will return the response from the server. If there is an error, it will return False.
        """
        # Get user id of requested user
        user = self.get_user(user_name)
        
        headers = {
                    "Accept": "application/json",
                    "Content-Type": "application/json"
                }

        name_parts = user.name.rsplit('.', 1)
        if len(name_parts) > 1:
            first_name = name_parts[0]
            last_name = name_parts[1]
        else:
            first_name = ""
            last_name = user.name

        body = {
            "Id": user.id,
            "Name": user.name,
            "FirstName": first_name,
            "LastName": last_name,
            "EMail": user.email,
            "Salutation": "",
            "DBName": user.db_name,
            "Active": False
        }

        try:
            result = self.client.conn.post_text(self.endpoints['userInfo'], headers=headers, json=body)
        except Exception as e:
            print(f'Error deactivating user:\n\n{e}')
            return False
        return result
    
    def activate_user(self, user_name):
        """
        This function activates a user by sending a POST request with user information to an endpoint.
        
        :param userName: The username of the user that needs to be activated
        :return: the result of the API call made to activate the user. If the API call is successful, it
        will return the response from the server. If there is an error, it will return False.
        """
        # Get user id of requested user
        user = self.get_user(user_name)
        
        headers = {
                    "Accept": "application/json",
                    "Content-Type": "application/json"
                }

        name_parts = user.name.rsplit('.', 1)
        if len(name_parts) > 1:
            first_name = name_parts[0]
            last_name = name_parts[1]
        else:
            first_name = ""
            last_name = user.name

        body = {
            "Id": user.id,
            "Name": user.name,
            "FirstName": first_name,
            "LastName": last_name,
            "EMail": user.email,
            "Salutation": "",
            "DBName": user.db_name,
            "Active": True
        }

        try:
            result = self.client.conn.post_text(self.endpoints['userInfo'], headers=headers, json=body)
        except Exception as e:
            print(f'Error activating user:\n\n{e}')
            return False
        return result


    # Group functions
    @property
    def groups(self):
        """
        This function retrieves a list of groups from a client connection and returns them as a list of
        Group objects.
        :return: The `groups()` method is returning a tuple of `Group` objects. The `Group` objects are
        created using the `Group` class and the data obtained from the `result` variable, which is a JSON
        object obtained from the `self.client.conn.get_json()` method call. The `result.get("Item", [])`
        method call returns a list of dictionaries, where each dictionary represents a group
        """
        result = self.client.conn.get_json(self.endpoints["groups"])
        return (Group(group, self) for group in result.get("Item", []))
    
    def get_group(self, key:str, default:Union[Any,None]=NOTHING):
        """
        This function returns the first item in a list of groups that matches a given key, or a default
        value if no match is found.
        
        :param key: The key parameter is a string that represents the identifier or name of the group that
        we want to retrieve
        :type key: str
        :param default: The default value to return if the key is not found in the groups list. If no
        default value is provided, the function will raise a KeyError if the key is not found. The default
        value is set to NOTHING, which is likely a custom constant defined elsewhere in the code
        :type default: Union[Any,None]
        :return: The `get_group` method is returning the first item in the `groups` list that matches the
        given `key` parameter, either by its `id` or `name` attribute. If no match is found, it returns the
        `default` value, which is set to `NOTHING` by default but can be set to any other value.
        """
        return _first_item_by_id_or_name(self.groups, key, default=default)
    
    def get_group_list(self):
        """
        This function retrieves a list of groups from a JSON endpoint and returns it.
        :return: The `get_group_list` method is returning a list of items from the "groups" endpoint of the
        client's connection in JSON format. If there are no items, it will return an empty list.
        """
        result = self.client.conn.get_json(self.endpoints["groups"])
        return (result.get("Item", []))

    def __str__(self):
        return f"{self.__class__.__name__} '{self.name}' [{self.id}]"


class User:
    def __init__(self, config:dict, organization:Organization):
        self.organization = organization
        self.name = config.get("Name")
        self.id = config.get("Id")
        self.first_name = config.get("FirstName")
        self.last_name = config.get("LastName")
        self.salutation = config.get("Salutation")
        self.db_name = config.get("DBName")
        self.active = config.get("Active")
        self.email = config.get("EMail")
        self.endpoints = structs.Endpoints(config)
        self._dialogs = None

    def __str__(self):
        return f"{self.__class__.__name__} '{self.name}' [{self.id}]"
    

class Group:
    def __init__(self, config:dict, organization:Organization):
        self.organization = organization
        self.name = config.get("Name")
        self.id = config.get("Id")
        self.endpoints = structs.Endpoints(config)
        self._dialogs = None

    def __str__(self):
        return f"{self.__class__.__name__} '{self.name}' [{self.id}]"


class FileCabinet:
    def __init__(self, config:dict, organization:Organization):
        self.organization = organization
        self.name = config.get("Name")
        self.id = config.get("Id")
        self.endpoints = structs.Endpoints(config)
        self._dialogs = None

    @property
    def dialogs(self):
        if self._dialogs is None:
            result = self.organization.client.conn.get_json(self.endpoints["dialogs"])
            self._dialogs = [
                Dialog.from_config(dlg, self) for dlg in result.get("Dialog", [])
                    if dlg.get("$type") == "DialogInfo" and ("_" not in dlg.get("Id"))
                        # and (dlg.get("IsDefault") or dlg.get("IsForMobile"))
            ]
        return self._dialogs

    def dialog(self, key:str, default:Union[Any,None]=NOTHING):
        return _first_item_by_id_or_name(self.dialogs, key, default=default)

    def search_dialog(self, key:Union[str,None]=None, default:Union[Any,None]=NOTHING):
        # TODO: Is there a default search dialog?
        if key:
            return _first_item_by_id_or_name(
                (dlg for dlg in self.dialogs if isinstance(dlg, SearchDialog)),
                key,
                default=default
            )
        else:
            return _first_item_by_class(self.dialogs, SearchDialog, default=default)

    def __str__(self):
        return f"{self.__class__.__name__} '{self.name}' [{self.id}]"


class Dialog:
    def __init__(self, config:dict, file_cabinet:FileCabinet):
        self.file_cabinet = file_cabinet
        self.client = file_cabinet.organization.client
        self.name = config.get("DisplayName")
        self.type = config.get("Type")
        self.id = config.get("Id")
        self.endpoints = structs.Endpoints(config)

    @staticmethod
    def from_config(config:dict, file_cabinet:FileCabinet):
        dlg_type = config.get("Type")
        if dlg_type == "Search":
            return SearchDialog(config, file_cabinet)
        elif dlg_type == "Store":
            return StoreDialog(config, file_cabinet)
        elif dlg_type == "ResultList":
            return ResultListDialog(config, file_cabinet)
        elif dlg_type == "TaskList":
            return TaskListDialog(config, file_cabinet)
        return Dialog(config, file_cabinet)

    def __str__(self):
        return f"{self.__class__.__name__} '{self.name}' [{self.id}]"


class StoreDialog(Dialog):
    pass


class ResultListDialog(Dialog):
    pass


class TaskListDialog(Dialog):
    def __init__(self, config:dict, file_cabinet:FileCabinet):
        super().__init__(config, file_cabinet)
        self._fields = None

    def _load(self):
        if self._fields is None:
            config = self.client.conn.get_json(self.endpoints["self"])
            print_json(config)
            self._fields = {f.id:f for f in 
                [SearchField(fld, self) for fld in config.get("Fields", [])]
            }

    @property
    def fields(self):
        self._load()
        return self._fields


class SearchDialog(Dialog):
    def __init__(self, config:dict, file_cabinet:FileCabinet):
        super().__init__(config, file_cabinet)
        self._fields = None

    def _load(self):
        if self._fields is None:
            config = self.client.conn.get_json(self.endpoints["self"])
            self._fields = {f.id:f for f in
                [SearchField(fld, self) for fld in config.get("Fields", [])]
            }
            # NB: SearchQuery depends on self.fields
            self._query = SearchQuery(config.get("Query", {}), self)

    @property
    def fields(self):
        self._load()
        return self._fields

    def search(self, conditions:Dict[str,str], operation:str=None):
        self._load()
        return self._query.search(conditions=conditions, operation=operation)
        

class SearchField:
    def __init__(self, config:dict, dialog:Dialog):
        self.dialog = dialog
        self.id = config.get("DBFieldName")
        self.name = config.get("DlgLabel", self.id)
        self.length = config.get("Length", -1)
        self.type = config.get("DWFieldType")
        self.endpoints = structs.Endpoints(config)
    
    def values(self):
        if "simpleSelectList" in self.endpoints:
            result = self.dialog.client.conn.get_json(self.endpoints["simpleSelectList"])
            return result.get("Value", [])
        return []

    def __str__(self):
        if self.length>0:
            return f"Field '{self.name}' [{self.id}, {self.type}({self.length})]"
        else:
            return f"Field '{self.name}' [{self.id}, {self.type}]"


Conditions = Union[str, List[str], Tuple[str], Dict[str, Union[str, List[str]]]]


class ConditionParser:
    def __init__(self, dialog:SearchDialog):
        self.fields_by_name = {}
        self.fields_by_id = {}
        for field in dialog.fields.values():
            self.fields_by_name[field.name.casefold()] = field
            self.fields_by_id[field.id.casefold()] = field

    @staticmethod
    def convert_field_value(value:Any) -> str:
        if value is None:
            return "*"
        if isinstance(value, date):
            value = datetime(value.year, value.month, value.day)
        if isinstance(value, datetime):
            value = utils.datetime_to_string(value)
        return str(value)

    def field_by_name(self, name:str) -> SearchField:
        iname = name.casefold()
        if iname in self.fields_by_id:
            field = self.fields_by_id[iname]
        elif iname in self.fields_by_name:
            field = self.fields_by_name[iname]
        else:
            raise errors.SearchConditionError(f"Unknown field: {name}")
        return field

    def _term(self, name:str, value:Union[str,List[str]]) -> Tuple[str,List[str]]:
        field = self.field_by_name(name)
        if isinstance(value, str):
            value = [str]
        else:
            try:
                value = [self.convert_field_value(i) for i in value]
            except TypeError:
                value = [str(value)]
        return field.id, value

    def parse_list(self, conditions:Union[List[str],Tuple[str]]):
        return [self._term(*parser.parse_search_condition(c)) for c in conditions]

    def parse_dict(self, conditions:Dict[str,List[str]]):
        terms = [self._term(k, v) for k, v in conditions.items()]

    def parse(self, conditions:Conditions):
        if isinstance(conditions, str):
            return self.parse_list([conditions])
        elif isinstance(conditions, (list, tuple)):
            return self.parse_list(conditions)
        else:
            return self.parse_dict(conditions)


class SearchQuery:
    def __init__(self, config:dict, dialog:SearchDialog):
        self.dialog = dialog
        self.force_refresh = config.get("ForceRefresh", False)
        self.exclude_system_fields = config.get("ExcludeSystemFields", False)
        self.include_suggestions = config.get("IncludeSuggestions", False)
        self.expression = config.get("Expression", "")
        self.endpoints = structs.Endpoints(config)
        # self.fields = {f:dialog.fields.get(f) for f in config.get("Fields", [])}
        self.cond_parser = ConditionParser(self.dialog)
        if "dialogExpressionLink" not in self.endpoints:
            # WTF: This endpoint is needed but not included in the response, instead there is
            # a 'dialogExpression' endpoint that can be forged to:
            #     /DocuWare/Platform/FileCabinets/<FC_ID>/Query/DialogExpressionLink?dialogId=<DLG_ID>
            # Looks like a bug in DocuWare's API.
            if "dialogExpression" in self.endpoints:
                self.endpoints["dialogExpressionLink"] = re.sub(r"/DialogExpression\b",
                                                                "/DialogExpressionLink",
                                                                self.endpoints["dialogExpression"],
                                                                flags=re.IGNORECASE)
            else:
                raise errors.InternalError("Endpoint 'dialogExpression' missing")

    def search(self, conditions:Conditions, operation:str=None, sort_field:str=None, sort_order:str=None):
        terms = self.cond_parser.parse(conditions)
        query = {"fields": ",".join([t[0] for t in terms])}
        if sort_field:
            query["sortOrder"] = f"{self.cond_parser.field_by_name(sort_field).id} {sort_order if sort_order else 'Asc'}"
        path = self.dialog.client.conn.make_path(self.endpoints["dialogExpressionLink"], query=query)
        data = {
            "Condition": [{"DBName": k, "Value": v} for k, v in terms],
            "Operation": operation or AND,
        }
        result_url = self.dialog.client.conn.post_text(path, json=data).split("\n", 1)[0]
        result = self.dialog.client.conn.get_json(result_url)
        return SearchResult(result, self)

    def __str__(self):
        return f"{self.__class__.__name__} [{self.dialog.id}]"


class SearchResult:
    def __init__(self, config:dict, query:SearchQuery):
        self.query = query
        self.count = config.get("Count", {}).get("Value", 0)
        self.endpoints = structs.Endpoints(config)
        self.items = self._items(config)

    def _items(self, config:dict) -> Iterator:
        return (SearchResultItem(item, self) for item in config.get("Items", []))

    def __iter__(self):
        return self

    def __next__(self):
        while (item := next(self.items, None)) is None:
            if "next" in self.endpoints:
                result = self.query.dialog.client.conn.get_json(self.endpoints["next"])
                self.endpoints = structs.Endpoints(result)
                self.items = self._items(result)
            else:
                raise StopIteration
        return item

    def __str__(self):
        return f"{self.__class__.__name__} [{self.count}]"


class SearchResultItem:
    def __init__(self, config:dict, result:SearchResult):
        self.result = result
        self.fields = [FieldValue.from_config(f) for f in config.get("Fields", [])]
        self.content_type = config.get("ContentType")
        self.title = config.get("Title")
        self.file_cabinet_id = config.get("FileCabinetId")
        self.endpoints = structs.Endpoints(config)
        self._document = None

    def thumbnail(self) -> Tuple[bytes,str,str]:
        dw = self.result.query.dialog.client
        return dw.conn.get_bytes(self.endpoints["thumbnail"])

    @property
    def document(self):
        if self._document is None:
            dw = self.result.query.dialog.client
            config = dw.conn.get_json(self.endpoints["self"])
            self._document = Document(config, self.result.query.dialog.file_cabinet)
        return self._document

    def __str__(self):
        return f"{self.__class__.__name__} '{self.title}' [{self.content_type}]"


class FieldValue:
    TYPE_TABLE = {}

    def __init__(self, config:dict):
        self.name = config.get("FieldLabel")
        self.id = config.get("FieldName")
        self.content_type = config.get("ItemElementName")
        self.read_only = config.get("ReadOnly", True)
        self.internal = config.get("SystemField", False)
        self.value = config.get("Item")

    @staticmethod
    def from_config(config:dict):
        content_type = config.get("ItemElementName")
        return FieldValue.TYPE_TABLE.get(content_type, FieldValue)(config)

    def __str__(self):
        return f"Value '{self.name}' [{self.id}, {self.content_type}] = '{self.value}'"


class StringFieldValue(FieldValue):
    def __init__(self, config:dict):
        super().__init__(config)
        self.value = str(self.value) if self.value else None

    def __str__(self):
        return f"Text '{self.name}' [{self.id}] = '{self.value}'"


class KeywordsFieldValue(FieldValue):
    def __init__(self, config:dict):
        super().__init__(config)
        values = config.get("Item", {}).get("Keyword", [])
        self.value = values if values else None

    def __str__(self):
        return f"Keywords '{self.name}' [{self.id}] = {', '.join(self.value if self.value else [])}"


class IntFieldValue(FieldValue):
    def __init__(self, config:dict):
        super().__init__(config)
        try:
            self.value = None if self.value is None else int(self.value)
        except ValueError:
            raise errors.DataError(f"Value of field '{self.id}' is expected to be of type integer, found '{self.value}'")

    def __str__(self):
        return f"Integer '{self.name}' [{self.id}] = {self.value}"


class DecimalFieldValue(FieldValue):
    def __init__(self, config:dict):
        super().__init__(config)
        try:
            self.value = None if self.value is None else float(self.value)
        except ValueError:
            raise errors.DataError(f"Value of field '{self.id}' is expected to be of type float, found '{self.value}'")

    def __str__(self):
        return f"Decimal '{self.name}' [{self.id}] = {self.value}"


class DateTimeFieldValue(FieldValue):

    def __init__(self, config:dict):
        super().__init__(config)
        if self.content_type == "Date":
            self.value = utils.date_from_string(self.value)
        else:
            self.value = utils.datetime_from_string(self.value)

    def __str__(self):
        return f"{self.content_type} '{self.name}' [{self.id}] = {self.value}"


FieldValue.TYPE_TABLE = cidict.CaseInsensitiveDict({
    "Date": DateTimeFieldValue,
    "DateTime": DateTimeFieldValue,
    "Int": IntFieldValue,
    "Decimal": DecimalFieldValue,
    "String": StringFieldValue,
    "Keywords": KeywordsFieldValue,
})


class Document:
    def __init__(self, config:dict, file_cabinet:FileCabinet):
        self.file_cabinet = file_cabinet
        self.id = config.get("Id")
        self.title = config.get("Title")
        self.content_type = config.get("ContentType")
        self.size = config.get("FileSize", 0)
        self.modified = utils.datetime_from_string(config.get("LastModified"))
        self.created = utils.datetime_from_string(config.get("CreatedAt"))
        self.endpoints = structs.Endpoints(config)
        self.attachments = [DocumentAttachment(s, self) for s in config.get("Sections", [])]
        self.fields = [FieldValue.from_config(f) for f in config.get("Fields", [])]

    @staticmethod
    def _download(client:DocuwareClient, endpoint:str, keep_annotations:bool=True) -> Tuple[bytes,str,str]:
        return client.conn.get_bytes(endpoint, data={
            "keepAnnotations": "true" if keep_annotations else "false",
            "targetFileType": "PDF" if keep_annotations else "Auto",
        })

    def thumbnail(self) -> Tuple[bytes,str,str]:
        dw = self.file_cabinet.organization.client
        return dw.conn.get_bytes(self.endpoints["thumbnail"])

    def download(self, keep_annotations:bool=True) -> Tuple[bytes,str,str]:
        return Document._download(
            self.file_cabinet.organization.client,
            self.endpoints["fileDownload"],
            keep_annotations=keep_annotations,
        )

    def download_all(self) -> Tuple[bytes,str,str]:
        dw = self.file_cabinet.organization.client
        return dw.conn.get_bytes(self.endpoints["downloadAsArchive"])

    def __str__(self):
        return f"{self.__class__.__name__} '{self.title}' [{self.id}]"


# Attachment seems more reasonable than Section. In the DocuWare context a section is
# not a part of a file or document, but an individual attachment to the DocuWare document.
class DocumentAttachment:
    def __init__(self, config:dict, document:Document):
        self.document = document
        self.content_type = config.get("ContentType")
        self.filename = config.get("OriginalFileName")
        self.id = config.get("Id")
        self.size = config.get("FileSize", 0)
        self.pages = config.get("PageCount", 0)
        self.modified = utils.datetime_from_string(config.get("ContentModified"))
        self.has_annotations = config.get("HasTextAnnotation")
        self.endpoints = structs.Endpoints(config)
    
    def _fetch_endpoints(self):
        if "fileDownload" not in self.endpoints:
            dw = self.document.file_cabinet.organization.client
            config = dw.conn.get_json(self.endpoints["self"])
            self.endpoints = structs.Endpoints(config)

    def download(self, keep_annotations:bool=False) -> Tuple[bytes,str,str]:
        self._fetch_endpoints()
        data, mime, filename = Document._download(
            self.document.file_cabinet.organization.client,
            self.endpoints["fileDownload"],
            keep_annotations=keep_annotations,
        )
        return data, mime, self.filename or filename

    def __str__(self):
        return f"Attachment '{self.filename}' [{self.id}, {self.content_type}]"


class MyTasks:
    """Not working!"""
    def __init__(self, config:dict, organization:Organization):
        self.organization = organization
        self.endpoints = structs.Endpoints(config)
        self._tasks = None
        self.count = 0
        self.timestamp = None
        self.refresh()

    def refresh(self):
        result = self.organization.client.conn.get_json(self.endpoints["myTasks"])
        self._tasks = iter(result.get("Task", []))
        self.count = result.get("Count", 0)
        self.timestamp = utils.datetime_from_string(result.get("TimeStamp"))

    def __iter__(self):
        return self

    def __next__(self):
        if self._tasks:
            return next(self._tasks)
        else:
            raise StopIteration


# vim: set et sw=4 ts=4: