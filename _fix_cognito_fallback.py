content = open('member-handler/lambda_function.py', 'r', encoding='utf-8').read()

# ── Fix validate_token: fallback to JWT if Cognito not configured ─────────
old_validate = '''def validate_token(event):
    """Validate Cognito JWT from Authorization header.
    Returns decoded payload on success, error response dict on failure.
    """
    headers = event.get('headers', {}) or {}
    auth_header = headers.get('authorization') or headers.get('Authorization') or ''

    if not auth_header.startswith('Bearer '):
        return create_error_response(401, 'AuthError', 'Authentication required')

    token = auth_header[7:]

    try:
        # Use Cognito GetUser to validate the access token
        user_resp = cognito_client.get_user(AccessToken=token)
        email = next(
            (a['Value'] for a in user_resp.get('UserAttributes', []) if a['Name'] == 'email'),
            user_resp.get('Username', '')
        ).lower()
        display_name = next(
            (a['Value'] for a in user_resp.get('UserAttributes', []) if a['Name'] == 'custom:displayName'),
            email.split('@')[0]
        )
        return {'sub': email, 'role': 'member', 'displayName': display_name, 'username': user_resp.get('Username', '')}
    except cognito_client.exceptions.NotAuthorizedException:
        return create_error_response(401, 'AuthError', 'Session expired, please log in again')
    except cognito_client.exceptions.UserNotFoundException:
        return create_error_response(401, 'AuthError', 'Authentication required')
    except Exception as e:
        logger.warning(f"Token validation error: {e}")
        return create_error_response(401, 'AuthError', 'Authentication required')'''

new_validate = '''def validate_token(event):
    """Validate token from Authorization header.
    
    If Cognito is configured (COGNITO_USER_POOL_ID set), validates via Cognito GetUser.
    Falls back to legacy JWT validation for backward compatibility during migration.
    """
    headers = event.get('headers', {}) or {}
    auth_header = headers.get('authorization') or headers.get('Authorization') or ''

    if not auth_header.startswith('Bearer '):
        return create_error_response(401, 'AuthError', 'Authentication required')

    token = auth_header[7:]

    # ── Cognito path (new) ────────────────────────────────────────────────
    if COGNITO_USER_POOL_ID:
        try:
            user_resp = cognito_client.get_user(AccessToken=token)
            email = next(
                (a['Value'] for a in user_resp.get('UserAttributes', []) if a['Name'] == 'email'),
                user_resp.get('Username', '')
            ).lower()
            display_name = next(
                (a['Value'] for a in user_resp.get('UserAttributes', []) if a['Name'] == 'custom:displayName'),
                email.split('@')[0]
            )
            return {'sub': email, 'role': 'member', 'displayName': display_name, 'username': user_resp.get('Username', '')}
        except cognito_client.exceptions.NotAuthorizedException:
            # Could be a legacy JWT token — try fallback
            pass
        except cognito_client.exceptions.UserNotFoundException:
            return create_error_response(401, 'AuthError', 'Authentication required')
        except Exception as e:
            logger.warning(f"Cognito token validation error: {e}")
            # Fall through to legacy JWT validation

    # ── Legacy JWT path (fallback / migration period) ─────────────────────
    if JWT_SECRET:
        try:
            decoded = jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
            if decoded.get('role') == 'member':
                return decoded
        except jwt.ExpiredSignatureError:
            return create_error_response(401, 'AuthError', 'Session expired, please log in again')
        except jwt.InvalidTokenError:
            pass

    return create_error_response(401, 'AuthError', 'Authentication required')'''

if old_validate in content:
    content = content.replace(old_validate, new_validate)
    print('validate_token updated with fallback')
else:
    print('ERROR: validate_token pattern not found')

# ── Fix handle_login: fallback to DynamoDB if Cognito not configured ──────
old_login_try = '''    try:
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
    })'''

new_login_try = '''    # ── Cognito login (new) ──────────────────────────────────────────────────
    if COGNITO_CLIENT_ID:
        try:
            auth_resp = cognito_client.initiate_auth(
                AuthFlow="USER_PASSWORD_AUTH",
                AuthParameters={"USERNAME": email, "PASSWORD": password},
                ClientId=COGNITO_CLIENT_ID,
            )
            auth_result = auth_resp.get("AuthenticationResult", {})
            access_token = auth_result.get("AccessToken", "")
            refresh_token = auth_result.get("RefreshToken", "")

            display_name = email.split("@")[0]
            members_table = dynamodb.Table(MEMBERS_TABLE_NAME)
            try:
                member = members_table.get_item(Key={"email": email}).get("Item")
                if member:
                    display_name = member.get("displayName", display_name)
                else:
                    now_iso = datetime.now(timezone.utc).isoformat()
                    members_table.put_item(Item={"email": email, "displayName": display_name, "createdAt": now_iso, "lastLoginAt": now_iso, "favoriteQueries": []})
            except ClientError:
                pass
            try:
                members_table.update_item(Key={"email": email}, UpdateExpression="SET lastLoginAt = :ts", ExpressionAttributeValues={":ts": datetime.now(timezone.utc).isoformat()})
            except ClientError:
                pass

            logger.info(f"Member Cognito login successful for: {email}")
            return create_response(200, {"token": access_token, "refreshToken": refresh_token, "email": email, "displayName": display_name})

        except cognito_client.exceptions.NotAuthorizedException:
            return create_error_response(401, "AuthError", "Invalid email or password")
        except cognito_client.exceptions.UserNotFoundException:
            return create_error_response(401, "AuthError", "Invalid email or password")
        except cognito_client.exceptions.UserNotConfirmedException:
            return create_error_response(401, "AuthError", "Please verify your email before logging in")
        except ClientError as e:
            logger.error(f"Cognito login error: {e}")
            return create_error_response(500, "ServerError", "An unexpected error occurred.")

    # ── Legacy DynamoDB login (fallback during migration) ─────────────────
    members_table = dynamodb.Table(MEMBERS_TABLE_NAME)
    try:
        result = members_table.get_item(Key={"email": email})
        member = result.get("Item")
    except ClientError as e:
        logger.error(f"DynamoDB read error: {e}")
        return create_error_response(500, "ServerError", "An unexpected error occurred.")

    if not member:
        return create_error_response(401, "AuthError", "Invalid email or password")

    try:
        password_valid = bcrypt.checkpw(password.encode("utf-8"), member["passwordHash"].encode("utf-8"))
    except Exception:
        return create_error_response(401, "AuthError", "Invalid email or password")

    if not password_valid:
        return create_error_response(401, "AuthError", "Invalid email or password")

    now = int(time.time())
    token = jwt.encode({"sub": email, "role": "member", "iat": now, "exp": now + 86400}, JWT_SECRET, algorithm="HS256")

    try:
        members_table.update_item(Key={"email": email}, UpdateExpression="SET lastLoginAt = :ts", ExpressionAttributeValues={":ts": datetime.now(timezone.utc).isoformat()})
    except ClientError:
        pass

    display_name = member.get("displayName", email.split("@")[0])
    logger.info(f"Member legacy login successful for: {email}")
    return create_response(200, {"token": token, "email": email, "displayName": display_name})'''

if old_login_try in content:
    content = content.replace(old_login_try, new_login_try)
    print('handle_login updated with fallback')
else:
    print('ERROR: handle_login pattern not found')

open('member-handler/lambda_function.py', 'w', encoding='utf-8').write(content)
print('Done')
