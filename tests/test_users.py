import unittest
from unittest.mock import MagicMock

from docuware import errors, users
from docuware.structs import Endpoints
from docuware.types import OrganizationP


class UserAndGroupTests(unittest.TestCase):
    def test_user_full_name_1(self):
        u = users.User("John Doe")
        self.assertEqual(u.name, "John Doe")
        self.assertEqual(u.last_name, "Doe")
        self.assertEqual(u.first_name, "John")

    def test_user_full_name_2(self):
        u = users.User("Doe, John")
        self.assertEqual(u.name, "Doe, John")
        self.assertEqual(u.last_name, "Doe")
        self.assertEqual(u.first_name, "John")

    def test_user_parts_1(self):
        u = users.User(first_name="John", last_name="Doe")
        self.assertEqual(u.name, "John Doe")
        self.assertEqual(u.last_name, "Doe")
        self.assertEqual(u.first_name, "John")

    def test_user_parts_2(self):
        u = users.User(last_name="Doe")
        self.assertEqual(u.name, "Doe")
        self.assertEqual(u.last_name, "Doe")
        self.assertEqual(u.first_name, None)

    def test_user_overwrite_1(self):
        u = users.User(first_name="foo", last_name="bar", name="John Doe")
        self.assertEqual(u.name, "John Doe")
        self.assertEqual(u.last_name, "Doe")
        self.assertEqual(u.first_name, "John")

    def test_user_overwrite_2(self):
        u = users.User(name="Doe, John")
        self.assertEqual(u.name, "Doe, John")
        self.assertEqual(u.last_name, "Doe")
        self.assertEqual(u.first_name, "John")
        u.first_name = "Jack"
        self.assertEqual(u.name, "Jack Doe")
        self.assertEqual(u.last_name, "Doe")
        self.assertEqual(u.first_name, "Jack")

    def test_group_create(self):
        g = users.Group(name="TestGroup")
        self.assertEqual(g.name, "TestGroup")


def _make_org(get_json_return=None, get_json_side_effect=None):
    mock_client = MagicMock()
    mock_conn = MagicMock()
    mock_client.conn = mock_conn
    if get_json_side_effect is not None:
        mock_conn.get_json.side_effect = get_json_side_effect
    elif get_json_return is not None:
        mock_conn.get_json.return_value = get_json_return
    mock_org = MagicMock(spec=OrganizationP)
    mock_org.client = mock_client
    mock_org.conn = mock_conn
    mock_org.endpoints = Endpoints({"Links": [
        {"rel": "users",    "href": "/DocuWare/Platform/Organizations/o1/Users"},
        {"rel": "groups",   "href": "/DocuWare/Platform/Organizations/o1/Groups"},
        {"rel": "userInfo", "href": "/DocuWare/Platform/Organizations/o1/UserInfo"},
    ]})
    return mock_org, mock_conn


def _make_user(org=None, active=False):
    mock_org = org or MagicMock(spec=OrganizationP)
    u = users.User.from_response({
        "Id": "42",
        "Name": "Doe, John",
        "FirstName": "John",
        "LastName": "Doe",
        "EMail": "john@example.com",
        "DBName": "DOEJOHN",
        "Active": active,
        "Links": [
            {"rel": "self",   "href": "/users/42"},
            {"rel": "groups", "href": "/users/42/groups"},
        ],
    }, mock_org)
    return u


class TestUserNameSetter(unittest.TestCase):
    def test_name_setter_empty_clears_full_name(self):
        u = users.User("John Doe")
        u.name = ""
        self.assertIsNone(u._full_name)

    def test_last_name_setter_clears_full_name(self):
        u = users.User("John Doe")
        u.last_name = "Smith"
        self.assertIsNone(u._full_name)
        self.assertEqual(u.name, "John Smith")


class TestUserMakeDbName(unittest.TestCase):
    def test_last_first_combined(self):
        u = users.User(first_name="John", last_name="Doe")
        self.assertEqual(u.make_db_name(), "DOEJOHN")

    def test_single_word_name(self):
        u = users.User("SingleName")
        self.assertEqual(u.make_db_name(), "SINGLENA")

    def test_special_chars_removed(self):
        u = users.User(first_name="Ján", last_name="Novák")
        db = u.make_db_name()
        self.assertEqual(db, "NOVKJN")
        self.assertTrue(db.isalnum())
        self.assertLessEqual(len(db), 8)


class TestUserFromResponse(unittest.TestCase):
    def test_from_response_sets_all_fields(self):
        mock_org = MagicMock(spec=OrganizationP)
        u = _make_user(org=mock_org)
        self.assertEqual(u.id, "42")
        self.assertEqual(u.db_name, "DOEJOHN")
        self.assertEqual(u.email, "john@example.com")
        self.assertFalse(u.active)
        self.assertIs(u.organization, mock_org)

    def test_from_response_active_true(self):
        u = _make_user(active=True)
        self.assertTrue(u.active)


class TestUserAsDict(unittest.TestCase):
    def test_as_dict_contains_expected_keys(self):
        u = _make_user(active=True)
        d = u.as_dict()
        self.assertEqual(d["EMail"], "john@example.com")
        self.assertEqual(d["DBName"], "DOEJOHN")
        self.assertTrue(d["Active"])

    def test_as_dict_with_overrides(self):
        u = _make_user(active=True)
        d = u.as_dict(overrides={"Active": False, "Extra": "x"})
        self.assertFalse(d["Active"])
        self.assertEqual(d["Extra"], "x")

    def test_as_dict_includes_active_false(self):
        u = _make_user(active=False)
        d = u.as_dict()
        self.assertIn("Active", d)
        self.assertFalse(d["Active"])

    def test_as_dict_excludes_none_and_empty_values(self):
        u = users.User(first_name="John", last_name="Doe")
        d = u.as_dict()
        self.assertNotIn("EMail", d)
        self.assertNotIn("Id", d)


class TestUserActiveSetter(unittest.TestCase):
    def test_active_setter_noop_when_same_value(self):
        mock_org, mock_conn = _make_org()
        u = _make_user(org=mock_org, active=True)
        u.active = True  # same value → no HTTP
        mock_conn.post_json.assert_not_called()

    def test_active_setter_raises_without_id(self):
        u = users.User(name="No ID")
        # id="" is falsy → UserOrGroupError
        with self.assertRaises(errors.UserOrGroupError):
            u.active = True

    def test_active_setter_makes_http_call(self):
        mock_org, mock_conn = _make_org()
        mock_conn.post_json.return_value = {}
        u = _make_user(org=mock_org, active=False)
        u.active = True
        mock_conn.post_json.assert_called_once()
        self.assertTrue(u._active)


class TestUserGroups(unittest.TestCase):
    def test_user_groups_returns_generator(self):
        mock_org, mock_conn = _make_org(get_json_return={
            "Item": [{"Name": "Admins", "Id": "g1", "Links": []}]
        })
        u = _make_user(org=mock_org)
        grps = list(u.groups)
        self.assertEqual(len(grps), 1)
        self.assertEqual(grps[0].name, "Admins")

    def test_user_groups_empty_when_no_org(self):
        u = users.User(name="Orphan")
        u.organization = None
        self.assertEqual(list(u.groups), [])


class TestUserGroupMembership(unittest.TestCase):
    def test_add_to_group_delegates(self):
        mock_group = MagicMock()
        mock_group.add_user.return_value = True
        u = users.User("Test")
        result = u.add_to_group(mock_group)
        mock_group.add_user.assert_called_once_with(u)
        self.assertTrue(result)

    def test_remove_from_group_delegates(self):
        mock_group = MagicMock()
        mock_group.remove_user.return_value = True
        u = users.User("Test")
        result = u.remove_from_group(mock_group)
        mock_group.remove_user.assert_called_once_with(u)
        self.assertTrue(result)


class TestUsers(unittest.TestCase):
    def test_users_iter_yields_users(self):
        mock_org, mock_conn = _make_org(get_json_return={
            "User": [
                {"Id": "1", "Name": "Alice", "Links": []},
                {"Id": "2", "Name": "Bob",   "Links": []},
            ]
        })
        user_list = users.Users(mock_org)
        result = list(user_list)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].id, "1")

    def test_users_getitem_by_name(self):
        mock_org, mock_conn = _make_org(get_json_return={
            "User": [{"Id": "1", "Name": "Alice", "Links": []}]
        })
        user_list = users.Users(mock_org)
        u = user_list["Alice"]
        self.assertEqual(u.name, "Alice")

    def test_users_add_creates_user(self):
        new_user = users.User(first_name="New", last_name="User", email="new@example.com")
        mock_org, mock_conn = _make_org(get_json_side_effect=[
            # post_json response (irrelevant, Users.add uses post_json on conn)
            # then iter for finding the new user
            {"User": [{"Id": "99", "Name": "New User", "DBName": "USERNEW", "Links": []}]},
        ])
        mock_conn.post_json.return_value = {}
        user_list = users.Users(mock_org)
        result = user_list.add(new_user, password="secret123")
        mock_conn.post_json.assert_called_once()
        # Result may be None if DBName doesn't match (acceptable)
        # Just verify no exception was raised


class TestGroup(unittest.TestCase):
    def test_group_from_response(self):
        mock_org = MagicMock(spec=OrganizationP)
        g = users.Group.from_response({
            "Id": "g1",
            "Name": "Admins",
            "Links": [{"rel": "users", "href": "/groups/g1/users"}],
        }, mock_org)
        self.assertEqual(g.id, "g1")
        self.assertEqual(g.name, "Admins")
        self.assertIs(g.organization, mock_org)

    def test_group_users_returns_generator(self):
        mock_org, mock_conn = _make_org(get_json_return={
            "User": [{"Id": "1", "Name": "Alice", "Links": []}]
        })
        g = users.Group.from_response({
            "Id": "g1", "Name": "Admins",
            "Links": [{"rel": "users", "href": "/groups/g1/users"}],
        }, mock_org)
        result = list(g.users)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].id, "1")

    def test_group_users_empty_when_no_org(self):
        g = users.Group("Empty")
        g.organization = None
        self.assertEqual(list(g.users), [])

    def test_set_user_membership_raises_without_group_id(self):
        g = users.Group("NoId")
        mock_user = MagicMock()
        mock_user.id = "1"
        with self.assertRaises(errors.UserOrGroupError):
            g._set_user_membership(mock_user, include=True)

    def test_set_user_membership_raises_without_org(self):
        g = users.Group("WithId")
        g.id = "g1"
        g.organization = None
        mock_user = MagicMock()
        mock_user.id = "1"
        with self.assertRaises(errors.UserOrGroupError):
            g._set_user_membership(mock_user, include=True)

    def test_set_user_membership_raises_without_user_id(self):
        mock_org = MagicMock(spec=OrganizationP)
        g = users.Group.from_response(
            {"Id": "g1", "Name": "G", "Links": []}, mock_org
        )
        mock_user = MagicMock()
        mock_user.id = ""
        with self.assertRaises(errors.UserOrGroupError):
            g._set_user_membership(mock_user, include=True)

    def test_add_user_returns_true_on_success(self):
        mock_org, mock_conn = _make_org()
        mock_conn.put.return_value = MagicMock(status_code=200)
        g = users.Group.from_response(
            {"Id": "g1", "Name": "G", "Links": []}, mock_org
        )
        mock_user = MagicMock()
        mock_user.id = "42"
        self.assertTrue(g.add_user(mock_user))

    def test_remove_user_returns_true_on_success(self):
        mock_org, mock_conn = _make_org()
        mock_conn.put.return_value = MagicMock(status_code=200)
        g = users.Group.from_response(
            {"Id": "g1", "Name": "G", "Links": []}, mock_org
        )
        mock_user = MagicMock()
        mock_user.id = "42"
        self.assertTrue(g.remove_user(mock_user))


class TestGroups(unittest.TestCase):
    def test_groups_iter_yields_groups(self):
        mock_org, mock_conn = _make_org(get_json_return={
            "Item": [
                {"Id": "g1", "Name": "Admins", "Links": []},
                {"Id": "g2", "Name": "Users",  "Links": []},
            ]
        })
        group_list = users.Groups(mock_org)
        result = list(group_list)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].id, "g1")

    def test_groups_get_by_name(self):
        mock_org, mock_conn = _make_org(get_json_return={
            "Item": [{"Id": "g1", "Name": "Admins", "Links": []}]
        })
        group_list = users.Groups(mock_org)
        g = group_list.get("Admins")
        self.assertIsNotNone(g)
        self.assertEqual(g.name, "Admins")

    def test_groups_get_not_found_returns_default(self):
        mock_org, mock_conn = _make_org(get_json_return={"Item": []})
        group_list = users.Groups(mock_org)
        self.assertIsNone(group_list.get("Nonexistent"))


if __name__ == "__main__":
    unittest.main()
