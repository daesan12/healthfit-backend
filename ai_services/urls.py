from django.urls import path

from .views import (
    DietEvaluationView,
    DietRecommendationDetailView,
    DietRecommendationReplaceView,
    DietRecommendationRerollView,
    DietRecommendationView,
    RecommendationSaveMealView,
    RecommendationSaveRoutineView,
    RecommendationSaveSavedMealView,
    WorkoutRecommendationView,
    WorkoutProgressionView,
)


urlpatterns = [
    path('diet/evaluations/', DietEvaluationView.as_view(), name='ai-diet-evaluation'),
    path('diet/recommendations/', DietRecommendationView.as_view(), name='ai-diet-recommendation'),
    path(
        'diet/recommendations/<int:recommendation_id>/',
        DietRecommendationDetailView.as_view(),
        name='ai-diet-recommendation-detail',
    ),
    path(
        'workout/recommendations/',
        WorkoutRecommendationView.as_view(),
        name='ai-workout-recommendation',
    ),
    path(
        'workout/progression/',
        WorkoutProgressionView.as_view(),
        name='ai-workout-progression',
    ),
    path(
        'recommendations/<int:recommendation_id>/save-meal/',
        RecommendationSaveMealView.as_view(),
        name='ai-recommendation-save-meal',
    ),
    path(
        'diet/recommendations/<int:recommendation_id>/save/',
        RecommendationSaveSavedMealView.as_view(),
        name='ai-recommendation-save-saved-meal',
    ),
    path(
        'diet/recommendations/<int:recommendation_id>/replace/',
        DietRecommendationReplaceView.as_view(),
        name='ai-diet-recommendation-replace',
    ),
    path(
        'diet/recommendations/<int:recommendation_id>/reroll/',
        DietRecommendationRerollView.as_view(),
        name='ai-diet-recommendation-reroll',
    ),
    path(
        'recommendations/<int:recommendation_id>/save-routine/',
        RecommendationSaveRoutineView.as_view(),
        name='ai-recommendation-save-routine',
    ),
]
