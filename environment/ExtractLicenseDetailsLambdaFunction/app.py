import os
import boto3
from datetime import datetime, timezone

env_table = os.environ['TABLE']
env_topic = os.environ['TOPIC']

dynamodb = boto3.resource('dynamodb')
ddb_table = dynamodb.Table(env_table)
textract = boto3.client('textract')
sns = boto3.client('sns')

LICENSE_FIELDS = {
    'DOCUMENT_NUMBER', 'FIRST_NAME', 'LAST_NAME', 'DATE_OF_BIRTH',
    'ADDRESS', 'STATE_IN_ADDRESS', 'CITY_IN_ADDRESS', 'ZIP_CODE_IN_ADDRESS',
    'EXPIRATION_DATE', 'ID_TYPE',
}

REQUIRED_FIELDS = {'DOCUMENT_NUMBER', 'FIRST_NAME', 'LAST_NAME', 'DATE_OF_BIRTH'}


def extract_license(bucket, license_key):
    response = textract.analyze_id(
        DocumentPages=[{'S3Object': {'Bucket': bucket, 'Name': license_key}}]
    )
    id_fields = response['IdentityDocuments'][0]['IdentityDocumentFields']
    return {
        f['Type']['Text']: f['ValueDetection']['Text']
        for f in id_fields
        if f['Type']['Text'] in LICENSE_FIELDS
           and f['ValueDetection']['Text']
    }


def lambda_handler(event, context):
    bucket = event['detail']['bucket']['name']
    patient_id = event['application']['patient_id']
    license_key = f"{patient_id}_license.jpg"

    extracted = extract_license(bucket, license_key)

    missing = REQUIRED_FIELDS - set(extracted.keys())
    license_valid = len(missing) == 0

    ddb_table.update_item(
        Key={'PATIENT_ID': patient_id},
        UpdateExpression='SET LICENSE_DATA = :data, LICENSE_VALID = :valid, LICENSE_TIMESTAMP = :ts',
        ExpressionAttributeValues={
            ':data':  extracted,
            ':valid': license_valid,
            ':ts':    datetime.now(timezone.utc).isoformat(),
        },
    )

    if not license_valid:
        sns.publish(
            TopicArn=env_topic,
            Message=(
                f"License extraction for patient {patient_id} is missing "
                f"required fields: {', '.join(missing)}"
            ),
            Subject='Patient Onboarding — License Extraction Incomplete',
        )

    return {
        'patient_id':     patient_id,
        'extracted':      extracted,
        'license_valid':  license_valid,
        'missing_fields': list(missing),
    }
