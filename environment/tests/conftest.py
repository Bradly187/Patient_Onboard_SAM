import os

# Set env vars at module level — conftest is loaded before any test file,
# so Lambda modules imported in test files will see these values.
os.environ.setdefault('TABLE',              'TestTable')
os.environ.setdefault('TOPIC',              'arn:aws:sns:us-east-1:000000000000:TestTopic')
os.environ.setdefault('CLINIC_API_URL',     'https://clinic.example.com/api')
os.environ.setdefault('LICENSE_VERIFY_URL', 'https://verify.example.com/verify')
