# Backend Agent Rules

## Scope

Work only on the Django backend.

Do not touch frontend files.

Before implementing a feature, read the related backend docs under `docs/`.

Use the docs as the source of truth for:

* ERD
* API endpoints
* request/response format
* related tables
* feature requirements

## API Rules

All APIs must be under:

```text
/api/v1/
```

Use this common response format.

Success:

```json
{
  "success": true,
  "message": "message",
  "data": {}
}
```

Error:

```json
{
  "success": false,
  "message": "message",
  "errors": {}
}
```

Do not return raw serializer errors directly. Wrap errors in the common response format.

## User Model Rules

Use the custom User model:

```text
accounts.User
```

Rules:

* Do not use Django default User directly.
* Do not import `User` from `django.contrib.auth.models`.
* In models, use `settings.AUTH_USER_MODEL`.
* In serializers, views, and services, use `get_user_model()`.
* Use `create_user()` when creating users.
* Email must be unique.

## Auth Rules

Use JWT authentication.

Authorization header:

```http
Authorization: Bearer {access_token}
```

## Work Rules

* Implement only the requested feature.
* Do not implement unrelated APIs.
* Keep changes small.
* Do not touch frontend files.
* Do not delete docs or fixtures.
* Do not hardcode API keys.
* Use serializers for validation.
* Use permissions for ownership checks when needed.
* Run this after backend changes:

```bash
python manage.py check
```

If models changed, also run:

```bash
python manage.py makemigrations
python manage.py migrate
```

## Explanation Rules

After every task, explain the changes in a beginner-friendly way.

Do not only list changed files.

Explain:

1. What feature was implemented
2. Which files were changed
3. Why each file was changed
4. What each important code block does
5. How the request flows through URL -> view -> serializer -> model
6. How authentication or permissions are handled
7. How to test the feature manually
8. What commands were run
9. Whether the commands passed or failed
10. What should be done next

Use simple language.

Assume the reader is still learning Django and DRF.

When explaining code, include short examples.

Bad explanation:

```text
Implemented auth APIs and updated serializers.
```

Good explanation:

```text
I added signup, login, logout, and me APIs.

accounts/serializers.py:
This file validates incoming request data.
SignupSerializer checks username/email/password and creates a user using create_user().
Using create_user() is important because it hashes the password instead of saving plain text.

accounts/views.py:
This file receives HTTP requests.
SignupView receives POST /api/v1/auth/signup/, validates data with SignupSerializer, and returns the common response format.

accounts/urls.py:
This file connects URL paths to views.
```

## Final Response Format

After each task, respond with this structure:

```text
## What I implemented

## Changed files

## File-by-file explanation

## Request flow

## Commands run

## Test result

## How to test manually

## Notes / TODO
```
