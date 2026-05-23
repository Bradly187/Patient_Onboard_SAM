from unittest.mock import MagicMock, patch
from helpers import (
    load_lambda, textract_query_response, textract_query_response_low_confidence,
    patient_event,
)

app = load_lambda('ExtractInsuranceLambdaFunction')

_REQUIRED = [
    ('MEMBER_ID',   'MBR123456'),
    ('PAYER_NAME',  'Blue Cross'),
    ('MEMBER_NAME', 'Jane Doe'),
]
_OPTIONAL = [
    ('POLICY_NUMBER', 'POL-789'),
    ('GROUP_NUMBER',  'GRP-001'),
]


def test_all_required_fields_extracted_posts_to_api():
    mock_textract = MagicMock()
    mock_textract.analyze_document.return_value = textract_query_response(_REQUIRED + _OPTIONAL)
    mock_table = MagicMock()
    mock_requests = MagicMock()
    mock_requests.post.return_value.raise_for_status.return_value = None

    with patch.object(app, 'textract', mock_textract), \
         patch.object(app, 'ddb_table', mock_table), \
         patch('requests.post', mock_requests.post):
        result = app.lambda_handler(patient_event('PT001'), {})

    assert result['extraction_ok'] is True
    assert result['needs_review'] is False
    assert result['insurance_data']['memberName'] == 'Jane Doe'
    mock_requests.post.assert_called_once()
    mock_table.update_item.assert_called_once()


def test_missing_required_field_soft_fails_without_raising():
    # MEMBER_ID missing — should not raise, should flag needs_review
    mock_textract = MagicMock()
    mock_textract.analyze_document.return_value = textract_query_response(
        [('PAYER_NAME', 'Blue Cross'), ('MEMBER_NAME', 'Jane Doe')]
    )
    mock_table, mock_sns = MagicMock(), MagicMock()

    with patch.object(app, 'textract', mock_textract), \
         patch.object(app, 'ddb_table', mock_table), \
         patch.object(app, 'sns', mock_sns):
        result = app.lambda_handler(patient_event('PT001'), {})

    assert result['extraction_ok'] is False
    assert result['needs_review'] is True
    assert 'MEMBER_ID' in result['missing_fields']
    mock_sns.publish.assert_called_once()


def test_low_confidence_answers_are_excluded():
    mock_textract = MagicMock()
    mock_textract.analyze_document.return_value = textract_query_response_low_confidence(_REQUIRED)
    mock_table, mock_sns = MagicMock(), MagicMock()

    with patch.object(app, 'textract', mock_textract), \
         patch.object(app, 'ddb_table', mock_table), \
         patch.object(app, 'sns', mock_sns):
        result = app.lambda_handler(patient_event('PT001'), {})

    # All answers below threshold — all required fields missing
    assert result['extraction_ok'] is False
    assert set(result['missing_fields']) == {'MEMBER_ID', 'PAYER_NAME', 'MEMBER_NAME'}
