from django.urls import path

from .views import (
    FoodDetailView,
    FoodListCreateView,
    MealDashboardView,
    MealDetailView,
    MealListCreateView,
    SavedMealCreateMealView,
    SavedMealDetailView,
    SavedMealListCreateView,
)


urlpatterns = [
    path('foods/', FoodListCreateView.as_view(), name='food-list-create'),
    path('foods/<int:food_id>/', FoodDetailView.as_view(), name='food-detail'),
    path('meals/', MealListCreateView.as_view(), name='meal-list-create'),
    path('meals/dashboard/', MealDashboardView.as_view(), name='meal-dashboard'),
    path('meals/<int:meal_id>/', MealDetailView.as_view(), name='meal-detail'),
    path('saved-meals/', SavedMealListCreateView.as_view(), name='saved-meal-list-create'),
    path('saved-meals/<int:saved_meal_id>/', SavedMealDetailView.as_view(), name='saved-meal-detail'),
    path(
        'saved-meals/<int:saved_meal_id>/create-meal/',
        SavedMealCreateMealView.as_view(),
        name='saved-meal-create-meal',
    ),
]
