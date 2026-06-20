from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated

from accounts.views import CommonResponseAPIView, calculate_recommended_calories, error_response, success_response

from .models import Food, Meal, MealItem, SavedMeal
from .serializers import (
    FoodSerializer,
    MealSerializer,
    SavedMealCreateMealSerializer,
    SavedMealSerializer,
)


class FoodListCreateView(CommonResponseAPIView):
    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsAuthenticated()]
        return [AllowAny()]

    def get(self, request):
        foods = Food.objects.all()

        if request.user.is_authenticated:
            if request.query_params.get('mine') == 'true':
                foods = foods.filter(user=request.user)
            else:
                foods = foods.filter(Q(user__isnull=True) | Q(user=request.user))
        else:
            foods = foods.filter(user__isnull=True)

        search = request.query_params.get('search')
        if search:
            foods = foods.filter(name__icontains=search)

        category = request.query_params.get('category')
        if category:
            foods = foods.filter(category=category)

        serializer = FoodSerializer(foods.order_by('id'), many=True)
        return success_response('음식 목록 조회 성공', serializer.data)

    def post(self, request):
        serializer = FoodSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response('음식 추가에 실패했습니다.', serializer.errors)

        food = serializer.save(user=request.user)
        return success_response('음식이 추가되었습니다.', FoodSerializer(food).data, status.HTTP_201_CREATED)


class FoodDetailView(CommonResponseAPIView):
    def get_permissions(self):
        if self.request.method in ['PATCH', 'DELETE']:
            return [IsAuthenticated()]
        return [AllowAny()]

    def get(self, request, food_id):
        foods = Food.objects.all()
        if request.user.is_authenticated:
            foods = foods.filter(Q(user__isnull=True) | Q(user=request.user))
        else:
            foods = foods.filter(user__isnull=True)

        try:
            food = foods.get(id=food_id)
        except Food.DoesNotExist:
            return error_response(
                '음식을 찾을 수 없습니다.',
                {'food_id': ['조회 가능한 음식이 아닙니다.']},
                status.HTTP_404_NOT_FOUND,
            )

        return success_response('음식 상세 조회 성공', FoodSerializer(food).data)

    def patch(self, request, food_id):
        try:
            food = Food.objects.get(id=food_id, user=request.user)
        except Food.DoesNotExist:
            return error_response(
                '음식 수정에 실패했습니다.',
                {'food_id': ['수정 가능한 내 음식이 아닙니다.']},
                status.HTTP_404_NOT_FOUND,
            )

        serializer = FoodSerializer(food, data=request.data, partial=True)
        if not serializer.is_valid():
            return error_response('음식 수정에 실패했습니다.', serializer.errors)

        serializer.save()
        return success_response('음식이 수정되었습니다.', serializer.data)

    def delete(self, request, food_id):
        try:
            food = Food.objects.get(id=food_id, user=request.user)
        except Food.DoesNotExist:
            return error_response(
                '음식 삭제에 실패했습니다.',
                {'food_id': ['삭제 가능한 내 음식이 아닙니다.']},
                status.HTTP_404_NOT_FOUND,
            )

        food.delete()
        return success_response('음식이 삭제되었습니다.', None)


class MealListCreateView(CommonResponseAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        meals = Meal.objects.filter(user=request.user)

        date = request.query_params.get('date')
        if date:
            meals = meals.filter(intake_date=date)

        start_date = request.query_params.get('start_date')
        if start_date:
            meals = meals.filter(intake_date__gte=start_date)

        end_date = request.query_params.get('end_date')
        if end_date:
            meals = meals.filter(intake_date__lte=end_date)

        meal_type = request.query_params.get('meal_type')
        if meal_type:
            meals = meals.filter(meal_type=meal_type)

        serializer = MealSerializer(meals.order_by('-intake_date', '-id'), many=True)
        return success_response('식단 기록 목록 조회 성공', serializer.data)

    def post(self, request):
        serializer = MealSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return error_response('식단 기록 등록에 실패했습니다.', serializer.errors)

        try:
            meal = serializer.save(user=request.user)
        except ValidationError as exc:
            return error_response('식단 기록 등록에 실패했습니다.', exc.detail)

        return success_response('식단 기록이 등록되었습니다.', MealSerializer(meal).data, status.HTTP_201_CREATED)


class MealDashboardView(CommonResponseAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        target_date = self.get_target_date(request)
        if target_date is None:
            return error_response(
                '식단 대시보드 조회에 실패했습니다.',
                {'date': ['날짜 형식은 YYYY-MM-DD이어야 합니다.']},
            )

        meals = Meal.objects.filter(user=request.user, intake_date=target_date)
        totals = self.get_totals(meals)
        calorie_target = self.get_calorie_target(request.user, totals['total_calories'])

        data = {
            'date': target_date,
            **totals,
            **calorie_target,
            'meal_type_summary': self.get_meal_type_summary(meals),
        }
        return success_response('식단 대시보드 조회 성공', data)

    def get_target_date(self, request):
        date_text = request.query_params.get('date')
        if not date_text:
            return timezone.localdate()
        return parse_date(date_text)

    def get_totals(self, meals):
        return {
            'total_calories': round(sum(meal.total_calories for meal in meals), 2),
            'total_carbohydrate': round(sum(meal.total_carbohydrate for meal in meals), 2),
            'total_protein': round(sum(meal.total_protein for meal in meals), 2),
            'total_fat': round(sum(meal.total_fat for meal in meals), 2),
        }

    def get_calorie_target(self, user, total_calories):
        if not hasattr(user, 'profile'):
            return {
                'recommended_calories': None,
                'carbohydrate_ratio': None,
                'protein_ratio': None,
                'fat_ratio': None,
                'recommended_carbohydrate': None,
                'recommended_protein': None,
                'recommended_fat': None,
                'remaining_calories': None,
            }

        recommended_calories = calculate_recommended_calories(user.profile)
        carbohydrate_ratio = 50
        protein_ratio = 30
        fat_ratio = 20

        return {
            'recommended_calories': recommended_calories,
            'carbohydrate_ratio': carbohydrate_ratio,
            'protein_ratio': protein_ratio,
            'fat_ratio': fat_ratio,
            'recommended_carbohydrate': round(recommended_calories * carbohydrate_ratio / 100 / 4, 1),
            'recommended_protein': round(recommended_calories * protein_ratio / 100 / 4, 1),
            'recommended_fat': round(recommended_calories * fat_ratio / 100 / 9, 1),
            'remaining_calories': round(recommended_calories - total_calories, 2),
        }

    def get_meal_type_summary(self, meals):
        summary = {
            'breakfast': self.empty_meal_type_summary(),
            'lunch': self.empty_meal_type_summary(),
            'dinner': self.empty_meal_type_summary(),
            'snack': self.empty_meal_type_summary(),
        }

        for meal in meals:
            if meal.meal_type not in summary:
                summary[meal.meal_type] = self.empty_meal_type_summary()
            summary[meal.meal_type]['total_calories'] += meal.total_calories
            summary[meal.meal_type]['total_carbohydrate'] += meal.total_carbohydrate
            summary[meal.meal_type]['total_protein'] += meal.total_protein
            summary[meal.meal_type]['total_fat'] += meal.total_fat
            summary[meal.meal_type]['meal_count'] += 1

        for values in summary.values():
            for key in ['total_calories', 'total_carbohydrate', 'total_protein', 'total_fat']:
                values[key] = round(values[key], 2)

        return summary

    def empty_meal_type_summary(self):
        return {
            'total_calories': 0,
            'total_carbohydrate': 0,
            'total_protein': 0,
            'total_fat': 0,
            'meal_count': 0,
        }


class MealDetailView(CommonResponseAPIView):
    permission_classes = [IsAuthenticated]

    def get_meal(self, request, meal_id, message):
        try:
            return Meal.objects.get(id=meal_id, user=request.user)
        except Meal.DoesNotExist:
            return error_response(
                message,
                {'meal_id': ['조회 가능한 식단 기록이 아닙니다.']},
                status.HTTP_404_NOT_FOUND,
            )

    def get(self, request, meal_id):
        meal = self.get_meal(request, meal_id, '식단 기록 상세 조회에 실패했습니다.')
        if not isinstance(meal, Meal):
            return meal

        return success_response('식단 기록 상세 조회 성공', MealSerializer(meal).data)

    def patch(self, request, meal_id):
        meal = self.get_meal(request, meal_id, '식단 기록 수정에 실패했습니다.')
        if not isinstance(meal, Meal):
            return meal

        serializer = MealSerializer(meal, data=request.data, partial=True, context={'request': request})
        if not serializer.is_valid():
            return error_response('식단 기록 수정에 실패했습니다.', serializer.errors)

        try:
            meal = serializer.save()
        except ValidationError as exc:
            return error_response('식단 기록 수정에 실패했습니다.', exc.detail)

        return success_response('식단 기록이 수정되었습니다.', MealSerializer(meal).data)

    def delete(self, request, meal_id):
        meal = self.get_meal(request, meal_id, '식단 기록 삭제에 실패했습니다.')
        if not isinstance(meal, Meal):
            return meal

        meal.delete()
        return success_response('식단 기록이 삭제되었습니다.', None)


class SavedMealListCreateView(CommonResponseAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        saved_meals = SavedMeal.objects.filter(user=request.user).prefetch_related('items__food')
        serializer = SavedMealSerializer(saved_meals.order_by('-id'), many=True)
        return success_response('저장 식단 목록 조회 성공', serializer.data)

    def post(self, request):
        serializer = SavedMealSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return error_response('저장 식단 등록에 실패했습니다.', serializer.errors)

        try:
            saved_meal = serializer.save(user=request.user)
        except ValidationError as exc:
            return error_response('저장 식단 등록에 실패했습니다.', exc.detail)

        data = SavedMealSerializer(saved_meal).data
        return success_response('저장 식단이 등록되었습니다.', data, status.HTTP_201_CREATED)


class SavedMealDetailView(CommonResponseAPIView):
    permission_classes = [IsAuthenticated]

    def get_saved_meal(self, request, saved_meal_id, message):
        try:
            return SavedMeal.objects.prefetch_related('items__food').get(
                id=saved_meal_id,
                user=request.user,
            )
        except SavedMeal.DoesNotExist:
            return error_response(
                message,
                {'saved_meal_id': ['조회 가능한 저장 식단이 아닙니다.']},
                status.HTTP_404_NOT_FOUND,
            )

    def get(self, request, saved_meal_id):
        saved_meal = self.get_saved_meal(request, saved_meal_id, '저장 식단 상세 조회에 실패했습니다.')
        if not isinstance(saved_meal, SavedMeal):
            return saved_meal

        return success_response('저장 식단 상세 조회 성공', SavedMealSerializer(saved_meal).data)

    def patch(self, request, saved_meal_id):
        saved_meal = self.get_saved_meal(request, saved_meal_id, '저장 식단 수정에 실패했습니다.')
        if not isinstance(saved_meal, SavedMeal):
            return saved_meal

        serializer = SavedMealSerializer(
            saved_meal,
            data=request.data,
            partial=True,
            context={'request': request},
        )
        if not serializer.is_valid():
            return error_response('저장 식단 수정에 실패했습니다.', serializer.errors)

        try:
            saved_meal = serializer.save()
        except ValidationError as exc:
            return error_response('저장 식단 수정에 실패했습니다.', exc.detail)

        return success_response('저장 식단이 수정되었습니다.', SavedMealSerializer(saved_meal).data)

    def delete(self, request, saved_meal_id):
        saved_meal = self.get_saved_meal(request, saved_meal_id, '저장 식단 삭제에 실패했습니다.')
        if not isinstance(saved_meal, SavedMeal):
            return saved_meal

        saved_meal.delete()
        return success_response('저장 식단이 삭제되었습니다.', None)


class SavedMealCreateMealView(CommonResponseAPIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, saved_meal_id):
        try:
            saved_meal = SavedMeal.objects.prefetch_related('items').get(
                id=saved_meal_id,
                user=request.user,
            )
        except SavedMeal.DoesNotExist:
            return error_response(
                '식단 기록 생성에 실패했습니다.',
                {'saved_meal_id': ['조회 가능한 저장 식단이 아닙니다.']},
                status.HTTP_404_NOT_FOUND,
            )

        request_serializer = SavedMealCreateMealSerializer(data=request.data)
        if not request_serializer.is_valid():
            return error_response('식단 기록 생성에 실패했습니다.', request_serializer.errors)

        with transaction.atomic():
            meal = Meal.objects.create(user=request.user, **request_serializer.validated_data)
            for item in saved_meal.items.select_related('food', 'food_snapshot'):
                MealItem.objects.create(
                    meal=meal,
                    food=item.food,
                    food_snapshot=item.food_snapshot,
                    amount=item.amount,
                    calories=item.calories,
                    carbohydrate=item.carbohydrate,
                    protein=item.protein,
                    fat=item.fat,
                )
            meal.recalculate_totals()

        return success_response(
            '저장 식단으로 식단 기록을 생성했습니다.',
            MealSerializer(meal).data,
            status.HTTP_201_CREATED,
        )
