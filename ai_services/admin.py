from django.contrib import admin

from .models import AIChat, AIRecommendation, DietFeedback


admin.site.register(AIRecommendation)
admin.site.register(DietFeedback)
admin.site.register(AIChat)
