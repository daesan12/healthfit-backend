from django.urls import path

from .views import FoodDetailView, FoodListCreateView, MealDashboardView, MealDetailView, MealListCreateView


urlpatterns = [
    path('foods/', FoodListCreateView.as_view(), name='food-list-create'),
    path('foods/<int:food_id>/', FoodDetailView.as_view(), name='food-detail'),
    path('meals/', MealListCreateView.as_view(), name='meal-list-create'),
    path('meals/dashboard/', MealDashboardView.as_view(), name='meal-dashboard'),
    path('meals/<int:meal_id>/', MealDetailView.as_view(), name='meal-detail'),
]
