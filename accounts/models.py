from django.contrib.auth.models import AbstractUser
from django.conf import settings
from django.db import models


class User(AbstractUser):
    email = models.EmailField(unique=True)


class Profile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile')
    gender = models.CharField(max_length=20)
    age = models.PositiveIntegerField()
    height = models.FloatField()
    weight = models.FloatField()
    body_type = models.CharField(max_length=50)
    activity_level = models.CharField(max_length=20)
    workout_goal = models.CharField(max_length=30)
    workout_experience = models.CharField(max_length=30)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.user.username} profile'


class BodyRecord(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='body_records',
    )
    record_date = models.DateField()
    weight = models.FloatField(null=True, blank=True)
    body_fat_percentage = models.FloatField(null=True, blank=True)
    skeletal_muscle_mass = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.user.username} {self.record_date}'
