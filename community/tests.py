from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Profile
from diets.models import Food, FoodSnapshot, SavedMeal, SavedMealItem
from workouts.models import Exercise, RoutineItem, WorkoutRoutine

from .models import Post, SharedPostSave


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


class CommunitySharingAPITests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.author = User.objects.create_user(
            username='author', email='author@example.com', password='password123!',
        )
        self.viewer = User.objects.create_user(
            username='viewer', email='viewer@example.com', password='password123!',
        )
        self.other = User.objects.create_user(
            username='other', email='other@example.com', password='password123!',
        )
        self.food = Food.objects.create(
            name='현미밥', category='곡류', calories=150,
            carbohydrate=32, protein=3, fat=1,
        )
        self.ai_food = FoodSnapshot.objects.create(
            name='AI 닭가슴살 샐러드',
            ai_food_key='ai-chicken-salad',
            source_type=FoodSnapshot.SOURCE_FREE,
            nutrition_per_100g={
                'calories': 120, 'carbohydrate': 8, 'protein': 18, 'fat': 3,
            },
        )
        self.saved_meal = SavedMeal.objects.create(
            user=self.author,
            name='고단백 식단',
            description='운동 후 식단',
        )
        SavedMealItem.objects.create(saved_meal=self.saved_meal, food=self.food, amount=150)
        SavedMealItem.objects.create(
            saved_meal=self.saved_meal,
            food_snapshot=self.ai_food,
            amount=100,
        )
        self.saved_meal.recalculate_totals()

        self.other_saved_meal = SavedMeal.objects.create(
            user=self.other,
            name='타인 식단',
            description='',
        )
        SavedMealItem.objects.create(
            saved_meal=self.other_saved_meal,
            food=self.food,
            amount=100,
        )
        self.other_saved_meal.recalculate_totals()

        self.exercise = Exercise.objects.create(
            exercise_id='community-share-exercise',
            name='푸쉬업',
            gif_url=None,
            body_parts=['chest'],
            equipments=['body weight'],
            target_muscles=['pectorals'],
            secondary_muscles=['triceps'],
            instructions=['팔굽혀펴기를 수행합니다.'],
        )
        self.routine = WorkoutRoutine.objects.create(
            user=self.author,
            name='초보자 전신 루틴',
            description='주 3회 루틴',
        )
        RoutineItem.objects.create(
            routine=self.routine,
            exercise=self.exercise,
            order=1,
            sets=3,
            reps=10,
            weight=0,
            rest_seconds=60,
        )
        self.other_routine = WorkoutRoutine.objects.create(
            user=self.other,
            name='타인 루틴',
            description='',
        )

    def authenticate(self, user):
        self.client.force_authenticate(user=user)

    def create_diet_post(self):
        self.authenticate(self.author)
        response = self.client.post('/api/v1/posts/', {
            'title': '고단백 감량 식단 공유',
            'content': '운동 후 먹기 좋습니다.',
            'category': 'diet',
            'shared_saved_meal_id': self.saved_meal.id,
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        return Post.objects.get(pk=response.data['data']['id'])

    def create_workout_post(self):
        self.authenticate(self.author)
        response = self.client.post('/api/v1/posts/', {
            'title': '초보자 전신 루틴 공유',
            'content': '주 3회 진행합니다.',
            'category': 'workout',
            'shared_workout_routine_id': self.routine.id,
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        return Post.objects.get(pk=response.data['data']['id'])

    def test_author_can_create_diet_post_with_own_saved_meal_snapshot(self):
        post = self.create_diet_post()

        self.assertEqual(post.shared_saved_meal, self.saved_meal)
        self.assertEqual(post.shared_saved_meal_snapshot['name'], self.saved_meal.name)
        self.assertEqual(len(post.shared_saved_meal_snapshot['items']), 2)

        response = self.client.get(f'/api/v1/posts/{post.id}/')
        data = response.data['data']
        self.assertEqual(data['author']['id'], self.author.id)
        self.assertEqual(data['shared_type'], SharedPostSave.SAVED_MEAL)
        self.assertEqual(data['shared_saved_meal']['items'][1]['ai_food_key'], 'ai-chicken-salad')
        self.assertIsNone(data['shared_workout_routine'])

    def test_author_cannot_attach_other_users_saved_meal(self):
        self.authenticate(self.author)
        response = self.client.post('/api/v1/posts/', {
            'title': '잘못된 공유', 'content': '내용', 'category': 'diet',
            'shared_saved_meal_id': self.other_saved_meal.id,
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('shared_saved_meal_id', response.data['errors'])

    def test_diet_post_rejects_workout_routine(self):
        self.authenticate(self.author)
        response = self.client.post('/api/v1/posts/', {
            'title': '잘못된 공유', 'content': '내용', 'category': 'diet',
            'shared_workout_routine_id': self.routine.id,
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('shared_workout_routine_id', response.data['errors'])

    def test_author_can_create_workout_post_with_own_routine_snapshot(self):
        post = self.create_workout_post()
        response = self.client.get(f'/api/v1/posts/{post.id}/')
        data = response.data['data']

        self.assertEqual(data['shared_type'], SharedPostSave.WORKOUT_ROUTINE)
        self.assertEqual(data['shared_workout_routine']['exercise_count'], 1)
        self.assertEqual(data['shared_workout_routine']['items'][0]['exercise_id'], self.exercise.id)
        self.assertIsNone(data['shared_saved_meal'])

    def test_author_cannot_attach_other_users_workout_routine(self):
        self.authenticate(self.author)
        response = self.client.post('/api/v1/posts/', {
            'title': '잘못된 공유', 'content': '내용', 'category': 'workout',
            'shared_workout_routine_id': self.other_routine.id,
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('shared_workout_routine_id', response.data['errors'])

    def test_workout_post_rejects_saved_meal_and_free_rejects_all_shares(self):
        self.authenticate(self.author)
        workout_response = self.client.post('/api/v1/posts/', {
            'title': '잘못된 운동 글', 'content': '내용', 'category': 'workout',
            'shared_saved_meal_id': self.saved_meal.id,
        }, format='json')
        free_response = self.client.post('/api/v1/posts/', {
            'title': '잘못된 자유 글', 'content': '내용', 'category': 'free',
            'shared_workout_routine_id': self.routine.id,
        }, format='json')

        self.assertEqual(workout_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(free_response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_category_change_to_free_clears_shared_fields_and_snapshots(self):
        post = self.create_diet_post()
        response = self.client.patch(
            f'/api/v1/posts/{post.id}/',
            {'category': 'free'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        post.refresh_from_db()
        self.assertIsNone(post.shared_saved_meal_id)
        self.assertIsNone(post.shared_saved_meal_snapshot)
        self.assertIsNone(response.data['data']['shared_type'])

    def test_another_user_can_save_shared_meal_with_all_items_once(self):
        post = self.create_diet_post()
        self.authenticate(self.viewer)
        first = self.client.post(f'/api/v1/posts/{post.id}/save-shared-meal/')
        second = self.client.post(f'/api/v1/posts/{post.id}/save-shared-meal/')

        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertFalse(first.data['data']['already_saved'])
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertTrue(second.data['data']['already_saved'])
        copied = SavedMeal.objects.get(pk=first.data['data']['saved_meal_id'])
        self.assertEqual(copied.user, self.viewer)
        self.assertEqual(copied.items.count(), 2)
        self.assertEqual(copied.items.filter(food_snapshot__ai_food_key='ai-chicken-salad').count(), 1)
        self.assertEqual(
            SharedPostSave.objects.filter(
                user=self.viewer, post=post, save_type=SharedPostSave.SAVED_MEAL,
            ).count(),
            1,
        )

        detail = self.client.get(f'/api/v1/posts/{post.id}/')
        self.assertEqual(detail.data['data']['viewer_save_status'], {
            'saved': True,
            'saved_meal_id': copied.id,
            'workout_routine_id': None,
        })

    def test_another_user_can_save_shared_routine_with_items_once(self):
        post = self.create_workout_post()
        self.authenticate(self.viewer)
        first = self.client.post(f'/api/v1/posts/{post.id}/save-shared-routine/')
        second = self.client.post(f'/api/v1/posts/{post.id}/save-shared-routine/')

        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertTrue(second.data['data']['already_saved'])
        copied = WorkoutRoutine.objects.get(pk=first.data['data']['routine_id'])
        self.assertEqual(copied.user, self.viewer)
        self.assertEqual(copied.items.count(), 1)
        copied_item = copied.items.get()
        self.assertEqual(copied_item.exercise, self.exercise)
        self.assertEqual(copied_item.sets, 3)

    def test_original_changes_or_delete_do_not_change_post_snapshot(self):
        post = self.create_diet_post()
        original_name = post.shared_saved_meal_snapshot['name']
        self.saved_meal.name = '수정된 원본 이름'
        self.saved_meal.save(update_fields=['name', 'updated_at'])
        self.saved_meal.delete()

        response = self.client.get(f'/api/v1/posts/{post.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['data']['shared_saved_meal']['name'], original_name)
        post.refresh_from_db()
        self.assertIsNone(post.shared_saved_meal_id)

    def test_missing_exercise_returns_common_error_without_creating_routine(self):
        post = self.create_workout_post()
        self.exercise.delete()
        self.authenticate(self.viewer)
        before = WorkoutRoutine.objects.filter(user=self.viewer).count()

        response = self.client.post(f'/api/v1/posts/{post.id}/save-shared-routine/')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data['success'])
        self.assertIn('exercises', response.data['errors'])
        self.assertEqual(WorkoutRoutine.objects.filter(user=self.viewer).count(), before)

    def test_unauthenticated_user_cannot_save_shared_items(self):
        diet_post = self.create_diet_post()
        workout_post = self.create_workout_post()
        self.client.force_authenticate(user=None)

        meal_response = self.client.post(f'/api/v1/posts/{diet_post.id}/save-shared-meal/')
        routine_response = self.client.post(f'/api/v1/posts/{workout_post.id}/save-shared-routine/')

        self.assertEqual(meal_response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(routine_response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertFalse(meal_response.data['success'])
        self.assertFalse(routine_response.data['success'])
