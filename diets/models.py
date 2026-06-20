from django.conf import settings
from django.db import models


class Food(models.Model):
    name = models.CharField(max_length=255)
    category = models.CharField(max_length=100)
    calories = models.FloatField()
    carbohydrate = models.FloatField(null=True, blank=True)
    protein = models.FloatField(null=True, blank=True)
    fat = models.FloatField(null=True, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class FoodSnapshot(models.Model):
    SOURCE_DB = 'db'
    SOURCE_FREE = 'free'
    SOURCE_CHOICES = [(SOURCE_DB, 'DB'), (SOURCE_FREE, 'Free')]

    name = models.CharField(max_length=255)
    ai_food_key = models.CharField(max_length=100, blank=True)
    source_type = models.CharField(max_length=10, choices=SOURCE_CHOICES)
    original_food = models.ForeignKey(
        Food,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='snapshots',
    )
    nutrition_per_100g = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Meal(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    meal_type = models.CharField(max_length=20)
    meal_order = models.PositiveSmallIntegerField(default=1)
    meal_label = models.CharField(max_length=50, blank=True)
    intake_date = models.DateField()
    total_calories = models.FloatField(default=0)
    total_carbohydrate = models.FloatField(default=0)
    total_protein = models.FloatField(default=0)
    total_fat = models.FloatField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def recalculate_totals(self):
        items = self.items.all()
        self.total_calories = sum(item.calories for item in items)
        self.total_carbohydrate = sum(item.carbohydrate for item in items)
        self.total_protein = sum(item.protein for item in items)
        self.total_fat = sum(item.fat for item in items)
        self.save(update_fields=[
            'total_calories',
            'total_carbohydrate',
            'total_protein',
            'total_fat',
            'updated_at',
        ])

    def __str__(self):
        return f'{self.user} {self.intake_date} {self.meal_type}'


class MealItem(models.Model):
    meal = models.ForeignKey(Meal, on_delete=models.CASCADE, related_name='items')
    food = models.ForeignKey(Food, on_delete=models.CASCADE, null=True, blank=True)
    food_snapshot = models.ForeignKey(
        FoodSnapshot,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='meal_items',
    )
    amount = models.FloatField()
    calories = models.FloatField()
    carbohydrate = models.FloatField()
    protein = models.FloatField()
    fat = models.FloatField()

    @property
    def food_name(self):
        return self.food.name if self.food_id else self.food_snapshot.name

    def __str__(self):
        return f'{self.food_name} {self.amount}g'


class SavedMeal(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    total_calories = models.FloatField(default=0)
    total_carbohydrate = models.FloatField(default=0)
    total_protein = models.FloatField(default=0)
    total_fat = models.FloatField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def recalculate_totals(self):
        items = self.items.select_related('food')
        self.total_calories = round(sum(item.calories for item in items), 2)
        self.total_carbohydrate = round(sum(item.carbohydrate for item in items), 2)
        self.total_protein = round(sum(item.protein for item in items), 2)
        self.total_fat = round(sum(item.fat for item in items), 2)
        self.save(update_fields=[
            'total_calories',
            'total_carbohydrate',
            'total_protein',
            'total_fat',
            'updated_at',
        ])

    def __str__(self):
        return self.name


class SavedMealItem(models.Model):
    saved_meal = models.ForeignKey(SavedMeal, on_delete=models.CASCADE, related_name='items')
    food = models.ForeignKey(Food, on_delete=models.CASCADE, null=True, blank=True)
    food_snapshot = models.ForeignKey(
        FoodSnapshot,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='saved_meal_items',
    )
    amount = models.FloatField()

    @property
    def nutrition(self):
        if self.food_id:
            return {
                'calories': self.food.calories,
                'carbohydrate': self.food.carbohydrate,
                'protein': self.food.protein,
                'fat': self.food.fat,
            }
        return self.food_snapshot.nutrition_per_100g

    @property
    def food_name(self):
        return self.food.name if self.food_id else self.food_snapshot.name

    def calculate(self, value):
        return round((value or 0) * self.amount / 100, 2)

    @property
    def calories(self):
        return self.calculate(self.nutrition.get('calories'))

    @property
    def carbohydrate(self):
        return self.calculate(self.nutrition.get('carbohydrate'))

    @property
    def protein(self):
        return self.calculate(self.nutrition.get('protein'))

    @property
    def fat(self):
        return self.calculate(self.nutrition.get('fat'))

    def __str__(self):
        return f'{self.saved_meal.name}: {self.food_name} {self.amount}g'


class SavedMealPlan(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    target_calories = models.FloatField(null=True, blank=True)
    target_carbohydrate = models.FloatField(null=True, blank=True)
    target_protein = models.FloatField(null=True, blank=True)
    target_fat = models.FloatField(null=True, blank=True)
    total_calories = models.FloatField(default=0)
    total_carbohydrate = models.FloatField(default=0)
    total_protein = models.FloatField(default=0)
    total_fat = models.FloatField(default=0)
    source_recommendation = models.ForeignKey(
        'ai_services.AIRecommendation',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='saved_meal_plans',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title


class SavedMealPlanMeal(models.Model):
    plan = models.ForeignKey(SavedMealPlan, on_delete=models.CASCADE, related_name='meals')
    meal_order = models.PositiveSmallIntegerField()
    meal_label = models.CharField(max_length=50)
    target_calories = models.FloatField(null=True, blank=True)
    total_calories = models.FloatField(default=0)
    total_carbohydrate = models.FloatField(default=0)
    total_protein = models.FloatField(default=0)
    total_fat = models.FloatField(default=0)

    class Meta:
        ordering = ['meal_order', 'id']


class SavedMealPlanItem(models.Model):
    plan_meal = models.ForeignKey(SavedMealPlanMeal, on_delete=models.CASCADE, related_name='items')
    food = models.ForeignKey(Food, on_delete=models.CASCADE, null=True, blank=True)
    food_snapshot = models.ForeignKey(
        FoodSnapshot,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='saved_meal_plan_items',
    )
    amount = models.FloatField()
    calories = models.FloatField()
    carbohydrate = models.FloatField()
    protein = models.FloatField()
    fat = models.FloatField()
