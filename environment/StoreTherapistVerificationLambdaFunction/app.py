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


def post_verification_to_api(therapist_id, face_result, verify_result, extract_result):
    payload = {
        'therapistId':     therapist_id,
        'faceMatch':       face_result.get('face_match'),
        'faceSimilarity':  face_result.get('face_similarity'),
        'licenseVerified': verify_result.get('license_verified'),
        'licenseStatus':   verify_result.get('license_status'),
        'licenseData':     extract_result.get('extracted', {}),
        'extractionOk':    extract_result.get('extraction_ok'),
        'verifiedAt':      datetime.now(timezone.utc).isoformat(),
    }
    r = requests.post(
        f"{clinic_api_url}/therapists/{therapist_id}/verify",
        json=payload,
        timeout=10,
    )
    r.raise_for_status()
    return payload


def lambda_handler(event, context):
    therapist_id = event['application']['therapist_id']
    # Parallel branch outputs in declaration order: face, verify_license, extract_license
    face_result, verify_result, extract_result = event['checks']

    overall_pass = face_result['face_match'] and verify_result['license_verified']

    ddb_table.update_item(
        Key={'THERAPIST_ID': therapist_id},
        UpdateExpression='SET VERIFICATION_PASSED = :pass, NEEDS_REVIEW = :review, COMPLETED_AT = :ts',
        ExpressionAttributeValues={
            ':pass':   overall_pass,
            ':review': not extract_result.get('extraction_ok', True),
            ':ts':     datetime.now(timezone.utc).isoformat(),
        },
    )

    if not overall_pass:
        sns.publish(
            TopicArn=env_topic,
            Message=(
                f"Therapist onboarding verification FAILED for {therapist_id}. "
                f"Face match: {face_result['face_match']}, "
                f"License verified: {verify_result['license_verified']}"
            ),
            Subject='Therapist Onboarding — Verification Failed',
        )
        raise RuntimeError(f"Therapist verification failed for {therapist_id}")

    post_verification_to_api(therapist_id, face_result, verify_result, extract_result)

    return {
        'therapist_id':        therapist_id,
        'verification_passed': True,
        'needs_review':        not extract_result.get('extraction_ok', True),
    }
