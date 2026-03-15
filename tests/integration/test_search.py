from datetime import date

def test_search_dialog_has_fields(dw_search_dialog):
    fields = dw_search_dialog.fields
    assert isinstance(fields, dict)
    assert len(fields) > 0


def test_search_date_range(dw_search_dialog):
    # Uses DWSTOREDATETIME — adjust field name if not available in your dialog
    results = dw_search_dialog.search({"DWSTOREDATETIME": [date(2000, 1, 1), date.today()]})
    assert results.count >= 0


def test_search_can_iterate(dw_search_dialog):
    import itertools
    results = dw_search_dialog.search({"DWSTOREDATETIME": [date(2000, 1, 1), date.today()]})
    items = list(itertools.islice(results, 3))
    assert isinstance(items, list)
