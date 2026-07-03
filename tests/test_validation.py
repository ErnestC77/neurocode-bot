from services.validation import is_valid_email


def test_valid_email_accepted():
    assert is_valid_email("name@example.com") is True


def test_missing_at_rejected():
    assert is_valid_email("nameexample.com") is False


def test_missing_domain_dot_rejected():
    assert is_valid_email("name@examplecom") is False


def test_spaces_rejected():
    assert is_valid_email("name @example.com") is False


def test_empty_string_rejected():
    assert is_valid_email("") is False
