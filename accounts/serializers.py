from django.contrib.auth import authenticate, get_user_model
from rest_framework import serializers

from .models import Profile


class SignupSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate_username(self, value):
        User = get_user_model()
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError('이미 사용 중인 아이디입니다.')
        return value

    def validate_email(self, value):
        User = get_user_model()
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError('이미 사용 중인 이메일입니다.')
        return value

    def create(self, validated_data):
        User = get_user_model()
        return User.objects.create_user(**validated_data)


class LoginSerializer(serializers.Serializer):
    login_id = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        User = get_user_model()
        login_id = attrs.get('login_id')
        password = attrs.get('password')

        user = authenticate(username=login_id, password=password)

        if user is None:
            try:
                matched_user = User.objects.get(email=login_id)
            except User.DoesNotExist:
                matched_user = None

            if matched_user is not None:
                user = authenticate(username=matched_user.username, password=password)

        if user is None:
            raise serializers.ValidationError({'non_field_errors': ['아이디 또는 비밀번호가 올바르지 않습니다.']})

        if not user.is_active:
            raise serializers.ValidationError({'non_field_errors': ['비활성화된 계정입니다.']})

        attrs['user'] = user
        return attrs


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class ProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = Profile
        fields = [
            'id',
            'gender',
            'age',
            'height',
            'weight',
            'body_type',
            'activity_level',
            'workout_goal',
            'workout_experience',
        ]

    def validate_age(self, value):
        if value <= 0:
            raise serializers.ValidationError('나이는 1 이상이어야 합니다.')
        return value

    def validate_height(self, value):
        if value <= 0:
            raise serializers.ValidationError('키는 0보다 커야 합니다.')
        return value

    def validate_weight(self, value):
        if value <= 0:
            raise serializers.ValidationError('몸무게는 0보다 커야 합니다.')
        return value
