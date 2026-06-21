from django.db.models import Q

from workouts.models import Exercise, WorkoutLog

from ai_services.serializers import WorkoutProgressionAIResultSerializer

from .gms_client import GMSAPIError, GMSClient, GMSResponseError
from .prompt_builder import build_workout_progression_prompt
from .recommendation_service import AIServiceError, profile_context


DEFAULT_SAFETY_NOTE = '추천 중량이 너무 무겁거나 가볍게 느껴지면 중량, 반복 수, 세트 수를 직접 조절하세요.'


def recommend_workout_progression(user, request_data):
    exercise = get_visible_exercise(user, request_data['workout_id'])
    target_date = request_data['target_date']
    profile = getattr(user, 'profile', None)
    goal = request_data.get('goal') or getattr(profile, 'workout_goal', None) or 'maintenance'
    experience = getattr(profile, 'workout_experience', None)

    history = build_history_summary(user, exercise, target_date)
    recovery = build_recovery_summary(user, exercise, target_date)
    preliminary = build_preliminary_recommendation(exercise, history, recovery, goal)
    payload = {
        'user_context': {'goal': goal, 'experience': experience},
        'target_workout': {
            'workout_id': exercise.id,
            'name': exercise.name,
            'body_parts': exercise.body_parts,
            'target_muscles': exercise.target_muscles,
            'secondary_muscles': exercise.secondary_muscles,
            'equipment': exercise.equipments,
        },
        'target_date': target_date.isoformat(),
        'user_request': request_data.get('message', ''),
        'same_workout_history': history,
        'recovery_summary': recovery,
        'backend_preliminary_recommendation': preliminary,
    }

    final = gms_or_preliminary(payload, preliminary, recovery, exercise, history)
    return {
        'workout_id': exercise.id,
        'workout_name': exercise.name,
        'target_date': target_date,
        'decision': final['decision'],
        'recommendation': final['recommendation'],
        'recovery_summary': recovery,
        'history_summary': history,
        'reason': final['reason'],
        'safety_note': final['safety_note'],
    }


def get_visible_exercise(user, workout_id):
    try:
        return Exercise.objects.filter(
            Q(user__isnull=True) | Q(user=user)
        ).get(pk=workout_id)
    except Exercise.DoesNotExist as exc:
        raise AIServiceError(
            '운동 진행 추천에 실패했습니다.',
            {'workout_id': ['조회 가능한 운동이 아닙니다.']},
            404,
        ) from exc


def build_history_summary(user, exercise, target_date):
    logs = list(
        WorkoutLog.objects.filter(
            user=user,
            exercise=exercise,
            workout_date__lte=target_date,
        )
        .prefetch_related('sets')
        .order_by('-workout_date', '-id')[:5]
    )
    return [serialize_history_log(log) for log in logs]


def serialize_history_log(log):
    sets = [
        {
            'set_order': item.set_order,
            'weight_kg': item.weight_kg,
            'repetition': item.repetition,
            'duration_seconds': item.duration_seconds,
            'rpe': item.rpe,
            'is_warmup': item.is_warmup,
        }
        for item in log.sets.all()
    ]
    weighted_sets = [
        item for item in sets
        if not item['is_warmup']
        and item['weight_kg'] is not None
        and item['repetition'] is not None
    ]
    total_volume = (
        round(sum(item['weight_kg'] * item['repetition'] for item in weighted_sets), 2)
        if weighted_sets
        else None
    )
    return {
        'date': log.workout_date.isoformat(),
        'sets': sets,
        'total_volume': total_volume,
    }


def build_recovery_summary(user, exercise, target_date):
    muscles = unique_names([*exercise.target_muscles, *exercise.secondary_muscles])
    logs = list(
        WorkoutLog.objects.filter(user=user, workout_date__lt=target_date)
        .select_related('exercise')
        .order_by('-workout_date', '-id')
    )
    summary = []
    for muscle in muscles:
        normalized = muscle.casefold()
        matched = next(
            (
                log for log in logs
                if normalized in {
                    item.casefold()
                    for item in [*log.exercise.target_muscles, *log.exercise.secondary_muscles]
                    if isinstance(item, str)
                }
            ),
            None,
        )
        days_since = (target_date - matched.workout_date).days if matched else None
        summary.append({
            'muscle': muscle,
            'last_trained_date': matched.workout_date.isoformat() if matched else None,
            'days_since': days_since,
            'status': recovery_status(days_since),
        })
    return summary


def unique_names(values):
    result = []
    seen = set()
    for value in values:
        if not isinstance(value, str) or not value.strip():
            continue
        key = value.strip().casefold()
        if key not in seen:
            seen.add(key)
            result.append(value.strip())
    return result


def recovery_status(days_since):
    if days_since is None:
        return 'unknown'
    if days_since <= 1:
        return 'not_fully_recovered'
    if days_since == 2:
        return 'moderate'
    return 'recovered'


def build_preliminary_recommendation(exercise, history, recovery, goal):
    rest_seconds = rest_for_goal(goal)
    if not history or not history[0]['sets']:
        return preliminary_result(
            'insufficient_history', 3, 8, None, rest_seconds,
            '동일 운동의 세트별 기록이 없어 보수적인 시작 목표를 제안합니다.',
        )

    latest_sets = history[0]['sets']
    working_sets = [item for item in latest_sets if not item['is_warmup']] or latest_sets
    reps = [item['repetition'] for item in working_sets if item['repetition'] is not None]
    weights = [item['weight_kg'] for item in working_sets if item['weight_kg'] is not None]
    set_count = max(1, len(working_sets))
    target_reps = max(reps, default=8)
    latest_weight = weights[0] if weights else None

    if is_bodyweight_exercise(exercise, working_sets):
        next_reps = min(100, target_reps + 1)
        next_sets = min(10, set_count + 1) if target_reps >= 100 else set_count
        return preliminary_result(
            'bodyweight_progression', next_sets, next_reps, None,
            max(15, rest_seconds - 15),
            '추가 중량 기록이 없어 반복 수를 소폭 늘리는 맨몸 운동 진행 방식을 적용했습니다.',
        )

    increment = safe_weight_increment(exercise)
    min_days = min(
        (item['days_since'] for item in recovery if item['days_since'] is not None),
        default=None,
    )
    first_rep = reps[0] if reps else target_reps
    last_rep = reps[-1] if reps else target_reps
    spread = max(reps, default=target_reps) - min(reps, default=target_reps)

    if spread >= 3 or first_rep - last_rep >= 3:
        next_weight = round_to_increment(max(0, latest_weight - increment), increment)
        return preliminary_result(
            'decrease', set_count, max(1, round(sum(reps) / len(reps))) if reps else 8,
            next_weight, rest_seconds,
            '최근 작업 세트의 반복 수 하락이 커서 중량을 소폭 낮추는 편이 안전합니다.',
        )
    if min_days is not None and min_days <= 1:
        return preliminary_result(
            'maintain', set_count, target_reps, latest_weight, rest_seconds,
            '관련 근육을 1일 이내에 훈련해 중량을 올리지 않고 유지하도록 제안합니다.',
        )
    if spread <= 1 and (min_days is None or min_days >= 3):
        next_weight = round_to_increment(latest_weight + increment, increment)
        return preliminary_result(
            'increase', set_count, target_reps, next_weight, rest_seconds,
            f'최근 작업 세트 반복 수가 안정적이고 관련 근육이 회복되어 {increment}kg 이내 증가를 제안합니다.',
        )
    return preliminary_result(
        'maintain', set_count, target_reps, latest_weight, rest_seconds,
        '최근 세트에 작은 반복 수 하락 또는 중간 수준의 회복 상태가 있어 현재 중량을 유지합니다.',
    )


def preliminary_result(decision, set_count, repetition, weight_kg, rest_seconds, reason):
    return {
        'decision': decision,
        'set_count': set_count,
        'repetition': repetition,
        'weight_kg': weight_kg,
        'rest_seconds': rest_seconds,
        'reason': reason,
    }


def rest_for_goal(goal):
    normalized = (goal or '').casefold()
    if 'strength' in normalized or '근력' in normalized:
        return 180
    if 'muscle' in normalized or 'gain' in normalized or '근육' in normalized:
        return 120
    return 90


def is_bodyweight_exercise(exercise, working_sets):
    equipment_text = ' '.join(str(item) for item in exercise.equipments).casefold()
    bodyweight_keywords = ['body weight', 'bodyweight', '맨몸']
    return any(keyword in equipment_text for keyword in bodyweight_keywords) or not any(
        item['weight_kg'] is not None for item in working_sets
    )


def safe_weight_increment(exercise):
    equipment_text = ' '.join(str(item) for item in exercise.equipments).casefold()
    body_text = ' '.join(str(item) for item in exercise.body_parts).casefold()
    if 'dumbbell' in equipment_text or '덤벨' in equipment_text:
        return 1.0
    lower_keywords = ['leg', 'thigh', 'glute', 'lower body', '다리', '허벅지', '둔근', '하체']
    if any(keyword in body_text for keyword in lower_keywords):
        return 5.0
    return 2.5


def round_to_increment(value, increment):
    return round(round(value / increment) * increment, 2)


def gms_or_preliminary(payload, preliminary, recovery, exercise, history):
    fallback = format_preliminary(preliminary)
    try:
        ai_result = GMSClient().generate_json(
            build_workout_progression_prompt(payload),
            temperature=0.6,
        )
        serializer = WorkoutProgressionAIResultSerializer(data=ai_result)
        if not serializer.is_valid():
            return fallback
        final = serializer.validated_data
        if not is_safe_ai_progression(final, preliminary, recovery, exercise, history):
            return fallback
        return final
    except (GMSAPIError, GMSResponseError):
        return fallback


def format_preliminary(preliminary):
    return {
        'decision': preliminary['decision'],
        'recommendation': {
            'set_count': preliminary['set_count'],
            'repetition': preliminary['repetition'],
            'weight_kg': preliminary['weight_kg'],
            'rest_seconds': preliminary['rest_seconds'],
        },
        'reason': preliminary['reason'],
        'safety_note': DEFAULT_SAFETY_NOTE,
    }


def is_safe_ai_progression(final, preliminary, recovery, exercise, history):
    if any(item['days_since'] is not None and item['days_since'] <= 1 for item in recovery):
        if final['decision'] == 'increase':
            return False

    locked_decisions = {
        'maintain', 'decrease', 'deload', 'bodyweight_progression', 'insufficient_history'
    }
    if preliminary['decision'] in locked_decisions and final['decision'] != preliminary['decision']:
        return False

    recommendation = final['recommendation']
    if abs(recommendation['set_count'] - preliminary['set_count']) > 1:
        return False
    if abs(recommendation['repetition'] - preliminary['repetition']) > 2:
        return False
    if abs(recommendation['rest_seconds'] - preliminary['rest_seconds']) > 60:
        return False

    expected_weight = preliminary['weight_kg']
    final_weight = recommendation['weight_kg']
    if expected_weight is None:
        return final_weight is None
    if final_weight is None:
        return False
    increment = safe_weight_increment(exercise)
    if abs(final_weight - expected_weight) > increment:
        return False

    if final['decision'] == 'increase' and history:
        latest_weights = [
            item['weight_kg']
            for item in history[0]['sets']
            if not item['is_warmup'] and item['weight_kg'] is not None
        ]
        if latest_weights and final_weight > latest_weights[0] + increment:
            return False
    return True
