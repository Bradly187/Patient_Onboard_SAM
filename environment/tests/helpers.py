"""Shared response-builder helpers for mocking AWS service calls."""
import os
import sys
import importlib.util


def load_lambda(lambda_dir):
    """Import a Lambda app.py under a unique module name to avoid sys.modules collisions."""
    path = os.path.join(os.path.dirname(__file__), '..', lambda_dir, 'app.py')
    if lambda_dir in sys.modules:
        return sys.modules[lambda_dir]
    spec = importlib.util.spec_from_file_location(lambda_dir, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[lambda_dir] = mod
    spec.loader.exec_module(mod)
    return mod


# --- Rekognition helpers ---

def rekognition_match(similarity=95.0):
    return {'FaceMatches': [{'Similarity': similarity}], 'UnmatchedFaces': []}

def rekognition_no_match():
    return {'FaceMatches': [], 'UnmatchedFaces': [{}]}


# --- Textract helpers ---

def textract_query_response(alias_text_pairs, confidence=95.0):
    """Build a Textract analyze_document Queries response from (alias, text) pairs."""
    blocks = []
    for i, (alias, text) in enumerate(alias_text_pairs):
        qid, rid = f'q{i}', f'r{i}'
        blocks.append({
            'BlockType': 'QUERY',
            'Id': qid,
            'Query': {'Alias': alias},
            'Relationships': [{'Type': 'ANSWER', 'Ids': [rid]}],
        })
        blocks.append({
            'BlockType': 'QUERY_RESULT',
            'Id': rid,
            'Text': text,
            'Confidence': confidence,
        })
    return {'Blocks': blocks}

def textract_query_response_low_confidence(alias_text_pairs):
    """Same structure but confidence below the 80% threshold — fields should be dropped."""
    return textract_query_response(alias_text_pairs, confidence=50.0)

def analyze_id_response(fields):
    """Build a Textract analyze_id response from a plain dict of field→value."""
    return {
        'IdentityDocuments': [{
            'IdentityDocumentFields': [
                {'Type': {'Text': k}, 'ValueDetection': {'Text': v}}
                for k, v in fields.items()
            ]
        }]
    }


# --- Event builders ---

BUCKET = 'test-onboarding-bucket'

def patient_event(patient_id='PT001'):
    return {
        'detail': {
            'bucket': {'name': BUCKET},
            'object': {'key': f'{patient_id}_selfie.png'},
        },
        'application': {'patient_id': patient_id},
    }

def therapist_event(therapist_id='TH001'):
    return {
        'detail': {
            'bucket': {'name': BUCKET},
            'object': {'key': f'{therapist_id}_therapist_selfie.png'},
        },
        'application': {'therapist_id': therapist_id},
    }

def store_verification_event(patient_id='PT001', face_match=True, license_valid=True,
                              extraction_ok=True, needs_review=False):
    return {
        'application': {'patient_id': patient_id},
        'checks': [
            {'patient_id': patient_id, 'face_match': face_match, 'face_similarity': 95.0},
            {'patient_id': patient_id, 'extracted': {'FIRST_NAME': 'Jane'}, 'license_valid': license_valid, 'missing_fields': []},
            {'patient_id': patient_id, 'extraction_ok': extraction_ok, 'insurance_data': {'memberName': 'Jane Doe'}, 'needs_review': needs_review, 'missing_fields': []},
        ],
    }

def store_therapist_event(therapist_id='TH001', face_match=True, license_verified=True,
                           extraction_ok=True):
    return {
        'application': {'therapist_id': therapist_id},
        'checks': [
            {'therapist_id': therapist_id, 'face_match': face_match, 'face_similarity': 92.0},
            {'therapist_id': therapist_id, 'license_verified': license_verified, 'license_status': 'active'},
            {'therapist_id': therapist_id, 'extracted': {'LICENSE_NUMBER': 'MD12345'}, 'extraction_ok': extraction_ok, 'missing_fields': []},
        ],
    }
