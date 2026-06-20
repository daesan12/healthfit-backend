import uuid

from django.db import transaction
from django.utils import timezone
from django.db.models import Q
from rest_framework import serializers

from .models import Exercise, RoutineItem, WorkoutLog, WorkoutLogSet, WorkoutRoutine


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


class WorkoutLogSetSerializer(serializers.ModelSerializer):
    set_order = serializers.IntegerField(min_value=1)
    weight_kg = serializers.FloatField(min_value=0, required=False, allow_null=True)
    repetition = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    duration_seconds = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    rpe = serializers.FloatField(min_value=1, max_value=10, required=False, allow_null=True)
    is_warmup = serializers.BooleanField(required=False, default=False)

    class Meta:
        model = WorkoutLogSet
        fields = [
            'id',
            'set_order',
            'weight_kg',
            'repetition',
            'duration_seconds',
            'rpe',
            'is_warmup',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate(self, attrs):
        if attrs.get('repetition') is None and attrs.get('duration_seconds') is None:
            raise serializers.ValidationError(
                'repetition 또는 duration_seconds 중 하나는 필요합니다.'
            )
        return attrs


class WorkoutLogSerializer(serializers.ModelSerializer):
    log_id = serializers.IntegerField(source='id', read_only=True)
    exercise_id = serializers.IntegerField(required=False)
    workout_id = serializers.IntegerField(required=False, write_only=True)
    exercise = ExerciseSerializer(read_only=True)
    routine_id = serializers.IntegerField(required=False, allow_null=True)
    workout_time = serializers.IntegerField(min_value=0, required=False, allow_null=True)
    set_count = serializers.IntegerField(min_value=0, required=False, default=0)
    repetition = serializers.IntegerField(min_value=0, required=False, default=0)
    sets = WorkoutLogSetSerializer(many=True, required=False, allow_empty=False)

    class Meta:
        model = WorkoutLog
        fields = [
            'id',
            'log_id',
            'workout_id',
            'exercise_id',
            'exercise',
            'routine_id',
            'workout_date',
            'workout_time',
            'set_count',
            'repetition',
            'memo',
            'sets',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['workout_id'] = instance.exercise_id
        return data

    def validate(self, attrs):
        workout_id = attrs.pop('workout_id', None)
        exercise_id = attrs.get('exercise_id')
        if workout_id is not None and exercise_id is not None and workout_id != exercise_id:
            raise serializers.ValidationError(
                {'workout_id': ['workout_id와 exercise_id가 서로 다릅니다.']}
            )
        selected_id = exercise_id or workout_id
        if self.instance is None and selected_id is None:
            raise serializers.ValidationError({'workout_id': ['workout_id가 필요합니다.']})
        if selected_id is not None:
            self.validate_exercise_id(selected_id)
            attrs['exercise_id'] = selected_id

        sets = attrs.get('sets')
        if self.instance is None and not sets:
            set_count = attrs.get('set_count', 0)
            repetition = attrs.get('repetition', 0)
            if set_count > 0 and repetition > 0:
                attrs['sets'] = [
                    {
                        'set_order': order,
                        'weight_kg': None,
                        'repetition': repetition,
                        'duration_seconds': None,
                        'rpe': None,
                        'is_warmup': False,
                    }
                    for order in range(1, set_count + 1)
                ]
            else:
                raise serializers.ValidationError({'sets': ['세트 기록을 1개 이상 입력해주세요.']})
        if sets is not None:
            orders = [item['set_order'] for item in sets]
            if len(orders) != len(set(orders)):
                raise serializers.ValidationError({'sets': ['set_order는 중복될 수 없습니다.']})
        return attrs

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

    @transaction.atomic
    def create(self, validated_data):
        sets_data = validated_data.pop('sets')
        log = WorkoutLog.objects.create(**validated_data)
        self._replace_sets(log, sets_data)
        return log

    @transaction.atomic
    def update(self, instance, validated_data):
        sets_data = validated_data.pop('sets', None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()
        if sets_data is not None:
            instance.sets.all().delete()
            self._replace_sets(instance, sets_data)
        return instance

    def _replace_sets(self, log, sets_data):
        WorkoutLogSet.objects.bulk_create([
            WorkoutLogSet(workout_log=log, **item)
            for item in sets_data
        ])
        log.update_summary_from_sets()
