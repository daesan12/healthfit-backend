from django.conf import settings
from django.db import models


class AIRecommendation(models.Model):
    DIET = 'diet'
    WORKOUT = 'workout'
    TYPE_CHOICES = [
        (DIET, 'Diet'),
        (WORKOUT, 'Workout'),
    ]
    SCOPE_MEAL = 'meal'
    SCOPE_DAY = 'day'
    SCOPE_REMAINING = 'remaining'
    SCOPE_REPLACEMENT = 'replacement'
    SCOPE_REROLL = 'reroll'
    SCOPE_CHOICES = [
        (SCOPE_MEAL, 'Meal'),
        (SCOPE_DAY, 'Day'),
        (SCOPE_REMAINING, 'Remaining'),
        (SCOPE_REPLACEMENT, 'Replacement'),
        (SCOPE_REROLL, 'Reroll'),
    ]
    FOOD_SOURCE_CHOICES = [
        ('all', 'All'),
        ('my_fridge', 'My fridge'),
        ('free', 'Free'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='ai_recommendations',
    )
    recommendation_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    input_data = models.JSONField(default=dict)
    result_data = models.JSONField(default=dict)
    source = models.CharField(max_length=20)
    recommendation_scope = models.CharField(max_length=20, choices=SCOPE_CHOICES, default=SCOPE_MEAL)
    food_source = models.CharField(max_length=20, choices=FOOD_SOURCE_CHOICES, default='all')
    target_date = models.DateField(null=True, blank=True)
    parent_recommendation = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='derived_recommendations',
    )
    content = models.JSONField(default=dict)
    is_saved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.user.username} {self.recommendation_type} recommendation'


class DietFeedback(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='diet_feedbacks',
    )
    target_date = models.DateField()
    score = models.IntegerField()
    summary = models.TextField()
    good_points = models.JSONField(default=list)
    improvement_points = models.JSONField(default=list)
    recommendation = models.TextField()
    result_data = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.user.username} {self.target_date} diet feedback'


class AIChat(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='ai_chats',
    )
    question = models.TextField()
    answer = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']

    def __str__(self):
        return f'{self.user.username}: {self.question[:30]}'
