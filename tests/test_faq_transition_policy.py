"""Offline FAQ transition contract: no click or crawler claims."""
from rasai.faq_transition_policy import compare_faq_dom_views

URL = "https://example.test/faq"


def _html(expanded: bool, controls: int = 1) -> str:
    toggle = '<button aria-controls="faq-answer" aria-expanded="%s">Question</button>' % (
        "true" if expanded else "false"
    )
    return "<section>" + toggle * controls + (
        '<div id="faq-answer">Response visible in DOM</div>' if expanded else ""
    ) + "</section>"


def test_single_control_describes_snapshots_without_claiming_click() -> None:
    result = compare_faq_dom_views(
        _html(False), _html(True), target_id="faq-answer",
        before_url=URL, later_url=URL,
    )
    assert result["status"] == "DESCRIPTIVE_SNAPSHOT_PAIR_ONLY"
    assert result["action_or_click_verified"] is False
    assert result["crawler_discovery_verified"] is False
    assert result["score_change_authorized"] is False


def test_duplicate_controls_fail_closed_even_if_states_agree() -> None:
    for pre, post in ((_html(False, 2), _html(True)), (_html(False), _html(True, 2))):
        result = compare_faq_dom_views(
            pre, post, target_id="faq-answer", before_url=URL, later_url=URL,
        )
        assert result["status"] == "NOT_COMPARABLE"
        assert result["reason"] == "DOM_CONTROL_OR_PANEL_AMBIGUOUS"


def test_cross_url_snapshots_cannot_be_compared() -> None:
    result = compare_faq_dom_views(
        _html(False), _html(True), target_id="faq-answer",
        before_url=URL, later_url="https://other.test/faq",
    )
    assert result["status"] == "NOT_COMPARABLE"


def test_duplicate_controls_are_ambiguous_in_observation() -> None:
    from rasai.faq_observation import inspect_faq_html

    result = inspect_faq_html(_html(False, 2))
    assert result["controls"] == 1
    assert result["ambiguous"] == 1
    assert result["collapsed"] == 0
    assert result["unmounted"] == 0


def test_multiple_idrefs_or_duplicate_aria_controls_are_ambiguous() -> None:
    from rasai.faq_observation import inspect_faq_html
    for control in (
        '<button aria-controls="faq-one faq-two" aria-expanded="false">Q</button>',
        '<button aria-controls="faq-one" aria-controls="faq-two" aria-expanded="false">Q</button>',
    ):
        observed = inspect_faq_html(control)
        assert observed["controls"] == 2
        assert observed["ambiguous"] == 2
        assert observed["collapsed"] == 0
        comparison = compare_faq_dom_views(
            control, control, target_id="faq-one", before_url=URL, later_url=URL,
        )
        assert comparison["status"] == "NOT_COMPARABLE"
        assert comparison["reason"] == "DOM_CONTROL_OR_PANEL_AMBIGUOUS"


def test_faq_read_only_projection_never_creates_missing_database(tmp_path) -> None:
    from rasai.faq_observation import faq_observation_html
    missing = tmp_path / "missing.db"
    assert faq_observation_html(missing, "AUD-NO-DB") == ""
    assert not missing.exists()


def test_faq_read_only_projection_refuses_symlinked_database(tmp_path) -> None:
    from rasai.faq_observation import faq_observation_html
    import sqlite3
    source = tmp_path / "real.db"
    with sqlite3.connect(source) as con:
        con.execute("CREATE TABLE pages(page_id TEXT, audit_id TEXT)")
    alias = tmp_path / "redirect.db"
    try:
        alias.symlink_to(source)
    except (OSError, NotImplementedError):
        return
    assert faq_observation_html(alias, "AUD-OTHER") == ""
    assert source.is_file()


def test_faq_read_only_projection_abstains_on_corrupt_sqlite(tmp_path) -> None:
    from rasai.faq_observation import faq_observation_html
    db = tmp_path / "corrupt.db"
    db.write_bytes(b"not-a-sqlite-database")
    before = db.read_bytes()
    assert faq_observation_html(db, "AUD-CORRUPT") == ""
    assert db.read_bytes() == before


def test_faq_observer_does_not_open_uncheckpointed_sqlite(tmp_path) -> None:
    from rasai.faq_observation import faq_observation_html
    import sqlite3
    db = tmp_path / "audit.db"
    with sqlite3.connect(db) as con:
        con.execute("CREATE TABLE pages(page_id TEXT, audit_id TEXT)")
    journal = tmp_path / "audit.db-wal"
    journal.write_bytes(b"pending")
    assert faq_observation_html(db, "AUD-PENDING") == ""
    assert journal.read_bytes() == b"pending"


def test_faq_observer_refuses_symlinked_rendered_evidence(tmp_path) -> None:
    from rasai.faq_observation import _safe_rendered_file
    root = tmp_path / "AUD-LOCAL"
    evidence = root / "artifacts" / "rendered"
    evidence.mkdir(parents=True)
    real = evidence / "physical.html"
    real.write_text("<h1>FAQ</h1>", encoding="utf-8")
    alias = evidence / "alias.html"
    try:
        alias.symlink_to(real)
    except (OSError, NotImplementedError):
        return
    assert _safe_rendered_file(root, "artifacts/rendered/alias.html") is None
    assert _safe_rendered_file(root, "artifacts/rendered/physical.html") == real
