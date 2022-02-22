import unittest

from docuware import cidict, parser


class ParserTests(unittest.TestCase):
    CD_OK_1 = 'form-data; Name="fieldName"'
    CD_OK_2 = 'form-data; name="fieldName"; filename="filename.jpg"'
    CD_OK_3 = 'form-data; name=fieldName; filename=filename.jpg'
    CD_OK_4 = 'form-data; name="fieldName" ; filename=filename.jpg'
    CD_OK_5 = 'form-data; name="name1; name2"; filename=filename.jpg'
    CD_OK_6 = 'form-data;name=;filename=filename.jpg'
    CD_ERR_1 = 'form-data;name="Name"; filename="filename.jpg'
    CD_ERR_2 = 'form-data;name='
    CD_EXC_1 = 'form-data;name=="" ?'

    def test_CharReader(self):
        r = parser.CharReader("ABC")
        self.assertEqual(r.getch(), "A")
        self.assertEqual(r.getch(), "B")
        r.ungetch("X")
        self.assertEqual(r.getch(), "X")
        self.assertEqual(r.getch(), "C")
        r.ungetch("Ä")
        r.ungetch("ÖÜ")
        self.assertEqual(r.getch(), "Ä")
        self.assertEqual(r.getch(), "ÖÜ")

    def test_content_disposition(self):
        cd = parser.parse_content_disposition("", case_insensitive=False)
        self.assertEqual(cd, {})
        cd = parser.parse_content_disposition(None, case_insensitive=False)
        self.assertEqual(cd, {})
        cd = parser.parse_content_disposition(self.CD_OK_1)
        self.assertIsInstance(cd, cidict.CaseInsensitiveDict)
        self.assertEqual(cd.get("Type"), "form-data")
        self.assertEqual(cd.get("NAME"), "fieldName")
        cd = parser.parse_content_disposition(self.CD_OK_2, case_insensitive=False)
        self.assertIsInstance(cd, dict)
        self.assertEqual(cd.get("type"), "form-data")
        self.assertEqual(cd.get("name"), "fieldName")
        self.assertEqual(cd.get("filename"), "filename.jpg")
        cd = parser.parse_content_disposition(self.CD_OK_3)
        self.assertEqual(cd.get("type"), "form-data")
        self.assertEqual(cd.get("name"), "fieldName")
        self.assertEqual(cd.get("filename"), "filename.jpg")
        cd = parser.parse_content_disposition(self.CD_OK_4)
        self.assertEqual(cd.get("type"), "form-data")
        self.assertEqual(cd.get("name"), "fieldName")
        self.assertEqual(cd.get("filename"), "filename.jpg")
        cd = parser.parse_content_disposition(self.CD_OK_5)
        self.assertEqual(cd.get("type"), "form-data")
        self.assertEqual(cd.get("name"), "name1; name2")
        self.assertEqual(cd.get("filename"), "filename.jpg")
        cd = parser.parse_content_disposition(self.CD_OK_6)
        self.assertEqual(cd.get("type"), "form-data")
        self.assertEqual(cd.get("name"), "")
        self.assertEqual(cd.get("filename"), "filename.jpg")
        cd = parser.parse_content_disposition(self.CD_ERR_1)
        self.assertEqual(cd.get("name"), "Name")
        self.assertEqual(cd.get("filename"), "filename.jpg")
        cd = parser.parse_content_disposition(self.CD_ERR_2)
        self.assertEqual(cd.get("type"), "form-data")
        self.assertEqual(cd.get("name"), "")
        self.assertRaises(ValueError, parser.parse_content_disposition, self.CD_EXC_1)

    def test_condition_parser(self):
        sc = parser.parse_search_condition("keyword=test")
        self.assertEqual(sc, ("keyword", ["test"]))
        sc = parser.parse_search_condition(" keyword = test ")
        self.assertEqual(sc, ("keyword", ["test"]))
        sc = parser.parse_search_condition("keyword=test1,test2")
        self.assertEqual(sc, ("keyword", ["test1", "test2"]))
        sc = parser.parse_search_condition('keyword="test 1",test2')
        self.assertEqual(sc, ("keyword", ["test 1", "test2"]))
        sc = parser.parse_search_condition('keyword=test1,"test 2"')
        self.assertEqual(sc, ("keyword", ["test1", "test 2"]))
        sc = parser.parse_search_condition('keyword="test 1","test 2"')
        self.assertEqual(sc, ("keyword", ["test 1", "test 2"]))
        sc = parser.parse_search_condition('keyword = "test 1" , "test 2"')
        self.assertEqual(sc, ("keyword", ["test 1", "test 2"]))
        sc = parser.parse_search_condition('keyword = "test\\" 1" , " test 2 "')
        self.assertEqual(sc, ("keyword", ["test\" 1", " test 2 "]))
