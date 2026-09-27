from backend.tools.mock import mock_research


def test_mock_research_success():
    res = mock_research("AI market")
    assert res["tool"] == "mock_research"
    assert res["summary"] == "Mock research completed successfully."
    assert res["mock"] is True


def test_mock_research_failure():
    try:
        mock_research("FAIL_TOOL")
        assert False
    except RuntimeError as e:
        assert "failure requested" in str(e)
