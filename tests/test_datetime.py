import unittest

from datetime import datetime, date

from docuware import utils


class DateTimeTests(unittest.TestCase):

    DATETIME_1 = datetime(2022, 3, 5, 13, 37, 24)
    DATETIME_1_STR = "/Date(1646483844000)/"
    DATE_1 = date(2022, 3, 5)
    DATE_1_STR = "/Date(1646434800000)/"

    def test_datetime2str(self):
        self.assertEqual(utils.datetime_to_string(self.DATETIME_1), self.DATETIME_1_STR)
        self.assertEqual(utils.datetime_from_string(self.DATETIME_1_STR), self.DATETIME_1)

    def test_date2str(self):
        self.assertEqual(utils.date_to_string(self.DATE_1), self.DATE_1_STR)
        self.assertEqual(utils.date_from_string(self.DATE_1_STR), self.DATE_1)

