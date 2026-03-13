# Patient Onboarding SAM Application

This project implements a serverless patient onboarding and identity verification workflow using AWS services. It leverages AWS Rekognition for facial comparison and AWS Textract for optical character recognition (OCR) to validate a patient's identity against their driver's license and extract information from their insurance card. The entire process is orchestrated by an AWS Step Functions state machine and built on the AWS Serverless Application Model (SAM).

## Overview

The primary goal of this application is to automate the initial patient data collection and identity verification process for a clinic. The workflow is triggered when a staff member uploads a series of images for a new patient into a designated S3 bucket.

The process involves:
1.  A clinic staff member uploads images of the patient's driver's license and insurance card.
2.  The staff member then takes a "selfie" of the patient and uploads it.
3.  The upload of the selfie image triggers the verification workflow.
4.  The system compares the face in the selfie to the face on the driver's license using Amazon Rekognition.
5.  It extracts personal information (name, DOB, address) from the driver's license using Amazon Textract.
6.  It extracts insurance details (carrier, policy number) from the insurance card using Amazon Textract.
7.  All collected information is stored in an Amazon DynamoDB table.
8.  The final verification status and data are posted to an external Clinic Scheduler API.
9.  If any step fails or requires manual review (e.g., low-confidence face match, unreadable insurance card), an alert is sent to a designated staff email address.

## Architecture

The application is designed as an event-driven, serverless workflow on AWS.

```
                                     +-------------------------+
                                     | Clinic Staff Member     |
                                     +-------------------------+
                                                 |
                                (1. Uploads license & insurance card)
                                (2. Uploads selfie)
                                                 |
                                                 v
+-------------------------------------------------------------------------------------------------+
|                                                                                                 |
|   +-----------------------+      +--------------------------+      +--------------------------+   |
|   | Amazon S3 Bucket      |----->| EventBridge Rule         |----->| Step Functions State     |   |
|   | (DocumentBucket)      |      | (on selfie upload)       |      | Machine                  |   |
|   +-----------------------+      +--------------------------+      +--------------------------+   |
|                                                                                                 |
|                                                                                |                |
|                      +---------------------------------------------------------+                |
|                      |                                                                          |
|                      v (3. Triggers Parallel Execution)                                         |
|                                                                                                 |
|   +-------------------------+      +------------------------------+      +--------------------+   |
|   | CompareFaces (Lambda)   |      | ExtractLicense (Lambda)      |      | ExtractInsurance   |   |
|   | (Rekognition)           |      | (Textract)                   |      | (Lambda, Textract) |   |
|   +-------------------------+      +------------------------------+      +--------------------+   |
|             |                              |                                 |                  |
|             +------------------------------+---------------------------------+                  |
|                                            |                                                    |
|                                            v (4. Consolidate Results)                             |
|                                                                                                 |
|                                  +---------------------------+                                  |
|                                  | StoreVerification (Lambda)|                                  |
|                                  +---------------------------+                                  |
|                                     |          |               |                                |
|   +---------------------------------+          |               +----------------------------+   |
|   |                                            |                                            |   |
|   v (5a. Write to Table)                       v (5b. POST to API)                          |   |
|                                                                                             |   |
|   +-------------------------+      +--------------------------+      +--------------------+   |
|   | DynamoDB Table          |      | Clinic Scheduler API     |      | SNS Topic          |   |
|   | (PatientVerification)   |      |                          |      | (for alerts)       |<--+
|   +-------------------------+      +--------------------------+      +--------------------+   |
|                                                                        (5c. Send alert on failure)
|                                                                                                 |
+-------------------------------------------------------------------------------------------------+
                                         AWS Cloud
```

### Components

*   **AWS SAM Template (`template.yaml`):** Defines all the AWS resources required for the application, including IAM roles, S3 buckets, Lambda functions, a DynamoDB table, an SNS topic, and the Step Function state machine.
*   **Amazon S3 (`DocumentBucket`):** A secure, private S3 bucket to store the patient's images. It is configured to trigger an EventBridge event when a new object ending in `_selfie.png` is created.
*   **AWS Lambda Functions:** A set of single-purpose, event-driven functions that form the core logic of the application.
    *   `CompareFacesLambdaFunction`: Compares the patient's selfie with the photo on their driver's license using Amazon Rekognition's face comparison capabilities.
    *   `ExtractLicenseDetailsLambdaFunction`: Uses Amazon Textract's `analyze_id` feature to perform OCR on the driver's license and extract structured data.
    *   `ExtractInsuranceLambdaFunction`: Uses Amazon Textract's `analyze_document` (with Queries) to extract key-value pairs from the patient's insurance card.
    *   `StoreVerificationLambdaFunction`: This function is called after the parallel checks are complete. It aggregates the results, writes the final record to the DynamoDB table, and sends the data to the external clinic API.
*   **AWS Step Functions (`PatientOnboardingStateMachine`):** A state machine that orchestrates the entire workflow. It starts when triggered by the selfie upload, runs the verification checks in parallel, handles retries and errors, and ensures the final data is stored correctly.
*   **Amazon DynamoDB (`PatientVerificationTable`):** A NoSQL database table used to store the results of the verification process for each patient, indexed by a unique `PATIENT_ID`.
*   **Amazon SNS (`ApplicationStatusTopic`):** A Simple Notification Service topic that sends email alerts to clinic staff in case of verification failures or when manual review is required.
*   **Amazon EventBridge:** A serverless event bus that connects the S3 upload event to the Step Functions state machine, decoupling the components.

## Prerequisites

*   AWS CLI installed and configured
*   AWS SAM CLI installed
*   Python 3.13
*   An external Clinic Scheduler API endpoint (or a mock endpoint for testing)
*   An email address for failure notifications

## Deployment

The application is deployed using the AWS Serverless Application Model (SAM).

1.  **Build the application:**
    ```bash
    sam build
    ```

2.  **Deploy to AWS:**
    ```bash
    sam deploy --guided
    ```
    The guided deployment will prompt you for parameters, including:
    *   `Stack Name`: A unique name for your CloudFormation stack (e.g., `patient-onboarding-app`).
    *   `AWS Region`: The AWS region to deploy to.
    *   `ClinicApiUrl`: The base URL of your clinic's scheduler API.
    *   `StaffAlertEmail`: The email address for receiving SNS notifications.

    SAM will then provision all the necessary resources in your AWS account.

## Usage

Once deployed, the workflow is triggered by uploading files to the S3 bucket created during deployment.

1.  **Retrieve the S3 Bucket Name:** Find the `DocumentBucketName` in the outputs of the `sam deploy` command or in the CloudFormation stack outputs in the AWS console.

2.  **Upload Files:** Upload the patient's documents to the root of the bucket using the following naming convention:
    *   Driver's License: `{patient_id}_license.jpg`
    *   Insurance Card: `{patient_id}_insurance.jpg`
    *   Patient Selfie: `{patient_id}_selfie.png`

    Replace `{patient_id}` with a unique identifier for the patient. The workflow is specifically triggered by the upload of the file ending in `_selfie.png`. It is recommended to upload the license and insurance card first, followed by the selfie.

3.  **Monitor Execution:** You can monitor the execution of the state machine in the AWS Step Functions console to see the live status of the verification process for each patient.
