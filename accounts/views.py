from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed, NotAuthenticated, PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from .serializers import LoginSerializer, LogoutSerializer, SignupSerializer


def success_response(message, data=None, status_code=status.HTTP_200_OK):
    return Response(
        {
            'success': True,
            'message': message,
            'data': data,
        },
        status=status_code,
    )


def error_response(message, errors=None, status_code=status.HTTP_400_BAD_REQUEST):
    return Response(
        {
            'success': False,
            'message': message,
            'errors': errors or {},
        },
        status=status_code,
    )


def user_data(user):
    return {
        'id': user.id,
        'username': user.username,
        'email': user.email,
    }


class CommonResponseAPIView(APIView):
    def handle_exception(self, exc):
        if isinstance(exc, (AuthenticationFailed, NotAuthenticated)):
            return error_response(
                '인증이 필요합니다.',
                {'detail': [str(exc)]},
                status.HTTP_401_UNAUTHORIZED,
            )

        if isinstance(exc, PermissionDenied):
            return error_response(
                '권한이 없습니다.',
                {'detail': [str(exc)]},
                status.HTTP_403_FORBIDDEN,
            )

        return super().handle_exception(exc)


class SignupView(CommonResponseAPIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = SignupSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response('회원가입에 실패했습니다.', serializer.errors)

        user = serializer.save()
        data = {
            **user_data(user),
            'created_at': user.date_joined,
        }
        return success_response('회원가입이 완료되었습니다.', data, status.HTTP_201_CREATED)


class LoginView(CommonResponseAPIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response('로그인에 실패했습니다.', serializer.errors, status.HTTP_401_UNAUTHORIZED)

        user = serializer.validated_data['user']
        refresh = RefreshToken.for_user(user)
        data = {
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': user_data(user),
        }
        return success_response('로그인에 성공했습니다.', data)


class LogoutView(CommonResponseAPIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response('로그아웃에 실패했습니다.', serializer.errors)

        try:
            token = RefreshToken(serializer.validated_data['refresh'])
            token.blacklist()
        except TokenError:
            return error_response(
                '로그아웃에 실패했습니다.',
                {'refresh': ['유효하지 않은 refresh token입니다.']},
                status.HTTP_400_BAD_REQUEST,
            )

        return success_response('로그아웃되었습니다.', None)


class MeView(CommonResponseAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        data = {
            **user_data(request.user),
            'has_profile': hasattr(request.user, 'profile'),
        }
        return success_response('내 정보 조회 성공', data)
