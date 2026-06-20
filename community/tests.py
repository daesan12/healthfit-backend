from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Profile

from .models import Post


class PublicProfileAPITests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username='public-user',
            email='public@example.com',
            password='password123!',
        )

    def test_public_profile_is_available_without_authentication(self):
        Profile.objects.create(
            user=self.user,
            gender='male',
            age=27,
            height=180,
            weight=75,
            body_type='normal',
            activity_level='normal',
            workout_goal='maintenance',
            workout_experience='beginner',
        )
        Post.objects.create(
            user=self.user,
            title='첫 번째 글',
            content='공개 게시글 내용',
            category='free',
        )

        response = self.client.get(f'/api/v1/users/{self.user.pk}/public-profile/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        data = response.data['data']
        self.assertEqual(data['user']['id'], self.user.pk)
        self.assertEqual(data['user']['username'], self.user.username)
        self.assertIn('created_at', data['user'])
        self.assertNotIn('email', data['user'])
        self.assertEqual(data['profile'], {'workout_goal': 'maintenance'})
        self.assertEqual(data['post_count'], 1)
        self.assertEqual(len(data['posts']), 1)
        self.assertIsNone(data['representative_saved_meal'])
        self.assertIsNone(data['representative_workout_routine'])

    def test_public_profile_returns_null_when_profile_does_not_exist(self):
        response = self.client.get(f'/api/v1/users/{self.user.pk}/public-profile/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data['data']['profile'])
        self.assertEqual(response.data['data']['post_count'], 0)
        self.assertEqual(response.data['data']['posts'], [])

    def test_public_profile_returns_common_error_for_unknown_user(self):
        response = self.client.get('/api/v1/users/999999/public-profile/')

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(
            response.data,
            {
                'success': False,
                'message': '공개 프로필을 찾을 수 없습니다.',
                'errors': {'user_id': ['존재하지 않는 사용자입니다.']},
            },
        )
