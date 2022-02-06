import re
from unittest import mock

from django.apps import apps
from django.core import mail
from django.urls import reverse
from django.utils import timezone

from rest_framework.test import APITestCase

from zeynep.tests.factories import UserFactory
from zeynep.verification.models import RegistrationVerification


class TestRegistrationVerification(APITestCase):
    def setUp(self):
        self.url_send = reverse("registration-verification-list")
        self.url_check = reverse("registration-verification-check")

    def test_code_gen(self):
        verification = RegistrationVerification.objects.create(
            email="world@exmaple.com"
        )

        self.assertEqual(6, len(verification.code))
        self.assertTrue(verification.code.isdigit())

    def test_send(self):
        test_backend = "django.core.mail.backends.locmem.EmailBackend"
        email = "patato@example.com"

        with self.settings(EMAIL_BACKEND=test_backend):
            self.client.post(self.url_send, data={"email": email})
            (code,) = re.findall(r"[\d]{6}", mail.outbox[0].body)

        verification = RegistrationVerification.objects.get(
            code=code, email=email
        )

        self.assertFalse(verification.is_eligible)
        self.assertIsNone(verification.user)

        with self.assertRaises(AssertionError):
            verification.create_consent()

    def test_send_case_exists(self):
        email_taken = "hello@example.com"
        UserFactory(email=email_taken)

        response = self.client.post(self.url_send, data={"email": email_taken})
        self.assertEqual(400, response.status_code)

    def test_check(self):
        email = "worldt@exmaple.com"
        verification = RegistrationVerification.objects.create(email=email)

        # Check non-matching
        invalid = self.client.post(
            self.url_check,
            {"email": email, "code": "000000"},
        )
        self.assertEqual(404, invalid.status_code)

        # Check valid
        payload = {"email": email, "code": verification.code}
        valid = self.client.post(self.url_check, payload)
        verification.refresh_from_db()
        self.assertEqual(200, valid.status_code)
        self.assertContains(valid, "consent")
        self.assertTrue(verification.is_eligible)
        self.assertIsNotNone(verification.date_verified)

        # Resend to confirm that it is no more valid
        resend = self.client.post(self.url_check, payload)
        self.assertEqual(404, resend.status_code)

    def test_check_case_expired(self):
        config = apps.get_app_config("verification")
        period = config.REGISTRATION_VERIFY_PERIOD + 10
        expired_create = timezone.now() - timezone.timedelta(seconds=period)
        email = "worldz@exmaple.com"

        with mock.patch(
            "django.utils.timezone.now",
            return_value=expired_create,
        ):
            verification = RegistrationVerification.objects.create(email=email)

        response = self.client.post(
            self.url_check,
            {"email": email, "code": verification.code},
        )
        self.assertEqual(404, response.status_code)
