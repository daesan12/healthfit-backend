import uuid

from django.utils import timezone
from django.db.models import Q
from rest_framework import serializers

from .models import Exercise, RoutineItem, WorkoutLog, WorkoutRoutine


class ExerciseSerializer(serializers.ModelSerializer):
    user_id = serializers.IntegerField(source='user.id', read_only=True)
    body_parts = serializers.ListField(child=serializers.CharField(), allow_empty=False)
    equipments = serializers.ListField(child=serializers.CharField(), allow_empty=False)
    target_muscles = serializers.ListField(child=serializers.CharField(), allow_empty=False)
    secondary_muscles = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_empty=True,
    )
    instructions = serializers.ListField(child=serializers.CharField(), allow_empty=False)

    class Meta:
        model = Exercise
        fields = [
            'id',
            'exercise_id',
            'name',
            'gif_url',
            'body_parts',
            'equipments',
            'target_muscles',
            'secondary_muscles',
            'instructions',
            'user_id',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['exercise_id', 'created_at', 'updated_at']

    def create(self, validated_data):
        validated_data['exercise_id'] = f'custom-{uuid.uuid4().hex[:13]}'
        return super().create(validated_data)

    def update(self, instance, validated_data):
        validated_data['updated_at'] = timezone.now()
        return super().update(instance, validated_data)


class RoutineItemSerializer(serializers.ModelSerializer):
    exercise_id = serializers.IntegerField(write_only=True)
    exercise = ExerciseSerializer(read_only=True)
    order = serializers.IntegerField(min_value=1)
    sets = serializers.IntegerField(min_value=1)
    reps = serializers.IntegerField(min_value=1)
    weight = serializers.FloatField(min_value=0)
    rest_seconds = serializers.IntegerField(min_value=0)

    class Meta:
        model = RoutineItem
        fields = [
            'id',
            'exercise_id',
            'exercise',
            'order',
            'sets',
            'reps',
            'weight',
            'rest_seconds',
        ]

    def validate_exercise_id(self, value):
        user = self.context['request'].user
        if not Exercise.objects.filter(pk=value).filter(
            Q(user__isnull=True) | Q(user=user)
        ).exists():
            raise serializers.ValidationError('사용할 수 있는 운동이 아닙니다.')
        return value


class WorkoutRoutineSerializer(serializers.ModelSerializer):
    items = RoutineItemSerializer(many=True, read_only=True)

    class Meta:
        model = WorkoutRoutine
        fields = [
            'id',
            'name',
            'description',
            'items',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']

    def validate(self, attrs):
        if 'items' in self.initial_data:
            raise serializers.ValidationError(
                {'items': ['루틴 항목은 별도의 routine item API를 사용해주세요.']}
            )
        return attrs


class WorkoutLogSerializer(serializers.ModelSerializer):
    exercise_id = serializers.IntegerField()
    exercise = ExerciseSerializer(read_only=True)
    routine_id = serializers.IntegerField(required=False, allow_null=True)
    workout_time = serializers.IntegerField(min_value=0)
    set_count = serializers.IntegerField(min_value=0)
    repetition = serializers.IntegerField(min_value=0)

    class Meta:
        model = WorkoutLog
        fields = [
            'id',
            'exercise_id',
            'exercise',
            'routine_id',
            'workout_date',
            'workout_time',
            'set_count',
            'repetition',
            'memo',
            'created_at',
        ]
        read_only_fields = ['created_at']

    def validate_exercise_id(self, value):
        user = self.context['request'].user
        if not Exercise.objects.filter(pk=value).filter(
            Q(user__isnull=True) | Q(user=user)
        ).exists():
            raise serializers.ValidationError('사용할 수 있는 운동이 아닙니다.')
        return value

    def validate_routine_id(self, value):
        if value is None:
            return value

        user = self.context['request'].user
        if not WorkoutRoutine.objects.filter(pk=value, user=user).exists():
            raise serializers.ValidationError('사용할 수 있는 내 운동 루틴이 아닙니다.')
        return value
