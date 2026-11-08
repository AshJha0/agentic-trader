"""Regression tests for the EDGAR section cutter, from short excerpts of real filings.

Each case is a cutting bug found by inspecting the 2015-2021 10-K/10-Q filings of the core
names (scripts/v15_edgar_design.py coverage). The heading and cross-reference lines are quoted
from the named filing; the body text between them is neutral filler.
"""
from agentic_trader.data.edgar_text import MIN_PERIODIC_CHARS, extract_sections

BODY = "\n\n".join(["Net sales rose in every segment during the year."] * 40)
OTHER = "\n\n".join(["The company has offices in several countries."] * 40)


def test_wrapped_cross_reference_does_not_start_mdna():
    # AAPL 10-K 0001193125-15-356351: a forward-looking-statements paragraph wraps so a line
    # starts "Item 7 of this Form 10-K ..."; it used to win as the MD&A start (6 kB, wrong).
    text = "\n".join([
        "Item 7.", "Management’s Discussion and Analysis", "Item 8.", "Financial Statements",
        "Forward-looking statements are discussed in Part II,",
        "Item 7 of this Form 10-K under the heading “Management’s Discussion and Analysis of "
        "Financial Condition and Results of Operations.” " + OTHER,
        "Item 7.", "Management’s Discussion and Analysis of Financial Condition and Results of Operations",
        BODY,
        "Item 8 of this Form 10-K in the Notes to Consolidated Financial Statements.",
        "More MD&A text after a wrapped reference to Item 8.",
        "Item 8.", "Financial Statements and Supplementary Data", "Statements follow.",
    ])
    mdna = extract_sections(text, "10-K")["7"]
    assert mdna.startswith("Management’s Discussion and Analysis of Financial Condition")
    assert "More MD&A text" in mdna            # the wrapped "Item 8 of this Form" did not end it
    assert "offices in several countries" not in mdna and "Statements follow" not in mdna


def test_risk_factor_reference_inside_mdna_does_not_start_1a():
    # XOM 10-K 0000034088-16-000065: inside the financial section a line reads
    # "Item 1A. Risk Factors for a more complete discussion of risks."; from there to the end
    # of the document (200 kB) used to be cut as Item 1A.
    text = "\n".join([
        "ITEM 1A. RISK FACTORS", BODY, "ITEM 1B. UNRESOLVED STAFF COMMENTS", "None.",
        "ITEM 7. MANAGEMENT’S DISCUSSION", "Reference is made to the Financial Section.",
        "ITEM 8. FINANCIAL STATEMENTS", "Reference is made to the Financial Section.",
        "FINANCIAL SECTION", OTHER * 3,
        "Item 1A. Risk Factors for a more complete discussion of risks.", OTHER * 3,
    ])
    secs = extract_sections(text, "10-K")
    assert secs["1A"].strip().endswith("during the year.")
    assert "7" not in secs                       # a one-line pointer is not an MD&A


def test_10q_risk_factor_pointer_and_part_ii_item_2():
    # JPM 10-Q 0000019617-17-000552: "Item 1A: Risk Factors in JPMorgan Chase’s 2016 Annual
    # Report on Form 10-K ..." starts a line mid-document (it was cut as a 340 kB Item 1A), and
    # the MD&A has no Item 2 heading, so Part II "Item 2. Unregistered Sales of Equity
    # Securities" was cut as the MD&A.
    text = "\n".join([
        "Part I", "Management’s discussion and analysis", BODY,
        "For a discussion of certain risks, see Part II,",
        "Item 1A: Risk Factors in JPMorgan Chase’s 2016 Annual Report on Form 10-K for the year ended "
        "December 31, 2016.", OTHER,
        "Part II – Other Information", "Item 1A. Risk Factors.",
        "For a discussion of certain risk factors affecting the Firm, see Risk Factors in the 2016 Form 10-K.",
        "Item 2. Unregistered Sales of Equity Securities and Use of Proceeds.", OTHER,
        "Item 6. Exhibits.",
    ])
    secs = extract_sections(text, "10-Q")
    assert secs == {}                            # 1A is a short pointer; there is no MD&A heading


def test_short_pointer_sections_are_omitted():
    # JPM 10-K 0000019617-18-000057 Item 7 is a pointer ("... appears on pages 40-145"), JNJ
    # 10-K 0000200406-15-000004 Item 1A points to Exhibit 99: neither is text to measure tone on.
    pointer = ("Management’s discussion and analysis of financial condition and results of operations, "
               "entitled “Management’s discussion and analysis,” appears on pages 40–145.")
    assert len(pointer) < MIN_PERIODIC_CHARS
    text = "\n".join(["Item 1A. Risk Factors", BODY, "Item 1B. Unresolved Staff Comments", "None.",
                      "Item 7. Management’s Discussion and Analysis", pointer, "Item 8. Financial Statements"])
    secs = extract_sections(text, "10-K")
    assert set(secs) == {"1A"}


def test_8k_items_unaffected_by_minimum():
    # 8-K items are short by nature (XOM 0000034088-20-000028 item 7.01 is 412 characters).
    text = "\n".join(["Item 7.01 Regulation FD Disclosure.",
                      "Exxon Mobil Corporation 1Q20 Earnings Considerations is furnished as Exhibit 99.1.",
                      "Item 9.01 Financial Statements and Exhibits."])
    assert "Earnings Considerations" in extract_sections(text, "8-K")["7.01"]


def test_passages_merge_short_html_lines():
    # Real 10-K text from HTML splits table cells into "paragraphs" of a few characters (median 9
    # on the core-name filings); with min_chars the RAG passages are merged runs of paragraphs.
    from datetime import datetime, timezone

    from agentic_trader.agentic.research_rag import passages_from_filings
    from agentic_trader.data.edgar_text import FilingSection
    text = "\n\n".join(["Risk factors"] + ["$ 1,234"] * 30 + ["The company faces competition. " * 30])
    s = FilingSection("X", "0000000001-21-000001", "10-K", "1A", datetime(2021, 2, 1, tzinfo=timezone.utc), text)
    one = passages_from_filings([s])
    merged = passages_from_filings([s], min_chars=300)
    assert len(one) == 32 and len(merged) < len(one)
    assert all(len(p.text) >= 300 for p in merged[:-1])
    assert "".join(p.text for p in merged).replace("\n\n", "") == text.strip().replace("\n\n", "")
    assert [p.id for p in merged] == [f"0000000001-21-000001#1A#{i}" for i in range(len(merged))]
