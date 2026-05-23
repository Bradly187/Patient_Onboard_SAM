import pytest
from unittest.mock import MagicMock, patch
from helpers import load_lambda, therapist_event

app = load_lambda('VerifyMedicalLicenseLambdaFunction')

_EVENT = therapist_event('TH001')

def _ddb_with_license(license_number='MD12345', state='CA'):
    mock = MagicMock()
    mock.get_item.return_value = {
        'Item': {
            'THERAPIST_ID':             'TH001',
            'DECLARED_LICENSE_NUMBER':  license_number,
            'DECLARED_LICENSE_STATE':   state,
        }
    }
    return mock

def _ddb_no_license():
    mock = MagicMock()
    mock.get_item.return_value = {'Item': {}}
    return mock

def _registry_response(valid=True, status='active'):
    m = MagicMock()
    m.post.return_value.raise_for_status.return_value = None
    m.post.return_value.json.return_value = {'valid': valid, 'status': status}
    return m


def test_license_found_and_verified():
    mock_table = _ddb_with_license()
    mock_requests = _registry_response(valid=True, status='active')

    with patch.object(app, 'ddb_table', mock_table), \
         patch('requests.post', mock_requests.post):
        result = app.lambda_handler(_EVENT, {})

    assert result == {'therapist_id': 'TH001', 'license_verified': True, 'license_status': 'active'}
    mock_table.update_item.assert_called_once()


def test_no_declared_license_returns_false_and_publishes_sns():
    mock_table = _ddb_no_license()
    mock_sns = MagicMock()

    with patch.object(app, 'ddb_table', mock_table), patch.object(app, 'sns', mock_sns):
        result = app.lambda_handler(_EVENT, {})

    assert result['license_verified'] is False
    assert result['license_status'] == 'no_license_on_record'
    mock_sns.publish.assert_called_once()
    mock_table.update_item.assert_called_once()


def test_registry_returns_invalid_publishes_sns():
    mock_table = _ddb_with_license()
    mock_requests = _registry_response(valid=False, status='expired')
    mock_sns = MagicMock()

    with patch.object(app, 'ddb_table', mock_table), \
         patch.object(app, 'sns', mock_sns), \
         patch('requests.post', mock_requests.post):
        result = app.lambda_handler(_EVENT, {})

    assert result['license_verified'] is False
    assert result['license_status'] == 'expired'
    mock_sns.publish.assert_called_once()


def test_registry_http_error_propagates():
    mock_table = _ddb_with_license()
    mock_post = MagicMock()
    mock_post.raise_for_status.side_effect = Exception('503 Service Unavailable')

    with patch.object(app, 'ddb_table', mock_table), \
         patch('requests.post', return_value=mock_post):
        with pytest.raises(Exception, match='503'):
            app.lambda_handler(_EVENT, {})
