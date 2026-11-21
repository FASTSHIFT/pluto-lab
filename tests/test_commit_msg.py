# -*- coding: utf-8 -*-
"""Tests for the commit message rules and the Chinese scanner.

The rules live in ``scripts/check_commit_msg.py`` and
``scripts/check_no_chinese.py``; the commit-msg hook and CI call the same code,
so there is only one definition of "compliant".
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import check_commit_msg as ccm
import check_no_chinese as cnc


# ---------------------------------------------------------------- subject
def test_valid_subjects():
    for s in (
        "feat(adsb): add tar1090 web backend",
        "fix(modes): use NL-1 longitude zones for odd CPR frames",
        "docs: document the antenna length table",
        "ci: add a multi-platform test matrix",
        "refactor(sdr)!: split capture from decoding",
        "chore: bump the dependency pins",
    ):
        ok, why = ccm.validate_subject(s)
        assert ok, (s, why)


def test_invalid_subjects():
    for s in (
        "added some stuff",  # no type
        "feat: ",  # empty summary
        "feat(adsb) add web backend",  # missing colon
        "Feat(adsb): wrong case",
        "feat(ADSB): scope must be lowercase",
        "unknown: undefined type",
        "",
    ):
        ok, why = ccm.validate_subject(s)
        assert not ok, "should have been rejected: %r" % s


# Escape sequences keep this file ASCII while still exercising the CJK path.
CN = "\u4e2d\u6587"  # two Chinese characters
CN_TEXT = "\u8fd9\u91cc\u5199\u4e86\u4e2d\u6587"  # a short Chinese sentence


def test_chinese_subject_rejected():
    ok, why = ccm.validate_subject("feat(adsb): " + CN)
    assert not ok
    assert "English" in why


def test_chinese_body_rejected():
    text = "feat(adsb): add web backend\n\n" + CN_TEXT + "\n"
    ok, why = ccm.validate_message(text)
    assert not ok
    assert "body" in why


def test_english_body_accepted():
    text = "feat(adsb): add web backend\n\n- serve data/aircraft.json\n- default to AMap tiles\n"
    ok, why = ccm.validate_message(text)
    assert ok, why


def test_trailing_period_rejected():
    ok, _ = ccm.validate_subject("fix(ci): adjust the timeout")
    assert ok
    ok, why = ccm.validate_subject("fix(ci): adjust the timeout.")
    assert not ok and "period" in why


def test_length_limit():
    assert len("feat: ") + 94 == 100
    ok, _ = ccm.validate_subject("feat: " + "x" * 94)
    assert ok  # exactly 100 is allowed
    ok, why = ccm.validate_subject("feat: " + "x" * 95)
    assert not ok and "100" in why


def test_auto_messages_exempt():
    for s in ("Merge branch 'main' into dev", 'Revert "feat: x"', "fixup! feat(adsb): y", "squash! fix: z"):
        ok, _ = ccm.validate_subject(s)
        assert ok, s


def test_text_mode_exit_codes():
    assert ccm.main(["--text", "feat(adsb): add tar1090 web backend"]) == 0
    assert ccm.main(["--text", "random subject"]) == 1


def test_bad_range_returns_2():
    assert ccm.main(["--range", "definitely-not-a-ref..HEAD"]) == 2


# ---------------------------------------------------------------- chinese scan
def test_chinese_scanner_detects_cjk():
    assert cnc.CJK.search("const a = 1; // " + CN)
    assert cnc.CJK.search(CN)
    assert not cnc.CJK.search("plain english comment")


def test_chinese_scanner_on_repo():
    """The repo itself must be clean; the scanner is the source of truth."""
    assert cnc.main(["--quiet"]) == 0
