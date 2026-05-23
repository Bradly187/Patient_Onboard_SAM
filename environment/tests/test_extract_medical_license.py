from unittest.mock import MagicMock, patch
from helpers import (
    load_lambda, textract_query_response, textract_query_response_low_confidence,
    therapist_event, BUCKET,
)

app = load_lambda('ExtractMedicalLicenseLambdaFunction')

_EVENT = therapist_event('TH001')

_FULL_FIELDS = [
    ('LICENSE_NUMBER',  'MD12345'),
    ('LICENSEE_NAME',   'Dr. Jane Doe'),
    ('EXPIRATION_DATE', '2026-12-31'),
    ('SPECIALTY',       'Psychiatry'),
    ('ISSUING_STATE',   'CA'),
]


def test_extracts_required_fields_and_stores_in_dynamo():
    mock_textract = MagicMock()
    mock_textract.analyze_document.return_value = textract_query_response(_FULL_FIELDS)
    mock_table = MagicMock()

    with patch.object(app, 'textract', mock_textract), patch.object(app, 'ddb_table', mock_table):
        result = app.lambda_handler(_EVENT, {})

    assert result['extraction_ok'] is True
    assert result['missing_fields'] == []
    assert result['extracted']['LICENSE_NUMBER'] == 'MD12345'
    mock_textract.analyze_document.assert_called_once_with(
        Document={'S3Object': {'Bucket': BUCKET, 'Name': 'TH001_medical_license.jpg'}},
        FeatureTypes=['QUERIES'],
        QueriesConfig={'Queries': app.MEDICAL_LICENSE_QUERIES},
    )
    mock_table.update_item.assert_called_once()


def test_missing_required_field_sets_extraction_not_ok_and_publishes_sns():
    partial = [f for f in _FULL_FIELDS if f[0] != 'LICENSE_NUMBER']
    mock_textract = MagicMock()
    mock_textract.analyze_document.return_value = textract_query_response(partial)
    mock_table, mock_sns = MagicMock(), MagicMock()

    with patch.object(app, 'textract', mock_textract), \
         patch.object(app, 'ddb_table', mock_table), \
         patch.object(app, 'sns', mock_sns):
        result = app.lambda_handler(_EVENT, {})

    assert result['extraction_ok'] is False
    assert 'LICENSE_NUMBER' in result['missing_fields']
    mock_sns.publish.assert_called_once()


def test_low_confidence_answers_dropped():
    mock_textract = MagicMock()
    mock_textract.analyze_document.return_value = textract_query_response_low_confidence(_FULL_FIELDS)
    mock_table, mock_sns = MagicMock(), MagicMock()

    with patch.object(app, 'textract', mock_textract), \
         patch.object(app, 'ddb_table', mock_table), \
         patch.object(app, 'sns', mock_sns):
        result = app.lambda_handler(_EVENT, {})

    assert result['extracted'] == {}
    assert result['extraction_ok'] is False
