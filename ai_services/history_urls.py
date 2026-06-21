from django.urls import path

from .views import DietFeedbackListView


urlpatterns = [
    path('diet-feedbacks/', DietFeedbackListView.as_view(), name='diet-feedback-list'),
]
