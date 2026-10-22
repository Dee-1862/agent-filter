"""PII tests, run with the regex fallback and (when the spaCy model is present) Presidio."""
import pytest

from otr import pii


def _presidio_ok() -> bool:
    try:
        return pii.presidio_available()
    except Exception:
        return False


MODES = [pytest.param(False, id="regex"),
         pytest.param(True, id="presidio", marks=pytest.mark.skipif(
             not _presidio_ok(), reason="Presidio/spaCy model unavailable (or OTR_NO_PRESIDIO set)"))]


@pytest.fixture(params=MODES)
def mode(request):
    return request.param


def labels(text, mode):
    return pii.redact_pii(text, mode)[1]


def test_email_phone_ssn_card(mode):
    assert "EMAIL" in labels("mail me at bob@acme.com please", mode)
    assert "PHONE" in labels("call 415-555-0199 tomorrow", mode)
    assert "SSN" in labels("my ssn is 123-45-6789", mode)
    assert "CREDIT_CARD" in labels("card 4111 1111 1111 1111 exp soon", mode)


def test_masking_output(mode):
    masked, labs = pii.redact_pii("email bob@acme.com now", mode)
    assert masked == "email [EMAIL] now" and labs == ["EMAIL"]
    assert pii.redact_pii("nothing here", mode) == ("nothing here", [])


def test_spoken_phone(mode):
    t = "my number is four one five five five five zero one nine nine ok"
    masked, labs = pii.redact_pii(t, mode)
    assert "PHONE" in labs
    assert masked.startswith("my number is [PHONE]") and masked.endswith("ok")


def test_spoken_email(mode):
    masked, labs = pii.redact_pii("send it to bob at acme dot com thanks", mode)
    assert "EMAIL" in labs and masked == "send it to [EMAIL] thanks"


def test_split_phone_across_segments(mode):
    segs = ["my number is 415 555", "0199 call me"]
    assert labels(segs[0], mode) == [] and "PHONE" not in labels(segs[1], mode)
    per = pii.find_pii_window(segs, mode)
    assert per[0] and per[1]
    out = pii.redact_pii_window(segs, mode)
    assert "415" not in out[0][0] and "0199" not in out[1][0]


def test_window_offsets_single_segment(mode):
    segs = ["hello there", "mail bob@acme.com ok", "bye"]
    per = pii.find_pii_window(segs, mode)
    assert per[0] == [] and per[2] == []
    (lab, s, e), = per[1]
    assert lab == "EMAIL" and segs[1][s:e] == "bob@acme.com"


@pytest.mark.parametrize("text", [
    "Alice and Bob will present the roadmap",
    "I bought an iPhone 15 yesterday",
    "we ship version 3.12.1 on Friday",
    "the standup is at 4:15 today",
    "let us meet at 4:15 or 16:45",
    "revenue grew 15 percent in Q3 2025",
    "Dr. Chen from Seattle joined the call",
    "one two three go",
])
def test_no_false_positives(text, mode):
    assert pii.redact_pii(text, mode) == (text, [])


def test_person_only_with_sensitive_context():
    if not _presidio_ok():
        pytest.skip("Presidio unavailable")
    assert pii.redact_pii("Sarah Johnson is presenting the demo", True)[1] == []
    assert "PERSON" in pii.redact_pii("Sarah Johnson has a cancer diagnosis", True)[1]


def test_flags():
    assert isinstance(pii.presidio_available(), bool)
    assert isinstance(pii.presidio_model(), str)
