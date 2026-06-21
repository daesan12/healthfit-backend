from datetime import date, timedelta

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Food, Meal, SavedMeal


class DietPaginationTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username='diet-pagination',
            email='diet-pagination@example.com',
            password='password123!',
        )
        self.client.force_authenticate(user=self.user)
        Food.objects.bulk_create([
            Food(
                name=f'닭가슴살 {index:02d}',
                category='육류',
                calories=100 + index,
                carbohydrate=0,
                protein=20,
                fat=2,
            )
            for index in range(25)
        ])
        Food.objects.create(
            user=self.user,
            name='내 오트밀',
            category='곡류',
            calories=380,
            carbohydrate=65,
            protein=13,
            fat=7,
        )

    def assert_paginated(self, response):
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        for field in [
            'count', 'page', 'page_size', 'total_pages', 'next', 'previous',
            'has_next', 'has_previous', 'results',
        ]:
            self.assertIn(field, response.data['data'])

    def test_foods_use_page_size_and_search_before_pagination(self):
        response = self.client.get('/api/v1/foods/?search=닭가슴살&page=2&page_size=10')

        self.assert_paginated(response)
        data = response.data['data']
        self.assertEqual(data['count'], 25)
        self.assertEqual(data['page'], 2)
        self.assertEqual(data['page_size'], 10)
        self.assertEqual(len(data['results']), 10)
        self.assertTrue(all('닭가슴살' in item['name'] for item in data['results']))
        self.assertTrue(data['has_previous'])

    def test_food_source_and_max_page_size_are_supported(self):
        response = self.client.get('/api/v1/foods/?source=my&page_size=1000')

        self.assert_paginated(response)
        data = response.data['data']
        self.assertEqual(data['count'], 1)
        self.assertEqual(data['page_size'], 100)
        self.assertEqual(data['results'][0]['name'], '내 오트밀')

    def test_invalid_and_out_of_range_pages_use_common_error(self):
        invalid = self.client.get('/api/v1/foods/?page=abc')
        out_of_range = self.client.get('/api/v1/foods/?page=999')
        invalid_size = self.client.get('/api/v1/foods/?page_size=0')

        for response in [invalid, out_of_range, invalid_size]:
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertFalse(response.data['success'])
            self.assertEqual(response.data['message'], '페이지 조회에 실패했습니다.')

    def test_meals_paginate_after_date_and_label_filters(self):
        start = date(2026, 2, 1)
        for index in range(12):
            Meal.objects.create(
                user=self.user,
                meal_type='custom',
                meal_order=index + 1,
                meal_label='운동 전' if index < 7 else '운동 후',
                intake_date=start + timedelta(days=index % 3),
            )

        response = self.client.get(
            '/api/v1/meals/?start_date=2026-02-01&end_date=2026-02-03&meal_label=운동 전&page_size=5'
        )

        self.assert_paginated(response)
        data = response.data['data']
        self.assertEqual(data['count'], 7)
        self.assertEqual(len(data['results']), 5)
        self.assertTrue(all(item['meal_label'] == '운동 전' for item in data['results']))

    def test_saved_meals_are_paginated_and_searchable(self):
        SavedMeal.objects.bulk_create([
            SavedMeal(user=self.user, name=f'고단백 식단 {index}', description='운동 식단')
            for index in range(23)
        ])
        SavedMeal.objects.create(user=self.user, name='채식 식단', description='야채')

        response = self.client.get('/api/v1/saved-meals/?search=고단백&page_size=10')

        self.assert_paginated(response)
        self.assertEqual(response.data['data']['count'], 23)
        self.assertEqual(len(response.data['data']['results']), 10)
