from unittest.mock import MagicMock, patch
from helpers import load_lambda, analyze_id_response, patient_event, BUCKET

app = load_lambda('ExtractLicenseDetailsLambdaFunction')

_FULL_FIELDS = {
    'DOCUMENT_NUMBER': 'D123456',
    'FIRST_NAME':      'Jane',
    'LAST_NAME':       'Doe',
    'DATE_OF_BIRTH':   '1990-01-15',
    'EXPIRATION_DATE': '2028-01-15',
}


def test_extracts_required_fields_and_returns_license_valid():
    mock_textract = MagicMock()
    mock_textract.analyze_id.return_value = analyze_id_response(_FULL_FIELDS)
    mock_table = MagicMock()

    with patch.object(app, 'textract', mock_textract), patch.object(app, 'ddb_table', mock_table):
        result = app.lambda_handler(patient_event('PT001'), {})

    assert result['license_valid'] is True
    assert result['missing_fields'] == []
    assert result['extracted']['DOCUMENT_NUMBER'] == 'D123456'
    mock_textract.analyze_id.assert_called_once_with(
        DocumentPages=[{'S3Object': {'Bucket': BUCKET, 'Name': 'PT001_license.jpg'}}]
    )
    mock_table.update_item.assert_called_once()


def test_missing_required_field_sets_license_invalid_and_publishes_sns():
    incomplete = {k: v for k, v in _FULL_FIELDS.items() if k != 'DATE_OF_BIRTH'}
    mock_textract = MagicMock()
    mock_textract.analyze_id.return_value = analyze_id_response(incomplete)
    mock_table, mock_sns = MagicMock(), MagicMock()

    with patch.object(app, 'textract', mock_textract), \
         patch.object(app, 'ddb_table', mock_table), \
         patch.object(app, 'sns', mock_sns):
        result = app.lambda_handler(patient_event('PT001'), {})

    assert result['license_valid'] is False
    assert 'DATE_OF_BIRTH' in result['missing_fields']
    mock_sns.publish.assert_called_once()


def test_non_required_field_missing_does_not_affect_validity():
    # EXPIRATION_DATE is extracted but not required — omitting it should still pass
    without_optional = {k: v for k, v in _FULL_FIELDS.items() if k != 'EXPIRATION_DATE'}
    mock_textract = MagicMock()
    mock_textract.analyze_id.return_value = analyze_id_response(without_optional)
    mock_table = MagicMock()

    with patch.object(app, 'textract', mock_textract), patch.object(app, 'ddb_table', mock_table):
        result = app.lambda_handler(patient_event('PT001'), {})

    assert result['license_valid'] is True
