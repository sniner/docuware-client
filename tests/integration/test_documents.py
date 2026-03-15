def test_create_and_delete_document(dw_file_cabinet):
    # Adjust field name to match a field in your file cabinet
    doc = dw_file_cabinet.create_document(fields={"SUBJECT": "__integration_test__"})
    assert doc is not None
    assert doc.id is not None
    doc.delete()


def test_upload_and_download_attachment(dw_file_cabinet, tmp_path):
    # Create a minimal test file
    test_file = tmp_path / "test.txt"
    test_content = b"integration test attachment"
    test_file.write_bytes(test_content)

    doc = dw_file_cabinet.create_document(fields={"SUBJECT": "__integration_test_upload__"})
    assert doc.id is not None
    try:
        att = doc.upload_attachment(test_file)
        assert att is not None

        data, _mime, _filename = att.download()
        assert data == test_content
    finally:
        doc.delete()
