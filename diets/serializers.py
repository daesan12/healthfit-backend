from rest_framework import serializers

from .models import Food, Meal, MealItem


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


class MealItemInputSerializer(serializers.Serializer):
    food_id = serializers.IntegerField()
    amount = serializers.FloatField()

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError('섭취량은 0보다 커야 합니다.')
        return value


class MealItemSerializer(serializers.ModelSerializer):
    food_id = serializers.IntegerField(source='food.id', read_only=True)
    food_name = serializers.CharField(source='food.name', read_only=True)

    class Meta:
        model = MealItem
        fields = [
            'id',
            'food_id',
            'food_name',
            'amount',
            'calories',
            'carbohydrate',
            'protein',
            'fat',
        ]


class MealSerializer(serializers.ModelSerializer):
    items = MealItemInputSerializer(many=True, write_only=True, required=False)
    meal_items = MealItemSerializer(source='items', many=True, read_only=True)

    class Meta:
        model = Meal
        fields = [
            'id',
            'meal_type',
            'intake_date',
            'total_calories',
            'total_carbohydrate',
            'total_protein',
            'total_fat',
            'items',
            'meal_items',
        ]
        read_only_fields = [
            'total_calories',
            'total_carbohydrate',
            'total_protein',
            'total_fat',
        ]

    def validate(self, attrs):
        if self.instance is None and not attrs.get('items'):
            raise serializers.ValidationError({'items': ['식단 항목을 1개 이상 입력해주세요.']})
        return attrs

    def create(self, validated_data):
        items_data = validated_data.pop('items')
        meal = Meal.objects.create(**validated_data)
        self._replace_items(meal, items_data)
        return meal

    def update(self, instance, validated_data):
        items_data = validated_data.pop('items', None)

        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()

        if items_data is not None:
            instance.items.all().delete()
            self._replace_items(instance, items_data)
        else:
            instance.recalculate_totals()

        return instance

    def _replace_items(self, meal, items_data):
        request = self.context['request']

        for item_data in items_data:
            food = self._get_food(item_data['food_id'], request.user)
            amount = item_data['amount']
            MealItem.objects.create(
                meal=meal,
                food=food,
                amount=amount,
                calories=self._calculate(food.calories, amount),
                carbohydrate=self._calculate(food.carbohydrate, amount),
                protein=self._calculate(food.protein, amount),
                fat=self._calculate(food.fat, amount),
            )

        meal.recalculate_totals()

    def _get_food(self, food_id, user):
        try:
            return Food.objects.get(id=food_id, user__isnull=True)
        except Food.DoesNotExist:
            try:
                return Food.objects.get(id=food_id, user=user)
            except Food.DoesNotExist as exc:
                raise serializers.ValidationError({'items': [f'조회 가능한 음식이 아닙니다: {food_id}']}) from exc

    def _calculate(self, value, amount):
        return round((value or 0) * amount / 100, 2)
