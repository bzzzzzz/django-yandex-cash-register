# coding=utf-8
from __future__ import absolute_import, unicode_literals

from decimal import Decimal
from unittest import mock
from uuid import UUID

from django.test import TestCase, Client, override_settings

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

    def _req(self, data=None, headers=None):
        headers = headers or {}
        c = Client()
        if data:
            response = c.post(self._get_url(), data, **headers)
        else:
            response = c.get(self._get_url(), **headers)
        self.assertEqual(response.resolver_match.func.__name__,
                         self.VIEW_CLASS.as_view().__name__)
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
        response = self._req()
        self.assertEqual(response.status_code, 405)

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
        response = self._req(self._get_data())
        self.assertEqual(response.status_code, 200)

        payment = Payment.objects.get(pk=self.payment.id)
        expected_content = '<?xml version=\'1.0\' encoding=\'UTF-8\'?>\n' \
                           '<checkOrderResponse performedDatetime="{}" ' \
                           'code="0" invoiceId="{}" ' \
                           'shopId="{}"/>'\
            .format(payment.performed.isoformat(), self.INVOICE_ID,
                    TEST_SHOP_ID)
        self.assertEqual(response.content, expected_content.encode('utf-8'))

        self.assertIsNone(payment.completed)
        self.assertEqual(payment.invoice_id, self.INVOICE_ID)
        self.assertEqual(payment.state, Payment.STATE_PROCESSED)
        self.assertEqual(payment.shop_sum, Decimal('975.3'))
        self.assertEqual(payment.payer_code, '12345678901234567890')

        # Проверяем что отправились правильные сигналы
        self._check_signals(1, 0, 0)

    def test_check_twice(self):
        self.test_correct()

        response = self._req(self._get_data())
        self.assertEqual(response.status_code, 200)

        payment = Payment.objects.get(pk=self.payment.id)
        self.assertEqual(payment.state, Payment.STATE_FAIL)
        self.assertIsNotNone(payment.completed)
        expected_content = '<?xml version=\'1.0\' encoding=\'UTF-8\'?>\n' \
                           '<checkOrderResponse code="200" ' \
                           'message="Ошибка обработки заказа"/>'
        self.assertEqual(response.content, expected_content.encode('utf-8'))

        # Проверяем что отправились правильные сигналы
        self._check_signals(1, 0, 1)

    def test_invalid_form(self):
        response = self._req(self._get_data(md5='A' * 32))
        self.assertEqual(response.status_code, 200)

        payment = Payment.objects.get(pk=self.payment.id)

        self.assertIsNotNone(payment.completed)
        self.assertEqual(payment.state, Payment.STATE_FAIL)

        expected_content = '<?xml version=\'1.0\' encoding=\'UTF-8\'?>\n' \
                           '<checkOrderResponse code="1" ' \
                           'message="Неверный MD5 код в запросе"/>'
        self.assertEqual(response.content, expected_content.encode('utf-8'))

        # Проверяем что отправились правильные сигналы
        self._check_signals(0, 0, 1)

    def test_wrong_action_in_process(self):
        response = self._req(
            self._get_data(action='paymentAviso',
                           md5='A436AD4F03575E9FD6167EC3750110D9')
        )
        self.assertEqual(response.status_code, 200)

        payment = Payment.objects.get(pk=self.payment.id)

        self.assertIsNotNone(payment.completed)
        self.assertEqual(payment.state, Payment.STATE_FAIL)

        expected_content = '<?xml version=\'1.0\' encoding=\'UTF-8\'?>\n' \
                           '<checkOrderResponse code="100" ' \
                           'message="Неожиданный параметр"/>'
        self.assertEqual(response.content, expected_content.encode('utf-8'))

        # Проверяем что отправились правильные сигналы
        self._check_signals(0, 0, 1)

    def test_failed_payment(self):
        self.payment.fail()
        self.assertEqual(fail_mock.call_count, 1)

        response = self._req(self._get_data())
        self.assertEqual(response.status_code, 200)

        payment = Payment.objects.get(pk=self.payment.id)
        self.assertEqual(payment.state, Payment.STATE_FAIL)

        expected_content = '<?xml version=\'1.0\' encoding=\'UTF-8\'?>\n' \
                           '<checkOrderResponse code="200" ' \
                           'message="Ошибка обработки заказа"/>'
        self.assertEqual(response.content, expected_content.encode('utf-8'))

        # Проверяем что отправились правильные сигналы
        self._check_signals(0, 0, 1)

    def test_succeeded_payment(self):
        self.payment.process()
        self.payment.complete()
        self.assertEqual(process_mock.call_count, 1)
        self.assertEqual(success_mock.call_count, 1)

        response = self._req(self._get_data())
        self.assertEqual(response.status_code, 200)

        payment = Payment.objects.get(pk=self.payment.id)
        self.assertEqual(payment.state, Payment.STATE_SUCCESS)

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
        response = self._req(self._get_data())
        self.assertEqual(response.status_code, 200)

        payment = Payment.objects.get(pk=self.payment.id)
        expected_content = '<?xml version=\'1.0\' encoding=\'UTF-8\'?>\n' \
                           '<paymentAvisoResponse performedDatetime="{}" ' \
                           'code="0" invoiceId="{}" ' \
                           'shopId="{}"/>'\
            .format(payment.completed.isoformat(), self.INVOICE_ID,
                    TEST_SHOP_ID)
        self.assertEqual(response.content, expected_content.encode('utf-8'))

        self.assertIsNotNone(payment.completed)
        self.assertEqual(payment.state, Payment.STATE_SUCCESS)
        # Проверяем что отправились правильные сигналы
        self._check_signals(0, 1, 0)

    def test_triple(self):
        for i in range(3):
            self.test_correct()

    def test_invalid_form(self):
        response = self._req(self._get_data(md5='A' * 32))
        self.assertEqual(response.status_code, 200)

        payment = Payment.objects.get(pk=self.payment.id)

        self.assertIsNotNone(payment.completed)
        self.assertEqual(payment.state, Payment.STATE_FAIL)

        expected_content = '<?xml version=\'1.0\' encoding=\'UTF-8\'?>\n' \
                           '<paymentAvisoResponse code="1" ' \
                           'message="Неверный MD5 код в запросе"/>'
        self.assertEqual(response.content, expected_content.encode('utf-8'))

        # Проверяем что отправились правильные сигналы
        self._check_signals(0, 0, 1)

    def test_wrong_action_in_process(self):
        response = self._req(
            self._get_data(action='checkOrder',
                           md5='54B30079ACF352701B9CA83A3AC7F640')
        )
        self.assertEqual(response.status_code, 200)

        payment = Payment.objects.get(pk=self.payment.id)

        self.assertIsNotNone(payment.completed)
        self.assertEqual(payment.state, Payment.STATE_FAIL)

        expected_content = '<?xml version=\'1.0\' encoding=\'UTF-8\'?>\n' \
                           '<paymentAvisoResponse code="100" ' \
                           'message="Неожиданный параметр"/>'
        self.assertEqual(response.content, expected_content.encode('utf-8'))

        # Проверяем что отправились правильные сигналы
        self._check_signals(0, 0, 1)

    def test_failed_payment(self):
        self.payment.fail()
        self.assertEqual(fail_mock.call_count, 1)
        fail_mock.reset_mock()

        self.test_correct()

    def test_failed_and_unprocessed_payment(self):
        self.payment.fail()
        self.assertEqual(fail_mock.call_count, 1)
        fail_mock.reset_mock()
        self.payment.performed = None
        self.payment.save()

        response = self._req(self._get_data())
        self.assertEqual(response.status_code, 200)

        payment = Payment.objects.get(pk=self.payment.id)

        self.assertIsNotNone(payment.completed)
        self.assertEqual(payment.state, Payment.STATE_FAIL)

        expected_content = '<?xml version=\'1.0\' encoding=\'UTF-8\'?>\n' \
                           '<paymentAvisoResponse code="200" ' \
                           'message="Ошибка обработки заказа"/>'
        self.assertEqual(response.content, expected_content.encode('utf-8'))

        # Проверяем что отправились правильные сигналы
        self._check_signals(0, 0, 0)


class PaymentFinishViewTestCase(BaseClientMixin, TestCase):
    ACTION_SUCCESS = 'PaymentSuccess'
    ACTION_FAIL = 'PaymentFail'
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
            'shopId': conf.SHOP_ID, 'orderNumber': self.payment.order_id,
            'customerNumber': self.payment.customer_id,
            'paymentType': conf.PAYMENT_TYPE_YANDEX_MONEY,
            'action': self.ACTION_SUCCESS,
        }

    @override_settings(DEBUG=False)
    def test_get_response(self):
        response = self._req()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/')
        response = self._req(headers={'HTTP_REFERER': conf.TARGET})
        self.assertEqual(response.status_code, 200)

    @override_settings(DEBUG=True)
    def test_get_response_debug(self):
        response = self._req()
        self.assertEqual(response.status_code, 200)

    def test_invalid_payment(self):
        response = self._req(self._get_data(empty_fields=['orderNumber']))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/')

    @mock.patch('yandex_cash_register.views.apps')
    def test_invalid_with_valid_payment_no_order(self, m_apps):
        m_model = mock.MagicMock()
        m_model.get_by_order_id.return_value = None
        m_apps.get_model.return_value = m_model

        response = self._req(self._get_data(empty_fields=['shopId']))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/')

        m_apps.get_model.assert_called_once_with(*conf.MODEL)
        m_model.get_by_order_id.assert_called_once_with(self.payment.order_id)

        payment = Payment.objects.get(pk=self.payment.id)
        self.assertEqual(payment.state, payment.STATE_FAIL)

        # Проверяем что отправились правильные сигналы
        self._check_signals(0, 0, 1)

    @mock.patch('yandex_cash_register.views.apps')
    def test_invalid_with_valid_payment(self, m_apps):
        m_order = mock.MagicMock()
        m_order.get_payment_complete_url.return_value = '/order/url/'
        m_model = mock.MagicMock()
        m_model.get_by_order_id.return_value = m_order
        m_apps.get_model.return_value = m_model

        response = self._req(self._get_data(empty_fields=['shopId']))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/order/url/')

        m_apps.get_model.assert_called_once_with(*conf.MODEL)
        m_model.get_by_order_id.assert_called_once_with(self.payment.order_id)
        m_order.get_payment_complete_url.assert_called_once_with(False)

        payment = Payment.objects.get(pk=self.payment.id)
        self.assertEqual(payment.state, payment.STATE_FAIL)

        # Проверяем что отправились правильные сигналы
        self._check_signals(0, 0, 1)

    @mock.patch('yandex_cash_register.views.apps')
    def test_invalid_with_valid_success_payment(self, m_apps):
        m_order = mock.MagicMock()
        m_order.get_payment_complete_url.return_value = '/order/url/'
        m_model = mock.MagicMock()
        m_model.get_by_order_id.return_value = m_order
        m_apps.get_model.return_value = m_model

        self.payment.process()
        self.payment.complete()

        response = self._req(self._get_data(empty_fields=['shopId']))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/order/url/')

        m_apps.get_model.assert_called_once_with(*conf.MODEL)
        m_model.get_by_order_id.assert_called_once_with(self.payment.order_id)
        m_order.get_payment_complete_url.assert_called_once_with(False)

        payment = Payment.objects.get(pk=self.payment.id)
        self.assertEqual(payment.state, payment.STATE_SUCCESS)

        # Проверяем что отправились правильные сигналы
        self._check_signals(1, 1, 0)

    @mock.patch('yandex_cash_register.views.apps')
    def test_invalid_with_valid_processed_payment(self, m_apps):
        m_order = mock.MagicMock()
        m_order.get_payment_complete_url.return_value = '/order/url/'
        m_model = mock.MagicMock()
        m_model.get_by_order_id.return_value = m_order
        m_apps.get_model.return_value = m_model

        self.payment.process()

        response = self._req(self._get_data(empty_fields=['shopId']))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/order/url/')

        m_apps.get_model.assert_called_once_with(*conf.MODEL)
        m_model.get_by_order_id.assert_called_once_with(self.payment.order_id)
        m_order.get_payment_complete_url.assert_called_once_with(False)

        payment = Payment.objects.get(pk=self.payment.id)
        self.assertEqual(payment.state, payment.STATE_FAIL)

        # Проверяем что отправились правильные сигналы
        self._check_signals(1, 0, 1)

    @mock.patch('yandex_cash_register.views.apps')
    def test_invalid_with_valid_failed_payment(self, m_apps):
        m_order = mock.MagicMock()
        m_order.get_payment_complete_url.return_value = '/order/url/'
        m_model = mock.MagicMock()
        m_model.get_by_order_id.return_value = m_order
        m_apps.get_model.return_value = m_model

        self.payment.process()
        self.payment.fail()

        response = self._req(self._get_data(empty_fields=['shopId']))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/order/url/')

        m_apps.get_model.assert_called_once_with(*conf.MODEL)
        m_model.get_by_order_id.assert_called_once_with(self.payment.order_id)
        m_order.get_payment_complete_url.assert_called_once_with(False)

        payment = Payment.objects.get(pk=self.payment.id)
        self.assertEqual(payment.state, payment.STATE_FAIL)

        # Проверяем что отправились правильные сигналы
        self._check_signals(1, 0, 1)

    @mock.patch('yandex_cash_register.views.apps')
    def test_valid_success(self, m_apps):
        m_order = mock.MagicMock()
        m_order.get_payment_complete_url.return_value = '/order/url/'
        m_model = mock.MagicMock()
        m_model.get_by_order_id.return_value = m_order
        m_apps.get_model.return_value = m_model

        response = self._req(self._get_data())
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/order/url/')

        m_apps.get_model.assert_called_once_with(*conf.MODEL)
        m_model.get_by_order_id.assert_called_once_with(self.payment.order_id)
        m_order.get_payment_complete_url.assert_called_once_with(True)

        payment = Payment.objects.get(pk=self.payment.id)
        self.assertEqual(payment.state, self.payment.state)

        # Проверяем что отправились правильные сигналы
        self._check_signals(0, 0, 0)

    @mock.patch('yandex_cash_register.views.apps')
    def test_valid_fail(self, m_apps):
        m_order = mock.MagicMock()
        m_order.get_payment_complete_url.return_value = '/order/url/'
        m_model = mock.MagicMock()
        m_model.get_by_order_id.return_value = m_order
        m_apps.get_model.return_value = m_model

        response = self._req(self._get_data(action=self.ACTION_FAIL))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/order/url/')

        m_apps.get_model.assert_called_once_with(*conf.MODEL)
        m_model.get_by_order_id.assert_called_once_with(self.payment.order_id)
        m_order.get_payment_complete_url.assert_called_once_with(False)

        payment = Payment.objects.get(pk=self.payment.id)
        self.assertEqual(payment.state, payment.STATE_FAIL)

        # Проверяем что отправились правильные сигналы
        self._check_signals(0, 0, 1)

    @mock.patch('yandex_cash_register.views.apps')
    def test_valid_already_success(self, m_apps):
        m_order = mock.MagicMock()
        m_order.get_payment_complete_url.return_value = '/order/url/'
        m_model = mock.MagicMock()
        m_model.get_by_order_id.return_value = m_order
        m_apps.get_model.return_value = m_model

        self.payment.process()
        self.payment.complete()

        response = self._req(self._get_data())
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/order/url/')

        m_apps.get_model.assert_called_once_with(*conf.MODEL)
        m_model.get_by_order_id.assert_called_once_with(self.payment.order_id)
        m_order.get_payment_complete_url.assert_called_once_with(True)

        payment = Payment.objects.get(pk=self.payment.id)
        self.assertEqual(payment.state, payment.STATE_SUCCESS)

        # Проверяем что отправились правильные сигналы
        self._check_signals(1, 1, 0)

    @mock.patch('yandex_cash_register.views.apps')
    def test_valid_already_fail(self, m_apps):
        m_order = mock.MagicMock()
        m_order.get_payment_complete_url.return_value = '/order/url/'
        m_model = mock.MagicMock()
        m_model.get_by_order_id.return_value = m_order
        m_apps.get_model.return_value = m_model

        self.payment.process()
        self.payment.fail()

        response = self._req(self._get_data())
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/order/url/')

        m_apps.get_model.assert_called_once_with(*conf.MODEL)
        m_model.get_by_order_id.assert_called_once_with(self.payment.order_id)
        m_order.get_payment_complete_url.assert_called_once_with(False)

        payment = Payment.objects.get(pk=self.payment.id)
        self.assertEqual(payment.state, payment.STATE_FAIL)

        # Проверяем что отправились правильные сигналы
        self._check_signals(1, 0, 1)
