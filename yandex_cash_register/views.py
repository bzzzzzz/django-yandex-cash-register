# coding=utf-8
from __future__ import absolute_import, unicode_literals

from decimal import Decimal

from collections import OrderedDict
import logging

from django.apps import apps
from django.conf import settings
from django.db import transaction
from django.shortcuts import redirect
from django.http import HttpResponse, HttpResponseNotAllowed
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import FormView
from lxml import etree
from lxml.builder import E

from .forms import PaymentProcessingForm, FinalPaymentStateForm
from .models import Payment
from . import conf


logger = logging.getLogger(__name__)


class BaseFormView(FormView):
    form_class = PaymentProcessingForm
    accepted_action = None

    @method_decorator(csrf_exempt)
    @method_decorator(transaction.atomic)
    def dispatch(self, request, *args, **kwargs):
        return super(BaseFormView, self).dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        return HttpResponseNotAllowed(['POST'])

    def get_response(self, params):
        if 'code' not in params:
            params['code'] = 0

        for key in params:
            try:
                params[key] = str(params[key])
            except UnicodeEncodeError:
                pass

        content = getattr(E, '{}Response'.format(self.accepted_action))()
        for key, value in params.items():
            content.attrib[key] = value
        data = etree.tostring(content, xml_declaration=True, encoding='UTF-8',
                              method='xml')
        logger.info('Response: %r', data)
        return HttpResponse(data, content_type='application/xml')

    def form_invalid(self, form):
        """
        :type form: yandex_cash_register.forms.PaymentProcessingForm
        """
        logger.info('Error when validating payment form')
        logger.info('Form data: %s', dict(form.cleaned_data))
        if form.errors:
            logger.info('%s', dict(form.errors))

        # Устанавливаем статус в FAIL
        payment = form.payment_obj
        if payment is not None:
            try:
                if not payment.is_completed:
                    payment.fail()
            except Exception:
                logger.exception('Error when saving payment form')

        return self.get_response(
            OrderedDict((('code', form.error_code),
                         ('message', form.error_message)))
        )

    def form_valid(self, form):
        """
        :type form: yandex_cash_register.forms.PaymentProcessingForm
        """
        logger.info('Payment form validated correctly')
        logger.info('Form data: %s', dict(form.cleaned_data))

        action = form.cleaned_data['action']
        if action != self.accepted_action:
            form.set_error(PaymentProcessingForm.ERROR_CODE_UNKNOWN_ORDER,
                           'Неожиданный параметр')
            return self.form_invalid(form)

        order_num = form.cleaned_data['customerNumber']

        payment = form.payment_obj
        try:
            if payment.is_completed:
                raise RuntimeError('Payment is already completed')
            self.process(payment, form.cleaned_data)

            logger.info('Successful request to payment #%s', payment.order_id)

            # Key order is important, they say
            response_dict = OrderedDict()
            if payment.completed is None:
                response_dict['performedDatetime'] = \
                    payment.performed.isoformat()
            else:
                response_dict['performedDatetime'] = \
                    payment.completed.isoformat()
            response_dict['code'] = 0
            response_dict['invoiceId'] = payment.invoice_id
            response_dict['shopId'] = conf.SHOP_ID
        except Exception:
            msg = 'Error when processing payment #%s' % order_num
            logger.warn(msg, exc_info=True)
            form.set_error(PaymentProcessingForm.ERROR_CODE_INTERNAL,
                           'Ошибка обработки заказа')
            return self.form_invalid(form)

        return self.get_response(response_dict)

    def process(self, payment, data):
        """
        :type payment: yandex_cash_register.models.Payment
        :type data: dict[str]
        """
        raise NotImplementedError()


class CheckOrderView(BaseFormView):
    accepted_action = PaymentProcessingForm.ACTION_CHECK

    def process(self, payment, data):
        """
        :type payment: yandex_cash_register.models.Payment
        :type data: dict[str]
        """
        logger.info('Request to check payment #%s', payment.order_id)
        if payment.state == Payment.STATE_CREATED:
            payment.payer_code = data.get('paymentPayerCode', '')
            payment.order_currency = data['orderSumCurrencyPaycash']
            payment.shop_sum = Decimal(data['shopSumAmount'])
            payment.shop_currency = data['shopSumCurrencyPaycash']
            payment.invoice_id = data['invoiceId']
            if not payment.payment_type:
                payment.payment_type = data['paymentType']

            payment.process()
        else:
            raise RuntimeError('Payment is already completed')


class PaymentAvisoView(BaseFormView):
    accepted_action = PaymentProcessingForm.ACTION_CPAYMENT

    def process(self, payment, data):
        """
        :type payment: yandex_cash_register.models.Payment
        :type data: dict[str]
        """
        logger.info('Request to confirm payment #%s', payment.order_id)
        if payment.state != Payment.STATE_SUCCESS:
            payment.complete()


class PaymentFinishView(FormView):
    form_class = FinalPaymentStateForm
    template_name = 'yandex_cash_register/finish_payment.html'

    @method_decorator(csrf_exempt)
    @method_decorator(transaction.atomic)
    def dispatch(self, request, *args, **kwargs):
        return super(PaymentFinishView, self).dispatch(request, *args,
                                                       **kwargs)

    def get(self, request, *args, **kwargs):
        if not request.META.get(
                'HTTP_REFERER', '').startswith(conf.MONEY_URL) and \
                not settings.DEBUG:
            return HttpResponseNotAllowed(['POST'])
        return super(PaymentFinishView, self).get(request, *args, **kwargs)

    def get_initial(self):
        if self.request.method == 'GET':
            return self.request.GET
        return super(PaymentFinishView, self).get_initial()

    @staticmethod
    def _generate_response(payment, success=None):
        """
        :type payment: yandex_cash_register.models.Payment
        :type success: bool
        """
        # If success is defined as False and payment is not completed - fail it
        if success is not None and not success and not payment.is_completed:
            logger.info('Setting state to fail, order #%s', payment.order_id)
            payment.fail()

        model = apps.get_model(*conf.MODEL)
        order = model.get_by_order_id(payment.order_id)

        if order is None:
            return redirect('/')
        if success is None or payment.is_completed:
            url = order.get_absolute_url()
        else:
            url = order.get_payment_complete_url(success)
        return redirect(url)

    def form_valid(self, form):
        """
        :type form: yandex_cash_register.forms.FinalPaymentStateForm
        """
        logger.info('Form is valid: %s', dict(form.cleaned_data))
        action = form.cleaned_data['cr_action']
        payment = form.payment_obj
        if payment is None:
            return redirect('/')

        if not payment.is_started:
            return self._generate_response(payment)
        if payment.state in (Payment.STATE_SUCCESS, Payment.STATE_FAIL):
            success = payment.state == Payment.STATE_SUCCESS
        else:
            if action == form.ACTION_CONFIRM:
                success = True
            else:
                success = False
        return self._generate_response(payment, success)

    def form_invalid(self, form):
        logger.info('Form is invalid: %s', dict(form.cleaned_data))
        payment = form.payment_obj
        if payment is not None:
            return self._generate_response(payment)
        else:
            return redirect('/')
