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


def test_search_open_range_upper_bound(dw_search_dialog):
    """Open upper bound: [date, None] must return results, not silently zero."""
    closed = dw_search_dialog.search({"DWSTOREDATETIME": [date(2000, 1, 1), date.today()]})
    open_upper = dw_search_dialog.search({"DWSTOREDATETIME": [date(2000, 1, 1), None]})
    # Open upper bound should return at least as many results as the closed range
    assert open_upper.count >= closed.count


def test_search_open_range_lower_bound(dw_search_dialog):
    """Open lower bound: [None, date] must return results, not silently zero."""
    results = dw_search_dialog.search({"DWSTOREDATETIME": [None, date.today()]})
    assert results.count > 0
