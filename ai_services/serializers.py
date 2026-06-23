from rest_framework import serializers
from django.utils import timezone

from .models import AIChat, DietFeedback


class GuardrailResultSerializer(serializers.Serializer):
    is_allowed = serializers.BooleanField()
    category = serializers.ChoiceField(choices=[
        'diet', 'workout', 'nutrition', 'health_habit', 'medical_caution', 'unsupported',
    ])
    risk_level = serializers.ChoiceField(choices=['normal', 'caution', 'unsafe'])
    relevant_summary = serializers.CharField(allow_blank=True)
    reason = serializers.CharField(allow_blank=True)
    blocked_message = serializers.CharField(allow_blank=True)


class AIChatRequestSerializer(serializers.Serializer):
    question = serializers.CharField(allow_blank=False, max_length=2000)


class AIChatSerializer(serializers.ModelSerializer):
    class Meta:
        model = AIChat
        fields = ['id', 'question', 'answer', 'created_at']


class DietEvaluationRequestSerializer(serializers.Serializer):
    target_date = serializers.DateField(required=False)
    date = serializers.DateField(required=False, write_only=True)

    def validate(self, attrs):
        target_date = attrs.get('target_date')
        legacy_date = attrs.pop('date', None)
        if target_date is None and legacy_date is None:
            raise serializers.ValidationError({'target_date': ['평가 날짜가 필요합니다.']})
        if target_date and legacy_date and target_date != legacy_date:
            raise serializers.ValidationError({'target_date': ['target_date와 date가 서로 다릅니다.']})
        attrs['target_date'] = target_date or legacy_date
        return attrs


class DietRecommendationRequestSerializer(serializers.Serializer):
    FOOD_SOURCE_CHOICES = ['all', 'my_fridge', 'free']
    MEAL_TYPE_CHOICES = ['breakfast', 'lunch', 'dinner', 'snack']
    SCOPE_CHOICES = ['meal', 'day', 'remaining']

    scope = serializers.ChoiceField(choices=SCOPE_CHOICES, default='meal')
    message = serializers.CharField(required=False, allow_blank=False)
    meal_type = serializers.ChoiceField(choices=MEAL_TYPE_CHOICES, required=False)
    meal_order = serializers.IntegerField(required=False, min_value=1, max_value=6, default=1)
    meal_label = serializers.CharField(required=False, max_length=50, allow_blank=False)
    target_date = serializers.DateField()
    food_source = serializers.ChoiceField(choices=FOOD_SOURCE_CHOICES, default='all')
    meal_count = serializers.IntegerField(required=False, min_value=1, max_value=6)
    exclude_food_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        required=False,
        default=list,
    )
    preference = serializers.CharField(required=False, allow_blank=False)

    def validate(self, attrs):
        attrs['message'] = attrs.get('message') or attrs.get('preference') or '건강한 식단을 추천해줘.'
        if attrs['scope'] == 'day':
            attrs['meal_count'] = attrs.get('meal_count', 3)
        elif 'meal_count' in attrs:
            attrs.pop('meal_count')
        attrs['meal_label'] = attrs.get('meal_label') or f"{attrs['meal_order']}번째 식사"
        return attrs


class WorkoutRecommendationRequestSerializer(serializers.Serializer):
    EXERCISE_SOURCE_CHOICES = ['all', 'my_exercises']

    message = serializers.CharField(required=False, allow_blank=False)
    target_body_part = serializers.CharField(required=False, allow_blank=False)
    available_time = serializers.IntegerField(min_value=1, max_value=300)
    exercise_source = serializers.ChoiceField(choices=EXERCISE_SOURCE_CHOICES, default='all')
    weekly_frequency = serializers.IntegerField(required=False, min_value=1, max_value=7)
    preference = serializers.CharField(required=False, allow_blank=False)

    def validate(self, attrs):
        attrs['message'] = attrs.get('message') or attrs.get('preference') or '내 목표에 맞는 운동 루틴을 추천해줘.'
        return attrs


class WorkoutProgressionRequestSerializer(serializers.Serializer):
    workout_id = serializers.IntegerField(min_value=1)
    target_date = serializers.DateField(required=False, default=timezone.localdate)
    goal = serializers.CharField(required=False, allow_blank=False)
    message = serializers.CharField(required=False, allow_blank=False, default='')


class WorkoutProgressionTargetSerializer(serializers.Serializer):
    set_count = serializers.IntegerField(min_value=1, max_value=10)
    repetition = serializers.IntegerField(min_value=1, max_value=100)
    weight_kg = serializers.FloatField(min_value=0, max_value=1000, allow_null=True)
    rest_seconds = serializers.IntegerField(min_value=15, max_value=600)


class WorkoutProgressionAIResultSerializer(serializers.Serializer):
    DECISIONS = [
        'increase',
        'maintain',
        'decrease',
        'deload',
        'bodyweight_progression',
        'insufficient_history',
    ]

    decision = serializers.ChoiceField(choices=DECISIONS)
    recommendation = WorkoutProgressionTargetSerializer()
    reason = serializers.CharField()
    safety_note = serializers.CharField()


class SaveMealRequestSerializer(serializers.Serializer):
    meal_type = serializers.ChoiceField(choices=['breakfast', 'lunch', 'dinner', 'snack'])
    intake_date = serializers.DateField()


class SaveSavedMealRequestSerializer(serializers.Serializer):
    SAVE_TARGET_CHOICES = ['meals', 'saved_meal', 'meal_plan', 'both']

    save_target = serializers.ChoiceField(choices=SAVE_TARGET_CHOICES, default='saved_meal')
    meal_orders = serializers.ListField(
        child=serializers.IntegerField(min_value=1, max_value=6),
        required=False,
        allow_empty=False,
    )
    title = serializers.CharField(max_length=255, required=False, allow_blank=False)
    name = serializers.CharField(max_length=255, required=False, allow_blank=False, write_only=True)
    description = serializers.CharField(required=False, allow_blank=True, default='')

    def validate(self, attrs):
        attrs['title'] = attrs.get('title') or attrs.pop('name', None) or 'AI 추천 식단'
        meal_orders = attrs.get('meal_orders')
        if meal_orders:
            attrs['meal_orders'] = list(dict.fromkeys(meal_orders))
        return attrs


class ReplaceDietItemRequestSerializer(serializers.Serializer):
    meal_order = serializers.IntegerField(min_value=1)
    replace_food_id = serializers.IntegerField(min_value=1, required=False)
    replace_ai_food_key = serializers.CharField(max_length=100, required=False)
    message = serializers.CharField()

    def validate(self, attrs):
        if bool(attrs.get('replace_food_id')) == bool(attrs.get('replace_ai_food_key')):
            raise serializers.ValidationError({
                'target': ['replace_food_id 또는 replace_ai_food_key 중 하나만 입력해주세요.'],
            })
        return attrs


class RerollDietRequestSerializer(serializers.Serializer):
    message = serializers.CharField()


class SaveRoutineRequestSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)
    description = serializers.CharField(required=False, allow_blank=True, default='')


class StringListField(serializers.ListField):
    child = serializers.CharField(allow_blank=False)


class DietEvaluationAIResultSerializer(serializers.Serializer):
    score = serializers.IntegerField(min_value=0, max_value=100, required=False)
    strengths = StringListField(required=False)
    improvements = StringListField(required=False)
    recommended_actions = StringListField(required=False)
    feedback = serializers.CharField(required=False)
    summary = serializers.CharField(required=False)
    good_points = StringListField(required=False)
    improvement_points = StringListField(required=False)
    recommendation = serializers.CharField(required=False)

    def validate(self, attrs):
        attrs['strengths'] = attrs.get('strengths') or attrs.get('good_points') or []
        attrs['improvements'] = attrs.get('improvements') or attrs.get('improvement_points') or []
        attrs['recommended_actions'] = attrs.get('recommended_actions') or (
            [attrs['recommendation']] if attrs.get('recommendation') else []
        )
        attrs['feedback'] = attrs.get('feedback') or attrs.get('summary') or ''
        attrs['summary'] = attrs['feedback']
        attrs['good_points'] = attrs['strengths']
        attrs['improvement_points'] = attrs['improvements']
        attrs['recommendation'] = ' '.join(attrs['recommended_actions'])
        return attrs


class ConditionAIResultSerializer(serializers.Serializer):
    intent = serializers.CharField(required=False)
    cuisine_style = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    spicy_level = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    preferred_foods = StringListField(required=False, allow_null=True, default=list)
    excluded_foods = StringListField(required=False, allow_null=True, default=list)
    simple_cooking = serializers.BooleanField(required=False, allow_null=True)
    goal = serializers.CharField(required=False)
    conditions = serializers.DictField(default=dict)

    def validate(self, attrs):
        attrs['preferred_foods'] = attrs.get('preferred_foods') or []
        attrs['excluded_foods'] = attrs.get('excluded_foods') or []
        conditions = attrs.get('conditions', {})
        conditions['preferred_keywords'] = attrs.get('preferred_foods') or conditions.get('preferred_keywords', [])
        conditions['exclude_keywords'] = attrs.get('excluded_foods') or conditions.get('exclude_keywords', [])
        attrs['conditions'] = conditions
        return attrs


class CandidateDietItemAIResultSerializer(serializers.Serializer):
    food_id = serializers.IntegerField(min_value=1)
    amount = serializers.FloatField(min_value=10, max_value=500)
    role = serializers.CharField(required=False, default='side')


class CandidateDietAIResultSerializer(serializers.Serializer):
    title = serializers.CharField()
    summary = serializers.CharField()
    items = CandidateDietItemAIResultSerializer(
        many=True,
        allow_empty=False,
        min_length=2,
        max_length=5,
    )


class CandidateDietMealAIResultSerializer(serializers.Serializer):
    meal_order = serializers.IntegerField(min_value=1)
    meal_label = serializers.CharField(max_length=50)
    items = CandidateDietItemAIResultSerializer(many=True, min_length=2, max_length=5)


class CandidateDietPlanAIResultSerializer(serializers.Serializer):
    title = serializers.CharField()
    summary = serializers.CharField()
    meals = CandidateDietMealAIResultSerializer(many=True, min_length=1, max_length=6)


class NutritionPer100gSerializer(serializers.Serializer):
    calories = serializers.FloatField(min_value=0, max_value=1000)
    carbohydrate = serializers.FloatField(min_value=0, max_value=100)
    protein = serializers.FloatField(min_value=0, max_value=100)
    fat = serializers.FloatField(min_value=0, max_value=100)


class FreeDietItemAIResultSerializer(serializers.Serializer):
    food_id = serializers.IntegerField(required=False, allow_null=True)
    ai_food_key = serializers.CharField(max_length=100)
    name = serializers.CharField()
    amount = serializers.FloatField(min_value=10, max_value=500)
    role = serializers.CharField()
    nutrition_per_100g = NutritionPer100gSerializer()


class FreeDietAIResultSerializer(serializers.Serializer):
    title = serializers.CharField()
    summary = serializers.CharField()
    items = FreeDietItemAIResultSerializer(many=True, allow_empty=False)


class FreeDietMealAIResultSerializer(serializers.Serializer):
    meal_order = serializers.IntegerField(min_value=1)
    meal_label = serializers.CharField(max_length=50)
    items = FreeDietItemAIResultSerializer(many=True, min_length=2, max_length=5)


class FreeDietPlanAIResultSerializer(serializers.Serializer):
    title = serializers.CharField()
    summary = serializers.CharField()
    meals = FreeDietMealAIResultSerializer(many=True, min_length=1, max_length=6)


class WorkoutItemAIResultSerializer(serializers.Serializer):
    exercise_id = serializers.IntegerField(min_value=1)
    order = serializers.IntegerField(min_value=1)
    sets = serializers.IntegerField(min_value=1)
    reps = serializers.IntegerField(min_value=1)
    weight = serializers.FloatField(min_value=0, default=0)
    rest_seconds = serializers.IntegerField(min_value=0, default=60)


class WorkoutAIResultSerializer(serializers.Serializer):
    title = serializers.CharField()
    description = serializers.CharField()
    items = WorkoutItemAIResultSerializer(many=True, allow_empty=False)


class DietFeedbackSerializer(serializers.ModelSerializer):
    feedback_id = serializers.IntegerField(source='id', read_only=True)
    date = serializers.DateField(source='target_date', read_only=True)
    total_calories = serializers.SerializerMethodField()
    total_carbohydrate = serializers.SerializerMethodField()
    total_protein = serializers.SerializerMethodField()
    total_fat = serializers.SerializerMethodField()
    strengths = serializers.JSONField(source='good_points', read_only=True)
    improvements = serializers.JSONField(source='improvement_points', read_only=True)
    recommended_actions = serializers.SerializerMethodField()
    feedback = serializers.CharField(source='summary', read_only=True)
    target = serializers.SerializerMethodField()
    score_detail = serializers.SerializerMethodField()

    class Meta:
        model = DietFeedback
        fields = [
            'id',
            'feedback_id',
            'target_date',
            'date',
            'score',
            'total_calories',
            'total_carbohydrate',
            'total_protein',
            'total_fat',
            'target',
            'score_detail',
            'strengths',
            'improvements',
            'recommended_actions',
            'feedback',
            'summary',
            'good_points',
            'improvement_points',
            'recommendation',
            'result_data',
            'created_at',
            'updated_at',
        ]

    def get_total_calories(self, obj):
        return obj.result_data.get('total_calories', 0)

    def get_total_carbohydrate(self, obj):
        return obj.result_data.get('total_carbohydrate', 0)

    def get_total_protein(self, obj):
        return obj.result_data.get('total_protein', 0)

    def get_total_fat(self, obj):
        return obj.result_data.get('total_fat', 0)

    def get_recommended_actions(self, obj):
        actions = obj.result_data.get('recommended_actions')
        return actions if isinstance(actions, list) else ([obj.recommendation] if obj.recommendation else [])

    def get_target(self, obj):
        return obj.result_data.get('target', {
            'recommended_calories': obj.result_data.get('target_calories'),
            'recommended_carbohydrate': obj.result_data.get('target_carbohydrate'),
            'recommended_protein': obj.result_data.get('target_protein'),
            'recommended_fat': obj.result_data.get('target_fat'),
        })

    def get_score_detail(self, obj):
        return obj.result_data.get('score_detail', {})


class DietFeedbackFilterSerializer(serializers.Serializer):
    date = serializers.DateField(required=False)
    start_date = serializers.DateField(required=False)
    end_date = serializers.DateField(required=False)

    def validate(self, attrs):
        if attrs.get('start_date') and attrs.get('end_date'):
            if attrs['start_date'] > attrs['end_date']:
                raise serializers.ValidationError(
                    {'date_range': ['시작일은 종료일보다 늦을 수 없습니다.']}
                )
        return attrs
