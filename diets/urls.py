from django.urls import path

from .views import FoodDetailView, FoodListCreateView


urlpatterns = [
    path('foods/', FoodListCreateView.as_view(), name='food-list-create'),
    path('foods/<int:food_id>/', FoodDetailView.as_view(), name='food-detail'),
]
