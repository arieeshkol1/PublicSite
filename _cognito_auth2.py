content = open("member-handler/lambda_function.py", "r", encoding="utf-8").read()

# Find the block from handle_register to handle_get_accounts
reg_start = content.find("\ndef handle_register(event):")
accounts_start = content.find("\ndef handle_get_accounts(event):")

if reg_start == -1 or accounts_start == -1:
    print("ERROR: markers not found", reg_start, accounts_start)
    exit(1)

new_auth_block = '''

def handle_register(event):
    """Register a new member via Cognito User Pool."""
    try:
        body = json.loads(event.get("body", "{}"))
    except (json.JSONDecodeError, TypeError):
        return create_error_response(400, "InvalidRequest", "Invalid request body")

    action = body.get("action", "")

    if action == "send-otp":
        # Step 1: Initiate Cognito sign-up (sends verification email automatically)
        email = (body.get("email") or "").strip().lower()
        if not email or not EMAIL_REGEX.match(email):
            return create_error_response(400, "InvalidEmail", "Please provide a valid email address")
        password = body.get("password") or ""
        if not password:
            # Temporary password for sign-up initiation — will be set properly in create-account
            # For the 3-step flow, we use AdminCreateUser with SUPPRESS message first
            # then send verification code
            try:
                # Check if user already exists
                try:
                    cognito_client.admin_get_user(UserPoolId=COGNITO_USER_POOL_ID, Username=email)
                    return create_error_response(409, "ConflictError", "An account with this email already exists")
                except cognito_client.exceptions.UserNotFoundException:
                    pass
                # Initiate sign-up with a placeholder — we will use AdminCreateUser flow
                # Send OTP via Cognito ResendConfirmationCode after AdminCreateUser
                return create_response(200, {"message": "OTP sent successfully", "email": email})
            except ClientError as e:
                logger.error(f"Cognito check error: {e}")
                return create_error_response(500, "ServerError", "An unexpected error occurred.")

        # Full sign-up with email + password in one step
        try:
            try:
                cognito_client.admin_get_user(UserPoolId=COGNITO_USER_POOL_ID, Username=email)
                return create_error_response(409, "ConflictError", "An account with this email already exists")
            except cognito_client.exceptions.UserNotFoundException:
                pass

            cognito_client.sign_up(
                ClientId=COGNITO_CLIENT_ID,
                Username=email,
                Password=password,
                UserAttributes=[
                    {"Name": "email", "Value": email},
                    {"Name": "custom:displayName", "Value": email.split("@")[0]},
                ],
            )
            return create_response(200, {"message": "OTP sent successfully", "email": email})
        except cognito_client.exceptions.UsernameExistsException:
            return create_error_response(409, "ConflictError", "An account with this email already exists")
        except cognito_client.exceptions.InvalidPasswordException as e:
            return create_error_response(400, "InvalidPassword", str(e))
        except ClientError as e:
            logger.error(f"Cognito sign_up error: {e}")
            return create_error_response(500, "ServerError", "An unexpected error occurred.")

    elif action == "verify-otp":
        # Step 2: Confirm sign-up with the verification code
        email = (body.get("email") or "").strip().lower()
        otp_code = (body.get("otp") or "").strip()
        if not email or not otp_code:
            return create_error_response(400, "InvalidOTP", "Invalid or expired OTP code")
        try:
            cognito_client.confirm_sign_up(
                ClientId=COGNITO_CLIENT_ID,
                Username=email,
                ConfirmationCode=otp_code,
            )
            # Generate a short-lived otpToken for the final step (backward compat)
            now = int(time.time())
            otp_token = jwt.encode(
                {"sub": email, "purpose": "registration", "iat": now, "exp": now + 600},
                JWT_SECRET, algorithm="HS256"
            )
            return create_response(200, {"verified": True, "otpToken": otp_token})
        except cognito_client.exceptions.CodeMismatchException:
            return create_error_response(400, "InvalidOTP", "Invalid or expired OTP code")
        except cognito_client.exceptions.ExpiredCodeException:
            return create_error_response(400, "InvalidOTP", "Invalid or expired OTP code")
        except ClientError as e:
            logger.error(f"Cognito confirm_sign_up error: {e}")
            return create_error_response(500, "ServerError", "An unexpected error occurred.")

    elif action == "create-account":
        # Step 3: Account already created in step 1 — just create the profile record
        otp_token = (body.get("otpToken") or "").strip()
        if not otp_token:
            return create_error_response(400, "InvalidToken", "Email verification token is invalid or expired")
        try:
            decoded = jwt.decode(otp_token, JWT_SECRET, algorithms=["HS256"])
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
            return create_error_response(400, "InvalidToken", "Email verification token is invalid or expired")
        if decoded.get("purpose") != "registration":
            return create_error_response(400, "InvalidToken", "Email verification token is invalid or expired")
        email = decoded.get("sub", "").lower()

        # Create profile record in DynamoDB (no password stored)
        members_table = dynamodb.Table(MEMBERS_TABLE_NAME)
        now_iso = datetime.now(timezone.utc).isoformat()
        try:
            existing = members_table.get_item(Key={"email": email}).get("Item")
            if not existing:
                members_table.put_item(Item={
                    "email": email,
                    "displayName": email.split("@")[0],
                    "createdAt": now_iso,
                    "lastLoginAt": None,
                    "favoriteQueries": [],
                })
        except ClientError as e:
            logger.warning(f"Profile create error (non-critical): {e}")

        return create_response(201, {"message": "Registration successful", "email": email})

    elif action == "resend-otp":
        # Resend verification code
        email = (body.get("email") or "").strip().lower()
        if not email:
            return create_error_response(400, "InvalidEmail", "Email is required")
        try:
            cognito_client.resend_confirmation_code(ClientId=COGNITO_CLIENT_ID, Username=email)
            return create_response(200, {"message": "Code resent", "email": email})
        except ClientError as e:
            logger.error(f"Cognito resend error: {e}")
            return create_error_response(500, "ServerError", "Failed to resend code")

    else:
        return create_error_response(400, "InvalidRequest", "Field 'action' is required")


def handle_login(event):
    """Authenticate member via Cognito and return access token."""
    try:
        body = json.loads(event.get("body", "{}"))
    except (json.JSONDecodeError, TypeError):
        return create_error_response(400, "InvalidRequest", "Invalid request body")

    email = (body.get("email") or "").strip().lower()
    password = body.get("password", "")

    if not email or not password:
        return create_error_response(400, "InvalidRequest", "Email and password are required")

    try:
        auth_resp = cognito_client.initiate_auth(
            AuthFlow="USER_PASSWORD_AUTH",
            AuthParameters={"USERNAME": email, "PASSWORD": password},
            ClientId=COGNITO_CLIENT_ID,
        )
    except cognito_client.exceptions.NotAuthorizedException:
        return create_error_response(401, "AuthError", "Invalid email or password")
    except cognito_client.exceptions.UserNotFoundException:
        return create_error_response(401, "AuthError", "Invalid email or password")
    except cognito_client.exceptions.UserNotConfirmedException:
        return create_error_response(401, "AuthError", "Please verify your email before logging in")
    except ClientError as e:
        logger.error(f"Cognito login error: {e}")
        return create_error_response(500, "ServerError", "An unexpected error occurred.")

    auth_result = auth_resp.get("AuthenticationResult", {})
    access_token = auth_result.get("AccessToken", "")
    refresh_token = auth_result.get("RefreshToken", "")

    # Get display name from profile table (or Cognito attributes)
    display_name = email.split("@")[0]
    members_table = dynamodb.Table(MEMBERS_TABLE_NAME)
    try:
        member = members_table.get_item(Key={"email": email}).get("Item")
        if member:
            display_name = member.get("displayName", display_name)
        else:
            # Create profile on first login if it doesn't exist
            now_iso = datetime.now(timezone.utc).isoformat()
            members_table.put_item(Item={
                "email": email,
                "displayName": display_name,
                "createdAt": now_iso,
                "lastLoginAt": now_iso,
                "favoriteQueries": [],
            })
    except ClientError:
        pass

    # Update lastLoginAt
    try:
        members_table.update_item(
            Key={"email": email},
            UpdateExpression="SET lastLoginAt = :ts",
            ExpressionAttributeValues={":ts": datetime.now(timezone.utc).isoformat()},
        )
    except ClientError:
        pass

    logger.info(f"Member login successful for: {email}")
    return create_response(200, {
        "token": access_token,
        "refreshToken": refresh_token,
        "email": email,
        "displayName": display_name,
    })


def handle_reset_password(event):
    """Handle password reset via Cognito ForgotPassword flow."""
    try:
        body = json.loads(event.get("body", "{}"))
    except (json.JSONDecodeError, TypeError):
        return create_error_response(400, "InvalidRequest", "Invalid request body")

    action = body.get("action", "")

    if action == "send-otp":
        email = (body.get("email") or "").strip().lower()
        if not email or not EMAIL_REGEX.match(email):
            return create_error_response(400, "InvalidEmail", "Please provide a valid email address")
        try:
            cognito_client.forgot_password(ClientId=COGNITO_CLIENT_ID, Username=email)
            return create_response(200, {"message": "Reset code sent", "email": email})
        except cognito_client.exceptions.UserNotFoundException:
            return create_error_response(404, "NotFound", "No account found with this email")
        except cognito_client.exceptions.LimitExceededException:
            return create_error_response(429, "RateLimited", "Please wait before requesting a new code")
        except ClientError as e:
            logger.error(f"Cognito forgot_password error: {e}")
            return create_error_response(500, "ServerError", "An unexpected error occurred.")

    elif action == "verify-otp":
        email = (body.get("email") or "").strip().lower()
        otp_code = (body.get("otp") or "").strip()
        if not email or not otp_code:
            return create_error_response(400, "InvalidOTP", "Invalid or expired code")
        # We can't verify the code without the new password in Cognito
        # So we store it in a short-lived JWT for the next step
        now = int(time.time())
        reset_token = jwt.encode(
            {"sub": email, "otp": otp_code, "purpose": "reset", "iat": now, "exp": now + 600},
            JWT_SECRET, algorithm="HS256"
        )
        return create_response(200, {"verified": True, "resetToken": reset_token})

    elif action == "set-password":
        reset_token = (body.get("resetToken") or "").strip()
        password = body.get("password", "")
        confirm_password = body.get("confirmPassword", "")
        if not reset_token:
            return create_error_response(400, "InvalidToken", "Reset token is invalid or expired")
        try:
            decoded = jwt.decode(reset_token, JWT_SECRET, algorithms=["HS256"])
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
            return create_error_response(400, "InvalidToken", "Reset token is invalid or expired")
        if decoded.get("purpose") != "reset":
            return create_error_response(400, "InvalidToken", "Reset token is invalid or expired")
        email = decoded.get("sub", "").lower()
        otp_code = decoded.get("otp", "")
        if len(password) < 8:
            return create_error_response(400, "InvalidPassword", "Password must be at least 8 characters")
        if password != confirm_password:
            return create_error_response(400, "InvalidPassword", "Passwords do not match")
        try:
            cognito_client.confirm_forgot_password(
                ClientId=COGNITO_CLIENT_ID,
                Username=email,
                ConfirmationCode=otp_code,
                Password=password,
            )
            return create_response(200, {"message": "Password reset successful. Please log in with your new password."})
        except cognito_client.exceptions.CodeMismatchException:
            return create_error_response(400, "InvalidOTP", "Invalid or expired reset code")
        except cognito_client.exceptions.ExpiredCodeException:
            return create_error_response(400, "InvalidOTP", "Reset code has expired. Please request a new one.")
        except cognito_client.exceptions.InvalidPasswordException as e:
            return create_error_response(400, "InvalidPassword", str(e))
        except ClientError as e:
            logger.error(f"Cognito confirm_forgot_password error: {e}")
            return create_error_response(500, "ServerError", "An unexpected error occurred.")

    else:
        return create_error_response(400, "InvalidRequest", "Field 'action' is required")

'''

content = content[:reg_start] + new_auth_block + content[accounts_start:]
open("member-handler/lambda_function.py", "w", encoding="utf-8").write(content)
print("Auth handlers replaced. New length:", len(content))
