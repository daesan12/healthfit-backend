import os

from django.db import transaction
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated

from accounts.views import CommonResponseAPIView, error_response, success_response
from config.pagination import paginate_data
from diets.serializers import MealSerializer, SavedMealSerializer
from workouts.models import WorkoutRoutine
from workouts.serializers import RoutineItemSerializer, WorkoutRoutineSerializer

from .models import AIChat, AIRecommendation
from .serializers import (
    AIChatRequestSerializer,
    AIChatSerializer,
    DietEvaluationRequestSerializer,
    DietFeedbackSerializer,
    DietRecommendationRequestSerializer,
    ReplaceDietItemRequestSerializer,
    RerollDietRequestSerializer,
    SaveMealRequestSerializer,
    SaveRoutineRequestSerializer,
    SaveSavedMealRequestSerializer,
    WorkoutRecommendationRequestSerializer,
    WorkoutProgressionRequestSerializer,
)
from .services.chat_service import create_chat_answer
from .services.gms_client import GMSAPIError, GMSConfigurationError, GMSResponseError
from .services.recommendation_service import (
    AIServiceError,
    evaluate_diet,
    recommend_diet,
    recommend_workout,
    replace_diet_item,
    reroll_diet,
)
from .services.diet_save_service import save_diet_recommendation
from .services.workout_progression_service import recommend_workout_progression


class AIAPIView(CommonResponseAPIView):
    permission_classes = [IsAuthenticated]

    def require_gms_key(self):
        if os.getenv('GMS_KEY', '').strip():
            return None
        return error_response(
            'AI API key is not configured.',
            {'GMS_KEY': ['GMS_KEY is missing.']},
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    def service_error_response(self, exc):
        if isinstance(exc, GMSConfigurationError):
            return error_response(
                'AI API key is not configured.',
                {'GMS_KEY': ['GMS_KEY is missing.']},
                status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        if isinstance(exc, GMSAPIError):
            detail = (
                f'GMS API returned HTTP {exc.status_code}.'
                if exc.status_code
                else 'GMS API request failed. Please try again later.'
            )
            return error_response(
                'AI service request failed.',
                {'ai': [detail]},
                status.HTTP_502_BAD_GATEWAY,
            )
        if isinstance(exc, GMSResponseError):
            return error_response(
                'AI response could not be parsed.',
                {'ai': [str(exc)]},
                status.HTTP_502_BAD_GATEWAY,
            )
        if isinstance(exc, AIServiceError):
            return error_response(exc.message, exc.errors, exc.status_code)
        raise exc


def request_guardrail_text(request):
    values = []
    for field in ['message', 'preference']:
        value = request.data.get(field)
        if isinstance(value, str) and value.strip() and value.strip() not in values:
            values.append(value.strip())
    return '\n'.join(values) or None


class AIChatListCreateView(AIAPIView):
    def get(self, request):
        chats = AIChat.objects.filter(user=request.user).order_by('-created_at', '-id')
        data = paginate_data(request, chats, AIChatSerializer)
        return success_response('AI 채팅 기록 조회 성공', data)

    def post(self, request):
        key_error = self.require_gms_key()
        if key_error:
            return key_error
        serializer = AIChatRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response('AI 채팅 요청에 실패했습니다.', serializer.errors)

        question = serializer.validated_data['question']
        try:
            answer = create_chat_answer(request.user, question)
        except (GMSConfigurationError, GMSAPIError, GMSResponseError) as exc:
            return self.service_error_response(exc)
        chat = AIChat.objects.create(user=request.user, question=question, answer=answer)
        return success_response(
            'AI 답변이 생성되었습니다.',
            AIChatSerializer(chat).data,
            status.HTTP_201_CREATED,
        )


class DietEvaluationView(AIAPIView):
    def post(self, request):
        key_error = self.require_gms_key()
        if key_error:
            return key_error

        serializer = DietEvaluationRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response('AI 식단 평가에 실패했습니다.', serializer.errors)

        try:
            feedback = evaluate_diet(request.user, serializer.validated_data['target_date'])
        except (GMSConfigurationError, GMSAPIError, GMSResponseError, AIServiceError) as exc:
            return self.service_error_response(exc)
        return success_response('AI 식단 평가가 완료되었습니다.', DietFeedbackSerializer(feedback).data)


class DietRecommendationView(AIAPIView):
    def post(self, request):
        key_error = self.require_gms_key()
        if key_error:
            return key_error

        serializer = DietRecommendationRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response('AI 식단 추천에 실패했습니다.', serializer.errors)

        try:
            data = recommend_diet(
                request.user,
                serializer.validated_data,
                guardrail_text=request_guardrail_text(request),
            )
        except (GMSConfigurationError, GMSAPIError, GMSResponseError, AIServiceError) as exc:
            return self.service_error_response(exc)
        return success_response('AI 식단 추천이 완료되었습니다.', data)


class WorkoutRecommendationView(AIAPIView):
    def post(self, request):
        key_error = self.require_gms_key()
        if key_error:
            return key_error

        serializer = WorkoutRecommendationRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response('AI 운동 루틴 추천에 실패했습니다.', serializer.errors)

        try:
            data = recommend_workout(
                request.user,
                serializer.validated_data,
                guardrail_text=request_guardrail_text(request),
            )
        except (GMSConfigurationError, GMSAPIError, GMSResponseError, AIServiceError) as exc:
            return self.service_error_response(exc)
        return success_response('AI 운동 루틴 추천이 완료되었습니다.', data)


class WorkoutProgressionView(AIAPIView):
    def post(self, request):
        key_error = self.require_gms_key()
        if key_error:
            return key_error

        serializer = WorkoutProgressionRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response('운동 진행 추천에 실패했습니다.', serializer.errors)

        try:
            data = recommend_workout_progression(request.user, serializer.validated_data)
        except AIServiceError as exc:
            return self.service_error_response(exc)
        return success_response('운동 진행 추천이 완료되었습니다.', data)


class RecommendationSaveAPIView(AIAPIView):
    permission_classes = [IsAuthenticated]

    def get_recommendation(self, request, recommendation_id):
        try:
            return AIRecommendation.objects.get(pk=recommendation_id, user=request.user)
        except AIRecommendation.DoesNotExist:
            return error_response(
                'AI 추천 결과를 찾을 수 없습니다.',
                {'recommendation_id': ['조회 가능한 내 AI 추천 결과가 아닙니다.']},
                status.HTTP_404_NOT_FOUND,
            )

    def validate_type(self, recommendation, expected_type, message):
        if recommendation.recommendation_type != expected_type:
            return error_response(
                message,
                {'recommendation_id': [f'{expected_type} 추천 결과가 아닙니다.']},
            )
        return None

    def diet_items(self, recommendation, message):
        if recommendation.source == 'free':
            return error_response(
                message,
                {'food_source': ['free 추천은 Meal 또는 SavedMeal로 바로 저장할 수 없습니다.']},
            )
        items = recommendation.result_data.get('items')
        if not isinstance(items, list) or not items:
            return error_response(message, {'items': ['저장할 음식 항목이 없습니다.']})
        try:
            return [
                {'food_id': item['food_id'], 'amount': item['amount']}
                for item in items
            ]
        except (KeyError, TypeError):
            return error_response(message, {'items': ['음식 항목 형식이 올바르지 않습니다.']})


class DietRecommendationDetailView(RecommendationSaveAPIView):
    def get(self, request, recommendation_id):
        recommendation = self.get_recommendation(request, recommendation_id)
        if not isinstance(recommendation, AIRecommendation):
            return recommendation
        type_error = self.validate_type(
            recommendation,
            AIRecommendation.DIET,
            'AI 식단 추천 상세 조회에 실패했습니다.',
        )
        if type_error:
            return type_error
        data = {
            'recommendation_id': recommendation.id,
            'recommendation_scope': recommendation.recommendation_scope,
            'food_source': (recommendation.content or {}).get('food_source') or recommendation.source,
            'target_date': recommendation.target_date,
            'parent_recommendation_id': recommendation.parent_recommendation_id,
            'is_saved': recommendation.is_saved,
            'content': recommendation.content or recommendation.result_data,
            'created_at': recommendation.created_at,
            'updated_at': recommendation.updated_at,
        }
        return success_response('AI 식단 추천 상세 조회에 성공했습니다.', data)


class RecommendationSaveMealView(RecommendationSaveAPIView):
    def post(self, request, recommendation_id):
        request_serializer = SaveMealRequestSerializer(data=request.data)
        if not request_serializer.is_valid():
            return error_response('AI 추천 식단 저장에 실패했습니다.', request_serializer.errors)

        recommendation = self.get_recommendation(request, recommendation_id)
        if not isinstance(recommendation, AIRecommendation):
            return recommendation
        type_error = self.validate_type(recommendation, AIRecommendation.DIET, 'AI 추천 식단 저장에 실패했습니다.')
        if type_error:
            return type_error
        items = self.diet_items(recommendation, 'AI 추천 식단 저장에 실패했습니다.')
        if not isinstance(items, list):
            return items

        meal_data = {**request_serializer.validated_data, 'items': items}
        meal_serializer = MealSerializer(data=meal_data, context={'request': request})
        if not meal_serializer.is_valid():
            return error_response('AI 추천 식단 저장에 실패했습니다.', meal_serializer.errors)

        try:
            with transaction.atomic():
                meal = meal_serializer.save(user=request.user)
                self.mark_saved(recommendation)
        except ValidationError as exc:
            return error_response('AI 추천 식단 저장에 실패했습니다.', exc.detail)
        return success_response(
            'AI 추천을 식단 기록으로 저장했습니다.',
            MealSerializer(meal).data,
            status.HTTP_201_CREATED,
        )

    def mark_saved(self, recommendation):
        recommendation.is_saved = True
        recommendation.save(update_fields=['is_saved', 'updated_at'])


class RecommendationSaveSavedMealView(RecommendationSaveAPIView):
    def post(self, request, recommendation_id):
        request_serializer = SaveSavedMealRequestSerializer(data=request.data)
        if not request_serializer.is_valid():
            return error_response('AI 추천 저장 식단 생성에 실패했습니다.', request_serializer.errors)

        recommendation = self.get_recommendation(request, recommendation_id)
        if not isinstance(recommendation, AIRecommendation):
            return recommendation
        type_error = self.validate_type(
            recommendation,
            AIRecommendation.DIET,
            'AI 추천 저장 식단 생성에 실패했습니다.',
        )
        if type_error:
            return type_error
        try:
            data = save_diet_recommendation(
                request.user,
                recommendation,
                request_serializer.validated_data,
            )
        except AIServiceError as exc:
            return self.service_error_response(exc)
        return success_response(
            'AI 추천 식단을 저장했습니다.',
            data,
            status.HTTP_201_CREATED,
        )


class DietRecommendationReplaceView(RecommendationSaveAPIView):
    def post(self, request, recommendation_id):
        key_error = self.require_gms_key()
        if key_error:
            return key_error
        serializer = ReplaceDietItemRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response('추천 음식 교체에 실패했습니다.', serializer.errors)
        recommendation = self.get_recommendation(request, recommendation_id)
        if not isinstance(recommendation, AIRecommendation):
            return recommendation
        type_error = self.validate_type(recommendation, AIRecommendation.DIET, '추천 음식 교체에 실패했습니다.')
        if type_error:
            return type_error
        try:
            data = replace_diet_item(request.user, recommendation, serializer.validated_data)
        except (GMSConfigurationError, GMSAPIError, GMSResponseError, AIServiceError) as exc:
            return self.service_error_response(exc)
        return success_response('추천 음식 교체가 완료되었습니다.', data, status.HTTP_201_CREATED)


class DietRecommendationRerollView(RecommendationSaveAPIView):
    def post(self, request, recommendation_id):
        key_error = self.require_gms_key()
        if key_error:
            return key_error
        serializer = RerollDietRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response('AI 식단 재추천에 실패했습니다.', serializer.errors)
        recommendation = self.get_recommendation(request, recommendation_id)
        if not isinstance(recommendation, AIRecommendation):
            return recommendation
        type_error = self.validate_type(recommendation, AIRecommendation.DIET, 'AI 식단 재추천에 실패했습니다.')
        if type_error:
            return type_error
        try:
            data = reroll_diet(request.user, recommendation, serializer.validated_data['message'])
        except (GMSConfigurationError, GMSAPIError, GMSResponseError, AIServiceError) as exc:
            return self.service_error_response(exc)
        return success_response('AI 식단 재추천이 완료되었습니다.', data, status.HTTP_201_CREATED)


class RecommendationSaveRoutineView(RecommendationSaveAPIView):
    def post(self, request, recommendation_id):
        request_serializer = SaveRoutineRequestSerializer(data=request.data)
        if not request_serializer.is_valid():
            return error_response('AI 추천 운동 루틴 저장에 실패했습니다.', request_serializer.errors)

        recommendation = self.get_recommendation(request, recommendation_id)
        if not isinstance(recommendation, AIRecommendation):
            return recommendation
        type_error = self.validate_type(
            recommendation,
            AIRecommendation.WORKOUT,
            'AI 추천 운동 루틴 저장에 실패했습니다.',
        )
        if type_error:
            return type_error

        items = recommendation.result_data.get('items')
        if not isinstance(items, list) or not items:
            return error_response(
                'AI 추천 운동 루틴 저장에 실패했습니다.',
                {'items': ['저장할 운동 항목이 없습니다.']},
            )
        if any(not isinstance(item, dict) for item in items):
            return error_response(
                'AI 추천 운동 루틴 저장에 실패했습니다.',
                {'items': ['운동 항목 형식이 올바르지 않습니다.']},
            )
        item_serializers = []
        for item in items:
            item_data = {
                field: item.get(field)
                for field in ['exercise_id', 'order', 'sets', 'reps', 'weight', 'rest_seconds']
            }
            serializer = RoutineItemSerializer(data=item_data, context={'request': request})
            if not serializer.is_valid():
                return error_response('AI 추천 운동 루틴 저장에 실패했습니다.', serializer.errors)
            item_serializers.append(serializer)

        routine_serializer = WorkoutRoutineSerializer(data=request_serializer.validated_data)
        if not routine_serializer.is_valid():
            return error_response('AI 추천 운동 루틴 저장에 실패했습니다.', routine_serializer.errors)

        with transaction.atomic():
            routine = routine_serializer.save(user=request.user)
            for item_serializer in item_serializers:
                item_serializer.save(routine=routine)
            recommendation.is_saved = True
            recommendation.save(update_fields=['is_saved', 'updated_at'])

        routine = WorkoutRoutine.objects.prefetch_related('items__exercise').get(pk=routine.pk)
        return success_response(
            'AI 추천을 운동 루틴으로 저장했습니다.',
            WorkoutRoutineSerializer(routine).data,
            status.HTTP_201_CREATED,
        )
