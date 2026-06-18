# Backend Setup

## 1. 목적

이 문서는 HealthFit 백엔드 프로젝트의 기본 환경설정과 실행 방법을 정리한 문서이다.

현재 백엔드는 Django + Django REST Framework 기반 API 서버로 구성되어 있으며, Vue 프론트엔드와 연동하기 위한 CORS 설정과 JWT 인증 설정이 적용되어 있다.

---

## 2. 주요 설정 내용

현재 백엔드에 적용된 주요 설정은 다음과 같다.

| 항목         | 설명                                                  |
| ---------- | --------------------------------------------------- |
| DRF 설정     | Django에서 REST API를 만들기 위해 `djangorestframework`를 사용 |
| CORS 설정    | Vue 개발 서버에서 Django API 요청이 가능하도록 허용                 |
| JWT 설정     | 로그인 인증 방식으로 JWT 사용                                  |
| dotenv 설정  | `.env` 파일에서 환경변수 로드                                 |
| fixture 설정 | 초기 음식/운동 데이터 파일 위치 지정                               |

---

## 3. 설치된 주요 패키지

```text
djangorestframework
django-cors-headers
djangorestframework-simplejwt
python-dotenv
```

각 패키지 역할은 다음과 같다.

| 패키지                             | 역할                   |
| ------------------------------- | -------------------- |
| `djangorestframework`           | REST API 구현          |
| `django-cors-headers`           | 프론트엔드와 백엔드 간 CORS 허용 |
| `djangorestframework-simplejwt` | JWT 기반 로그인/인증 처리     |
| `python-dotenv`                 | `.env` 환경변수 로드       |

---

## 4. settings.py 주요 설정

### 4.1 CORS 설정

Vue 개발 서버에서 Django 백엔드로 요청할 수 있도록 아래 origin을 허용한다.

```python
CORS_ALLOWED_ORIGINS = [
    'http://localhost:5173',
    'http://127.0.0.1:5173',
]
```

Vue + Vite 개발 서버는 보통 `5173` 포트를 사용하고, Django 백엔드는 보통 `8000` 포트를 사용한다.
포트가 다르면 브라우저가 서로 다른 출처로 판단하기 때문에 CORS 설정이 필요하다.

---

### 4.2 JWT 인증 설정

DRF의 기본 인증 방식으로 JWT 인증을 사용한다.

```python
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.AllowAny',
    ),
}
```

로그인이 필요한 API 요청에서는 프론트엔드가 아래 형식으로 access token을 보낸다.

```http
Authorization: Bearer {access_token}
```

`Authorization`은 인증 정보를 담는 HTTP Header이고, `Bearer`는 JWT 토큰 인증 방식에서 사용하는 prefix이다.

---

### 4.3 JWT 토큰 유효 시간

```python
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=60),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': False,
    'BLACKLIST_AFTER_ROTATION': True,
    'AUTH_HEADER_TYPES': ('Bearer',),
}
```

현재 설정 기준:

```text
access token 유효 시간: 60분
refresh token 유효 시간: 7일
인증 헤더 방식: Bearer
```

---

### 4.4 fixture 경로 설정

초기 데이터 fixture 파일 위치는 `backend/fixtures/`로 지정한다.

```python
FIXTURE_DIRS = [
    BASE_DIR / 'fixtures',
]
```

현재 fixture 파일 위치:

```text
backend/
└── fixtures/
    ├── food_fixture.json
    └── exercise_fixture.json
```

fixture 데이터는 모델 생성 후 아래 명령어로 DB에 로드한다.

```bash
python manage.py loaddata food_fixture.json
python manage.py loaddata exercise_fixture.json
```

주의: Food / Workout 관련 모델이 생성되기 전에는 `loaddata`를 실행하지 않는다.

