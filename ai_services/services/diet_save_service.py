from django.db import transaction
from django.db.models import Q

from diets.models import (
    Food,
    FoodSnapshot,
    Meal,
    MealItem,
    SavedMeal,
    SavedMealItem,
    SavedMealPlan,
    SavedMealPlanItem,
    SavedMealPlanMeal,
)

from .recommendation_service import AIServiceError, meal_nutrition, nutrient_for_amount


def recommendation_meals(recommendation):
    content = recommendation.content or recommendation.result_data
    meals = content.get('meals')
    if not meals and content.get('items'):
        meals = [{
            'meal_order': 1,
            'meal_label': '1번째 식사',
            'items': content['items'],
            **meal_nutrition(content['items']),
        }]
    if not isinstance(meals, list) or not meals:
        raise AIServiceError('AI 추천 식단 저장에 실패했습니다.', {'meals': ['저장할 식사가 없습니다.']})
    return content, meals


def validate_and_prepare_item(user, source, item):
    amount = item.get('amount')
    if not isinstance(amount, (int, float)) or amount <= 0:
        raise AIServiceError('AI 추천 식단 저장에 실패했습니다.', {'amount': ['올바른 섭취량이 필요합니다.']})

    if source == 'free':
        nutrition = item.get('nutrition_per_100g')
        required = {'calories', 'carbohydrate', 'protein', 'fat'}
        if not item.get('ai_food_key') or not item.get('name') or not isinstance(nutrition, dict) or not required.issubset(nutrition):
            raise AIServiceError(
                'AI 추천 식단 저장에 실패했습니다.',
                {'items': ['free 음식의 이름, ai_food_key, nutrition_per_100g가 필요합니다.']},
            )
        snapshot = FoodSnapshot.objects.create(
            name=item['name'],
            ai_food_key=item['ai_food_key'],
            source_type=FoodSnapshot.SOURCE_FREE,
            nutrition_per_100g={key: float(nutrition[key]) for key in required},
        )
        return {
            'food': None,
            'food_snapshot': snapshot,
            'amount': amount,
            **calculated_nutrition(nutrition, amount),
        }

    food_id = item.get('food_id')
    foods = Food.objects.filter(Q(user__isnull=True) | Q(user=user))
    if source == 'my_fridge':
        foods = foods.filter(user=user)
    try:
        food = foods.get(pk=food_id)
    except Food.DoesNotExist as exc:
        raise AIServiceError(
            'AI 추천 식단 저장에 실패했습니다.',
            {'food_id': [f'저장 가능한 음식이 아닙니다: {food_id}']},
        ) from exc
    nutrition = {
        'calories': food.calories,
        'carbohydrate': food.carbohydrate or 0,
        'protein': food.protein or 0,
        'fat': food.fat or 0,
    }
    return {
        'food': food,
        'food_snapshot': None,
        'amount': amount,
        **calculated_nutrition(nutrition, amount),
    }


def calculated_nutrition(nutrition, amount):
    return {
        key: nutrient_for_amount(nutrition.get(key), amount)
        for key in ['calories', 'carbohydrate', 'protein', 'fat']
    }


def create_meals(user, recommendation, content, meals):
    source = content.get('food_source') or recommendation.source
    created = []
    for meal_data in meals:
        meal = Meal.objects.create(
            user=user,
            meal_type=meal_data.get('meal_type') or recommendation.input_data.get('meal_type') or 'meal',
            meal_order=meal_data.get('meal_order', 1),
            meal_label=meal_data.get('meal_label', ''),
            intake_date=recommendation.target_date or recommendation.input_data.get('target_date'),
        )
        for item in meal_data['items']:
            prepared = validate_and_prepare_item(user, source, item)
            MealItem.objects.create(meal=meal, **prepared)
        meal.recalculate_totals()
        created.append(meal)
    return created


def create_saved_meal(user, recommendation, content, meal_data, title, description):
    source = content.get('food_source') or recommendation.source
    saved_meal = SavedMeal.objects.create(user=user, name=title, description=description)
    for item in meal_data['items']:
        prepared = validate_and_prepare_item(user, source, item)
        SavedMealItem.objects.create(
            saved_meal=saved_meal,
            food=prepared['food'],
            food_snapshot=prepared['food_snapshot'],
            amount=prepared['amount'],
        )
    saved_meal.recalculate_totals()
    return saved_meal


def create_meal_plan(user, recommendation, content, meals, title, description):
    targets = content.get('daily_target') or {}
    totals = content.get('daily_totals') or meal_nutrition([
        {
            'calories': meal.get('total_calories', 0),
            'carbohydrate': meal.get('total_carbohydrate', 0),
            'protein': meal.get('total_protein', 0),
            'fat': meal.get('total_fat', 0),
        }
        for meal in meals
    ])
    plan = SavedMealPlan.objects.create(
        user=user,
        title=title,
        description=description,
        target_calories=targets.get('target_calories'),
        target_carbohydrate=targets.get('target_carbohydrate'),
        target_protein=targets.get('target_protein'),
        target_fat=targets.get('target_fat'),
        total_calories=totals.get('total_calories', 0),
        total_carbohydrate=totals.get('total_carbohydrate', 0),
        total_protein=totals.get('total_protein', 0),
        total_fat=totals.get('total_fat', 0),
        source_recommendation=recommendation,
    )
    source = content.get('food_source') or recommendation.source
    for meal_data in meals:
        plan_meal = SavedMealPlanMeal.objects.create(
            plan=plan,
            meal_order=meal_data['meal_order'],
            meal_label=meal_data['meal_label'],
            target_calories=meal_data.get('target_calories'),
            **meal_nutrition(meal_data['items']),
        )
        for item in meal_data['items']:
            prepared = validate_and_prepare_item(user, source, item)
            SavedMealPlanItem.objects.create(plan_meal=plan_meal, **prepared)
    return plan


@transaction.atomic
def save_diet_recommendation(user, recommendation, validated_data):
    content, meals = recommendation_meals(recommendation)
    target = validated_data['save_target']
    title = validated_data['title']
    description = validated_data.get('description', '')
    is_day = len(meals) > 1 or content.get('original_scope') == 'day' or content.get('scope') == 'day'

    if target == 'saved_meal' and is_day:
        raise AIServiceError('AI 추천 식단 저장에 실패했습니다.', {'save_target': ['saved_meal은 한 끼 추천에서만 사용할 수 있습니다.']})
    if target == 'meal_plan' and not is_day:
        raise AIServiceError('AI 추천 식단 저장에 실패했습니다.', {'save_target': ['meal_plan은 하루 식단 추천에서 사용해주세요.']})

    result = {}
    if target in {'meals', 'both'}:
        created_meals = create_meals(user, recommendation, content, meals)
        result['meal_ids'] = [meal.id for meal in created_meals]
    if target == 'saved_meal' or (target == 'both' and not is_day):
        saved_meal = create_saved_meal(user, recommendation, content, meals[0], title, description)
        result['saved_meal_id'] = saved_meal.id
    if target == 'meal_plan' or (target == 'both' and is_day):
        plan = create_meal_plan(user, recommendation, content, meals, title, description)
        result['meal_plan_id'] = plan.id

    recommendation.is_saved = True
    recommendation.save(update_fields=['is_saved', 'updated_at'])
    return {'save_target': target, **result}
