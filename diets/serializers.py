from rest_framework import serializers

from .models import Food


class FoodSerializer(serializers.ModelSerializer):
    user_id = serializers.IntegerField(source='user.id', read_only=True)

    class Meta:
        model = Food
        fields = [
            'id',
            'name',
            'category',
            'calories',
            'carbohydrate',
            'protein',
            'fat',
            'user_id',
        ]

    def validate_calories(self, value):
        if value < 0:
            raise serializers.ValidationError('칼로리는 0 이상이어야 합니다.')
        return value

    def validate(self, attrs):
        for field in ['carbohydrate', 'protein', 'fat']:
            value = attrs.get(field)
            if value is not None and value < 0:
                raise serializers.ValidationError({field: ['영양 성분은 0 이상이어야 합니다.']})
        return attrs
