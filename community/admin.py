from django.contrib import admin

from .models import Comment, Like, Post, SharedPostSave


admin.site.register([Post, Comment, Like, SharedPostSave])
