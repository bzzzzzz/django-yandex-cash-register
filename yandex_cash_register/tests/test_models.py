# coding=utf-8
from __future__ import absolute_import, unicode_literals

from decimal import Decimal

try:
    from unittest import mock
except ImportError:
    import mock

from django.test import TestCase

from ..forms import PaymentForm
from ..models import Payment
from ..signals import payment_fail, payment_process, payment_success
from .. import conf


success_mock = mock.MagicMock()
fail_mock = mock.MagicMock()
process_mock = mock.MagicMock()

payment_success.connect(success_mock)
payment_fail.connect(fail_mock)
payment_process.connect(process_mock)


class PaymentTestCase(TestCase):
    def setUp(self):
        self.payment = Payment.objects.create(
            order_sum=Decimal(1000.0), order_id='abcdef',
            cps_email='test@test.com', cps_phone='79991234567',
            payment_type=conf.PAYMENT_TYPE_YANDEX_MONEY
        )
        success_mock.reset_mock()
        fail_mock.reset_mock()
        process_mock.reset_mock()

    def test_form(self):
        form = self.payment.form()
        self.assertIsInstance(form, PaymentForm)

    def test_states_process(self):
        self.assertEqual(self.payment.state, Payment.STATE_CREATED)
        self.assertIsNone(self.payment.performed)
        self.assertIsNone(self.payment.completed)
        self.assertFalse(self.payment.is_completed)
        self.assertFalse(self.payment.is_payed)
        self.assertFalse(self.payment.is_started)

        self.payment.process()
        self.assertEqual(self.payment.state, Payment.STATE_PROCESSED)
        self.assertIsNotNone(self.payment.performed)
        self.assertIsNone(self.payment.completed)
        with self.assertRaises(RuntimeError):
            self.payment.process()

        self.assertEqual(self.payment.state, Payment.STATE_PROCESSED)
        self.assertIsNotNone(self.payment.performed)
        self.assertIsNone(self.payment.completed)

        self.assertFalse(self.payment.is_completed)
        self.assertFalse(self.payment.is_payed)
        self.assertTrue(self.payment.is_started)

        self.assertEqual(process_mock.call_count, 1)
        self.assertEqual(success_mock.call_count, 0)
        self.assertEqual(fail_mock.call_count, 0)

    def test_states_success(self):
        self.test_states_process()

        self.payment.complete()
        self.assertEqual(self.payment.state, Payment.STATE_SUCCESS)
        self.assertIsNotNone(self.payment.performed)
        self.assertIsNotNone(self.payment.completed)

        with self.assertRaises(RuntimeError):
            self.payment.complete()
        self.assertEqual(self.payment.state, Payment.STATE_SUCCESS)
        self.assertIsNotNone(self.payment.performed)
        self.assertIsNotNone(self.payment.completed)

        with self.assertRaises(RuntimeError):
            self.payment.process()
        self.assertEqual(self.payment.state, Payment.STATE_SUCCESS)
        self.assertIsNotNone(self.payment.performed)
        self.assertIsNotNone(self.payment.completed)

        self.assertTrue(self.payment.is_completed)
        self.assertTrue(self.payment.is_payed)
        self.assertTrue(self.payment.is_started)

        self.assertEqual(process_mock.call_count, 1)
        self.assertEqual(success_mock.call_count, 1)
        self.assertEqual(fail_mock.call_count, 0)

    def test_states_fail(self):
        self.test_states_process()

        self.payment.fail()
        self.assertEqual(self.payment.state, Payment.STATE_FAIL)
        self.assertIsNotNone(self.payment.performed)
        self.assertIsNotNone(self.payment.completed)

        with self.assertRaises(RuntimeError):
            self.payment.fail()
        self.assertEqual(self.payment.state, Payment.STATE_FAIL)
        self.assertIsNotNone(self.payment.performed)
        self.assertIsNotNone(self.payment.completed)

        with self.assertRaises(RuntimeError):
            self.payment.process()
        self.assertEqual(self.payment.state, Payment.STATE_FAIL)
        self.assertIsNotNone(self.payment.performed)
        self.assertIsNotNone(self.payment.completed)

        self.assertTrue(self.payment.is_completed)
        self.assertFalse(self.payment.is_payed)
        self.assertTrue(self.payment.is_started)

        self.assertEqual(process_mock.call_count, 1)
        self.assertEqual(success_mock.call_count, 0)
        self.assertEqual(fail_mock.call_count, 1)

    def test_state_direct_fail(self):
        self.assertEqual(self.payment.state, Payment.STATE_CREATED)
        self.assertIsNone(self.payment.performed)
        self.assertIsNone(self.payment.completed)
        self.assertFalse(self.payment.is_completed)
        self.assertFalse(self.payment.is_payed)
        self.assertFalse(self.payment.is_started)

        self.payment.fail()
        self.assertEqual(self.payment.state, Payment.STATE_FAIL)
        self.assertIsNone(self.payment.performed)
        self.assertIsNotNone(self.payment.completed)

        self.assertTrue(self.payment.is_completed)
        self.assertFalse(self.payment.is_payed)
        self.assertTrue(self.payment.is_started)

        self.assertEqual(process_mock.call_count, 0)
        self.assertEqual(success_mock.call_count, 0)
        self.assertEqual(fail_mock.call_count, 1)
