import pytest
from unittest.mock import MagicMock, patch
from helpers import load_lambda, store_verification_event

app = load_lambda('StoreVerificationLambdaFunction')


def _mock_post():
    m = MagicMock()
    m.post.return_value.raise_for_status.return_value = None
    return m


def test_all_checks_pass_posts_to_api_and_returns_success():
    mock_table = MagicMock()
    mock_requests = _mock_post()

    with patch.object(app, 'ddb_table', mock_table), \
         patch('requests.post', mock_requests.post):
        result = app.lambda_handler(store_verification_event('PT001'), {})

    assert result == {'patient_id': 'PT001', 'verification_passed': True, 'needs_review': False}
    mock_requests.post.assert_called_once()
    call_url = mock_requests.post.call_args[0][0]
    assert '/patients/PT001/verify' in call_url
    mock_table.update_item.assert_called_once()


def test_face_mismatch_raises_and_publishes_sns():
    mock_table, mock_sns = MagicMock(), MagicMock()

    with patch.object(app, 'ddb_table', mock_table), \
         patch.object(app, 'sns', mock_sns):
        with pytest.raises(RuntimeError):
            app.lambda_handler(store_verification_event(face_match=False), {})

    mock_sns.publish.assert_called_once()
    mock_table.update_item.assert_called_once()


def test_license_invalid_raises_and_publishes_sns():
    mock_table, mock_sns = MagicMock(), MagicMock()

    with patch.object(app, 'ddb_table', mock_table), \
         patch.object(app, 'sns', mock_sns):
        with pytest.raises(RuntimeError):
            app.lambda_handler(store_verification_event(license_valid=False), {})

    mock_sns.publish.assert_called_once()


def test_insurance_needs_review_does_not_prevent_success():
    # needs_review is a soft flag — the overall pipeline should still succeed
    mock_table = MagicMock()
    mock_requests = _mock_post()

    with patch.object(app, 'ddb_table', mock_table), \
         patch('requests.post', mock_requests.post):
        result = app.lambda_handler(
            store_verification_event(extraction_ok=False, needs_review=True), {}
        )

    assert result['verification_passed'] is True
    assert result['needs_review'] is True
