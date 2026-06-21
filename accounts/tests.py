from datetime import date, timedelta

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from .models import BodyRecord


class BodyRecordPaginationTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username='body-pagination',
            email='body-pagination@example.com',
            password='password123!',
        )
        self.client.force_authenticate(user=self.user)
        start = date(2026, 1, 1)
        BodyRecord.objects.bulk_create([
            BodyRecord(user=self.user, record_date=start + timedelta(days=index), weight=70 + index)
            for index in range(25)
        ])

    def test_body_records_are_paginated_after_date_filter(self):
        response = self.client.get(
            '/api/v1/body-records/?start_date=2026-01-10&end_date=2026-01-20&page_size=5'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data['data']
        self.assertEqual(data['count'], 11)
        self.assertEqual(data['page_size'], 5)
        self.assertEqual(len(data['results']), 5)
        self.assertTrue(data['has_next'])
