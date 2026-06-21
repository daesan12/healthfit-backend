from collections import defaultdict

from django.utils.dateparse import parse_date
from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed, NotAuthenticated, PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from config.pagination import PaginationError, paginate_data

from .models import BodyRecord, Profile
from .serializers import BodyRecordSerializer, LoginSerializer, LogoutSerializer, ProfileSerializer, SignupSerializer


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
        if isinstance(exc, PaginationError):
            return error_response('페이지 조회에 실패했습니다.', exc.errors)

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


class BodyRecordListCreateView(CommonResponseAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        records = BodyRecord.objects.filter(user=request.user).select_related('user__profile')

        start_date = request.query_params.get('start_date')
        if start_date:
            parsed_start = parse_date(start_date)
            if parsed_start is None:
                return error_response(
                    '신체 기록 목록 조회에 실패했습니다.',
                    {'start_date': ['날짜 형식은 YYYY-MM-DD이어야 합니다.']},
                )
            records = records.filter(record_date__gte=parsed_start)

        end_date = request.query_params.get('end_date')
        if end_date:
            parsed_end = parse_date(end_date)
            if parsed_end is None:
                return error_response(
                    '신체 기록 목록 조회에 실패했습니다.',
                    {'end_date': ['날짜 형식은 YYYY-MM-DD이어야 합니다.']},
                )
            records = records.filter(record_date__lte=parsed_end)

        data = paginate_data(
            request,
            records.order_by('-record_date', '-id'),
            BodyRecordSerializer,
        )
        return success_response('신체 기록 목록 조회 성공', data)

    def post(self, request):
        serializer = BodyRecordSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response('신체 기록 등록에 실패했습니다.', serializer.errors)

        record = serializer.save(user=request.user)
        return success_response(
            '신체 기록이 등록되었습니다.',
            BodyRecordSerializer(record).data,
            status.HTTP_201_CREATED,
        )


class BodyRecordDetailView(CommonResponseAPIView):
    permission_classes = [IsAuthenticated]

    def get_record(self, request, body_record_id, message):
        try:
            return BodyRecord.objects.select_related('user__profile').get(
                pk=body_record_id,
                user=request.user,
            )
        except BodyRecord.DoesNotExist:
            return error_response(
                message,
                {'body_record_id': ['수정 또는 삭제 가능한 내 신체 기록이 아닙니다.']},
                status.HTTP_404_NOT_FOUND,
            )

    def patch(self, request, body_record_id):
        record = self.get_record(request, body_record_id, '신체 기록 수정에 실패했습니다.')
        if not isinstance(record, BodyRecord):
            return record

        serializer = BodyRecordSerializer(record, data=request.data, partial=True)
        if not serializer.is_valid():
            return error_response('신체 기록 수정에 실패했습니다.', serializer.errors)

        serializer.save()
        return success_response('신체 기록이 수정되었습니다.', serializer.data)

    def delete(self, request, body_record_id):
        record = self.get_record(request, body_record_id, '신체 기록 삭제에 실패했습니다.')
        if not isinstance(record, BodyRecord):
            return record

        record.delete()
        return success_response('신체 기록이 삭제되었습니다.', None)


class ProgressView(CommonResponseAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        start_text = request.query_params.get('start_date')
        end_text = request.query_params.get('end_date')
        start_date = parse_date(start_text) if start_text else None
        end_date = parse_date(end_text) if end_text else None

        errors = {}
        if start_date is None:
            errors['start_date'] = ['YYYY-MM-DD 형식의 시작일이 필요합니다.']
        if end_date is None:
            errors['end_date'] = ['YYYY-MM-DD 형식의 종료일이 필요합니다.']
        if not errors and start_date > end_date:
            errors['date_range'] = ['시작일은 종료일보다 늦을 수 없습니다.']
        if errors:
            return error_response('진행 현황 조회에 실패했습니다.', errors)

        from diets.models import Meal
        from workouts.models import WorkoutLog

        body_records = BodyRecord.objects.filter(
            user=request.user,
            record_date__range=(start_date, end_date),
        ).select_related('user__profile').order_by('record_date', 'id')
        meals = Meal.objects.filter(
            user=request.user,
            intake_date__range=(start_date, end_date),
        )
        workout_logs = WorkoutLog.objects.filter(
            user=request.user,
            workout_date__range=(start_date, end_date),
        )

        profile = getattr(request.user, 'profile', None)
        data = {
            'start_date': start_date,
            'end_date': end_date,
            'profile': ProfileSerializer(profile).data if profile else None,
            'body_summary': self.body_summary(body_records),
            'meal_summary': self.meal_summary(meals),
            'workout_summary': self.workout_summary(workout_logs),
        }
        return success_response('진행 현황 조회 성공', data)

    def body_summary(self, records):
        records = list(records)
        weighted_records = [record for record in records if record.weight is not None]
        starting_weight = weighted_records[0].weight if weighted_records else None
        latest_weight = weighted_records[-1].weight if weighted_records else None
        weight_change = None
        if starting_weight is not None and latest_weight is not None:
            weight_change = round(latest_weight - starting_weight, 2)

        recent = list(reversed(records[-10:]))
        return {
            'starting_weight': starting_weight,
            'latest_weight': latest_weight,
            'weight_change': weight_change,
            'recent_records': BodyRecordSerializer(recent, many=True).data,
        }

    def meal_summary(self, meals):
        daily = defaultdict(lambda: {
            'meal_count': 0,
            'total_calories': 0,
            'total_carbohydrate': 0,
            'total_protein': 0,
            'total_fat': 0,
        })
        totals = {
            'meal_count': 0,
            'total_calories': 0,
            'total_carbohydrate': 0,
            'total_protein': 0,
            'total_fat': 0,
        }

        for meal in meals:
            values = daily[meal.intake_date.isoformat()]
            values['meal_count'] += 1
            totals['meal_count'] += 1
            for field in ['total_calories', 'total_carbohydrate', 'total_protein', 'total_fat']:
                value = getattr(meal, field)
                values[field] += value
                totals[field] += value

        for values in [totals, *daily.values()]:
            for field in ['total_calories', 'total_carbohydrate', 'total_protein', 'total_fat']:
                values[field] = round(values[field], 2)

        return {
            **totals,
            'meal_score': None,
            'daily': [{'date': date, **daily[date]} for date in sorted(daily)],
        }

    def workout_summary(self, logs):
        daily = defaultdict(lambda: {'workout_count': 0, 'total_workout_time': 0})
        workout_count = 0
        total_workout_time = 0

        for log in logs:
            values = daily[log.workout_date.isoformat()]
            values['workout_count'] += 1
            values['total_workout_time'] += log.workout_time or 0
            workout_count += 1
            total_workout_time += log.workout_time or 0

        return {
            'workout_count': workout_count,
            'total_workout_time': total_workout_time,
            'daily': [{'date': date, **daily[date]} for date in sorted(daily)],
        }
