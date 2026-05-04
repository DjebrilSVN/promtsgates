from evals.checks.schema import check_json_schema
from evals.checks.policy import check_banned_phrases, check_pii_leakage
from evals.checks.format import check_word_count, check_non_empty
from evals.checks.exact import check_exact_or_numeric_match


def test_json_schema_valid():
    valid_json = '{"invoice_number": "INV-100", "total_amount": 250.0}'
    result, data = check_json_schema(valid_json, required_fields=["invoice_number", "total_amount"])
    assert result.passed is True
    assert result.score == 1.0
    assert data["invoice_number"] == "INV-100"


def test_json_schema_markdown_fence_rejected():
    fenced_json = '```json\n{"invoice_number": "INV-100"}\n```'
    result, _ = check_json_schema(fenced_json, allow_markdown_fence=False)
    assert result.passed is False
    assert "markdown code block fences" in result.details


def test_json_schema_missing_fields():
    partial_json = '{"invoice_number": "INV-100"}'
    result, _ = check_json_schema(partial_json, required_fields=["invoice_number", "vendor"])
    assert result.passed is False
    assert "Missing required fields: ['vendor']" in result.details


def test_banned_phrases_detects_unauthorized_refund():
    text = "We apologize. I have promised you a full refund of $200."
    result = check_banned_phrases(text)
    assert result.passed is False
    assert "Violated policy" in result.details


def test_banned_phrases_clean_response():
    text = "We are reviewing your billing request with our finance department."
    result = check_banned_phrases(text)
    assert result.passed is True


def test_pii_leakage_detection():
    text = "Here is the card: 4111 2222 3333 4444."
    result = check_pii_leakage(text)
    assert result.passed is False
    assert "Credit Card" in result.details


def test_word_count_limits():
    short_text = "Hello world."
    assert check_word_count(short_text, min_words=5).passed is False

    long_text = " ".join(["word"] * 160)
    assert check_word_count(long_text, max_words=150).passed is False

    good_text = " ".join(["word"] * 50)
    assert check_word_count(good_text, min_words=10, max_words=150).passed is True


def test_exact_numeric_match():
    parsed = {"invoice_number": "INV-101", "total_amount": 250.00}
    expected = {"invoice_number": "inv-101", "total_amount": 250.004}
    result = check_exact_or_numeric_match(parsed, expected, tolerance=0.01)
    assert result.passed is True
