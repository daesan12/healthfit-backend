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
    workout_time = models.PositiveIntegerField(null=True, blank=True)
    set_count = models.PositiveIntegerField(default=0)
    repetition = models.PositiveIntegerField(default=0)
    memo = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def update_summary_from_sets(self):
        sets = list(self.sets.order_by('set_order'))
        working_sets = [item for item in sets if not item.is_warmup] or sets
        repetitions = [item.repetition for item in working_sets if item.repetition is not None]
        self.set_count = len(working_sets)
        self.repetition = max(repetitions, default=0)
        self.save(update_fields=['set_count', 'repetition', 'updated_at'])

    def __str__(self):
        return f'{self.user} {self.workout_date} {self.exercise.name}'


class WorkoutLogSet(models.Model):
    workout_log = models.ForeignKey(
        WorkoutLog,
        on_delete=models.CASCADE,
        related_name='sets',
    )
    set_order = models.PositiveIntegerField()
    weight_kg = models.FloatField(null=True, blank=True)
    repetition = models.PositiveIntegerField(null=True, blank=True)
    duration_seconds = models.PositiveIntegerField(null=True, blank=True)
    rpe = models.FloatField(null=True, blank=True)
    is_warmup = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['set_order', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['workout_log', 'set_order'],
                name='unique_workout_log_set_order',
            ),
        ]

    def __str__(self):
        return f'{self.workout_log_id} set {self.set_order}'
