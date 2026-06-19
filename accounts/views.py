from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed, NotAuthenticated, PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from .models import Profile
from .serializers import LoginSerializer, LogoutSerializer, ProfileSerializer, SignupSerializer


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


class MyProfileView(CommonResponseAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            profile = request.user.profile
        except Profile.DoesNotExist:
            return error_response(
                '프로필을 찾을 수 없습니다.',
                {'profile': ['프로필을 먼저 등록해주세요.']},
                status.HTTP_404_NOT_FOUND,
            )

        return success_response('프로필 조회 성공', ProfileSerializer(profile).data)

    def put(self, request):
        profile = getattr(request.user, 'profile', None)
        serializer = ProfileSerializer(instance=profile, data=request.data)
        if not serializer.is_valid():
            return error_response('프로필 저장에 실패했습니다.', serializer.errors)

        serializer.save(user=request.user)
        return success_response('프로필이 저장되었습니다.', serializer.data)


class CalorieTargetView(CommonResponseAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            profile = request.user.profile
        except Profile.DoesNotExist:
            return error_response(
                '권장 칼로리 계산에 실패했습니다.',
                {'profile': ['프로필을 먼저 등록해주세요.']},
                status.HTTP_404_NOT_FOUND,
            )

        recommended_calories = calculate_recommended_calories(profile)
        carbohydrate_ratio = 50
        protein_ratio = 30
        fat_ratio = 20

        data = {
            'recommended_calories': recommended_calories,
            'carbohydrate_ratio': carbohydrate_ratio,
            'protein_ratio': protein_ratio,
            'fat_ratio': fat_ratio,
            'recommended_carbohydrate': round(recommended_calories * carbohydrate_ratio / 100 / 4, 1),
            'recommended_protein': round(recommended_calories * protein_ratio / 100 / 4, 1),
            'recommended_fat': round(recommended_calories * fat_ratio / 100 / 9, 1),
        }
        return success_response('권장 칼로리 계산이 완료되었습니다.', data)


def calculate_recommended_calories(profile):
    gender = profile.gender.lower()
    if gender == 'male':
        bmr = 10 * profile.weight + 6.25 * profile.height - 5 * profile.age + 5
    elif gender == 'female':
        bmr = 10 * profile.weight + 6.25 * profile.height - 5 * profile.age - 161
    else:
        bmr = 10 * profile.weight + 6.25 * profile.height - 5 * profile.age - 78

    activity_multipliers = {
        'low': 1.2,
        'normal': 1.55,
        'high': 1.725,
    }
    goal_adjustments = {
        'fat_loss': -500,
        'muscle_gain': 300,
        'maintenance': 0,
        'weight_gain': 500,
    }

    calories = bmr * activity_multipliers.get(profile.activity_level, 1.2)
    calories += goal_adjustments.get(profile.workout_goal, 0)
    return max(round(calories), 1200)
