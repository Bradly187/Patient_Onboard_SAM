import os
import boto3
import requests
from datetime import datetime, timezone

env_table = os.environ['TABLE']
env_topic = os.environ['TOPIC']
clinic_api_url = os.environ['CLINIC_API_URL']

dynamodb = boto3.resource('dynamodb')
ddb_table = dynamodb.Table(env_table)
sns = boto3.client('sns')


def post_verification_to_api(patient_id, face_result, license_result, insurance_result):
    payload = {
        'patientId':              patient_id,
        'faceMatch':              face_result.get('face_match'),
        'faceSimilarity':         face_result.get('face_similarity'),
        'licenseValid':           license_result.get('license_valid'),
        'licenseData':            license_result.get('extracted', {}),
        'insuranceExtractionOk':  insurance_result.get('extraction_ok'),
        'insuranceData':          insurance_result.get('insurance_data', {}),
        'needsReview':            insurance_result.get('needs_review', False),
        'verifiedAt':             datetime.now(timezone.utc).isoformat(),
    }
    r = requests.post(
        f"{clinic_api_url}/patients/{patient_id}/verify",
        json=payload,
        timeout=10,
    )
    r.raise_for_status()
    return payload


def lambda_handler(event, context):
    patient_id = event['application']['patient_id']
    # Parallel branch outputs arrive in declaration order: face, license, insurance
    face_result, license_result, insurance_result = event['checks']

    overall_pass = face_result['face_match'] and license_result['license_valid']

    ddb_table.update_item(
        Key={'PATIENT_ID': patient_id},
        UpdateExpression='SET VERIFICATION_PASSED = :pass, NEEDS_REVIEW = :review, COMPLETED_AT = :ts',
        ExpressionAttributeValues={
            ':pass':   overall_pass,
            ':review': insurance_result.get('needs_review', False),
            ':ts':     datetime.now(timezone.utc).isoformat(),
        },
    )

    if not overall_pass:
        sns.publish(
            TopicArn=env_topic,
            Message=(
                f"Onboarding verification FAILED for patient {patient_id}. "
                f"Face match: {face_result['face_match']}, "
                f"License valid: {license_result['license_valid']}"
            ),
            Subject='Patient Onboarding — Verification Failed',
        )
        raise RuntimeError(f"Verification failed for patient {patient_id}")

    post_verification_to_api(patient_id, face_result, license_result, insurance_result)

    return {
        'patient_id':          patient_id,
        'verification_passed': True,
        'needs_review':        insurance_result.get('needs_review', False),
    }
