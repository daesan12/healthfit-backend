from django.conf import settings
from django.db import models


class Post(models.Model):
    CATEGORY_CHOICES = [
        ('diet', 'Diet'),
        ('workout', 'Workout'),
        ('free', 'Free'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='posts')
    title = models.CharField(max_length=255)
    content = models.TextField()
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    shared_saved_meal = models.ForeignKey(
        'diets.SavedMeal',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='shared_posts',
    )
    shared_workout_routine = models.ForeignKey(
        'workouts.WorkoutRoutine',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='shared_posts',
    )
    shared_saved_meal_snapshot = models.JSONField(null=True, blank=True)
    shared_workout_routine_snapshot = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title


class Comment(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='comments')
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='comments')
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.user.username}: {self.content[:30]}'


class Like(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='likes')
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='likes')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'post'], name='unique_user_post_like'),
        ]

    def __str__(self):
        return f'{self.user.username} likes {self.post_id}'


class SharedPostSave(models.Model):
    SAVED_MEAL = 'saved_meal'
    WORKOUT_ROUTINE = 'workout_routine'
    SAVE_TYPE_CHOICES = [
        (SAVED_MEAL, 'Saved Meal'),
        (WORKOUT_ROUTINE, 'Workout Routine'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='shared_post_saves',
    )
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='shared_saves')
    save_type = models.CharField(max_length=20, choices=SAVE_TYPE_CHOICES)
    saved_meal = models.ForeignKey(
        'diets.SavedMeal',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='shared_post_save_records',
    )
    workout_routine = models.ForeignKey(
        'workouts.WorkoutRoutine',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='shared_post_save_records',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'post', 'save_type'],
                name='unique_user_post_shared_save_type',
            ),
        ]

    def __str__(self):
        return f'{self.user.username} saved {self.post_id} as {self.save_type}'
