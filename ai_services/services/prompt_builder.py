import json

from ai_services.prompts import (
    HEALTHFIT_DIET_RECOMMENDATION_PROMPT,
    HEALTHFIT_PT_COACH_TONE,
    HEALTHFIT_WORKOUT_RECOMMENDATION_PROMPT,
)


JSON_ONLY_RULES = (
    '반드시 유효한 JSON 객체 하나만 반환하세요. '
    '마크다운, ```json 코드 블록, JSON 밖의 설명 문장을 절대 포함하지 마세요. '
    '모든 사용자용 문장은 한국어로 작성하세요.'
)

CANDIDATE_ID_RULES = (
    '제공된 후보 ID만 사용하세요. '
    'Use only the provided candidate ids. '
    'Do not invent food_id or exercise_id. '
    'Do not include ids that are not in the candidate list.'
)


def dump(data):
    return json.dumps(data, ensure_ascii=False, separators=(',', ':'))


def build_diet_evaluation_prompt(context):
    return (
        f'{JSON_ONLY_RULES}\n'
        f'{HEALTHFIT_PT_COACH_TONE}\n'
        '당신은 사용자의 하루 식단을 평가하는 영양 코치입니다. '
        '의학적 진단은 하지 말고 제공된 목표량, 실제 섭취량, 백엔드가 계산한 점수와 이유만 설명하세요. '
        '숫자 합계나 점수를 새로 계산하거나 변경하지 마세요.\n'
        f'평가 데이터: {dump(context)}\n'
        '다음 구조로 반환하세요: '
        '{"strengths":["장점"],"improvements":["개선점"],'
        '"recommended_actions":["실천 가능한 행동"],"feedback":"전체 피드백"}'
    )


def build_diet_condition_prompt(request_data, profile, guardrail=None):
    return (
        f'{JSON_ONLY_RULES}\n'
        '사용자의 식단 추천 요청을 데이터 조회 조건으로만 분석하세요. '
        'SQL이나 Python 코드를 만들지 마세요.\n'
        f'사용자 요청: {dump(request_data)}\n'
        f'가드레일 요약: {dump(guardrail or {})}\n'
        f'프로필: {dump(profile)}\n'
        '가드레일 relevant_summary가 있으면 그 내용을 자유 텍스트 조건의 기준으로 사용하고, 사용자 요청의 무관한 잡담은 무시하세요. '
        '사용자가 명시한 내용만 추출하고 언급하지 않은 값은 null 또는 빈 배열로 두세요. '
        '특히 "빼줘", "제외", "먹지 않아", "알레르기" 뒤의 음식은 excluded_foods에 넣으세요.\n'
        '다음 구조로 반환하세요: '
        '{"intent":"diet_recommendation",'
        '"cuisine_style":"한식","spicy_level":"맵지 않게",'
        '"preferred_foods":["두부"],"excluded_foods":["새우"],'
        '"simple_cooking":true,"goal":"fat_loss",'
        '"conditions":{"high_protein":true,"low_carbohydrate":false,"max_candidates":60}}'
    )


def build_diet_recommendation_prompt(context, candidates=None, free=False, correction=None):
    rules = '' if free else f' {CANDIDATE_ID_RULES}'
    candidate_section = '' if free else f'음식 후보: {dump(candidates or [])}\n'
    food_source_rule = (
        'food_source가 free입니다. DB 음식 후보나 candidate id를 사용하지 말고, 현실적인 음식을 자유롭게 구성하세요. '
        '각 item은 food_id 없이 ai_food_key, name, amount, role, nutrition_per_100g를 반드시 포함해야 합니다. '
        'nutrition_per_100g는 100g 기준 calories, carbohydrate, protein, fat 숫자값입니다. '
        if free
        else (
            '후보의 영양값은 100g 기준이며 amount는 실제 섭취할 gram 수입니다. '
            '추천 컨텍스트의 제외 음식은 후보에 있더라도 절대 사용하지 마세요. '
        )
    )
    meal_role_rule = '' if free else '음식명과 meal_role을 보고 평소 식탁에서 자연스럽게 함께 먹는 조합을 선택하세요. '
    meal_specs = context.get('meal_specs') or []
    expected_count = len(meal_specs)
    candidate_examples = candidates or []
    meals_example = []
    for spec in meal_specs:
        order = spec['meal_order']
        if free:
            items = [
                {
                    'ai_food_key': f'free_protein_{order}',
                    'name': '두부구이',
                    'amount': 150,
                    'role': 'protein',
                    'nutrition_per_100g': {
                        'calories': 97, 'carbohydrate': 3, 'protein': 10, 'fat': 5,
                    },
                },
                {
                    'ai_food_key': f'free_carb_{order}',
                    'name': '현미밥',
                    'amount': 120,
                    'role': 'carb',
                    'nutrition_per_100g': {
                        'calories': 150, 'carbohydrate': 32, 'protein': 3, 'fat': 1,
                    },
                },
            ]
        else:
            items = [
                {
                    'food_id': candidate['id'],
                    'amount': 100,
                    'role': candidate.get('meal_role', 'side'),
                }
                for candidate in candidate_examples[:2]
            ]
        meals_example.append({
            'meal_order': order,
            'meal_label': spec['meal_label'],
            'items': items,
        })
    response_example = {
        'title': '추천 식단 제목',
        'summary': '추천 이유',
        'meals': meals_example,
    }
    correction_text = f'이전 응답 오류: {correction}\n' if correction else ''
    return (
        f'{JSON_ONLY_RULES}\n'
        f'{HEALTHFIT_DIET_RECOMMENDATION_PROMPT}\n'
        f'{HEALTHFIT_PT_COACH_TONE}\n'
        f'{correction_text}'
        f'사용자의 목표에 맞으면서 실제 사람이 한 끼로 바로 먹을 수 있는 식단을 추천하세요.{rules}\n'
        '남은 하루 영양량 전체를 한 끼에 채우려고 하지 마세요. '
        '각 끼니는 2~5개 음식으로 구성하고, 감량 식사는 대체로 400~700kcal 범위에서 구성하세요. '
        '단백질 메인 1개, 채소 또는 반찬 1개를 우선 포함하고 저탄수 요청이 아니라면 밥이나 일반적인 탄수화물 1개를 포함하세요. '
        '말린 식품, 건조 원물, 분말, 추출물, 조미료, 생식용 원재료만 여러 개 조합하지 마세요. '
        '같은 종류의 고단백 원재료를 여러 개 중복 추천하지 마세요. '
        f'{meal_role_rule}'
        '권장 중량은 밥/면 100~250g, 단백질 메인 80~200g, 반찬/채소 30~150g, 국/찌개 150~300g 정도입니다. '
        f'{food_source_rule}'
        'request의 scope, meal_count, meal_order, meal_label은 자연어 해석이나 condition 결과보다 우선하는 확정값입니다. '
        f'meals 배열은 반드시 정확히 {expected_count}개여야 합니다. 더 적거나 많으면 실패입니다. '
        '각 meal은 요청된 meal_order와 meal_label을 정확히 사용하세요. '
        f'추천 컨텍스트: {dump(context)}\n'
        f'{candidate_section}'
        f'다음 {expected_count}끼 JSON 골격을 그대로 유지하고 각 items만 조건에 맞게 구성하세요: '
        f'{dump(response_example)}'
    )


def build_diet_replacement_prompt(context, candidates=None, free=False):
    candidate_text = '없음(자유 생성)' if free else dump(candidates or [])
    item_shape = (
        '{"ai_food_key":"free_fish_001","name":"구운 흰살생선",'
        '"amount":150,"role":"protein","nutrition_per_100g":'
        '{"calories":130,"carbohydrate":0,"protein":24,"fat":4}}'
        if free
        else '{"food_id":1,"amount":150,"role":"protein"}'
    )
    rules = '' if free else CANDIDATE_ID_RULES
    return (
        f'{JSON_ONLY_RULES}\n{HEALTHFIT_DIET_RECOMMENDATION_PROMPT}\n'
        f'{HEALTHFIT_PT_COACH_TONE}\n{rules}\n'
        '지정된 음식 하나를 비슷한 역할과 현실적인 양의 다른 음식 하나로 교체하세요. '
        '사용자의 추가 제외/선호 조건을 반드시 반영하세요.\n'
        f'교체 컨텍스트: {dump(context)}\n'
        f'사용 가능한 후보: {candidate_text}\n'
        f'다음 구조로 반환하세요: {{"item":{item_shape}}}'
    )


def build_workout_condition_prompt(request_data, profile, guardrail=None):
    return (
        f'{JSON_ONLY_RULES}\n'
        '사용자의 운동 추천 요청을 운동 후보 조회 조건으로만 분석하세요. '
        'SQL이나 Python 코드를 만들지 마세요.\n'
        f'사용자 요청: {dump(request_data)}\n'
        f'가드레일 요약: {dump(guardrail or {})}\n'
        f'프로필: {dump(profile)}\n'
        '가드레일 relevant_summary가 있으면 그 내용을 자유 텍스트 조건의 기준으로 사용하고, 사용자 요청의 무관한 잡담은 무시하세요. '
        '다음 구조로 반환하세요: '
        '{"intent":"workout_recommendation","goal":"muscle_gain",'
        '"conditions":{"body_part_keywords":["가슴"],"equipment_keywords":[],'
        '"beginner_friendly":true,"max_candidates":60}}'
    )


def build_workout_recommendation_prompt(context, candidates):
    return (
        f'{JSON_ONLY_RULES}\n'
        f'{HEALTHFIT_WORKOUT_RECOMMENDATION_PROMPT}\n'
        f'{HEALTHFIT_PT_COACH_TONE}\n'
        f'사용자의 목표와 운동 경험에 맞는 운동 루틴을 추천하세요. {CANDIDATE_ID_RULES}\n'
        f'추천 컨텍스트: {dump(context)}\n'
        f'운동 후보: {dump(candidates)}\n'
        'exercise_id는 후보의 숫자 id이며 외부 문자열 ID가 아닙니다. '
        '다음 구조로 반환하세요: '
        '{"title":"제목","description":"설명","items":['
        '{"exercise_id":1,"order":1,"sets":3,"reps":12,'
        '"weight":0,"rest_seconds":60}]}'
    )


def build_workout_progression_prompt(payload):
    return (
        f'{JSON_ONLY_RULES}\n'
        f'{HEALTHFIT_WORKOUT_RECOMMENDATION_PROMPT}\n'
        f'{HEALTHFIT_PT_COACH_TONE}\n'
        '당신은 피트니스 기록 앱의 근력 운동 점진적 과부하 보조 코치입니다. '
        '백엔드가 계산한 최근 세트 기록, 관련 근육 회복 상태, 사용자 목표와 경험만 사용하세요. '
        '사용자 memo는 제공되지 않으며 추측해서도 안 됩니다. 운동 기록이나 운동 ID를 만들지 마세요. '
        'backend_preliminary_recommendation을 주 기준으로 사용하고 공격적인 중량 증가를 금지합니다. '
        '관련 근육 중 days_since가 0 또는 1이면 increase를 반환하지 마세요. '
        '백엔드가 회복 부족이나 반복 하락으로 maintain/decrease/deload를 선택했다면 increase로 바꾸지 마세요. '
        'reason은 어떤 세트 추세와 근육 회복 상태를 근거로 했는지 짧고 구체적으로 작성하세요. '
        'safety_note에는 사용자가 체감 난이도에 따라 중량·반복·세트를 직접 조절하라는 문장을 넣으세요.\n'
        f'구조화 데이터: {dump(payload)}\n'
        '다음 구조의 JSON만 반환하세요: '
        '{"decision":"maintain","recommendation":{"set_count":3,"repetition":8,'
        '"weight_kg":62.5,"rest_seconds":120},'
        '"reason":"최근 세트와 회복 상태에 근거한 설명",'
        '"safety_note":"체감 난이도에 따라 직접 조절하세요."}'
    )
