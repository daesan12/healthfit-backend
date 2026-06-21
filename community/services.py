from django.db.models import Q

from diets.models import Food, FoodSnapshot, SavedMeal, SavedMealItem
from workouts.models import Exercise, RoutineItem, WorkoutRoutine


class SharedSnapshotError(Exception):
    def __init__(self, errors):
        self.errors = errors
        super().__init__('Shared item snapshot is invalid.')


def build_saved_meal_snapshot(saved_meal):
    items = []
    for item in saved_meal.items.select_related('food', 'food_snapshot').all():
        nutrition = item.nutrition
        items.append({
            'food_id': item.food_id,
            'food_name': item.food_name,
            'ai_food_key': item.food_snapshot.ai_food_key if item.food_snapshot_id else None,
            'amount': item.amount,
            'calories': item.calories,
            'carbohydrate': item.carbohydrate,
            'protein': item.protein,
            'fat': item.fat,
            'nutrition_per_100g': {
                'calories': nutrition.get('calories') or 0,
                'carbohydrate': nutrition.get('carbohydrate') or 0,
                'protein': nutrition.get('protein') or 0,
                'fat': nutrition.get('fat') or 0,
            },
            'source_type': (
                item.food_snapshot.source_type
                if item.food_snapshot_id
                else FoodSnapshot.SOURCE_DB
            ),
        })

    return {
        'id': saved_meal.id,
        'name': saved_meal.name,
        'description': saved_meal.description,
        'total_calories': saved_meal.total_calories,
        'total_carbohydrate': saved_meal.total_carbohydrate,
        'total_protein': saved_meal.total_protein,
        'total_fat': saved_meal.total_fat,
        'items': items,
    }


def build_workout_routine_snapshot(routine):
    items = [
        {
            'exercise_id': item.exercise_id,
            'exercise_name': item.exercise.name,
            'order': item.order,
            'sets': item.sets,
            'reps': item.reps,
            'weight': item.weight,
            'rest_seconds': item.rest_seconds,
        }
        for item in routine.items.select_related('exercise').all()
    ]
    return {
        'id': routine.id,
        'name': routine.name,
        'description': routine.description,
        'exercise_count': len(items),
        'items': items,
    }


def copy_saved_meal_from_snapshot(snapshot, user):
    if not isinstance(snapshot, dict) or not snapshot.get('name'):
        raise SharedSnapshotError({'snapshot': ['공유 식단 snapshot 형식이 올바르지 않습니다.']})
    items = snapshot.get('items')
    if not isinstance(items, list) or not items:
        raise SharedSnapshotError({'snapshot': ['공유 식단 항목이 없습니다.']})

    normalized_items = [_normalize_saved_meal_item(item) for item in items]
    saved_meal = SavedMeal.objects.create(
        user=user,
        name=snapshot['name'],
        description=snapshot.get('description') or '',
    )
    for item in normalized_items:
        food = None
        if item['food_id']:
            food = Food.objects.filter(pk=item['food_id']).filter(
                Q(user__isnull=True) | Q(user=user)
            ).first()

        if food is not None:
            SavedMealItem.objects.create(
                saved_meal=saved_meal,
                food=food,
                amount=item['amount'],
            )
            continue

        food_snapshot = FoodSnapshot.objects.create(
            name=item['food_name'],
            ai_food_key=item['ai_food_key'] or '',
            source_type=item['source_type'],
            nutrition_per_100g=item['nutrition_per_100g'],
        )
        SavedMealItem.objects.create(
            saved_meal=saved_meal,
            food_snapshot=food_snapshot,
            amount=item['amount'],
        )

    saved_meal.recalculate_totals()
    return saved_meal


def _normalize_saved_meal_item(item):
    if not isinstance(item, dict):
        raise SharedSnapshotError({'snapshot': ['공유 식단 항목 형식이 올바르지 않습니다.']})
    try:
        amount = float(item['amount'])
        if amount <= 0:
            raise ValueError
        nutrition = item.get('nutrition_per_100g') or {
            key: round(float(item.get(key) or 0) * 100 / amount, 4)
            for key in ['calories', 'carbohydrate', 'protein', 'fat']
        }
        nutrition = {
            key: max(float(nutrition.get(key) or 0), 0)
            for key in ['calories', 'carbohydrate', 'protein', 'fat']
        }
    except (KeyError, TypeError, ValueError):
        raise SharedSnapshotError({'snapshot': ['공유 식단 영양 정보가 올바르지 않습니다.']})

    source_type = item.get('source_type')
    if source_type not in dict(FoodSnapshot.SOURCE_CHOICES):
        source_type = FoodSnapshot.SOURCE_FREE if item.get('ai_food_key') else FoodSnapshot.SOURCE_DB
    return {
        'food_id': item.get('food_id'),
        'food_name': item.get('food_name') or '공유 음식',
        'ai_food_key': item.get('ai_food_key'),
        'amount': amount,
        'nutrition_per_100g': nutrition,
        'source_type': source_type,
    }


def copy_workout_routine_from_snapshot(snapshot, user):
    if not isinstance(snapshot, dict) or not snapshot.get('name'):
        raise SharedSnapshotError({'snapshot': ['공유 루틴 snapshot 형식이 올바르지 않습니다.']})
    items = snapshot.get('items')
    if not isinstance(items, list):
        raise SharedSnapshotError({'snapshot': ['공유 루틴 항목 형식이 올바르지 않습니다.']})

    normalized_items = [_normalize_routine_item(item) for item in items]
    exercise_ids = {item['exercise_id'] for item in normalized_items}
    exercises = Exercise.objects.in_bulk(exercise_ids)
    missing_ids = sorted(exercise_ids - exercises.keys())
    if missing_ids:
        raise SharedSnapshotError({
            'exercises': [f'삭제되어 복사할 수 없는 운동이 있습니다: {missing_ids}'],
        })

    routine = WorkoutRoutine.objects.create(
        user=user,
        name=snapshot['name'],
        description=snapshot.get('description') or '',
    )
    RoutineItem.objects.bulk_create([
        RoutineItem(
            routine=routine,
            exercise=exercises[item['exercise_id']],
            order=item['order'],
            sets=item['sets'],
            reps=item['reps'],
            weight=item['weight'],
            rest_seconds=item['rest_seconds'],
        )
        for item in normalized_items
    ])
    return routine


def _normalize_routine_item(item):
    if not isinstance(item, dict):
        raise SharedSnapshotError({'snapshot': ['공유 루틴 항목 형식이 올바르지 않습니다.']})
    try:
        normalized = {
            'exercise_id': int(item['exercise_id']),
            'order': int(item['order']),
            'sets': int(item['sets']),
            'reps': int(item['reps']),
            'weight': float(item.get('weight') or 0),
            'rest_seconds': int(item.get('rest_seconds') or 0),
        }
        if any(normalized[key] < 1 for key in ['exercise_id', 'order', 'sets', 'reps']):
            raise ValueError
        if normalized['weight'] < 0 or normalized['rest_seconds'] < 0:
            raise ValueError
    except (KeyError, TypeError, ValueError):
        raise SharedSnapshotError({'snapshot': ['공유 루틴 항목 값이 올바르지 않습니다.']})
    return normalized
