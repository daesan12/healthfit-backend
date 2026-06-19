from django.urls import path

from .views import (
    ExerciseDetailView,
    ExerciseListView,
    RoutineItemCreateView,
    RoutineItemDetailView,
    WorkoutRoutineDetailView,
    WorkoutRoutineListCreateView,
)


urlpatterns = [
    path('exercises/', ExerciseListView.as_view(), name='exercise-list'),
    path('exercises/<int:pk>/', ExerciseDetailView.as_view(), name='exercise-detail'),
    path('workout-routines/', WorkoutRoutineListCreateView.as_view(), name='workout-routine-list-create'),
    path(
        'workout-routines/<int:routine_id>/items/',
        RoutineItemCreateView.as_view(),
        name='routine-item-create',
    ),
    path(
        'workout-routines/<int:routine_id>/',
        WorkoutRoutineDetailView.as_view(),
        name='workout-routine-detail',
    ),
    path(
        'routine-items/<int:routine_item_id>/',
        RoutineItemDetailView.as_view(),
        name='routine-item-detail',
    ),
]
