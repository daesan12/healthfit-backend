from django.urls import path

from .views import CalorieTargetView, MyProfileView


urlpatterns = [
    path('me/', MyProfileView.as_view(), name='profile-me'),
    path('me/calorie-target/', CalorieTargetView.as_view(), name='profile-calorie-target'),
]
