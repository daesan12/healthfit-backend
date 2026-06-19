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


class Meal(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    meal_type = models.CharField(max_length=20)
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
    food = models.ForeignKey(Food, on_delete=models.CASCADE)
    amount = models.FloatField()
    calories = models.FloatField()
    carbohydrate = models.FloatField()
    protein = models.FloatField()
    fat = models.FloatField()

    def __str__(self):
        return f'{self.food.name} {self.amount}g'
