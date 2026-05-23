import os
import boto3
from datetime import datetime, timezone

env_table = os.environ['TABLE']
env_topic = os.environ['TOPIC']

dynamodb = boto3.resource('dynamodb')
ddb_table = dynamodb.Table(env_table)
textract = boto3.client('textract')
sns = boto3.client('sns')

# Medical licenses vary by state board — Queries handles layout variation better than analyze_id
MEDICAL_LICENSE_QUERIES = [
    {'Text': 'What is the license number?',   'Alias': 'LICENSE_NUMBER'},
    {'Text': 'What is the licensee name?',     'Alias': 'LICENSEE_NAME'},
    {'Text': 'What is the first name?',        'Alias': 'FIRST_NAME'},
    {'Text': 'What is the last name?',         'Alias': 'LAST_NAME'},
    {'Text': 'What is the license type?',      'Alias': 'LICENSE_TYPE'},
    {'Text': 'What is the specialty?',         'Alias': 'SPECIALTY'},
    {'Text': 'What is the expiration date?',   'Alias': 'EXPIRATION_DATE'},
    {'Text': 'What is the issue date?',        'Alias': 'ISSUE_DATE'},
    {'Text': 'What is the issuing state?',     'Alias': 'ISSUING_STATE'},
    {'Text': 'What is the board name?',        'Alias': 'BOARD_NAME'},
]

REQUIRED_FIELDS = {'LICENSE_NUMBER', 'LICENSEE_NAME', 'EXPIRATION_DATE'}


def extract_medical_license(bucket, license_key):
    response = textract.analyze_document(
        Document={'S3Object': {'Bucket': bucket, 'Name': license_key}},
        FeatureTypes=['QUERIES'],
        QueriesConfig={'Queries': MEDICAL_LICENSE_QUERIES},
    )

    query_blocks  = {b['Id']: b for b in response['Blocks'] if b['BlockType'] == 'QUERY'}
    result_blocks = {b['Id']: b for b in response['Blocks'] if b['BlockType'] == 'QUERY_RESULT'}

    alias_map = {}
    for query_block in query_blocks.values():
        alias = query_block.get('Query', {}).get('Alias', '')
        for rel in query_block.get('Relationships', []):
            if rel['Type'] == 'ANSWER':
                for result_id in rel['Ids']:
                    result_block = result_blocks.get(result_id, {})
                    confidence = result_block.get('Confidence', 0)
                    text = result_block.get('Text', '').strip()
                    if confidence >= 80 and text:
                        alias_map[alias] = text

    return alias_map


def lambda_handler(event, context):
    bucket = event['detail']['bucket']['name']
    therapist_id = event['application']['therapist_id']
    license_key = f"{therapist_id}_medical_license.jpg"

    extracted = extract_medical_license(bucket, license_key)

    missing = REQUIRED_FIELDS - set(extracted.keys())
    extraction_ok = len(missing) == 0

    ddb_table.update_item(
        Key={'THERAPIST_ID': therapist_id},
        UpdateExpression='SET MEDICAL_LICENSE_DATA = :data, EXTRACTION_OK = :ok, EXTRACTION_TIMESTAMP = :ts',
        ExpressionAttributeValues={
            ':data': extracted,
            ':ok':   extraction_ok,
            ':ts':   datetime.now(timezone.utc).isoformat(),
        },
    )

    if not extraction_ok:
        sns.publish(
            TopicArn=env_topic,
            Message=(
                f"Medical license extraction for therapist {therapist_id} is missing "
                f"required fields: {', '.join(missing)}"
            ),
            Subject='Therapist Onboarding — License Extraction Incomplete',
        )

    return {
        'therapist_id':   therapist_id,
        'extracted':      extracted,
        'extraction_ok':  extraction_ok,
        'missing_fields': list(missing),
    }
