from django.db import models
from django.utils import timezone


class Exercise(models.Model):
    exercise_id = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=100)
    gif_url = models.URLField()
    body_parts = models.JSONField(default=list)
    equipments = models.JSONField(default=list)
    target_muscles = models.JSONField(default=list)
    secondary_muscles = models.JSONField(default=list)
    instructions = models.JSONField(default=list)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return self.name
