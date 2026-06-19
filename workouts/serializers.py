from rest_framework import serializers

from .models import Exercise


class ExerciseSerializer(serializers.ModelSerializer):
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
            'created_at',
            'updated_at',
        ]
