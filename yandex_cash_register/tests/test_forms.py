# coding=utf-8
from __future__ import absolute_import, unicode_literals

try:
    from unittest import mock
except ImportError:
    import mock

from decimal import Decimal
from uuid import UUID

from django.test import TestCase
from django import forms

from ..forms import ShopIdForm, PaymentForm, readonly_widget, \
    PaymentProcessingForm
from ..models import Payment
from .. import conf


TEST_SHOP_ID = 12345


class ShopIdFormTestCase(TestCase):
    def setUp(self):
        self.payment = Payment.objects.create(
            order_sum=Decimal(1000.0), order_id='abcdef',
            cps_email='test@test.com', cps_phone='79991234567',
            payment_type=conf.PAYMENT_TYPE_YANDEX_MONEY
        )

    def _get_form(self, empty_fields=None, **kwargs):
        data = {'shopId': conf.SHOP_ID, 'orderNumber': self.payment.order_id,
                'customerNumber': self.payment.customer_id,
                'paymentType': conf.PAYMENT_TYPE_YANDEX_MONEY}
        data.update(kwargs)
        if empty_fields is not None:
            for field in empty_fields:
                del data[field]
        return ShopIdForm(data)

    def test_correct_form(self):
        form = self._get_form()
        self.assertTrue(form.is_valid())
        self.assertEqual(form.payment_obj, self.payment)

    def test_no_payment_error(self):
        form = self._get_form(orderNumber='123456')
        self.assertFalse(form.is_valid())
        self.assertIsNone(form.payment_obj)
        self.assertEqual(list(form.errors.keys()), ['orderNumber'])

    def test_wrong_shop_id_error(self):
        form = self._get_form(shopId=str(conf.SHOP_ID) + '1')
        self.assertFalse(form.is_valid())
        self.assertEqual(form.payment_obj, self.payment)
        self.assertEqual(list(form.errors.keys()), ['shopId'])

    def test_wrong_customer_id_error(self):
        form = self._get_form(customerNumber='-----')
        self.assertFalse(form.is_valid())
        self.assertEqual(form.payment_obj, self.payment)
        self.assertEqual(list(form.errors.keys()), ['customerNumber'])

    def test_wrong_payment_type_error(self):
        form = self._get_form(paymentType=conf.PAYMENT_TYPE_CARD)
        self.assertFalse(form.is_valid())
        self.assertEqual(form.payment_obj, self.payment)
        self.assertEqual(list(form.errors.keys()), ['paymentType'])

    def test_empty_values(self):
        for field in ('shopId', 'orderNumber', 'customerNumber',
                      'paymentType'):
            form = self._get_form(empty_fields=[field])
            self.assertFalse(form.is_valid())
            self.assertEqual(list(form.errors.keys()), [field])


class PaymentFormTestCase(TestCase):
    def setUp(self):
        self.payment = Payment.objects.create(
            order_sum=Decimal(1000.0), order_id='abcdef',
            cps_email='test@test.com', cps_phone='79991234567',
            payment_type=conf.PAYMENT_TYPE_YANDEX_MONEY
        )

    def _get_form(self):
        return PaymentForm({
            'orderNumber': self.payment.order_id,
            'sum': self.payment.order_sum,
            'customerNumber': self.payment.customer_id,
            'cps_email': self.payment.cps_email,
            'cps_phone': self.payment.cps_phone,
            'paymentType': conf.PAYMENT_TYPE_YANDEX_MONEY,
            'shopId': conf.SHOP_ID, 'scid': conf.SCID,
            'shopSuccessURL': 'http://example.com',
            'shopFailURL': 'http://example.com'
        })

    @mock.patch('yandex_cash_register.forms.conf')
    def test_form_fields_debug(self, m_conf):
        m_conf.DEBUG = True
        m_conf.SHOP_ID = conf.SHOP_ID
        form = self._get_form()

        for name, field in form.fields.items():
            if name in conf.DISPLAY_FIELDS:
                self.assertNotIsInstance(field.widget, forms.HiddenInput)
                self.assertNotIsInstance(field.widget,
                                         readonly_widget.__class__)
                continue

            self.assertIsInstance(field.widget, readonly_widget.__class__)

        self.assertFalse(form.is_valid())
        self.assertEqual(list(form.errors.keys()), ['__all__'])

    @mock.patch('yandex_cash_register.forms.conf')
    def test_form_fields_no_debug(self, m_conf):
        m_conf.DEBUG = False
        m_conf.SHOP_ID = conf.SHOP_ID
        m_conf.DISPLAY_FIELDS = ['paymentType']
        form = self._get_form()

        for name, field in form.fields.items():
            if name in conf.DISPLAY_FIELDS:
                self.assertNotIsInstance(field.widget, forms.HiddenInput)
                self.assertNotIsInstance(field.widget,
                                         readonly_widget.__class__)
                continue

            self.assertIsInstance(field.widget, forms.HiddenInput)

        self.assertFalse(form.is_valid())
        self.assertEqual(list(form.errors.keys()), ['__all__'])


@mock.patch('yandex_cash_register.forms.conf',
            new=mock.MagicMock(SHOP_PASSWORD='123456', SHOP_ID=TEST_SHOP_ID))
class OrderProcessingFormTestCase(TestCase):
    def setUp(self):
        self.payment = Payment.objects.create(
            order_sum=Decimal(1000.0), order_id='abcdef',
            cps_email='test@test.com', cps_phone='79991234567',
            payment_type=conf.PAYMENT_TYPE_YANDEX_MONEY,
            customer_id=UUID('0c3c745b-8c7b-4813-8b28-c0a2b037f19c')
        )

    def _get_form(self, empty_fields=None, **kwargs):
        data = {
            'shopId': TEST_SHOP_ID, 'orderNumber': self.payment.order_id,
            'customerNumber': self.payment.customer_id,
            'paymentType': conf.PAYMENT_TYPE_YANDEX_MONEY,
            'action': PaymentProcessingForm.ACTION_CHECK,
            'md5': 'D3DFFF43EC59431056C6B1B63290CF63',
            'invoiceId': '123456', 'orderSumAmount': '1000.0',
            'orderSumCurrencyPaycash': '1',
            'orderSumBankPaycash': '1', 'shopSumAmount': '975.3',
            'shopSumCurrencyPaycash': '1'
        }
        data.update(kwargs)
        if empty_fields is not None:
            for field in empty_fields:
                del data[field]
        return PaymentProcessingForm(data)

    def test_all_correct(self):
        form = self._get_form()
        self.assertTrue(form.is_valid())
        self.assertEqual(form.payment_obj, self.payment)
        self.assertIsNone(form.error_code)
        self.assertIsNone(form.error_message)

    def test_all_correct_empty_payment_type(self):
        self.payment.payment_type = ''
        self.payment.save()

        form = self._get_form()
        self.assertTrue(form.is_valid())
        self.assertEqual(form.payment_obj, self.payment)
        self.assertIsNone(form.error_code)
        self.assertIsNone(form.error_message)

    def test_round(self):
        form = self._get_form()
        self.assertEqual(form._round(Decimal(1001.0)), 1000)
        self.assertEqual(form._round(Decimal(0)), 0)
        self.assertEqual(form._round(Decimal(333.33)), 330)
        self.assertEqual(form._round(Decimal(299.99)), 300)
        self.assertEqual(form._round(Decimal(15.99)), 20)

    def test_error_messages(self):
        form = self._get_form()
        form.set_error(1, 'Тест')
        self.assertEqual(form.error_code, 1)
        self.assertEqual(form.error_message, 'Тест')

        with self.assertRaises(forms.ValidationError):
            form.set_error(100, 'Тест2', raise_error=True)

        self.assertEqual(form.error_code, 100)
        self.assertEqual(form.error_message, 'Тест2')

    def test_round_comparison(self):
        form = self._get_form(orderSumAmount='999.99',
                              md5='DE51FC39AAFB023A4AA8984083BCAE03')
        self.assertTrue(form.is_valid())

        form = self._get_form(orderSumAmount='995.99',
                              md5='B7A40EA2CEB39A9C4F35C5112CE8AA3A')
        self.assertTrue(form.is_valid())

        form = self._get_form(orderSumAmount='994.99',
                              md5='D844D2AE1A250D356A3F46146302F0AE')
        self.assertFalse(form.is_valid())
        self.assertEqual(list(form.errors.keys()), ['__all__'])

    def test_error_values(self):
        form = self._get_form(md5='DE51FC39AAFB023A4AA8984083BCAE03')
        self.assertFalse(form.is_valid())
        self.assertEqual(form.error_code, PaymentProcessingForm.ERROR_CODE_MD5)
        self.assertIsNotNone(form.error_message)

        form = self._get_form(empty_fields=['md5'])
        self.assertFalse(form.is_valid())
        self.assertEqual(form.error_code, PaymentProcessingForm.ERROR_CODE_MD5)
        self.assertIsNotNone(form.error_message)

        form = self._get_form(empty_fields=['orderNumber'])
        self.assertFalse(form.is_valid())
        self.assertEqual(form.error_code,
                         PaymentProcessingForm.ERROR_CODE_UNKNOWN_ORDER)
        self.assertIsNotNone(form.error_message)

        form = self._get_form(orderNumber='asd')
        self.assertFalse(form.is_valid())
        self.assertEqual(form.error_code,
                         PaymentProcessingForm.ERROR_CODE_UNKNOWN_ORDER)
        self.assertIsNotNone(form.error_message)

        form = self._get_form(empty_fields=['customerNumber'])
        self.assertFalse(form.is_valid())
        self.assertEqual(form.error_code,
                         PaymentProcessingForm.ERROR_CODE_UNKNOWN_ORDER)
        self.assertIsNotNone(form.error_message)

        form = self._get_form(paymentType=conf.PAYMENT_TYPE_ALFA_CLICK)
        self.assertFalse(form.is_valid())
        self.assertEqual(form.error_code,
                         PaymentProcessingForm.ERROR_CODE_INTERNAL)
        self.assertIsNotNone(form.error_message)

        for field in ('orderSumAmount', 'invoiceId', 'orderSumCurrencyPaycash',
                      'orderSumBankPaycash', 'shopSumAmount',
                      'shopSumCurrencyPaycash', 'shopId', 'action',
                      'paymentType'):
            form = self._get_form(empty_fields=[field])
            self.assertFalse(form.is_valid())
            self.assertEqual(form.error_code,
                             PaymentProcessingForm.ERROR_CODE_INTERNAL)
            self.assertIsNotNone(form.error_message)
