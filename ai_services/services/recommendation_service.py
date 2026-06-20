from copy import deepcopy
from datetime import date
import re

from django.db.models import Q

from accounts.views import calculate_recommended_calories
from diets.models import Food, Meal
from workouts.models import Exercise

from ai_services.models import AIRecommendation, DietFeedback
from ai_services.serializers import (
    CandidateDietAIResultSerializer,
    CandidateDietItemAIResultSerializer,
    CandidateDietPlanAIResultSerializer,
    ConditionAIResultSerializer,
    DietEvaluationAIResultSerializer,
    FreeDietAIResultSerializer,
    FreeDietItemAIResultSerializer,
    FreeDietPlanAIResultSerializer,
    WorkoutAIResultSerializer,
)

from .gms_client import GMSClient, GMSResponseError
from .prompt_builder import (
    build_diet_condition_prompt,
    build_diet_evaluation_prompt,
    build_diet_recommendation_prompt,
    build_diet_replacement_prompt,
    build_workout_condition_prompt,
    build_workout_recommendation_prompt,
)


class AIServiceError(Exception):
    def __init__(self, message, errors, status_code=400):
        super().__init__(message)
        self.message = message
        self.errors = errors
        self.status_code = status_code


def json_safe(value):
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    return value


def profile_context(user):
    profile = getattr(user, 'profile', None)
    if profile is None:
        return None
    return {
        'gender': profile.gender,
        'age': profile.age,
        'height': profile.height,
        'weight': profile.weight,
        'body_type': profile.body_type,
        'activity_level': profile.activity_level,
        'workout_goal': profile.workout_goal,
        'workout_experience': profile.workout_experience,
    }


def calorie_targets(profile):
    if profile is None:
        return {
            'target_calories': None,
            'target_carbohydrate': None,
            'target_protein': None,
            'target_fat': None,
        }

    calories = calculate_recommended_calories(profile)
    return {
        'target_calories': calories,
        'target_carbohydrate': round(calories * 0.5 / 4, 1),
        'target_protein': round(calories * 0.3 / 4, 1),
        'target_fat': round(calories * 0.2 / 9, 1),
    }


def meal_totals(meals):
    return {
        'total_calories': round(sum(meal.total_calories for meal in meals), 2),
        'total_carbohydrate': round(sum(meal.total_carbohydrate for meal in meals), 2),
        'total_protein': round(sum(meal.total_protein for meal in meals), 2),
        'total_fat': round(sum(meal.total_fat for meal in meals), 2),
    }


def remaining_nutrition(targets, totals):
    pairs = {
        'remaining_calories': ('target_calories', 'total_calories'),
        'remaining_carbohydrate': ('target_carbohydrate', 'total_carbohydrate'),
        'remaining_protein': ('target_protein', 'total_protein'),
        'remaining_fat': ('target_fat', 'total_fat'),
    }
    return {
        output: (
            round(targets[target] - totals[total], 2)
            if targets[target] is not None
            else None
        )
        for output, (target, total) in pairs.items()
    }


def validate_ai_result(serializer_class, data):
    serializer = serializer_class(data=data)
    if not serializer.is_valid():
        raise AIServiceError(
            'AI response validation failed.',
            {
                'ai': ['GMS returned data in an unexpected format.'],
                'validation': json_safe(serializer.errors),
            },
            502,
        )
    return serializer.validated_data


def generate_stage_json(client, prompt, stage):
    try:
        return client.generate_json(prompt)
    except GMSResponseError as exc:
        raise GMSResponseError(f'{stage}: {exc}') from exc


def candidate_limit(conditions):
    raw_limit = conditions.get('max_candidates', 60)
    try:
        return max(30, min(int(raw_limit), 80))
    except (TypeError, ValueError):
        return 60


def visible_foods(user, source):
    if source == 'my_fridge':
        return Food.objects.filter(user=user)
    return Food.objects.filter(Q(user__isnull=True) | Q(user=user))


def visible_exercises(user, source):
    if source == 'my_exercises':
        return Exercise.objects.filter(user=user)
    return Exercise.objects.filter(Q(user__isnull=True) | Q(user=user))


def evaluate_diet(user, target_date):
    profile = getattr(user, 'profile', None)
    if profile is None:
        raise AIServiceError(
            'AI 식단 평가에 실패했습니다.',
            {'profile': ['프로필을 먼저 등록해주세요.']},
            400,
        )

    meals = list(
        Meal.objects.filter(user=user, intake_date=target_date)
        .prefetch_related('items__food', 'items__food_snapshot')
        .order_by('id')
    )
    if not meals:
        raise AIServiceError(
            'AI 식단 평가에 실패했습니다.',
            {'meals': ['해당 날짜의 식단 기록이 필요합니다.']},
            400,
        )

    targets = calorie_targets(profile)
    totals = meal_totals(meals)
    result_data = {**targets, **totals}
    context = {
        'target_date': target_date.isoformat(),
        'profile': profile_context(user),
        **result_data,
        'meals': [
            {
                'meal_type': meal.meal_type,
                'items': [
                    {
                        'food_name': item.food_name,
                        'amount': item.amount,
                        'calories': item.calories,
                        'carbohydrate': item.carbohydrate,
                        'protein': item.protein,
                        'fat': item.fat,
                    }
                    for item in meal.items.all()
                ],
            }
            for meal in meals
        ],
    }
    ai_result = generate_stage_json(
        GMSClient(),
        build_diet_evaluation_prompt(context),
        'diet_evaluation',
    )
    validated = validate_ai_result(DietEvaluationAIResultSerializer, ai_result)
    result_data['recommended_actions'] = validated['recommended_actions']
    return DietFeedback.objects.create(
        user=user,
        target_date=target_date,
        result_data=result_data,
        score=validated['score'],
        summary=validated['feedback'],
        good_points=validated['strengths'],
        improvement_points=validated['improvements'],
        recommendation=' '.join(validated['recommended_actions']),
    )


MEAL_CALORIE_RATIOS = {
    1: [100],
    2: [45, 55],
    3: [30, 40, 30],
    4: [25, 35, 30, 10],
    5: [20, 25, 10, 25, 20],
    6: [18, 22, 10, 22, 18, 10],
}


def recommend_diet(
    user,
    request_data,
    parent_recommendation=None,
    stored_scope=None,
    original_scope=None,
):
    request_data = json_safe(request_data)
    profile = getattr(user, 'profile', None)
    profile_data = profile_context(user)
    target_date = request_data['target_date']
    meals = list(Meal.objects.filter(user=user, intake_date=target_date))
    targets = calorie_targets(profile)
    totals = meal_totals(meals)
    scope = request_data.get('scope', 'meal')
    if scope in {'day', 'remaining'} and profile is None:
        raise AIServiceError(
            'AI 식단 추천에 실패했습니다.',
            {'profile': ['하루 목표 계산을 위해 프로필을 먼저 등록해주세요.']},
        )

    remaining = remaining_nutrition(targets, totals)
    if scope == 'remaining' and (
        remaining['remaining_calories'] is None or remaining['remaining_calories'] <= 150
    ):
        raise AIServiceError(
            '남은 권장 섭취량이 너무 적어 현실적인 식사를 추천하기 어렵습니다.',
            {'remaining_calories': [remaining['remaining_calories']]},
        )

    meal_specs = build_meal_specs(request_data, targets, remaining)
    context = {
        'request': request_data,
        'profile': profile_data,
        'targets': targets,
        'current_intake': totals,
        'remaining': remaining,
        'meal_specs': meal_specs,
    }

    client = GMSClient()
    condition_result = generate_stage_json(
        client,
        build_diet_condition_prompt(request_data, profile_data),
        'diet_condition_analysis',
    )
    condition = validate_ai_result(ConditionAIResultSerializer, condition_result)
    condition.pop('scope', None)
    condition.pop('meal_count', None)
    context['condition'] = condition
    source = request_data['food_source']

    if source == 'free':
        validated = generate_validated_diet_plan(
            client,
            context,
            meal_specs,
            free=True,
        )
        result = build_free_diet_result(validated, meal_specs, source, scope, targets, totals, remaining)
    else:
        foods = select_food_candidates(
            user,
            source,
            condition['conditions'],
            request_data.get('exclude_food_ids', []),
        )
        if not foods:
            raise AIServiceError(
                'AI 식단 추천에 실패했습니다.',
                {'foods': ['추천에 사용할 수 있는 음식이 없습니다.']},
                400,
            )
        candidates = [food_candidate(food) for food in foods]
        validated = generate_validated_diet_plan(
            client,
            context,
            meal_specs,
            candidates=candidates,
        )
        result = build_validated_diet_plan(
            validated, foods, source, scope, meal_specs, targets, totals, remaining
        )

    if original_scope:
        result['original_scope'] = original_scope

    recommendation = AIRecommendation.objects.create(
        user=user,
        recommendation_type=AIRecommendation.DIET,
        input_data={**request_data, 'condition': condition},
        result_data=result,
        source=source,
        recommendation_scope=stored_scope or scope,
        food_source=source,
        target_date=request_data['target_date'],
        parent_recommendation=parent_recommendation,
        content=result,
    )
    return {'recommendation_id': recommendation.id, **result}


def build_meal_specs(request_data, targets, remaining):
    scope = request_data.get('scope', 'meal')
    if scope == 'day':
        count = request_data.get('meal_count', 3)
        ratios = MEAL_CALORIE_RATIOS[count]
        target_calories = targets['target_calories']
        return [
            {
                'meal_order': index,
                'meal_label': f'{index}번째 식사',
                'target_calories': round(target_calories * ratio / 100, 2),
            }
            for index, ratio in enumerate(ratios, start=1)
        ]

    target = remaining['remaining_calories'] if scope == 'remaining' else (
        round(targets['target_calories'] * 0.3, 2)
        if targets['target_calories'] is not None
        else None
    )
    return [{
        'meal_order': request_data.get('meal_order', 1),
        'meal_label': request_data.get('meal_label') or f"{request_data.get('meal_order', 1)}번째 식사",
        'target_calories': target,
    }]


def normalize_legacy_plan_response(ai_result, meal_specs):
    if 'meals' in ai_result or 'items' not in ai_result:
        return ai_result
    spec = meal_specs[0]
    return {
        'title': ai_result.get('title', 'AI 추천 식단'),
        'summary': ai_result.get('summary', ''),
        'meals': [{
            'meal_order': spec['meal_order'],
            'meal_label': spec['meal_label'],
            'items': ai_result['items'],
        }],
    }


def generate_validated_diet_plan(client, context, meal_specs, candidates=None, free=False):
    serializer_class = FreeDietPlanAIResultSerializer if free else CandidateDietPlanAIResultSerializer
    correction = None
    last_error = None
    for attempt in range(2):
        ai_result = generate_stage_json(
            client,
            build_diet_recommendation_prompt(
                context,
                candidates=candidates,
                free=free,
                correction=correction,
            ),
            'diet_recommendation_generation' if attempt == 0 else 'diet_recommendation_retry',
        )
        ai_result = normalize_legacy_plan_response(ai_result, meal_specs)
        if free:
            ai_result = normalize_free_plan_response(ai_result, meal_specs)
        try:
            validated = validate_ai_result(serializer_class, ai_result)
            validate_meal_shape(validated['meals'], meal_specs)
            return validated
        except AIServiceError as exc:
            last_error = exc
            if attempt == 0:
                expected_orders = [spec['meal_order'] for spec in meal_specs]
                correction = (
                    f'이전 응답이 요청 스키마와 달랐습니다. 반드시 meals를 {len(meal_specs)}개 반환하고 '
                    f'meal_order는 {expected_orders}를 사용하세요. 오류: {json_safe(exc.errors)}'
                )
                continue
            raise
    raise last_error


def normalize_free_plan_response(ai_result, meal_specs):
    result = dict(ai_result)
    meals = result.get('meals') or result.get('daily_meals') or result.get('meal_plan')
    if isinstance(meals, dict):
        meals = meals.get('meals') or list(meals.values())
    if not isinstance(meals, list):
        return result

    normalized_meals = []
    for meal_index, meal in enumerate(meals):
        if not isinstance(meal, dict):
            normalized_meals.append(meal)
            continue
        spec = meal_specs[meal_index] if meal_index < len(meal_specs) else None
        items = meal.get('items') or meal.get('foods') or meal.get('menu') or []
        normalized_items = []
        for item_index, item in enumerate(items):
            if not isinstance(item, dict):
                normalized_items.append(item)
                continue
            name = item.get('name') or item.get('food_name')
            nutrition = (
                item.get('nutrition_per_100g')
                or item.get('nutrients_per_100g')
                or item.get('nutrition')
                or {}
            )
            normalized_nutrition = {
                'calories': first_numeric(nutrition, ['calories', 'calorie', 'kcal', 'energy']),
                'carbohydrate': first_numeric(
                    nutrition,
                    ['carbohydrate', 'carbohydrates', 'carbs', 'carb'],
                ),
                'protein': first_numeric(nutrition, ['protein', 'proteins']),
                'fat': first_numeric(nutrition, ['fat', 'fats']),
            }
            normalized_items.append({
                'food_id': None,
                'ai_food_key': item.get('ai_food_key') or (
                    f'free_{spec["meal_order"] if spec else meal_index + 1}_{item_index + 1}'
                ),
                'name': name,
                'amount': parse_numeric(item.get('amount')),
                'role': item.get('role') or food_meal_role(name or ''),
                'nutrition_per_100g': normalized_nutrition,
            })
        normalized_meals.append({
            'meal_order': spec['meal_order'] if spec else meal.get('meal_order'),
            'meal_label': spec['meal_label'] if spec else meal.get('meal_label'),
            'items': normalized_items,
        })

    result['title'] = result.get('title') or 'AI 추천 식단'
    result['summary'] = result.get('summary') or result.get('description') or '요청 조건을 반영한 식단입니다.'
    result['meals'] = normalized_meals
    return result


def first_numeric(data, keys):
    if not isinstance(data, dict):
        return None
    for key in keys:
        if key in data:
            return parse_numeric(data[key])
    return None


def parse_numeric(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    if isinstance(value, str):
        match = re.search(r'-?\d+(?:\.\d+)?', value.replace(',', ''))
        if match:
            return float(match.group())
    return None


def validate_meal_shape(meals, meal_specs):
    expected = {item['meal_order']: item for item in meal_specs}
    if len(meals) != len(meal_specs) or {meal['meal_order'] for meal in meals} != set(expected):
        raise AIServiceError(
            'AI response validation failed.',
            {'meals': ['GMS가 요청한 식사 수 또는 meal_order를 지키지 않았습니다.']},
            502,
        )
    return expected


def meal_nutrition(items):
    return {
        'total_calories': round(sum(item['calories'] for item in items), 2),
        'total_carbohydrate': round(sum(item['carbohydrate'] for item in items), 2),
        'total_protein': round(sum(item['protein'] for item in items), 2),
        'total_fat': round(sum(item['fat'] for item in items), 2),
    }


def finish_diet_result(title, summary, meals, source, scope, targets, totals, remaining):
    daily_totals = meal_nutrition([{
        'calories': meal['total_calories'],
        'carbohydrate': meal['total_carbohydrate'],
        'protein': meal['total_protein'],
        'fat': meal['total_fat'],
    } for meal in meals])
    first = meals[0]
    result = {
        'type': AIRecommendation.DIET,
        'scope': scope,
        'food_source': source,
        'save_available': True,
        'title': title,
        'summary': summary,
        'meals': sorted(meals, key=lambda item: item['meal_order']),
        'daily_target': targets,
        'daily_totals': daily_totals,
        'items': first['items'],
        **meal_nutrition(first['items']),
        'actions': [
            {'type': 'save', 'label': '추천 식단 저장'},
        ],
    }
    if scope == 'remaining':
        result['already_eaten'] = {
            key.removeprefix('total_'): value for key, value in totals.items()
        }
        result['remaining_target'] = {
            key.removeprefix('remaining_'): value for key, value in remaining.items()
        }
        result['meal'] = first
    return result


def build_validated_diet_plan(validated, candidate_foods, source, scope, meal_specs, targets, totals, remaining):
    specs = validate_meal_shape(validated['meals'], meal_specs)
    food_map = {food.id: food for food in candidate_foods}
    meals = []
    for meal in validated['meals']:
        requested_ids = [item['food_id'] for item in meal['items']]
        if len(requested_ids) != len(set(requested_ids)) or not set(requested_ids).issubset(food_map):
            raise invalid_candidate_error('food_id')
        items = []
        for item in meal['items']:
            food = food_map[item['food_id']]
            amount = item['amount']
            items.append({
                'food_id': food.id,
                'ai_food_key': None,
                'name': food.name,
                'food_name': food.name,
                'amount': amount,
                'role': item.get('role') or food_meal_role(food.name, food.category),
                'calories': nutrient_for_amount(food.calories, amount),
                'carbohydrate': nutrient_for_amount(food.carbohydrate, amount),
                'protein': nutrient_for_amount(food.protein, amount),
                'fat': nutrient_for_amount(food.fat, amount),
            })
        meals.append({
            'meal_order': meal['meal_order'],
            'meal_label': specs[meal['meal_order']]['meal_label'],
            'target_calories': specs[meal['meal_order']]['target_calories'],
            'items': items,
            **meal_nutrition(items),
        })
    return finish_diet_result(validated['title'], validated['summary'], meals, source, scope, targets, totals, remaining)


def build_free_diet_result(validated, meal_specs, source, scope, targets, totals, remaining):
    specs = validate_meal_shape(validated['meals'], meal_specs)
    seen_keys = set()
    meals = []
    for meal in validated['meals']:
        items = []
        for item in meal['items']:
            key = item['ai_food_key']
            if key in seen_keys:
                raise AIServiceError('AI response validation failed.', {'ai_food_key': ['값은 고유해야 합니다.']}, 502)
            seen_keys.add(key)
            nutrition = item['nutrition_per_100g']
            amount = item['amount']
            items.append({
                'food_id': None,
                'ai_food_key': key,
                'name': item['name'],
                'food_name': item['name'],
                'amount': amount,
                'role': item['role'],
                'nutrition_per_100g': nutrition,
                'calories': nutrient_for_amount(nutrition['calories'], amount),
                'carbohydrate': nutrient_for_amount(nutrition['carbohydrate'], amount),
                'protein': nutrient_for_amount(nutrition['protein'], amount),
                'fat': nutrient_for_amount(nutrition['fat'], amount),
            })
        meals.append({
            'meal_order': meal['meal_order'],
            'meal_label': specs[meal['meal_order']]['meal_label'],
            'target_calories': specs[meal['meal_order']]['target_calories'],
            'items': items,
            **meal_nutrition(items),
        })
    return finish_diet_result(validated['title'], validated['summary'], meals, source, scope, targets, totals, remaining)


def select_food_candidates(user, source, conditions, excluded_ids):
    foods = visible_foods(user, source).exclude(pk__in=excluded_ids)
    for keyword in safe_keywords(conditions.get('exclude_keywords')):
        foods = foods.exclude(name__icontains=keyword)

    limit = candidate_limit(conditions)
    if source == 'my_fridge':
        return list(practical_foods(foods).order_by('id')[:limit])

    practical = practical_foods(foods.filter(user__isnull=True))
    selected = []
    selected_ids = set()

    def add(queryset, count):
        for food in queryset[:count]:
            if food.id not in selected_ids:
                selected.append(food)
                selected_ids.add(food.id)

    custom_foods = practical_foods(foods.filter(user=user)).order_by('id')
    add(custom_foods, 10)

    preferred_filter = Q()
    for keyword in safe_keywords(conditions.get('preferred_keywords')):
        preferred_filter |= Q(name__icontains=keyword) | Q(category__icontains=keyword)
    if preferred_filter:
        add(practical.filter(preferred_filter).order_by('id'), 10)

    for category in CARBOHYDRATE_CATEGORIES:
        add(practical.filter(category=category).order_by('id'), 4)
    for category in PROTEIN_CATEGORIES:
        add(
            practical.filter(
                category=category,
                protein__gte=8,
                protein__lte=35,
            ).order_by('id'),
            3,
        )
    for category in VEGETABLE_CATEGORIES:
        add(practical.filter(category=category).order_by('id'), 3)
    for category in MIXED_MEAL_CATEGORIES:
        add(practical.filter(category=category).order_by('id'), 4)
    add(practical.order_by('id'), limit)
    return selected[:limit]


CARBOHYDRATE_CATEGORIES = [
    '밥류',
    '면 및 만두류',
    '죽 및 스프류',
    '감자류 및 전분류',
]

PROTEIN_CATEGORIES = [
    '구이류',
    '찜류',
    '볶음류',
    '조림류',
    '전·적 및 부침류',
]

VEGETABLE_CATEGORIES = [
    '생채·무침류',
    '채소류',
    '김치류',
    '버섯류',
    '해조류',
]

MIXED_MEAL_CATEGORIES = [
    '국 및 탕류',
    '찌개 및 전골류',
    '밥류',
    '면 및 만두류',
]

IMPRACTICAL_FOOD_KEYWORDS = [
    'dried',
    ' dry ',
    'powder',
    'seasoning',
    'sauce',
    'fish sauce',
    'salted seafood',
    'organ',
    'by-product',
    'concentrate',
    '말린것',
    '말린 것',
    '건조',
    '분말',
    '가루',
    '추출물',
    '농축액',
    '조미료',
    '생것',
    '생 것',
    '멸치',
    '뱅어포',
    '꼴뚜기',
    '건새우',
    '내장',
    '부산물',
]

IMPRACTICAL_FOOD_CATEGORIES = [
    '조미료류',
    '당류',
    '차류',
    '음료류',
]


def practical_foods(foods):
    foods = foods.exclude(category__in=IMPRACTICAL_FOOD_CATEGORIES)
    foods = foods.filter(calories__gt=5, calories__lt=500)
    foods = foods.filter(Q(protein__isnull=True) | Q(protein__lt=60))
    foods = foods.filter(Q(fat__isnull=True) | Q(fat__lt=50))
    for keyword in IMPRACTICAL_FOOD_KEYWORDS:
        foods = foods.exclude(name__icontains=keyword)
    return foods


def safe_keywords(value):
    if not isinstance(value, list):
        return []
    return [item.strip()[:50] for item in value[:10] if isinstance(item, str) and item.strip()][:10]


def food_candidate(food):
    return {
        'id': food.id,
        'name': food.name,
        'category': food.category,
        'meal_role': food_meal_role(food.name, food.category),
        'calories': food.calories,
        'carbohydrate': food.carbohydrate or 0,
        'protein': food.protein or 0,
        'fat': food.fat or 0,
    }


ROLE_KEYWORDS = {
    'carb': ['rice', 'brown rice', 'mixed grain', 'sweet potato', 'potato', 'noodle', 'bread', 'oat', '밥', '현미', '잡곡', '고구마', '감자', '면', '빵', '오트'],
    'protein': ['chicken', 'egg', 'tofu', 'beef', 'pork', 'fish', 'tuna', 'salmon', '닭', '계란', '달걀', '두부', '소고기', '돼지고기', '생선', '참치', '연어'],
    'vegetable': ['vegetable', 'namul', 'salad', 'broccoli', 'cabbage', 'kimchi', '채소', '나물', '샐러드', '브로콜리', '양배추', '김치'],
    'soup': ['soup', 'stew', 'tang', '국', '찌개', '탕', '스프'],
    'side': ['side dish', 'muchim', 'stir-fry', '반찬', '무침', '볶음'],
    'snack': ['yogurt', 'fruit', 'nuts', '요거트', '과일', '견과류'],
}


def food_meal_role(name, category=None):
    searchable = f'{name} {category or ""}'.lower()
    for role, keywords in ROLE_KEYWORDS.items():
        if any(keyword in searchable for keyword in keywords):
            return role
    category = category or ''
    if category in CARBOHYDRATE_CATEGORIES:
        return 'carb'
    if category in PROTEIN_CATEGORIES:
        return 'protein'
    if category in VEGETABLE_CATEGORIES:
        return 'vegetable'
    return 'side'


def build_validated_diet_result(validated, candidate_foods, source):
    requested_ids = [item['food_id'] for item in validated['items']]
    if len(requested_ids) != len(set(requested_ids)):
        raise invalid_candidate_error('food_id')

    food_map = {food.id: food for food in candidate_foods}
    if not set(requested_ids).issubset(food_map):
        raise invalid_candidate_error('food_id')

    items = []
    for item in validated['items']:
        food = food_map[item['food_id']]
        amount = item['amount']
        items.append({
            'food_id': food.id,
            'food_name': food.name,
            'amount': amount,
            'calories': nutrient_for_amount(food.calories, amount),
            'carbohydrate': nutrient_for_amount(food.carbohydrate, amount),
            'protein': nutrient_for_amount(food.protein, amount),
            'fat': nutrient_for_amount(food.fat, amount),
        })

    return {
        'type': AIRecommendation.DIET,
        'food_source': source,
        'save_available': True,
        'title': validated['title'],
        'summary': validated['summary'],
        'items': items,
        'total_calories': round(sum(item['calories'] for item in items), 2),
        'total_carbohydrate': round(sum(item['carbohydrate'] for item in items), 2),
        'total_protein': round(sum(item['protein'] for item in items), 2),
        'total_fat': round(sum(item['fat'] for item in items), 2),
        'actions': [
            {'type': 'save_meal', 'label': '오늘 식단으로 저장'},
            {'type': 'save_saved_meal', 'label': '저장 식단으로 저장'},
        ],
    }


def nutrient_for_amount(value, amount):
    return round((value or 0) * amount / 100, 2)


def replace_diet_item(user, recommendation, request_data):
    content = deepcopy(recommendation.content or recommendation.result_data)
    meals = content.get('meals')
    if not meals and content.get('items'):
        meals = [{
            'meal_order': 1,
            'meal_label': '1번째 식사',
            'items': content['items'],
        }]
        content['meals'] = meals

    target_meal = next(
        (meal for meal in meals or [] if meal.get('meal_order') == request_data['meal_order']),
        None,
    )
    if target_meal is None:
        raise AIServiceError('추천 음식 교체에 실패했습니다.', {'meal_order': ['해당 식사를 찾을 수 없습니다.']})

    target_index = None
    for index, item in enumerate(target_meal.get('items', [])):
        if request_data.get('replace_food_id') == item.get('food_id') or (
            request_data.get('replace_ai_food_key') == item.get('ai_food_key')
        ):
            target_index = index
            break
    if target_index is None:
        raise AIServiceError('추천 음식 교체에 실패했습니다.', {'target': ['교체할 음식을 찾을 수 없습니다.']})

    target_item = target_meal['items'][target_index]
    source = content.get('food_source') or recommendation.source
    condition_data = generate_stage_json(
        GMSClient(),
        build_diet_condition_prompt(
            {'scope': 'meal', 'message': request_data['message'], 'food_source': source},
            profile_context(user),
        ),
        'diet_replacement_condition_analysis',
    )
    condition = validate_ai_result(ConditionAIResultSerializer, condition_data)
    context = {
        'message': request_data['message'],
        'meal': target_meal,
        'target_item': target_item,
        'condition': condition,
    }
    client = GMSClient()
    if source == 'free':
        ai_result = generate_stage_json(
            client,
            build_diet_replacement_prompt(context, free=True),
            'diet_replacement_generation',
        )
        validated = validate_ai_result(FreeDietItemAIResultSerializer, ai_result.get('item', ai_result))
        nutrition = validated['nutrition_per_100g']
        amount = validated['amount']
        replacement = {
            'food_id': None,
            'ai_food_key': validated['ai_food_key'],
            'name': validated['name'],
            'food_name': validated['name'],
            'amount': amount,
            'role': validated['role'],
            'nutrition_per_100g': nutrition,
            'calories': nutrient_for_amount(nutrition['calories'], amount),
            'carbohydrate': nutrient_for_amount(nutrition['carbohydrate'], amount),
            'protein': nutrient_for_amount(nutrition['protein'], amount),
            'fat': nutrient_for_amount(nutrition['fat'], amount),
        }
    else:
        foods = select_food_candidates(user, source, condition['conditions'], [target_item.get('food_id')])
        if not foods:
            raise AIServiceError('추천 음식 교체에 실패했습니다.', {'foods': ['교체 후보가 없습니다.']})
        candidates = [food_candidate(food) for food in foods]
        ai_result = generate_stage_json(
            client,
            build_diet_replacement_prompt(context, candidates),
            'diet_replacement_generation',
        )
        validated = validate_ai_result(CandidateDietItemAIResultSerializer, ai_result.get('item', ai_result))
        food_map = {food.id: food for food in foods}
        food = food_map.get(validated['food_id'])
        if food is None:
            raise invalid_candidate_error('food_id')
        amount = validated['amount']
        replacement = {
            'food_id': food.id,
            'ai_food_key': None,
            'name': food.name,
            'food_name': food.name,
            'amount': amount,
            'role': validated.get('role') or food_meal_role(food.name, food.category),
            'calories': nutrient_for_amount(food.calories, amount),
            'carbohydrate': nutrient_for_amount(food.carbohydrate, amount),
            'protein': nutrient_for_amount(food.protein, amount),
            'fat': nutrient_for_amount(food.fat, amount),
        }

    target_meal['items'][target_index] = replacement
    target_meal.update(meal_nutrition(target_meal['items']))
    content['daily_totals'] = meal_nutrition([{
        'calories': meal.get('total_calories', meal_nutrition(meal['items'])['total_calories']),
        'carbohydrate': meal.get('total_carbohydrate', meal_nutrition(meal['items'])['total_carbohydrate']),
        'protein': meal.get('total_protein', meal_nutrition(meal['items'])['total_protein']),
        'fat': meal.get('total_fat', meal_nutrition(meal['items'])['total_fat']),
    } for meal in meals])
    first = sorted(meals, key=lambda meal: meal['meal_order'])[0]
    content['items'] = first['items']
    content.update(meal_nutrition(first['items']))
    content['scope'] = AIRecommendation.SCOPE_REPLACEMENT
    content['original_scope'] = recommendation.content.get('original_scope') or recommendation.input_data.get('scope', 'meal')

    created = AIRecommendation.objects.create(
        user=user,
        recommendation_type=AIRecommendation.DIET,
        input_data=json_safe(request_data),
        result_data=content,
        source=source,
        recommendation_scope=AIRecommendation.SCOPE_REPLACEMENT,
        food_source=source,
        target_date=recommendation.target_date,
        parent_recommendation=recommendation,
        content=content,
    )
    return {'recommendation_id': created.id, **content}


def reroll_diet(user, recommendation, message):
    original_scope = (
        (recommendation.content or {}).get('original_scope')
        or recommendation.input_data.get('scope')
        or recommendation.recommendation_scope
        or 'meal'
    )
    request_data = {
        key: value
        for key, value in recommendation.input_data.items()
        if key in {
            'scope', 'target_date', 'food_source', 'meal_count', 'meal_order',
            'meal_label', 'meal_type', 'exclude_food_ids',
        }
    }
    previous_message = recommendation.input_data.get('message', '')
    request_data.update({
        'scope': original_scope,
        'target_date': recommendation.target_date.isoformat() if recommendation.target_date else request_data.get('target_date'),
        'food_source': (recommendation.content or {}).get('food_source') or recommendation.source,
        'message': f'{previous_message}\n추가 조건: {message}'.strip(),
    })
    if original_scope == 'day':
        request_data['meal_count'] = len((recommendation.content or recommendation.result_data).get('meals', [])) or request_data.get('meal_count', 3)
    return recommend_diet(
        user,
        request_data,
        parent_recommendation=recommendation,
        stored_scope=AIRecommendation.SCOPE_REROLL,
        original_scope=original_scope,
    )


def recommend_workout(user, request_data):
    request_data = json_safe(request_data)
    profile_data = profile_context(user)
    client = GMSClient()
    condition_result = generate_stage_json(
        client,
        build_workout_condition_prompt(request_data, profile_data),
        'workout_condition_analysis',
    )
    condition = validate_ai_result(ConditionAIResultSerializer, condition_result)
    source = request_data['exercise_source']
    exercises = select_exercise_candidates(
        user,
        source,
        condition['conditions'],
        request_data.get('target_body_part'),
    )
    if not exercises:
        raise AIServiceError(
            'AI 운동 루틴 추천에 실패했습니다.',
            {'exercises': ['추천에 사용할 수 있는 운동이 없습니다.']},
            400,
        )

    candidates = [
        {
            'id': exercise.id,
            'name': exercise.name,
            'body_parts': exercise.body_parts,
            'equipments': exercise.equipments,
            'target_muscles': exercise.target_muscles,
            'secondary_muscles': exercise.secondary_muscles,
        }
        for exercise in exercises
    ]
    context = {
        'request': request_data,
        'profile': profile_data,
        'condition': condition,
    }
    ai_result = generate_stage_json(
        client,
        build_workout_recommendation_prompt(context, candidates),
        'workout_recommendation_generation',
    )
    validated = validate_ai_result(WorkoutAIResultSerializer, ai_result)
    result = build_validated_workout_result(validated, exercises, source)
    recommendation = AIRecommendation.objects.create(
        user=user,
        recommendation_type=AIRecommendation.WORKOUT,
        input_data={**request_data, 'condition': condition},
        result_data=result,
        source=source,
    )
    return {'recommendation_id': recommendation.id, **result}


BODY_PART_SEARCH_ALIASES = {
    '가슴': ['chest', 'pectorals', 'pectoral'],
    '등': ['back', 'lats', 'latissimus'],
    '어깨': ['shoulders', 'delts', 'deltoids'],
    '팔': ['upper arms', 'biceps', 'triceps'],
    '이두': ['biceps'],
    '삼두': ['triceps'],
    '복근': ['waist', 'abs', 'abdominals', 'core'],
    '하체': ['upper legs', 'lower legs', 'quads', 'hamstrings', 'glutes'],
    '허벅지': ['upper legs', 'quads', 'hamstrings'],
    '종아리': ['lower legs', 'calves'],
    '엉덩이': ['glutes'],
    '유산소': ['cardio'],
}

EQUIPMENT_SEARCH_ALIASES = {
    '맨몸': ['body weight', 'bodyweight'],
    '바벨': ['barbell'],
    '덤벨': ['dumbbell'],
    '케이블': ['cable'],
    '밴드': ['band', 'resistance band'],
    '머신': ['machine', 'leverage machine'],
}


def expand_search_keywords(keywords, aliases):
    expanded = []
    for keyword in keywords:
        if keyword not in expanded:
            expanded.append(keyword)
        normalized = keyword.casefold()
        for source, values in aliases.items():
            if normalized == source.casefold() or normalized in {item.casefold() for item in values}:
                for value in [source, *values]:
                    if value not in expanded:
                        expanded.append(value)
    return expanded


def select_exercise_candidates(user, source, conditions, target_body_part=None):
    limit = candidate_limit(conditions)
    exercises = visible_exercises(user, source)
    body_keywords = safe_keywords(conditions.get('body_part_keywords'))
    if target_body_part:
        body_keywords.append(str(target_body_part).strip()[:50])
    body_keywords = expand_search_keywords(body_keywords, BODY_PART_SEARCH_ALIASES)

    if body_keywords:
        body_filter = Q()
        for keyword in body_keywords:
            body_filter |= (
                Q(name__icontains=keyword)
                | Q(body_parts__icontains=keyword)
                | Q(target_muscles__icontains=keyword)
                | Q(secondary_muscles__icontains=keyword)
            )
        exercises = exercises.filter(body_filter)

    equipment_keywords = safe_keywords(conditions.get('equipment_keywords'))
    equipment_keywords = expand_search_keywords(equipment_keywords, EQUIPMENT_SEARCH_ALIASES)
    if equipment_keywords:
        equipment_filter = Q()
        for keyword in equipment_keywords:
            equipment_filter |= Q(equipments__icontains=keyword)
        exercises = exercises.filter(equipment_filter)

    return list(exercises.order_by('id')[:limit])


def build_validated_workout_result(validated, candidate_exercises, source):
    requested_ids = [item['exercise_id'] for item in validated['items']]
    if len(requested_ids) != len(set(requested_ids)):
        raise invalid_candidate_error('exercise_id')

    exercise_map = {exercise.id: exercise for exercise in candidate_exercises}
    if not set(requested_ids).issubset(exercise_map):
        raise invalid_candidate_error('exercise_id')

    items = [
        {
            'exercise_id': item['exercise_id'],
            'exercise_name': exercise_map[item['exercise_id']].name,
            'order': item['order'],
            'sets': item['sets'],
            'reps': item['reps'],
            'weight': item['weight'],
            'rest_seconds': item['rest_seconds'],
        }
        for item in validated['items']
    ]
    return {
        'type': AIRecommendation.WORKOUT,
        'exercise_source': source,
        'save_available': True,
        'title': validated['title'],
        'description': validated['description'],
        'items': sorted(items, key=lambda item: (item['order'], item['exercise_id'])),
        'actions': [{'type': 'save_routine', 'label': '내 루틴에 저장'}],
    }


def invalid_candidate_error(field):
    return AIServiceError(
        'AI response validation failed.',
        {field: ['GMS returned an unavailable candidate id.']},
        502,
    )
