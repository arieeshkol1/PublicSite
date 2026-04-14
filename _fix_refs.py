import os

replacements = [
    # admin-handler CORS
    ('admin-handler/lambda_function.py', 
     "https://www.eshkolai.com", 
     "https://slashmycloudbill.com"),
    # contact form sender
    ('contact-form-handler/lambda_function.py',
     "noreply@eshkolai.com",
     "noreply@slashmycloudbill.com"),
    ('contact-form-handler/lambda_function.py',
     "www.eshkolai.com",
     "slashmycloudbill.com"),
    # OTP handler sender email
    ('otp-handler/lambda_function.py',
     "noreply@eshkolai.com",
     "noreply@slashmycloudbill.com"),
    ('otp-handler/lambda_function.py',
     "www.eshkolai.com/SlashMyBill.png",
     "slashmycloudbill.com/SlashMyBill.png"),
    ('otp-handler/lambda_function.py',
     "eshkolai.com",
     "slashmycloudbill.com"),
    # member-handler sender email  
    ('member-handler/lambda_function.py',
     "noreply@eshkolai.com",
     "noreply@slashmycloudbill.com"),
    # help.js
    ('members/help.js',
     "eshkolai.com/members",
     "slashmycloudbill.com/members"),
    ('members/help.js',
     "support@eshkolai.com",
     "info@slashmycloudbill.com"),
    # admin CSS comment
    ('admin/admin.css',
     "eshkolai.com theme",
     "slashmycloudbill.com theme"),
]

for filepath, old, new in replacements:
    if not os.path.exists(filepath):
        print(f"SKIP: {filepath} not found")
        continue
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    count = content.count(old)
    if count > 0:
        content = content.replace(old, new)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"FIXED: {filepath} ({count} replacements)")
    else:
        print(f"OK: {filepath} (no matches)")
