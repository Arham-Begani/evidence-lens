import pytest

from evidence_study.io import StudyError
from evidence_study.provenance import resolve_origins


def test_shared_origin_does_not_remove_new_claim():
    nodes = [
        {"id": "report-a", "claim": "A", "relation": "direct"},
        {"id": "summary-a", "claim": "A", "relation": "derived", "parents": ["report-a"]},
        {"id": "mixed-a", "claim": "A", "relation": "derived", "parents": ["summary-a"]},
        {"id": "mixed-b", "claim": "B", "relation": "direct"},
        {"id": "uncertain-a", "claim": "A", "relation": "unknown"},
    ]
    result = resolve_origins(nodes)
    assert result["A"]["reporting_origins"] == ["report-a"]
    assert result["A"]["unresolved_nodes"] == ["uncertain-a"]
    assert result["B"]["reporting_origins"] == ["mixed-b"]
    assert all(r["statistical_independence"] == "not_established" for r in result.values())


def test_distinct_origins_still_do_not_prove_independence():
    result = resolve_origins([{"id": "x", "claim": "A", "relation": "direct"},
                              {"id": "y", "claim": "A", "relation": "direct"}])
    assert result["A"]["reporting_origins"] == ["x", "y"]
    assert result["A"]["statistical_independence"] == "not_established"


@pytest.mark.parametrize("nodes,message", [
    ([{"id": "a", "claim": "A", "relation": "derived", "parents": ["b"]},
      {"id": "b", "claim": "A", "relation": "derived", "parents": ["a"]}], "cycle"),
    ([{"id": "a", "claim": "A", "relation": "direct"},
      {"id": "b", "claim": "B", "relation": "derived", "parents": ["a"]}], "same claim"),
    ([{"id": "a", "claim": "A", "relation": "derived", "parents": ["missing"]}], "same claim"),
    ([{"id": "a", "claim": "A", "relation": "derived"}], "upstream node"),
    ([{"id": "a", "claim": "A", "relation": "unknown", "parents": ["x"]}], "Only derived"),
    ([{"id": "a", "claim": "A", "relation": "guessed"}], "Unknown reporting"),
    ([{}], "requires"), ([], "nonempty")])
def test_bad_provenance_rejected(nodes, message):
    with pytest.raises(StudyError, match=message): resolve_origins(nodes)
