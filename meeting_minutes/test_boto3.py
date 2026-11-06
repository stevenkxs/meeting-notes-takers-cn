"""Quick test of boto3 credentials and service access."""
import boto3

session = boto3.Session(profile_name="bruno-mcp-prod")

# Test 1: Credentials valid?
print("[Test 1] Checking STS identity...")
sts = session.client("sts", region_name="us-east-1")
identity = sts.get_caller_identity()
print(f"  OK - ARN: {identity['Arn']}")

# Test 2: Bedrock access?
print("[Test 2] Checking Bedrock access...")
bedrock = session.client("bedrock-runtime", region_name="us-east-1")
print("  OK - Bedrock client created")

# Test 3: Comprehend access?
print("[Test 3] Checking Comprehend access...")
comprehend = session.client("comprehend", region_name="us-east-1")
resp = comprehend.detect_dominant_language(Text="Hello world, this is a test.")
lang = resp["Languages"][0]
print(f"  OK - Detected language: {lang['LanguageCode']} ({lang['Score']:.0%})")

# Test 4: Quick Bedrock invoke?
print("[Test 4] Testing Bedrock model invoke...")
import json
body = json.dumps({
    "anthropic_version": "bedrock-2023-05-31",
    "max_tokens": 50,
    "messages": [{"role": "user", "content": "Say hello in one word."}],
    "temperature": 0,
})
response = bedrock.invoke_model(
    modelId="anthropic.claude-3-5-sonnet-20241022-v2:0",
    body=body,
    contentType="application/json",
    accept="application/json",
)
result = json.loads(response["body"].read())
print(f"  OK - Response: {result['content'][0]['text']}")

print()
print("=" * 40)
print("  ALL TESTS PASSED")
print("=" * 40)
