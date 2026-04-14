with open('member-handler/lambda_function.py', 'r', encoding='utf-8') as f:
    code = f.read()

# Use cross-region inference profile for Nova 2 Lite
code = code.replace("amazon.nova-lite-v1:0", "us.amazon.nova-2-lite-v1:0")

with open('member-handler/lambda_function.py', 'w', encoding='utf-8') as f:
    f.write(code)

print("Updated to us.amazon.nova-2-lite-v1:0 (cross-region inference profile)")
