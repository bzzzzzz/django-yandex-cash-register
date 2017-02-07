# coding=utf-8
from __future__ import absolute_import, unicode_literals

from decimal import Decimal
from uuid import UUID

try:
    from unittest import mock
except ImportError:
    import mock

from django.test import TestCase, Client, override_settings

from ..forms import FinalPaymentStateForm
from ..models import Payment
from ..views import CheckOrderView, PaymentAvisoView, PaymentFinishView
from ..signals import payment_fail, payment_process, payment_success
from .. import conf

success_mock = mock.MagicMock()
fail_mock = mock.MagicMock()
process_mock = mock.MagicMock()

payment_success.connect(success_mock)
payment_fail.connect(fail_mock)
payment_process.connect(process_mock)


TEST_SHOP_ID = 12345


class BaseClientMixin(object):
    VIEW_CLASS = NotImplemented

    def _get_data(self, empty_fields=None, **kwargs):
        data = self._get_initial()
        data.update(kwargs)
        if empty_fields is not None:
            for field in empty_fields:
                del data[field]
        return data

    def _req(self, data=None, headers=None, code=200):
        headers = headers or {}
        c = Client()
        if data:
            response = c.post(self._get_url(), data, **headers)
        else:
            response = c.get(self._get_url(), **headers)
        self.assertEqual(response.resolver_match.func.__name__,
                         self.VIEW_CLASS.as_view().__name__)
        self.assertEqual(response.status_code, code)
        return response

    def _check_signals(self, process, success, fail):
        self.assertEqual(process_mock.call_count, process)
        self.assertEqual(success_mock.call_count, success)
        self.assertEqual(fail_mock.call_count, fail)


class BaseViewTestCase(BaseClientMixin):
    ACTION = NotImplemented
    INVOICE_ID = NotImplemented
    MD5 = NotImplemented

    def _get_initial(self):
        return {
            'shopId': TEST_SHOP_ID, 'orderNumber': self.payment.order_id,
            'customerNumber': self.payment.customer_id,
            'paymentType': conf.PAYMENT_TYPE_YANDEX_MONEY,
            'action': self.ACTION, 'md5': self.MD5,
            'invoiceId': self.INVOICE_ID, 'orderSumAmount': '1000.0',
            'orderSumCurrencyPaycash': '643',
            'orderSumBankPaycash': '643', 'shopSumAmount': '975.3',
            'shopSumCurrencyPaycash': '643',
            'paymentPayerCode': '12345678901234567890'
        }

    def test_get_response(self):
        """GET request returns Not Allowed code and changes nothing"""
        self._req(code=405)

        payment = Payment.objects.get(pk=self.payment.id)
        for f in payment._meta.fields:
            self.assertEqual(getattr(payment, f.name),
                             getattr(self.payment, f.name))


@mock.patch('yandex_cash_register.forms.conf',
            new=mock.MagicMock(SHOP_PASSWORD='123456', SHOP_ID=TEST_SHOP_ID))
@mock.patch('yandex_cash_register.views.conf',
            new=mock.MagicMock(SHOP_ID=TEST_SHOP_ID))
class CheckOrderViewTestCase(BaseViewTestCase, TestCase):
    VIEW_CLASS = CheckOrderView
    ACTION = CheckOrderView.accepted_action
    INVOICE_ID = '123456'
    MD5 = '54B30079ACF352701B9CA83A3AC7F640'

    def _get_url(self):
        return '/{}/order-check/'.format(conf.LOCAL_URL)

    def setUp(self):
        self.payment = Payment.objects.create(
            order_sum=Decimal(1000.0), order_id='abcdef',
            cps_email='test@test.com', cps_phone='79991234567',
            payment_type=conf.PAYMENT_TYPE_YANDEX_MONEY,
            customer_id=UUID('0c3c745b-8c7b-4813-8b28-c0a2b037f19c')
        )
        success_mock.reset_mock()
        fail_mock.reset_mock()
        process_mock.reset_mock()

    def test_correct(self):
        """Valid checkOrder request sets required params and returns correct
        response
        """
        response = self._req(self._get_data())

        payment = Payment.objects.get(pk=self.payment.id)
        expected_content = '<?xml version=\'1.0\' encoding=\'UTF-8\'?>\n' \
                           '<checkOrderResponse performedDatetime="{}" ' \
                           'code="0" invoiceId="{}" ' \
                           'shopId="{}"/>'\
            .format(payment.performed.isoformat(), self.INVOICE_ID,
                    TEST_SHOP_ID)
        self.assertEqual(response.content, expected_content.encode('utf-8'))

        self.assertIsNone(payment.completed)
        self.assertIsNotNone(payment.performed)
        self.assertTrue(payment.is_started)
        self.assertFalse(payment.is_completed)
        self.assertFalse(payment.is_payed)
        self.assertEqual(payment.invoice_id, self.INVOICE_ID)
        self.assertEqual(payment.state, Payment.STATE_PROCESSED)
        self.assertEqual(payment.shop_sum, Decimal('975.3'))
        self.assertEqual(payment.payer_code, '12345678901234567890')

        # Проверяем что отправились правильные сигналы
        self._check_signals(1, 0, 0)

    def test_correct_no_payment_type(self):
        """Valid checkOrder request sets required params and returns correct
        response
        """
        self.payment.payment_type = ''
        self.payment.save()

        response = self._req(self._get_data())

        payment = Payment.objects.get(pk=self.payment.id)
        expected_content = '<?xml version=\'1.0\' encoding=\'UTF-8\'?>\n' \
                           '<checkOrderResponse performedDatetime="{}" ' \
                           'code="0" invoiceId="{}" ' \
                           'shopId="{}"/>'\
            .format(payment.performed.isoformat(), self.INVOICE_ID,
                    TEST_SHOP_ID)
        self.assertEqual(response.content, expected_content.encode('utf-8'))

        self.assertIsNone(payment.completed)
        self.assertIsNotNone(payment.performed)
        self.assertTrue(payment.is_started)
        self.assertFalse(payment.is_completed)
        self.assertFalse(payment.is_payed)
        self.assertEqual(payment.invoice_id, self.INVOICE_ID)
        self.assertEqual(payment.state, Payment.STATE_PROCESSED)
        self.assertEqual(payment.shop_sum, Decimal('975.3'))
        self.assertEqual(payment.payer_code, '12345678901234567890')
        self.assertEqual(payment.payment_type, conf.PAYMENT_TYPE_YANDEX_MONEY)

        # Проверяем что отправились правильные сигналы
        self._check_signals(1, 0, 0)

    def test_check_twice(self):
        """Valid checkOrder request fails payment if performed twice"""
        self.test_correct()

        response = self._req(self._get_data())

        payment = Payment.objects.get(pk=self.payment.id)

        self.assertIsNotNone(payment.completed)
        self.assertIsNotNone(payment.performed)
        self.assertTrue(payment.is_completed)
        self.assertFalse(payment.is_payed)
        self.assertEqual(payment.invoice_id, self.INVOICE_ID)
        self.assertEqual(payment.shop_sum, Decimal('975.3'))
        self.assertEqual(payment.payer_code, '12345678901234567890')

        expected_content = '<?xml version=\'1.0\' encoding=\'UTF-8\'?>\n' \
                           '<checkOrderResponse code="200" ' \
                           'message="Ошибка обработки заказа"/>'
        self.assertEqual(response.content, expected_content.encode('utf-8'))

        # Проверяем что отправились правильные сигналы
        self._check_signals(1, 0, 1)

    def test_invalid_form(self):
        """Invalid checkOrder request fails payment and returns error response
        """
        response = self._req(self._get_data(md5='A' * 32))

        payment = Payment.objects.get(pk=self.payment.id)

        self.assertIsNotNone(payment.completed)
        self.assertTrue(payment.is_completed)
        self.assertFalse(payment.is_payed)

        expected_content = '<?xml version=\'1.0\' encoding=\'UTF-8\'?>\n' \
                           '<checkOrderResponse code="1" ' \
                           'message="MD5 is incorrect"/>'
        self.assertEqual(response.content, expected_content.encode('utf-8'))

        # Проверяем что отправились правильные сигналы
        self._check_signals(0, 0, 1)

    def test_wrong_action_in_process(self):
        """Invalid checkOrder request fails payment and returns error response
        """
        response = self._req(
            self._get_data(action='paymentAviso',
                           md5='A436AD4F03575E9FD6167EC3750110D9')
        )

        payment = Payment.objects.get(pk=self.payment.id)

        self.assertIsNotNone(payment.completed)
        self.assertTrue(payment.is_completed)
        self.assertFalse(payment.is_payed)

        expected_content = '<?xml version=\'1.0\' encoding=\'UTF-8\'?>\n' \
                           '<checkOrderResponse code="100" ' \
                           'message="Неожиданный параметр"/>'
        self.assertEqual(response.content, expected_content.encode('utf-8'))

        # Проверяем что отправились правильные сигналы
        self._check_signals(0, 0, 1)

    def test_failed_payment(self):
        """Valid checkOrder request to failed payment and returns error
        response and don't change state
        """
        self.payment.fail()
        self.assertEqual(fail_mock.call_count, 1)

        response = self._req(self._get_data())

        payment = Payment.objects.get(pk=self.payment.id)

        self.assertIsNotNone(payment.completed)
        self.assertTrue(payment.is_completed)
        self.assertFalse(payment.is_payed)

        expected_content = '<?xml version=\'1.0\' encoding=\'UTF-8\'?>\n' \
                           '<checkOrderResponse code="200" ' \
                           'message="Ошибка обработки заказа"/>'
        self.assertEqual(response.content, expected_content.encode('utf-8'))

        # Проверяем что отправились правильные сигналы
        self._check_signals(0, 0, 1)

    def test_succeeded_payment(self):
        """Valid checkOrder request to completed payment and returns error
        response and don't change state
        """
        self.payment.process()
        self.payment.complete()
        self.assertEqual(process_mock.call_count, 1)
        self.assertEqual(success_mock.call_count, 1)

        response = self._req(self._get_data())

        payment = Payment.objects.get(pk=self.payment.id)

        self.assertIsNotNone(payment.performed)
        self.assertIsNotNone(payment.completed)
        self.assertTrue(payment.is_completed)
        self.assertTrue(payment.is_payed)

        expected_content = '<?xml version=\'1.0\' encoding=\'UTF-8\'?>\n' \
                           '<checkOrderResponse code="200" ' \
                           'message="Ошибка обработки заказа"/>'
        self.assertEqual(response.content, expected_content.encode('utf-8'))

        # Проверяем что отправились правильные сигналы
        self._check_signals(1, 1, 0)


@mock.patch('yandex_cash_register.forms.conf',
            new=mock.MagicMock(SHOP_PASSWORD='123456', SHOP_ID=TEST_SHOP_ID))
@mock.patch('yandex_cash_register.views.conf',
            new=mock.MagicMock(SHOP_ID=TEST_SHOP_ID))
class PaymentAvisoViewTestCase(BaseViewTestCase, TestCase):
    VIEW_CLASS = PaymentAvisoView
    ACTION = PaymentAvisoView.accepted_action
    INVOICE_ID = '123456'
    MD5 = 'A436AD4F03575E9FD6167EC3750110D9'

    def _get_url(self):
        return '/{}/payment-aviso/'.format(conf.LOCAL_URL)

    def setUp(self):
        self.payment = Payment.objects.create(
            order_sum=Decimal(1000.0), order_id='abcdef',
            cps_email='test@test.com', cps_phone='79991234567',
            payment_type=conf.PAYMENT_TYPE_YANDEX_MONEY,
            customer_id=UUID('0c3c745b-8c7b-4813-8b28-c0a2b037f19c'),
            invoice_id=self.INVOICE_ID, shop_sum=Decimal('975.3'),
        )
        self.payment.process()

        success_mock.reset_mock()
        fail_mock.reset_mock()
        process_mock.reset_mock()

    def test_correct(self):
        """PaymentAviso correct request should make payment completed, set it's
        state to success and fire success signal
        """
        response = self._req(self._get_data())

        payment = Payment.objects.get(pk=self.payment.id)
        expected_content = '<?xml version=\'1.0\' encoding=\'UTF-8\'?>\n' \
                           '<paymentAvisoResponse performedDatetime="{}" ' \
                           'code="0" invoiceId="{}" ' \
                           'shopId="{}"/>'\
            .format(payment.completed.isoformat(), self.INVOICE_ID,
                    TEST_SHOP_ID)
        self.assertEqual(response.content, expected_content.encode('utf-8'))

        self.assertTrue(payment.completed)
        self.assertTrue(payment.is_payed)
        # Проверяем что отправились правильные сигналы
        self._check_signals(0, 1, 0)

    def _test_already_completed(self, state):
        response = self._req(self._get_data())

        expected_content = '<?xml version=\'1.0\' encoding=\'UTF-8\'?>\n' \
                           '<paymentAvisoResponse code="200" ' \
                           'message="Ошибка обработки заказа"/>'
        self.assertEqual(response.content, expected_content.encode('utf-8'))

        payment = Payment.objects.get(pk=self.payment.id)
        self.assertTrue(payment.is_completed)
        self.assertEqual(payment.state, state)
        # Проверяем что отправились правильные сигналы
        self._check_signals(0, 0, 0)

    def test_already_completed(self):
        """PaymentAviso request to a completed payment should return an error
        and should not change payment state. No signals are fired
        """
        self.payment.complete()
        self.assertEqual(success_mock.call_count, 1)
        success_mock.reset_mock()

        self._test_already_completed(Payment.STATE_SUCCESS)

    def test_already_failed(self):
        """PaymentAviso request to a failed payment should return an error
        and should not change payment state. No signals are fired
        """
        self.payment.fail()
        self.assertEqual(fail_mock.call_count, 1)
        fail_mock.reset_mock()

        self._test_already_completed(Payment.STATE_FAIL)

    def test_double_correct(self):
        self.test_correct()
        success_mock.reset_mock()

        self._test_already_completed(Payment.STATE_SUCCESS)

    def test_double_fail(self):
        self.test_invalid_form()
        fail_mock.reset_mock()

        self._test_already_completed(Payment.STATE_FAIL)

    def test_invalid_form(self):
        """Invalid PaymentAviso request fails payment"""
        response = self._req(self._get_data(md5='A' * 32))

        payment = Payment.objects.get(pk=self.payment.id)

        self.assertTrue(payment.completed)
        self.assertFalse(payment.is_payed)

        expected_content = '<?xml version=\'1.0\' encoding=\'UTF-8\'?>\n' \
                           '<paymentAvisoResponse code="1" ' \
                           'message="MD5 is incorrect"/>'
        self.assertEqual(response.content, expected_content.encode('utf-8'))

        # Проверяем что отправились правильные сигналы
        self._check_signals(0, 0, 1)

    def test_wrong_action_in_process(self):
        """PaymentAviso request with wrong action fails payment"""
        response = self._req(
            self._get_data(action='checkOrder',
                           md5='54B30079ACF352701B9CA83A3AC7F640')
        )

        payment = Payment.objects.get(pk=self.payment.id)

        self.assertTrue(payment.completed)
        self.assertFalse(payment.is_payed)

        expected_content = '<?xml version=\'1.0\' encoding=\'UTF-8\'?>\n' \
                           '<paymentAvisoResponse code="100" ' \
                           'message="Неожиданный параметр"/>'
        self.assertEqual(response.content, expected_content.encode('utf-8'))

        # Проверяем что отправились правильные сигналы
        self._check_signals(0, 0, 1)


class PaymentFinishViewTestCase(BaseClientMixin, TestCase):
    ACTION_SUCCESS = FinalPaymentStateForm.ACTION_CONFIRM
    ACTION_FAIL = FinalPaymentStateForm.ACTION_FAIL
    VIEW_CLASS = PaymentFinishView

    def _get_url(self):
        return '/{}/finish/'.format(conf.LOCAL_URL)

    def setUp(self):
        self.payment = Payment.objects.create(
            order_sum=Decimal(1000.0), order_id='abcdef',
            cps_email='test@test.com', cps_phone='79991234567',
            payment_type=conf.PAYMENT_TYPE_YANDEX_MONEY,
            customer_id=UUID('0c3c745b-8c7b-4813-8b28-c0a2b037f19c')
        )
        success_mock.reset_mock()
        fail_mock.reset_mock()
        process_mock.reset_mock()

    def _get_initial(self):
        return {
            'cr_order_number': self.payment.order_id,
            'cr_action': self.ACTION_SUCCESS,
        }

    @override_settings(DEBUG=False)
    def test_get_response(self):
        """GET request with DEBUG=False is allowed only from correct referrer.
        Otherwise it returns Not Allowed HTTP code
        """
        self._req(headers={'HTTP_REFERER': conf.TARGET})
        self._req(code=405)

    @override_settings(DEBUG=True)
    def test_get_response_debug(self):
        """GET request with DEBUG=False is allowed from any referrer"""
        self._req()

    def test_invalid_payment(self):
        """GET request with DEBUG=False is allowed from any referrer"""
        response = self._req(self._get_data(empty_fields=['cr_order_number']),
                             code=302)
        if response['Location'].startswith('http://testserver'):
            response['Location'] = response['Location'][17:]
        self.assertEqual(response['Location'], '/')

    @mock.patch('yandex_cash_register.views.apps')
    def test_valid_not_started(self, m_apps):
        """Success request is not valid if payment is not performed.
        Payment state is not changed
        """
        m_order = mock.MagicMock()
        m_order.get_absolute_url.return_value = '/order/'
        m_model = mock.MagicMock()
        m_model.get_by_order_id.return_value = m_order
        m_apps.get_model.return_value = m_model

        response = self._req(self._get_data(), code=302)
        if response['Location'].startswith('http://testserver'):
            response['Location'] = response['Location'][17:]
        self.assertEqual(response['Location'], '/order/')

        payment = Payment.objects.get(pk=self.payment.id)
        m_apps.get_model.assert_called_once_with(*conf.MODEL)
        m_model.get_by_order_id.assert_called_once_with(self.payment.order_id)
        self.assertEqual(m_order.get_absolute_url.call_count, 1)

        self.assertEqual(payment.state, self.payment.state)
        self.assertFalse(payment.is_completed)
        self.assertFalse(payment.is_payed)
        self.assertFalse(payment.is_started)

        # Проверяем что отправились правильные сигналы
        self._check_signals(0, 0, 0)

    @mock.patch('yandex_cash_register.views.apps')
    def test_valid_success(self, m_apps):
        """Success request is valid even if payment is performed but not
        completed. Payment state is not changed
        """
        m_order = mock.MagicMock()
        m_order.get_payment_complete_url.return_value = '/order/url/'
        m_model = mock.MagicMock()
        m_model.get_by_order_id.return_value = m_order
        m_apps.get_model.return_value = m_model

        self.payment.process()
        process_mock.reset_mock()

        response = self._req(self._get_data(), code=302)
        if response['Location'].startswith('http://testserver'):
            response['Location'] = response['Location'][17:]
        self.assertEqual(response['Location'], '/order/url/')

        m_apps.get_model.assert_called_once_with(*conf.MODEL)
        m_model.get_by_order_id.assert_called_once_with(self.payment.order_id)
        m_order.get_payment_complete_url.assert_called_once_with(True)

        payment = Payment.objects.get(pk=self.payment.id)
        self.assertEqual(payment.state, self.payment.state)
        self.assertFalse(payment.is_completed)
        self.assertFalse(payment.is_payed)
        self.assertTrue(payment.is_started)

        # Проверяем что отправились правильные сигналы
        self._check_signals(0, 0, 0)

    @mock.patch('yandex_cash_register.views.apps')
    def test_valid_already_success(self, m_apps):
        """Success request is valid if payment is completed. Payment state is
        not changed
        """
        m_order = mock.MagicMock()
        m_order.get_absolute_url.return_value = '/order/url/'
        m_model = mock.MagicMock()
        m_model.get_by_order_id.return_value = m_order
        m_apps.get_model.return_value = m_model

        self.payment.process()
        self.payment.complete()
        process_mock.reset_mock()
        success_mock.reset_mock()

        response = self._req(self._get_data(), code=302)
        if response['Location'].startswith('http://testserver'):
            response['Location'] = response['Location'][17:]
        self.assertEqual(response['Location'], '/order/url/')

        m_apps.get_model.assert_called_once_with(*conf.MODEL)
        m_model.get_by_order_id.assert_called_once_with(self.payment.order_id)
        self.assertEqual(m_order.get_absolute_url.call_count, 1)

        payment = Payment.objects.get(pk=self.payment.id)
        self.assertTrue(payment.is_completed)
        self.assertTrue(payment.is_payed)
        self.assertTrue(payment.is_started)

        # Проверяем что отправились правильные сигналы
        self._check_signals(0, 0, 0)

    @mock.patch('yandex_cash_register.views.apps')
    def test_valid_fail_not_started(self, m_apps):
        """Fail request is not valid if payment is not performed.
        Payment state is not changed
        """
        m_order = mock.MagicMock()
        m_order.get_absolute_url.return_value = '/order/'
        m_model = mock.MagicMock()
        m_model.get_by_order_id.return_value = m_order
        m_apps.get_model.return_value = m_model

        response = self._req(self._get_data(cr_action=self.ACTION_FAIL),
                             code=302)
        if response['Location'].startswith('http://testserver'):
            response['Location'] = response['Location'][17:]
        self.assertEqual(response['Location'], '/order/')

        payment = Payment.objects.get(pk=self.payment.id)
        m_apps.get_model.assert_called_once_with(*conf.MODEL)
        m_model.get_by_order_id.assert_called_once_with(self.payment.order_id)
        self.assertEqual(m_order.get_absolute_url.call_count, 1)

        self.assertEqual(payment.state, self.payment.state)
        self.assertFalse(payment.is_completed)
        self.assertFalse(payment.is_payed)
        self.assertFalse(payment.is_started)

        # Проверяем что отправились правильные сигналы
        self._check_signals(0, 0, 0)

    @mock.patch('yandex_cash_register.views.apps')
    def test_valid_fail(self, m_apps):
        """Fail request is valid even if payment is performed but not
        completed. Payment state is changed to failed
        """
        m_order = mock.MagicMock()
        m_order.get_absolute_url.return_value = '/order/url/'
        m_model = mock.MagicMock()
        m_model.get_by_order_id.return_value = m_order
        m_apps.get_model.return_value = m_model

        self.payment.process()
        process_mock.reset_mock()

        response = self._req(self._get_data(cr_action=self.ACTION_FAIL),
                             code=302)
        if response['Location'].startswith('http://testserver'):
            response['Location'] = response['Location'][17:]
        self.assertEqual(response['Location'], '/order/url/')

        m_apps.get_model.assert_called_once_with(*conf.MODEL)
        m_model.get_by_order_id.assert_called_once_with(self.payment.order_id)
        self.assertEqual(m_order.get_absolute_url.call_count, 1)

        payment = Payment.objects.get(pk=self.payment.id)
        self.assertTrue(payment.is_completed)
        self.assertFalse(payment.is_payed)
        self.assertTrue(payment.is_started)

        # Проверяем что отправились правильные сигналы
        self._check_signals(0, 0, 1)

    @mock.patch('yandex_cash_register.views.apps')
    def test_valid_already_fail(self, m_apps):
        """Fail request is valid if payment is failed. Payment state is
        not changed
        """
        m_order = mock.MagicMock()
        m_order.get_absolute_url.return_value = '/order/url/'
        m_model = mock.MagicMock()
        m_model.get_by_order_id.return_value = m_order
        m_apps.get_model.return_value = m_model

        self.payment.process()
        self.payment.fail()
        process_mock.reset_mock()
        fail_mock.reset_mock()

        response = self._req(self._get_data(cr_action=self.ACTION_FAIL),
                             code=302)
        if response['Location'].startswith('http://testserver'):
            response['Location'] = response['Location'][17:]
        self.assertEqual(response['Location'], '/order/url/')

        m_apps.get_model.assert_called_once_with(*conf.MODEL)
        m_model.get_by_order_id.assert_called_once_with(self.payment.order_id)
        self.assertEqual(m_order.get_absolute_url.call_count, 1)

        payment = Payment.objects.get(pk=self.payment.id)
        self.assertTrue(payment.is_completed)
        self.assertFalse(payment.is_payed)
        self.assertTrue(payment.is_started)

        # Проверяем что отправились правильные сигналы
        self._check_signals(0, 0, 0)

    @mock.patch('yandex_cash_register.views.apps')
    def test_success_with_no_order(self, m_apps):
        """Success request with no order fails a payment"""
        m_model = mock.MagicMock()
        m_model.get_by_order_id.return_value = None
        m_apps.get_model.return_value = m_model

        response = self._req(self._get_data(), code=302)
        if response['Location'].startswith('http://testserver'):
            response['Location'] = response['Location'][17:]
        self.assertEqual(response['Location'], '/')

        m_apps.get_model.assert_called_once_with(*conf.MODEL)
        m_model.get_by_order_id.assert_called_once_with(self.payment.order_id)

        payment = Payment.objects.get(pk=self.payment.id)
        self.assertEqual(payment.state, self.payment.state)

        # Проверяем что отправились правильные сигналы
        self._check_signals(0, 0, 0)

    @mock.patch('yandex_cash_register.views.apps')
    def test_failreq_already_success(self, m_apps):
        """Fail request is valid if payment is completed. Payment state
        is not changed
        """
        m_order = mock.MagicMock()
        m_order.get_absolute_url.return_value = '/order/'
        m_model = mock.MagicMock()
        m_model.get_by_order_id.return_value = m_order
        m_apps.get_model.return_value = m_model

        self.payment.process()
        self.payment.complete()
        process_mock.reset_mock()
        success_mock.reset_mock()

        response = self._req(self._get_data(cr_action=self.ACTION_FAIL),
                             code=302)
        if response['Location'].startswith('http://testserver'):
            response['Location'] = response['Location'][17:]
        self.assertEqual(response['Location'], '/order/')

        m_apps.get_model.assert_called_once_with(*conf.MODEL)
        m_model.get_by_order_id.assert_called_once_with(self.payment.order_id)
        self.assertEqual(m_order.get_absolute_url.call_count, 1)

        payment = Payment.objects.get(pk=self.payment.id)
        self.assertTrue(payment.is_completed)
        self.assertTrue(payment.is_payed)
        self.assertTrue(payment.is_started)

        # Проверяем что отправились правильные сигналы
        self._check_signals(0, 0, 0)

    @mock.patch('yandex_cash_register.views.apps')
    def test_successrec_already_fail(self, m_apps):
        """Success request is valid if payment is failed. Payment state
        is not changed
        """
        m_order = mock.MagicMock()
        m_order.get_absolute_url.return_value = '/order/'
        m_model = mock.MagicMock()
        m_model.get_by_order_id.return_value = m_order
        m_apps.get_model.return_value = m_model

        self.payment.process()
        self.payment.fail()
        process_mock.reset_mock()
        fail_mock.reset_mock()

        response = self._req(self._get_data(cr_action=self.ACTION_FAIL),
                             code=302)
        if response['Location'].startswith('http://testserver'):
            response['Location'] = response['Location'][17:]
        self.assertEqual(response['Location'], '/order/')

        m_apps.get_model.assert_called_once_with(*conf.MODEL)
        m_model.get_by_order_id.assert_called_once_with(self.payment.order_id)
        self.assertEqual(m_order.get_absolute_url.call_count, 1)

        payment = Payment.objects.get(pk=self.payment.id)
        self.assertTrue(payment.is_completed)
        self.assertFalse(payment.is_payed)
        self.assertTrue(payment.is_started)

        # Проверяем что отправились правильные сигналы
        self._check_signals(0, 0, 0)

    @mock.patch('yandex_cash_register.views.apps')
    def test_invalid_form_redirects_to_model(self, m_apps):
        """Invalid form redirects to model if it can. Payment is not changed"""
        m_order = mock.MagicMock()
        m_order.get_absolute_url.return_value = '/order/'
        m_model = mock.MagicMock()
        m_model.get_by_order_id.return_value = m_order
        m_apps.get_model.return_value = m_model

        response = self._req(self._get_data(empty_fields=['cr_action']),
                             code=302)
        if response['Location'].startswith('http://testserver'):
            response['Location'] = response['Location'][17:]
        self.assertEqual(response['Location'], '/order/')

        m_apps.get_model.assert_called_once_with(*conf.MODEL)
        m_model.get_by_order_id.assert_called_once_with(self.payment.order_id)
        self.assertEqual(m_order.get_absolute_url.call_count, 1)

        payment = Payment.objects.get(pk=self.payment.id)
        for f in payment._meta.fields:
            self.assertEqual(getattr(payment, f.name),
                             getattr(self.payment, f.name))

        # Проверяем что отправились правильные сигналы
        self._check_signals(0, 0, 0)

    def test_invalid_form_redirects_to_root(self):
        """Invalid form redirects to / if it cannot find payment."""
        response = self._req(self._get_data(empty_fields=['cr_order_number']),
                             code=302)
        if response['Location'].startswith('http://testserver'):
            response['Location'] = response['Location'][17:]
        self.assertEqual(response['Location'], '/')

        payment = Payment.objects.get(pk=self.payment.id)
        for f in payment._meta.fields:
            self.assertEqual(getattr(payment, f.name),
                             getattr(self.payment, f.name))

        # Проверяем что отправились правильные сигналы
        self._check_signals(0, 0, 0)
