# coding=utf-8
from __future__ import absolute_import, unicode_literals

import uuid

from django.conf import settings
from django.core.urlresolvers import reverse
from django.db import models
from django.utils.encoding import python_2_unicode_compatible
from django.utils.timezone import now

from . import conf
from .forms import PaymentForm, FinalPaymentStateForm
from .signals import payment_process, payment_success, payment_fail


@python_2_unicode_compatible
class Payment(models.Model):
    STATE_CREATED = 'created'
    STATE_PROCESSED = 'processed'
    STATE_SUCCESS = 'success'
    STATE_FAIL = 'fail'
    STATE_CHOICES = (
        (STATE_CREATED, 'Created'),
        (STATE_PROCESSED, 'Processed'),
        (STATE_SUCCESS, 'Success'),
        (STATE_FAIL, 'Fail'),
    )

    CURRENCY_RUB = 643
    CURRENCY_TEST = 10643

    CURRENCY_CHOICES = (
        (CURRENCY_RUB, 'Рубли'),
        (CURRENCY_TEST, 'Тестовая валюта'),
    )

    user = models.ForeignKey(settings.AUTH_USER_MODEL, blank=True, null=True,
                             verbose_name='Пользователь')
    order_id = models.CharField('Номер заказа', max_length=50, unique=True,
                                editable=False, db_index=True)
    customer_id = models.UUIDField('Номер плательщика', unique=True,
                                   default=uuid.uuid4, editable=False)
    state = models.CharField('Статус', max_length=16, choices=STATE_CHOICES,
                             default=STATE_CREATED, editable=False)

    payment_type = models.CharField('Способ платежа', max_length=2,
                                    default=conf.PAYMENT_TYPE_YANDEX_MONEY,
                                    choices=conf.BASE_PAYMENT_TYPE_CHOICES,
                                    editable=False)
    invoice_id = models.CharField('Номер транзакции оператора', max_length=64,
                                  blank=True, editable=False)
    order_sum = models.DecimalField('Сумма заказа', max_digits=15,
                                    decimal_places=2, editable=False)
    shop_sum = models.DecimalField('Сумма полученная на р/с', max_digits=15,
                                   decimal_places=2, null=True,
                                   help_text='За вычетом коммиссии',
                                   editable=False)

    order_currency = models.PositiveIntegerField(
        'Валюта платежа', default=CURRENCY_RUB, choices=CURRENCY_CHOICES,
        editable=False)
    shop_currency = models.PositiveIntegerField(
        'Валюта полученная на р/с', null=True, default=CURRENCY_RUB,
        choices=CURRENCY_CHOICES)
    payer_code = models.CharField('Номер виртуального счета', max_length=33,
                                  blank=True, editable=False)

    cps_email = models.EmailField('Почта плательщика', blank=True,
                                  editable=False)
    cps_phone = models.CharField('Телефон плательщика', max_length=15,
                                 blank=True, editable=False)

    created = models.DateTimeField('Создан', auto_now_add=True)
    performed = models.DateTimeField('Обработан', null=True)
    completed = models.DateTimeField('Завершен', null=True)

    def __str__(self):
        return 'Платеж #{}'.format(self.order_id)

    class Meta:
        ordering = ('-created',)
        verbose_name = 'платеж'
        verbose_name_plural = 'Платежи'

    @property
    def is_payed(self):
        return self.state == self.STATE_SUCCESS

    @property
    def is_started(self):
        return self.state != self.STATE_CREATED

    @property
    def is_completed(self):
        return self.state in (self.STATE_SUCCESS, self.STATE_FAIL)

    def process(self):
        if self.state != self.STATE_CREATED:
            raise RuntimeError(
                'Cannot set state to "Processing" when current state '
                'is {}'.format(self.state))

        self.performed = now()
        self.state = self.STATE_PROCESSED
        self.save()

        payment_process.send(sender=self)

    def complete(self):
        if self.state == self.STATE_FAIL and self.performed is None:
            raise RuntimeError(
                'Cannot set state to "Success" when current state '
                'is {}'.format(self.state))
        if self.state not in (self.STATE_PROCESSED, self.STATE_FAIL):
            raise RuntimeError(
                'Cannot set state to "Success" when current state '
                'is {}'.format(self.state))

        self.completed = now()
        self.state = self.STATE_SUCCESS
        self.save()

        payment_success.send(sender=self)

    def fail(self):
        if self.state in (self.STATE_SUCCESS, self.STATE_FAIL):
            raise RuntimeError('Cannot set state to "Fail" when current '
                               'state is {}'.format(self.state))

        self.completed = now()
        self.state = self.STATE_FAIL
        self.save()

        payment_fail.send(sender=self)

    def form(self):
        initial = {
            'orderNumber': self.order_id,
            'sum': self.order_sum,
            'customerNumber': self.customer_id,
            'cps_email': self.cps_email,
            'cps_phone': self.cps_phone,
            'paymentType': self.payment_type,
        }
        if conf.SUCCESS_URL is None:
            url = reverse('yandex_cash_register:money_payment_finish')
            initial['shopSuccessURL'] = '{}{}?cr_action={}&cr_order_number={}'.format(
                conf.SHOP_DOMAIN, url, FinalPaymentStateForm.ACTION_CONFIRM,
                self.order_id
            )
            initial['shopFailURL'] = '{}{}?cr_action={}&cr_order_number={}'.format(
                conf.SHOP_DOMAIN, url, FinalPaymentStateForm.ACTION_FAIL,
                self.order_id
            )
        return PaymentForm(initial=initial)
