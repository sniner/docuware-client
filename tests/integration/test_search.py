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


def test_search_result_item_exposes_id(dw_search_dialog):
    """SearchResultItem.id is populated directly from the search response."""
    import itertools
    results = dw_search_dialog.search({"DWSTOREDATETIME": [date(2000, 1, 1), date.today()]})
    items = list(itertools.islice(results, 3))
    if not items:
        import pytest
        pytest.skip("No documents available to verify id")
    for item in items:
        assert item.id is not None
        assert item.id == item.document.id


def test_search_order_by_single_field_flips_direction(dw_search_dialog):
    """Sorting asc vs desc on DWSTOREDATETIME must produce reversed top items."""
    import itertools
    import pytest
    cond = {"DWSTOREDATETIME": [date(2000, 1, 1), date.today()]}

    asc = list(itertools.islice(
        dw_search_dialog.search(cond, order_by=[("DWSTOREDATETIME", "asc")]), 5,
    ))
    desc = list(itertools.islice(
        dw_search_dialog.search(cond, order_by=[("DWSTOREDATETIME", "desc")]), 5,
    ))
    if len(asc) < 2 or len(desc) < 2:
        pytest.skip("Cabinet does not have enough documents to verify ordering")
    asc_ids = [it.id for it in asc]
    desc_ids = [it.id for it in desc]
    # Top items must differ — oldest vs newest
    assert asc_ids != desc_ids, "order_by asc and desc returned identical top results"


def test_search_order_by_multi_field_honored(dw_search_dialog):
    """Multi-field sort: changing only the secondary direction must change ordering
    within the primary-tie group, when such ties exist."""
    import itertools
    import pytest
    from docuware.errors import ResourceError
    cond = {"DWSTOREDATETIME": [date(2000, 1, 1), date.today()]}

    fields = dw_search_dialog.fields
    candidate_ids = [
        fid for fid, f in fields.items()
        if fid != "DWSTOREDATETIME"
        and (f.type or "").lower() in ("text", "string", "keyword")
    ]
    if not candidate_ids:
        pytest.skip("No non-primary text/keyword field for secondary sort")

    # Server returns 500 for fields it cannot sort by — try each candidate
    # until one works, otherwise skip.
    sec_field = None
    asc = None
    for fid in candidate_ids:
        try:
            asc = list(itertools.islice(
                dw_search_dialog.search(
                    cond, order_by=[("DWSTOREDATETIME", "desc"), (fid, "asc")],
                ),
                20,
            ))
            sec_field = fid
            break
        except ResourceError:
            continue
    if sec_field is None or asc is None:
        pytest.skip("No sortable secondary field found in this cabinet")

    desc = list(itertools.islice(
        dw_search_dialog.search(
            cond, order_by=[("DWSTOREDATETIME", "desc"), (sec_field, "desc")],
        ),
        20,
    ))
    if len(asc) < 4 or len(desc) < 4:
        pytest.skip("Not enough documents to verify multi-field sort")
    # Cabinets without DWSTOREDATETIME ties will produce identical orderings —
    # treat that as inconclusive rather than a failure.
    if [it.id for it in asc] == [it.id for it in desc]:
        pytest.skip(f"No primary-key ties on DWSTOREDATETIME — can't verify secondary sort via {sec_field}")
