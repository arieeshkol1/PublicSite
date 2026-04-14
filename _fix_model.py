with open('member-handler/lambda_function.py', 'r', encoding='utf-8') as f:
    code = f.read()

# Replace nova-2-lite with nova-lite (v1 works on-demand)
old = "BEDROCK_MODEL_ID = os.environ.get('BEDROCK_MODEL_ID', 'amazon.nova-2-lite-v1:0')"
new = "BEDROCK_MODEL_ID = os.environ.get('BEDROCK_MODEL_ID', 'amazon.nova-lite-v1:0')"
code = code.replace(old, new)

# Also fix any hardcoded nova-2-lite references in the IAM policy section
code = code.replace("'arn:aws:bedrock:us-east-1::foundation-model/amazon.nova-2-lite-v1:0'",
                     "'arn:aws:bedrock:us-east-1::foundation-model/amazon.nova-lite-v1:0'")

with open('member-handler/lambda_function.py', 'w', encoding='utf-8') as f:
    f.write(code)

print("Model ID updated to amazon.nova-lite-v1:0")
