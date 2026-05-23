import os
import boto3
import requests
from datetime import datetime, timezone

env_table = os.environ['TABLE']
env_topic = os.environ['TOPIC']
license_verify_url = os.environ['LICENSE_VERIFY_URL']

dynamodb = boto3.resource('dynamodb')
ddb_table = dynamodb.Table(env_table)
sns = boto3.client('sns')


def get_declared_license(therapist_id):
    """Read the license number the therapist declared at registration."""
    response = ddb_table.get_item(Key={'THERAPIST_ID': therapist_id})
    item = response.get('Item', {})
    return item.get('DECLARED_LICENSE_NUMBER'), item.get('DECLARED_LICENSE_STATE')


def verify_with_registry(license_number, license_state):
    r = requests.post(
        license_verify_url,
        json={'licenseNumber': license_number, 'state': license_state},
        timeout=15,
    )
    r.raise_for_status()
    result = r.json()
    return result.get('valid', False), result.get('status', 'unknown')


def lambda_handler(event, context):
    therapist_id = event['application']['therapist_id']

    license_number, license_state = get_declared_license(therapist_id)

    if not license_number:
        ddb_table.update_item(
            Key={'THERAPIST_ID': therapist_id},
            UpdateExpression='SET LICENSE_VERIFIED = :v, LICENSE_STATUS = :s, LICENSE_VERIFY_TIMESTAMP = :ts',
            ExpressionAttributeValues={
                ':v':  False,
                ':s':  'no_license_on_record',
                ':ts': datetime.now(timezone.utc).isoformat(),
            },
        )
        sns.publish(
            TopicArn=env_topic,
            Message=f"No declared license number found for therapist {therapist_id}.",
            Subject='Therapist Onboarding — License Number Missing',
        )
        return {
            'therapist_id':     therapist_id,
            'license_verified': False,
            'license_status':   'no_license_on_record',
        }

    license_verified, license_status = verify_with_registry(license_number, license_state)

    ddb_table.update_item(
        Key={'THERAPIST_ID': therapist_id},
        UpdateExpression='SET LICENSE_VERIFIED = :v, LICENSE_STATUS = :s, LICENSE_VERIFY_TIMESTAMP = :ts',
        ExpressionAttributeValues={
            ':v':  license_verified,
            ':s':  license_status,
            ':ts': datetime.now(timezone.utc).isoformat(),
        },
    )

    if not license_verified:
        sns.publish(
            TopicArn=env_topic,
            Message=(
                f"Medical license verification FAILED for therapist {therapist_id}. "
                f"License: {license_number}, Status: {license_status}"
            ),
            Subject='Therapist Onboarding — License Verification Failed',
        )

    return {
        'therapist_id':     therapist_id,
        'license_verified': license_verified,
        'license_status':   license_status,
    }
