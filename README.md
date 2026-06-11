# Patient Onboard SAM — Serverless Identity Verification Pipeline

Serverless patient and therapist onboarding for a clinic: AWS Rekognition face matching, Textract OCR of driver's licenses, insurance cards, and medical licenses, orchestrated by two Step Functions state machines with three parallel verification branches each. Built with AWS SAM (Python 3.13), with EventBridge triggers, DynamoDB storage, SNS staff alerts, X-Ray tracing, and a 24-test pytest suite.

**All application code, the SAM template, and full documentation live in [`environment/`](environment/) — see [environment/README.md](environment/README.md) for the architecture diagram, deployment instructions, and security details.**

Part of my portfolio: https://bradtarver.com/projects/identity-pipeline.html
