"Extract insurance membership card details using Textract Queries"
import os
import boto3
import requests
from datetime import datetime, timezone

env_table = os.environ['TABLE']
env_topic = os.environ['TOPIC']
clinic_api_url = os.environ['CLINIC_API_URL']

s3 = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
ddb_table = dynamodb.Table(env_table)
textract = boto3.client('textract')
sns = boto3.client('sns')

# Insurance cards vary widely by payer — Queries handles any layout
INSURANCE_QUERIES = [
    {'Text': 'What is the member name?',        'Alias': 'MEMBER_NAME'},
    {'Text': 'What is the member ID?',           'Alias': 'MEMBER_ID'},
    {'Text': 'What is the policy number?',       'Alias': 'POLICY_NUMBER'},
    {'Text': 'What is the group number?',        'Alias': 'GROUP_NUMBER'},
    {'Text': 'What is the insurance company?',   'Alias': 'PAYER_NAME'},
    {'Text': 'What is the plan name?',           'Alias': 'PLAN_NAME'},
    {'Text': 'What is the plan type?',           'Alias': 'PLAN_TYPE'},
    {'Text': 'What is the effective date?',      'Alias': 'EFFECTIVE_DATE'},
    {'Text': 'What is the payer ID?',            'Alias': 'PAYER_ID'},
    {'Text': 'What is the copay amount?',        'Alias': 'COPAY'},
    {'Text': 'What is the specialist copay?',    'Alias': 'SPECIALIST_COPAY'},
    {'Text': 'What is the deductible?',          'Alias': 'DEDUCTIBLE'},
    {'Text': 'What is the RxBIN number?',        'Alias': 'RX_BIN'},
    {'Text': 'What is the RxPCN?',               'Alias': 'RX_PCN'},
    {'Text': 'What is the RxGroup?',             'Alias': 'RX_GROUP'},
    {'Text': 'What is the member services phone number?', 'Alias': 'MEMBER_SERVICES_PHONE'},
    {'Text': 'What is the provider services phone number?', 'Alias': 'PROVIDER_SERVICES_PHONE'},
]

# Fields required before the record is considered usable for billing
REQUIRED_FIELDS = {'MEMBER_ID', 'PAYER_NAME', 'MEMBER_NAME'}


def extract_insurance_card(bucket, insurance_key):
    "Send insurance card image to Textract using Queries feature"
    print(f"Starting insurance card extraction: {insurance_key}")

    response = textract.analyze_document(
        Document={'S3Object': {'Bucket': bucket, 'Name': insurance_key}},
        FeatureTypes=['QUERIES'],
        QueriesConfig={'Queries': INSURANCE_QUERIES},
    )

    alias_map = {}
    query_blocks = {b['Id']: b for b in response['Blocks'] if b['BlockType'] == 'QUERY'}
    result_blocks = {b['Id']: b for b in response['Blocks'] if b['BlockType'] == 'QUERY_RESULT'}

    for query_id, query_block in query_blocks.items():
        alias = query_block.get('Query', {}).get('Alias', '')
        relationships = query_block.get('Relationships', [])
        for rel in relationships:
            if rel['Type'] == 'ANSWER':
                for result_id in rel['Ids']:
                    result_block = result_blocks.get(result_id, {})
                    confidence = result_block.get('Confidence', 0)
                    text = result_block.get('Text', '').strip()
                    # Only keep answers Textract is confident about (>= 80%)
                    if confidence >= 80 and text:
                        alias_map[alias] = {'value': text, 'confidence': round(confidence, 2)}

    print(f"Extracted {len(alias_map)} fields from insurance card")
    return alias_map


def validate_required_fields(patient_id, alias_map):
    "Check that minimum required fields were extracted for billing use"
    extracted_keys = set(alias_map.keys())
    missing = REQUIRED_FIELDS - extracted_keys

    if missing:
        sns.publish(
            TopicArn=env_topic,
            Message=(
                f"Insurance card extraction for patient {patient_id} is missing "
                f"required fields: {', '.join(missing)}. Manual review needed."
            ),
            Subject='Insurance Card — Missing Required Fields',
        )
        return False, missing

    return True, set()


def store_to_dynamodb(patient_id, alias_map, extraction_ok, missing_fields):
    "Persist raw extraction results to DynamoDB"
    ddb_table.update_item(
        Key={'PATIENT_ID': patient_id},
        UpdateExpression='''SET INSURANCE_DATA = :ins,
                                INSURANCE_EXTRACTION_OK = :ok,
                                INSURANCE_MISSING_FIELDS = :missing,
                                INSURANCE_TIMESTAMP = :ts''',
        ExpressionAttributeValues={
            ':ins':     {k: v['value'] for k, v in alias_map.items()},
            ':ok':      extraction_ok,
            ':missing': list(missing_fields),
            ':ts':      datetime.now(timezone.utc).isoformat(),
        }
    )


def post_to_clinic_api(patient_id, alias_map):
    "Send extracted insurance data to clinic API for storage against the patient record"

    def val(key):
        return alias_map.get(key, {}).get('value')

    payload = {
        'memberName':            val('MEMBER_NAME'),
        'memberId':              val('MEMBER_ID'),
        'policyNumber':          val('POLICY_NUMBER'),
        'groupNumber':           val('GROUP_NUMBER'),
        'payerName':             val('PAYER_NAME'),
        'planName':              val('PLAN_NAME'),
        'planType':              val('PLAN_TYPE'),
        'effectiveDate':         val('EFFECTIVE_DATE'),
        'payerId':               val('PAYER_ID'),
        'copay':                 val('COPAY'),
        'specialistCopay':       val('SPECIALIST_COPAY'),
        'deductible':            val('DEDUCTIBLE'),
        'rxBin':                 val('RX_BIN'),
        'rxPcn':                 val('RX_PCN'),
        'rxGroup':               val('RX_GROUP'),
        'memberServicesPhone':   val('MEMBER_SERVICES_PHONE'),
        'providerServicesPhone': val('PROVIDER_SERVICES_PHONE'),
        'extractedAt':           datetime.now(timezone.utc).isoformat(),
    }

    r = requests.post(
        f"{clinic_api_url}/patients/{patient_id}/insurance",
        json=payload,
        timeout=10,
    )
    r.raise_for_status()
    return payload


def lambda_handler(event, context):
    "Extract insurance card details and store against the patient record"
    bucket = event['detail']['bucket']['name']
    patient_id = event['application']['patient_id']
    insurance_key = f"{patient_id}_insurance.jpg"

    alias_map = extract_insurance_card(bucket, insurance_key)

    extraction_ok, missing_fields = validate_required_fields(patient_id, alias_map)

    store_to_dynamodb(patient_id, alias_map, extraction_ok, missing_fields)

    if not extraction_ok:
        # Don't hard-fail — flag for manual review and let the workflow continue
        return {
            'patient_id':       patient_id,
            'extraction_ok':    False,
            'missing_fields':   list(missing_fields),
            'insurance_data':   {k: v['value'] for k, v in alias_map.items()},
            'needs_review':     True,
        }

    insurance_payload = post_to_clinic_api(patient_id, alias_map)

    return {
        'patient_id':     patient_id,
        'extraction_ok':  True,
        'missing_fields': [],
        'insurance_data': insurance_payload,
        'needs_review':   False,
    }
