# coding=utf-8
from __future__ import absolute_import, unicode_literals

import uuid

from django.conf import settings
from django.core.urlresolvers import reverse
from django.db import models
from django.utils.encoding import python_2_unicode_compatible
from django.utils.timezone import now
from django.utils.translation import ugettext_lazy as _

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
        (STATE_CREATED, _('Created')),
        (STATE_PROCESSED, _('Processed')),
        (STATE_SUCCESS, _('Succeed')),
        (STATE_FAIL, _('Failed')),
    )

    CURRENCY_RUB = 643
    CURRENCY_TEST = 10643

    CURRENCY_CHOICES = (
        (CURRENCY_RUB, _('Rouble')),
        (CURRENCY_TEST, _('Test currency')),
    )

    user = models.ForeignKey(settings.AUTH_USER_MODEL, blank=True, null=True,
                             verbose_name=_('User'))
    order_id = models.CharField(_('Order ID'), max_length=50, unique=True,
                                editable=False, db_index=True)
    customer_id = models.UUIDField(_('Customer ID'), unique=True,
                                   default=uuid.uuid4, editable=False)
    state = models.CharField(_('State'), max_length=16, choices=STATE_CHOICES,
                             default=STATE_CREATED, editable=False)

    payment_type = models.CharField(_('Payment method'), max_length=2,
                                    choices=conf.BASE_PAYMENT_TYPE_CHOICES,
                                    editable=False, blank=True)
    invoice_id = models.CharField(_('Invoice ID'), max_length=64,
                                  blank=True, editable=False)
    order_sum = models.DecimalField(_('Order sum'), max_digits=15,
                                    decimal_places=2, editable=False)
    shop_sum = models.DecimalField(_('Received sum'), max_digits=15,
                                   decimal_places=2, null=True,
                                   help_text=_('Order sum - Yandex.Kassa fee'),
                                   editable=False)

    order_currency = models.PositiveIntegerField(
        _('Order currency'), default=CURRENCY_RUB, choices=CURRENCY_CHOICES,
        editable=False)
    shop_currency = models.PositiveIntegerField(
        _('Payment currency'), null=True, default=CURRENCY_RUB,
        choices=CURRENCY_CHOICES)
    payer_code = models.CharField(_('Payer code'), max_length=33,
                                  blank=True, editable=False)

    cps_email = models.EmailField(_('Payer e-mail'), blank=True,
                                  editable=False)
    cps_phone = models.CharField(_('Payer phone'), max_length=15,
                                 blank=True, editable=False)

    created = models.DateTimeField(_('Created at'), auto_now_add=True)
    performed = models.DateTimeField(_('Started at'), null=True)
    completed = models.DateTimeField(_('Completed at'), null=True)

    def __str__(self):
        return _('Payment #%(payment)s') % {'payment': self.order_id}

    class Meta:
        ordering = ('-created',)
        verbose_name = _('payment')
        verbose_name_plural = _('payments')

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
            initial['shopSuccessURL'] = \
                '{}{}?cr_action={}&cr_order_number={}'.format(
                    conf.SHOP_DOMAIN, url,
                    FinalPaymentStateForm.ACTION_CONFIRM, self.order_id
                )
            initial['shopFailURL'] = \
                '{}{}?cr_action={}&cr_order_number={}'.format(
                    conf.SHOP_DOMAIN, url, FinalPaymentStateForm.ACTION_FAIL,
                    self.order_id
                )
        return PaymentForm(initial=initial)
