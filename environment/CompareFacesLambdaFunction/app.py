import os
from decimal import Decimal
import boto3

env_table = os.environ['TABLE']
env_topic = os.environ['TOPIC']

dynamodb = boto3.resource('dynamodb')
ddb_table = dynamodb.Table(env_table)
rekognition = boto3.client('rekognition')
sns = boto3.client('sns')

SIMILARITY_THRESHOLD = 80


def compare_faces(entity_id, id_attr, bucket, license_key, selfie_key):
    response = rekognition.compare_faces(
        SourceImage={'S3Object': {'Bucket': bucket, 'Name': license_key}},
        TargetImage={'S3Object': {'Bucket': bucket, 'Name': selfie_key}},
        SimilarityThreshold=SIMILARITY_THRESHOLD,
    )

    if response['FaceMatches']:
        similarity = response['FaceMatches'][0]['Similarity']
        face_match = similarity >= SIMILARITY_THRESHOLD
    else:
        similarity = 0.0
        face_match = False

    ddb_table.update_item(
        Key={id_attr: entity_id},
        UpdateExpression='SET FACE_MATCH = :match, FACE_SIMILARITY = :sim',
        ExpressionAttributeValues={
            ':match': face_match,
            ':sim':   Decimal(str(round(similarity, 2))),
        },
    )

    if not face_match:
        sns.publish(
            TopicArn=env_topic,
            Message=(
                f"Face comparison FAILED for {id_attr} {entity_id}. "
                f"Similarity: {similarity:.1f}%"
            ),
            Subject='Onboarding — Face Match Failed',
        )

    return face_match, round(similarity, 2)


def lambda_handler(event, context):
    bucket = event['detail']['bucket']['name']
    app = event['application']

    if 'patient_id' in app:
        entity_id = app['patient_id']
        id_attr = 'PATIENT_ID'
        selfie_key = f"{entity_id}_selfie.png"
    else:
        entity_id = app['therapist_id']
        id_attr = 'THERAPIST_ID'
        selfie_key = f"{entity_id}_therapist_selfie.png"

    license_key = f"{entity_id}_license.jpg"

    face_match, face_similarity = compare_faces(entity_id, id_attr, bucket, license_key, selfie_key)

    id_field = 'patient_id' if id_attr == 'PATIENT_ID' else 'therapist_id'
    return {
        id_field:          entity_id,
        'face_match':      face_match,
        'face_similarity': face_similarity,
    }
