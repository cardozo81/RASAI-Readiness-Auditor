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


def test_faq_observation_closes_read_only_sqlite_handle(tmp_path, monkeypatch):
    """Windows report presentation must not retain audit.db handles."""
    import sqlite3
    import rasai.faq_observation as observer

    db = tmp_path / "audit.db"
    with sqlite3.connect(db) as con:
        con.execute("CREATE TABLE pages(page_id TEXT, audit_id TEXT)")
        con.execute("CREATE TABLE page_snapshots("
                    "snapshot_id TEXT, rendered_artifact_ref TEXT, page_id TEXT)")
    real_connect = sqlite3.connect
    handles = []

    class TrackingConnection(sqlite3.Connection):
        closed_explicitly = False

        def close(self):
            self.closed_explicitly = True
            return super().close()

    def tracked_connect(*args, **kwargs):
        connection = real_connect(*args, factory=TrackingConnection, **kwargs)
        handles.append(connection)
        return connection

    monkeypatch.setattr(observer.sqlite3, "connect", tracked_connect)
    assert observer.faq_observation_html(db, "AUD-TEST") == ""
    assert len(handles) == 1 and handles[0].closed_explicitly


def test_601_dom_initial_separates_closed_mounted_unmounted_and_open_cases():
    from rasai.faq_observation import inspect_faq_dom_states
    html = (
        '<button aria-controls="faq-closed" aria-expanded="false">Q1</button>'
        '<div id="faq-closed" hidden>Answer present in captured DOM</div>'
        '<button aria-controls="faq-lazy" aria-expanded="false">Q2</button>'
        '<button aria-controls="faq-open" aria-expanded="true">Q3</button>'
        '<section id="faq-open">Answer in already expanded DOM</section>'
        '<button aria-controls="faq-empty" aria-expanded="true">Q4</button>'
        '<div id="faq-empty"></div>'
        '<button aria-controls="faq-open-lazy" aria-expanded="true">Q5</button>'
    )
    result = inspect_faq_dom_states(html)
    assert result == {
        "controls": 5, "ambiguous": 0, "collapsed": 2,
        "unmounted": 1, "mounted": 1, "mounted_with_text": 1,
        "mounted_without_text": 0, "expanded": 3,
        "expanded_with_text": 1, "expanded_without_text": 1,
        "expanded_unmounted": 1,
    }


def test_601_read_only_cat03_html_exposes_both_observation_scopes(tmp_path):
    from rasai.faq_observation import faq_observation_html
    import sqlite3

    aud = tmp_path / "AUD-601"
    rendered = aud / "artifacts" / "rendered"
    rendered.mkdir(parents=True)
    page = rendered / "snapshot.html"
    page.write_text(
        '<button aria-controls="faq-lazy" aria-expanded="false">Q</button>'
        '<button aria-controls="faq-onpage" aria-expanded="true">Q</button>'
        '<div id="faq-onpage">A in DOM</div>',
        encoding="utf-8",
    )
    db = aud / "audit.db"
    with sqlite3.connect(db) as con:
        con.executescript(
            "CREATE TABLE pages(page_id TEXT, audit_id TEXT);"
            "CREATE TABLE page_snapshots("
            "snapshot_id TEXT, page_id TEXT, rendered_artifact_ref TEXT);"
        )
        con.execute("INSERT INTO pages VALUES('PAGE-1','AUD-601')")
        con.execute(
            "INSERT INTO page_snapshots VALUES(?,?,?)",
            ("SNP-1", "PAGE-1", "artifacts/rendered/snapshot.html"),
        )
    db_before, html_before = db.read_bytes(), page.read_bytes()
    output = faq_observation_html(db, "AUD-601")
    assert "Capacidade sem interação" in output
    assert "Disponibilidade após clique" in output
    assert "N/D quando não existe recibo autenticado" in output
    assert "Em estado expandido na captura havia 1 painel" in output
    assert "1 com texto DOM" in output
    assert "Painel não materializado não prova ausência editorial" in output
    assert "BR-GEO-039" in output and "BR-GEO-049" in output
    assert db.read_bytes() == db_before
    assert page.read_bytes() == html_before


def test_601_repeated_id_attribute_is_not_a_unique_dom_panel():
    from rasai.faq_observation import inspect_faq_dom_states
    for panel in (
        '<div id="faq-answer" id="faq-answer">Response</div>',
        '<div id="faq-answer" id="faq-other">Response</div>',
    ):
        initial = (
            '<button aria-controls="faq-answer" aria-expanded="false">Q</button>'
            + panel
        )
        observed = inspect_faq_dom_states(initial)
        assert observed["controls"] == 1
        assert observed["ambiguous"] == 1
        assert observed["collapsed"] == 0
        later = initial.replace('aria-expanded="false"', 'aria-expanded="true"')
        result = compare_faq_dom_views(
            initial, later, target_id="faq-answer",
            before_url=URL, later_url=URL,
        )
        assert result["status"] == "NOT_COMPARABLE"


def test_601_faq_partial_coverage_and_unreadable_snapshots_are_disclosed(tmp_path):
    import sqlite3
    from rasai.faq_observation import faq_observation_html

    root = tmp_path / "AUD-PARTIAL-FAQ"
    evidence = root / "artifacts" / "rendered"
    evidence.mkdir(parents=True)
    (evidence / "s-00.html").write_text(
        '<button aria-controls="faq-lazy" aria-expanded="false">Q</button>',
        encoding="utf-8",
    )
    db = root / "audit.db"
    with sqlite3.connect(db) as con:
        con.executescript(
            "CREATE TABLE pages(page_id TEXT, audit_id TEXT);"
            "CREATE TABLE page_snapshots("
            "snapshot_id TEXT, page_id TEXT, rendered_artifact_ref TEXT);"
        )
        con.execute("INSERT INTO pages VALUES ('P1','AUD-PARTIAL-FAQ')")
        for number in range(14):
            con.execute(
                "INSERT INTO page_snapshots VALUES (?, ?, ?)",
                (f"S-{number:02d}", "P1",
                 f"artifacts/rendered/s-{number:02d}.html"),
            )
    original = db.read_bytes()
    report = faq_observation_html(db, "AUD-PARTIAL-FAQ")
    assert "Cobertura física" in report
    assert "12 captura(s) examinada(s)" in report
    assert "11 inacessível(is)" in report
    assert "capturas adicionais fora do limite" in report
    assert "BR-GEO-039" in report
    assert db.read_bytes() == original


def test_601_missing_faq_controls_are_nd_not_editorial_absence(tmp_path):
    import sqlite3
    from rasai.faq_observation import faq_observation_html
    root = tmp_path / "AUD-EMPTY-FAQ"
    rendered = root / "artifacts" / "rendered"
    rendered.mkdir(parents=True)
    (rendered / "page.html").write_text("<main>Other content</main>", encoding="utf-8")
    db = root / "audit.db"
    with sqlite3.connect(db) as con:
        con.executescript(
            "CREATE TABLE pages(page_id TEXT, audit_id TEXT);"
            "CREATE TABLE page_snapshots("
            "snapshot_id TEXT, page_id TEXT, rendered_artifact_ref TEXT);"
            "INSERT INTO pages VALUES ('P1','AUD-EMPTY-FAQ');"
            "INSERT INTO page_snapshots VALUES "
            "('S1','P1','artifacts/rendered/page.html');"
        )
    original = db.read_bytes()
    html = faq_observation_html(db, "AUD-EMPTY-FAQ")
    assert "FAQ não identificável nesta amostra" in html
    assert "não comprova ausência editorial" in html
    assert db.read_bytes() == original


def test_601_duplicate_snapshot_identity_cannot_produce_partial_faq_totals(tmp_path):
    import sqlite3
    from rasai.faq_observation import faq_observation_html
    root = tmp_path / "AUD-DUP-FAQ"
    root.mkdir()
    db = root / "audit.db"
    with sqlite3.connect(db) as con:
        con.executescript(
            "CREATE TABLE pages(page_id TEXT, audit_id TEXT);"
            "CREATE TABLE page_snapshots("
            "snapshot_id TEXT, page_id TEXT, rendered_artifact_ref TEXT);"
            "INSERT INTO pages VALUES ('P1','AUD-DUP-FAQ');"
            "INSERT INTO page_snapshots VALUES ('S1','P1','artifacts/rendered/a.html');"
            "INSERT INTO page_snapshots VALUES ('S1','P1','artifacts/rendered/b.html');"
        )
    output = faq_observation_html(db, "AUD-DUP-FAQ")
    assert "Snapshot IDs ausentes ou duplicados: N/D" in output
    assert "Foram identificados" not in output

def test_601_jsonld_faqpage_is_separate_from_initial_dom_and_click():
    from rasai.faq_observation import inspect_faq_jsonld, inspect_faq_dom_states
    html = (
        '<main>Opening text</main><script type="application/ld+json">'
        '{"@context":"https://schema.org","@type":"FAQPage","mainEntity":'
        '[{"@type":"Question","name":"What?","acceptedAnswer":'
        '{"@type":"Answer","text":"A documented answer."}},'
        '{"@type":"Question","name":"How?"}]}</script>'
    )
    assert inspect_faq_dom_states(html)["controls"] == 0
    assert inspect_faq_jsonld(html) == {
        "status": "JSONLD_PARSED", "faqpage_entries": 1,
        "question_entries": 2, "answers_with_text": 1,
    }


def test_601_jsonld_graph_duplicate_keys_and_invalid_json_abstain():
    from rasai.faq_observation import inspect_faq_jsonld
    valid_graph = (
        '<script type="application/ld+json">'
        '{"@graph":[{"@type":"FAQPage","mainEntity":'
        '{"@type":"Question","acceptedAnswer":{"text":"Answer"}}}]}</script>'
    )
    assert inspect_faq_jsonld(valid_graph)["answers_with_text"] == 1
    for broken in (
        '<script type="application/ld+json">{"@type":"FAQPage","@type":"FAQPage"}</script>',
        '<script type="application/ld+json">{"@type":"FAQPage",</script>',
        '<script type="application/ld+json">{"@type":"FAQPage","a":NaN}</script>',
    ):
        assert inspect_faq_jsonld(broken)["status"] == "JSONLD_UNVERIFIABLE"


def test_601_nonfaq_jsonld_does_not_create_faq_answers():
    from rasai.faq_observation import inspect_faq_jsonld
    observed = inspect_faq_jsonld(
        '<script type="application/ld+json">{"@type":"Product","name":"A"}</script>'
    )
    assert observed["status"] == "JSONLD_PARSED"
    assert observed["faqpage_entries"] == 0
    assert observed["answers_with_text"] == 0

def test_601_truncated_jsonld_script_abstains_instead_of_reporting_zero():
    from rasai.faq_observation import inspect_faq_jsonld
    html = '<script type="application/ld+json">{"@type":"FAQPage"'
    assert inspect_faq_jsonld(html)["status"] == "JSONLD_UNVERIFIABLE"


def test_601_cat03_jsonld_without_accordion_is_reported_as_markup_only(tmp_path):
    """Physical read-only projection must expose FAQPage, not fake a click."""
    import sqlite3
    from rasai.faq_observation import faq_observation_html

    root = tmp_path / "AUD-FAQ-LD"
    rendered = root / "artifacts" / "rendered"
    rendered.mkdir(parents=True)
    page = rendered / "page.html"
    page.write_text(
        '<main>Public content</main><script type="application/ld+json">'
        '{"@type":"FAQPage","mainEntity":[{"@type":"Question",'
        '"acceptedAnswer":{"@type":"Answer","text":"Text in metadata only"}}]}'
        '</script>',
        encoding="utf-8",
    )
    database = root / "audit.db"
    with sqlite3.connect(database) as con:
        con.executescript(
            "CREATE TABLE pages(page_id TEXT, audit_id TEXT);"
            "CREATE TABLE page_snapshots("
            "snapshot_id TEXT, page_id TEXT, rendered_artifact_ref TEXT);"
            "INSERT INTO pages VALUES ('P1','AUD-FAQ-LD');"
            "INSERT INTO page_snapshots VALUES "
            "('S1','P1','artifacts/rendered/page.html');"
        )
    old_db, old_html = database.read_bytes(), page.read_bytes()
    report = faq_observation_html(database, "AUD-FAQ-LD")
    assert "FAQ interativo — N/D" in report
    assert "FAQPage JSON-LD" in report
    assert "1 entrada(s) FAQPage" in report
    assert "1 com texto acceptedAnswer na marcação" in report
    assert "não comprova" in report
    assert database.read_bytes() == old_db
    assert page.read_bytes() == old_html
