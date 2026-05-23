from unittest.mock import MagicMock, patch
from helpers import (
    load_lambda, rekognition_match, rekognition_no_match,
    patient_event, therapist_event, BUCKET,
)

app = load_lambda('CompareFacesLambdaFunction')


def test_patient_face_match_returns_true():
    mock_rekog = MagicMock()
    mock_rekog.compare_faces.return_value = rekognition_match(95.0)
    mock_table = MagicMock()

    with patch.object(app, 'rekognition', mock_rekog), patch.object(app, 'ddb_table', mock_table):
        result = app.lambda_handler(patient_event('PT001'), {})

    assert result == {'patient_id': 'PT001', 'face_match': True, 'face_similarity': 95.0}
    mock_rekog.compare_faces.assert_called_once_with(
        SourceImage={'S3Object': {'Bucket': BUCKET, 'Name': 'PT001_license.jpg'}},
        TargetImage={'S3Object': {'Bucket': BUCKET, 'Name': 'PT001_selfie.png'}},
        SimilarityThreshold=80,
    )
    mock_table.update_item.assert_called_once()


def test_patient_face_no_match_returns_false_and_publishes_sns():
    mock_rekog = MagicMock()
    mock_rekog.compare_faces.return_value = rekognition_no_match()
    mock_table, mock_sns = MagicMock(), MagicMock()

    with patch.object(app, 'rekognition', mock_rekog), \
         patch.object(app, 'ddb_table', mock_table), \
         patch.object(app, 'sns', mock_sns):
        result = app.lambda_handler(patient_event('PT001'), {})

    assert result['face_match'] is False
    assert result['face_similarity'] == 0.0
    mock_sns.publish.assert_called_once()


def test_therapist_event_uses_therapist_key_and_selfie():
    mock_rekog = MagicMock()
    mock_rekog.compare_faces.return_value = rekognition_match(88.0)
    mock_table = MagicMock()

    with patch.object(app, 'rekognition', mock_rekog), patch.object(app, 'ddb_table', mock_table):
        result = app.lambda_handler(therapist_event('TH001'), {})

    assert result['therapist_id'] == 'TH001'
    assert result['face_match'] is True
    target_key = mock_rekog.compare_faces.call_args[1]['TargetImage']['S3Object']['Name']
    assert target_key == 'TH001_therapist_selfie.png'
    ddb_key = mock_table.update_item.call_args[1]['Key']
    assert 'THERAPIST_ID' in ddb_key
