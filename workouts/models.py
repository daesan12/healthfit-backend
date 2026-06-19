from django.conf import settings
from django.db import models
from django.utils import timezone


class Exercise(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    exercise_id = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=100)
    gif_url = models.URLField(null=True, blank=True)
    body_parts = models.JSONField(default=list)
    equipments = models.JSONField(default=list)
    target_muscles = models.JSONField(default=list)
    secondary_muscles = models.JSONField(default=list)
    instructions = models.JSONField(default=list)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return self.name


class WorkoutRoutine(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='workout_routines',
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class RoutineItem(models.Model):
    routine = models.ForeignKey(WorkoutRoutine, on_delete=models.CASCADE, related_name='items')
    exercise = models.ForeignKey(Exercise, on_delete=models.CASCADE)
    order = models.PositiveIntegerField()
    sets = models.PositiveIntegerField()
    reps = models.PositiveIntegerField()
    weight = models.FloatField()
    rest_seconds = models.PositiveIntegerField()

    class Meta:
        ordering = ['order', 'id']

    def __str__(self):
        return f'{self.routine.name}: {self.exercise.name}'


class WorkoutLog(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='workout_logs',
    )
    exercise = models.ForeignKey(Exercise, on_delete=models.CASCADE)
    routine = models.ForeignKey(
        WorkoutRoutine,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    workout_date = models.DateField()
    workout_time = models.PositiveIntegerField()
    set_count = models.PositiveIntegerField()
    repetition = models.PositiveIntegerField()
    memo = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.user} {self.workout_date} {self.exercise.name}'
