import unittest

from docuware import users


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
        
if __name__ == "__main__":
    unittest.main()
