from django.contrib import admin

from .models import Food, Meal, MealItem


admin.site.register(Food)
admin.site.register(Meal)
admin.site.register(MealItem)
