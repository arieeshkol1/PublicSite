# Generate SlashMyBill sequence diagram in draw.io XML format
# Sequence diagram: Registration, OTP, Bill Upload, Member Portal

PARTICIPANTS = [
    ("user",    "User\n(Browser)",          "#dae8fc", "#6c8ebf"),
    ("cf",      "CloudFront\n+ S3",         "#d5e8d4", "#82b366"),
    ("apigw",   "API Gateway",              "#fff2cc", "#d6b656"),
    ("otp",     "OTP Lambda",               "#f8cecc", "#b85450"),
    ("ddb_otp", "DynamoDB\nOTP Table",      "#e1d5e7", "#9673a6"),
    ("ses",     "Amazon SES",               "#f8cecc", "#b85450"),
    ("uh",      "Upload Handler\nLambda",   "#f8cecc", "#b85450"),
    ("ba",      "Bill Analyzer\nLambda",    "#f8cecc", "#b85450"),
    ("s3b",     "S3 Bills\nStorage",        "#d5e8d4", "#82b366"),
    ("mh",      "Member Handler\nLambda",   "#f8cecc", "#b85450"),
    ("cog",     "Amazon Cognito",           "#fff2cc", "#d6b656"),
    ("ddb_m",   "DynamoDB\nMembers",        "#e1d5e7", "#9673a6"),
    ("ddb_a",   "DynamoDB\nAccounts",       "#e1d5e7", "#9673a6"),
]

# Layout constants
PART_W = 120
PART_H = 60
PART_GAP = 40
TOP_Y = 40
LIFELINE_START = TOP_Y + PART_H
MSG_H = 40       # vertical spacing between messages
BOX_W = 200      # activation box width (for notes)
ACT_W = 10       # activation bar width

# Compute x centers for each participant
def px(idx):
    return idx * (PART_W + PART_GAP) + PART_W // 2

TOTAL_W = len(PARTICIPANTS) * (PART_W + PART_GAP)

# Messages: (from_idx, to_idx, label, style)
# style: "solid" | "dashed" | "note" | "divider"
MESSAGES = [
    # Phase 1: Page Load
    ("divider", "PHASE 1 — Landing Page Load"),
    (0, 1, "GET slashmycloudbill.com", "solid"),
    (1, 0, "index.html + assets", "dashed"),

    # Phase 2: OTP Verification
    ("divider", "PHASE 2 — OTP Email Verification (Bill Upload)"),
    (0, 0, "Fill form: name, company, email, phone", "self"),
    (0, 2, "POST /send-otp {email}", "solid"),
    (2, 3, "Invoke", "solid"),
    (3, 4, "GetItem(email) — rate limit check", "solid"),
    (4, 3, "OK (no recent OTP)", "dashed"),
    (3, 3, "Generate 6-digit OTP code", "self"),
    (3, 4, "PutItem {email, otp, TTL=5min}", "solid"),
    (3, 5, "SendEmail (OTP code)", "solid"),
    (5, 0, "Email: Your code is 123456", "dashed"),
    (3, 2, "200 {message: OTP sent}", "dashed"),
    (2, 0, "200 — starts 60s cooldown", "dashed"),
    (0, 2, "POST /verify-otp {email, otp}", "solid"),
    (2, 3, "Invoke", "solid"),
    (3, 4, "GetItem(email)", "solid"),
    (4, 3, "{otp, ttl}", "dashed"),
    (3, 3, "Compare codes + check TTL", "self"),
    (3, 4, "DeleteItem(email) — consume OTP", "solid"),
    (3, 2, "200 {verified: true}", "dashed"),
    (2, 0, "Email verified — file upload unlocked", "dashed"),

    # Phase 3: Bill Upload & Analysis
    ("divider", "PHASE 3 — Bill Upload & AI Analysis"),
    (0, 2, "POST /upload (multipart PDF)", "solid"),
    (2, 6, "Invoke", "solid"),
    (6, 8, "PutObject bills/{sessionId}.pdf", "solid"),
    (6, 11, "PutItem lead record", "solid"),
    (6, 2, "200 {sessionId}", "dashed"),
    (2, 0, "{sessionId}", "dashed"),
    (0, 2, "POST /analyze {sessionId, email}", "solid"),
    (2, 7, "Invoke", "solid"),
    (7, 8, "GetObject bills/{sessionId}.pdf", "solid"),
    (7, 7, "Parse PDF + invoke Bedrock", "self"),
    (7, 7, "Generate PDF report", "self"),
    (7, 8, "PutObject reports/{sessionId}.pdf", "solid"),
    (7, 2, "200 {status, summary, downloadUrl}", "dashed"),
    (2, 0, "{summary, downloadUrl}", "dashed"),
    (0, 8, "GET pre-signed URL (PDF report)", "solid"),
    (8, 0, "PDF report download", "dashed"),

    # Phase 4: Member Registration
    ("divider", "PHASE 4 — Member Registration (Cognito)"),
    (0, 1, "GET /members/ (Member Portal)", "solid"),
    (1, 0, "members/index.html", "dashed"),
    (0, 0, "Fill: email, password", "self"),
    (0, 2, "POST /members/register {action:send-otp, email, password}", "solid"),
    (2, 9, "Invoke", "solid"),
    (9, 10, "AdminGetUser(email) — check duplicate", "solid"),
    (10, 9, "UserNotFoundException", "dashed"),
    (9, 10, "SignUp(email, password)", "solid"),
    (10, 5, "Send verification email", "solid"),
    (5, 0, "Email: confirmation code 789012", "dashed"),
    (9, 2, "200 {message: OTP sent}", "dashed"),
    (2, 0, "Code sent", "dashed"),
    (0, 2, "POST /members/register {action:verify-otp, email, otp}", "solid"),
    (2, 9, "Invoke", "solid"),
    (9, 10, "ConfirmSignUp(email, code)", "solid"),
    (10, 9, "Success", "dashed"),
    (9, 9, "Generate otpToken (JWT 10min)", "self"),
    (9, 2, "200 {verified:true, otpToken}", "dashed"),
    (2, 0, "{otpToken}", "dashed"),
    (0, 2, "POST /members/register {action:create-account, otpToken}", "solid"),
    (2, 9, "Invoke", "solid"),
    (9, 9, "Decode + validate otpToken", "self"),
    (9, 11, "PutItem {email, displayName, createdAt}", "solid"),
    (9, 2, "201 {Registration successful}", "dashed"),
    (2, 0, "Redirect to login", "dashed"),

    # Phase 5: Login & Session
    ("divider", "PHASE 5 — Member Login & Session"),
    (0, 2, "POST /members/login {email, password}", "solid"),
    (2, 9, "Invoke", "solid"),
    (9, 10, "InitiateAuth(USER_PASSWORD_AUTH)", "solid"),
    (10, 9, "{AccessToken, RefreshToken}", "dashed"),
    (9, 11, "UpdateItem lastLoginAt", "solid"),
    (9, 2, "200 {token, email, displayName}", "dashed"),
    (2, 0, "JWT stored in localStorage", "dashed"),
    (0, 2, "GET /members/accounts (Bearer: token)", "solid"),
    (2, 9, "Invoke", "solid"),
    (9, 10, "GetUser(AccessToken) — validate", "solid"),
    (10, 9, "{email, attributes}", "dashed"),
    (9, 12, "Query accounts by memberEmail", "solid"),
    (12, 9, "[{accountId, status, ...}]", "dashed"),
    (9, 2, "200 {accounts: [...]}", "dashed"),
    (2, 0, "Member dashboard loaded", "dashed"),

    # Phase 6: Password Reset
    ("divider", "PHASE 6 — Password Reset"),
    (0, 2, "POST /members/reset-password {action:send-otp, email}", "solid"),
    (2, 9, "Invoke", "solid"),
    (9, 10, "ForgotPassword(email)", "solid"),
    (10, 5, "Send reset code", "solid"),
    (5, 0, "Email: reset code", "dashed"),
    (9, 2, "200 {message: Reset code sent}", "dashed"),
    (2, 0, "Code sent", "dashed"),
    (0, 2, "POST /members/reset-password {action:verify-otp, email, otp}", "solid"),
    (2, 9, "Invoke", "solid"),
    (9, 9, "Store otp in resetToken (JWT)", "self"),
    (9, 2, "200 {resetToken}", "dashed"),
    (2, 0, "{resetToken}", "dashed"),
    (0, 2, "POST /members/reset-password {action:set-password, resetToken, password}", "solid"),
    (2, 9, "Invoke", "solid"),
    (9, 10, "ConfirmForgotPassword(email, otp, newPassword)", "solid"),
    (10, 9, "Success", "dashed"),
    (9, 2, "200 {Password reset successful}", "dashed"),
    (2, 0, "Redirect to login", "dashed"),
]

def build_xml():
    cells = []
    uid = [1]

    def next_id():
        uid[0] += 1
        return str(uid[0])

    # Header
    cells.append('  <mxCell id="0"/>')
    cells.append('  <mxCell id="1" parent="0"/>')

    # Participant boxes
    for i, (key, label, fill, stroke) in enumerate(PARTICIPANTS):
        x = i * (PART_W + PART_GAP)
        cid = next_id()
        safe_label = label.replace('\n', '&#xa;')
        cells.append(
            f'  <mxCell id="{cid}" value="{safe_label}" style="rounded=1;whiteSpace=wrap;html=1;'
            f'fillColor={fill};strokeColor={stroke};fontStyle=1;fontSize=11;" '
            f'vertex="1" parent="1">'
            f'<mxGeometry x="{x}" y="{TOP_Y}" width="{PART_W}" height="{PART_H}" as="geometry"/>'
            f'</mxCell>'
        )

    # Compute total height needed
    current_y = LIFELINE_START + MSG_H
    divider_count = sum(1 for m in MESSAGES if m[0] == "divider")
    msg_count = len(MESSAGES) - divider_count
    total_h = LIFELINE_START + (msg_count + divider_count * 2) * MSG_H + 100

    # Lifelines
    for i in range(len(PARTICIPANTS)):
        x = i * (PART_W + PART_GAP) + PART_W // 2
        cid = next_id()
        cells.append(
            f'  <mxCell id="{cid}" value="" style="endArrow=none;dashed=1;strokeColor=#999999;" '
            f'edge="1" parent="1">'
            f'<mxGeometry x="{x}" y="{LIFELINE_START}" width="0" height="{total_h - LIFELINE_START}" '
            f'relative="0" as="geometry">'
            f'<mxPoint x="{x}" y="{LIFELINE_START}" as="sourcePoint"/>'
            f'<mxPoint x="{x}" y="{total_h}" as="targetPoint"/>'
            f'</mxGeometry>'
            f'</mxCell>'
        )

    # Messages
    y = LIFELINE_START + MSG_H
    for msg in MESSAGES:
        if msg[0] == "divider":
            # Phase divider band
            label = msg[1]
            cid = next_id()
            cells.append(
                f'  <mxCell id="{cid}" value="{label}" '
                f'style="text;html=1;strokeColor=#0f172a;fillColor=#0f172a;align=left;verticalAlign=middle;'
                f'spacingLeft=10;fontColor=#ffffff;fontStyle=1;fontSize=11;rounded=1;" '
                f'vertex="1" parent="1">'
                f'<mxGeometry x="0" y="{y}" width="{TOTAL_W}" height="28" as="geometry"/>'
                f'</mxCell>'
            )
            y += 40
            continue

        from_idx, to_idx, label, style = msg

        if style == "self":
            # Self-call loop
            x1 = from_idx * (PART_W + PART_GAP) + PART_W // 2
            cid = next_id()
            safe_label = label.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            cells.append(
                f'  <mxCell id="{cid}" value="{safe_label}" '
                f'style="edgeStyle=orthogonalEdgeStyle;html=1;exitX=1;exitY=0.5;exitDx=0;exitDy=0;'
                f'entryX=1;entryY=0.5;entryDx=0;entryDy=0;endArrow=block;endFill=1;strokeColor=#555555;fontSize=10;" '
                f'edge="1" parent="1">'
                f'<mxGeometry x="{x1}" y="{y}" width="60" height="30" relative="0" as="geometry">'
                f'<mxPoint x="{x1}" y="{y}" as="sourcePoint"/>'
                f'<mxPoint x="{x1 + 60}" y="{y}" as="targetPoint"/>'
                f'<Array as="points">'
                f'<mxPoint x="{x1 + 60}" y="{y - 10}"/>'
                f'<mxPoint x="{x1 + 60}" y="{y + 10}"/>'
                f'</Array>'
                f'</mxGeometry>'
                f'</mxCell>'
            )
            y += MSG_H
            continue

        x1 = from_idx * (PART_W + PART_GAP) + PART_W // 2
        x2 = to_idx * (PART_W + PART_GAP) + PART_W // 2

        arrow_style = "endArrow=block;endFill=1;" if style == "solid" else "endArrow=open;endFill=0;dashed=1;"
        color = "#1e293b" if style == "solid" else "#64748b"
        safe_label = label.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('{', '&#123;').replace('}', '&#125;')

        cid = next_id()
        cells.append(
            f'  <mxCell id="{cid}" value="{safe_label}" '
            f'style="html=1;{arrow_style}strokeColor={color};fontSize=10;align=center;verticalAlign=bottom;" '
            f'edge="1" parent="1">'
            f'<mxGeometry relative="1" as="geometry">'
            f'<mxPoint x="{x1}" y="{y}" as="sourcePoint"/>'
            f'<mxPoint x="{x2}" y="{y}" as="targetPoint"/>'
            f'</mxGeometry>'
            f'</mxCell>'
        )
        y += MSG_H

    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += '<mxfile host="app.diagrams.net" version="21.0.0">\n'
    xml += f'  <diagram name="SlashMyBill Registration Flow" id="smb-reg-flow">\n'
    xml += f'    <mxGraphModel dx="1422" dy="762" grid="0" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="{TOTAL_W + 100}" pageHeight="{total_h + 100}" math="0" shadow="0">\n'
    xml += '      <root>\n'
    for cell in cells:
        xml += '    ' + cell + '\n'
    xml += '      </root>\n'
    xml += '    </mxGraphModel>\n'
    xml += '  </diagram>\n'
    xml += '</mxfile>\n'
    return xml

with open('SlashMyBill-RegistrationFlow.drawio', 'w', encoding='utf-8') as f:
    f.write(build_xml())

print('Generated SlashMyBill-RegistrationFlow.drawio')
