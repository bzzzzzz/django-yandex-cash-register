# coding=utf-8
from __future__ import absolute_import, unicode_literals

from hashlib import md5

from django import forms
from django.apps import apps
from django.utils.functional import cached_property
from django.utils.translation import ugettext_lazy, ugettext as _

from .apps import YandexMoneyConfig
from . import conf


readonly_widget = forms.TextInput(attrs={'readonly': 'readonly'})


class ShopIdForm(forms.Form):
    shopId = forms.IntegerField(initial=conf.SHOP_ID, widget=readonly_widget)
    orderNumber = forms.CharField(min_length=1, max_length=64,
                                  widget=readonly_widget)
    customerNumber = forms.CharField(min_length=1, max_length=64,
                                     widget=readonly_widget)
    paymentType = forms.CharField(
        widget=forms.Select(choices=[('', ugettext_lazy('Method not chosen'))] + conf.PAYMENT_TYPE_CHOICES),
        min_length=2, max_length=2
    )

    @cached_property
    def payment_obj(self):
        """
        :rtype: yandex_cash_register.models.Payment
        """
        payment_model = apps.get_model(YandexMoneyConfig.name, 'Payment')
        order_number = self.cleaned_data.get('orderNumber')
        try:
            return payment_model.objects.select_for_update().get(
                order_id=order_number)
        except payment_model.DoesNotExist:
            return None

    def clean_orderNumber(self):
        order_number = self.cleaned_data.get('orderNumber')
        payment = self.payment_obj
        if payment is None:
            raise forms.ValidationError(
                _('Cannot find payment with order ID %(order_number)s'),
                code='invalid',
                params={'order_number': order_number},
            )
        return order_number

    def clean_shopId(self):
        shop_id = self.cleaned_data['shopId']
        if int(shop_id) != int(conf.SHOP_ID):
            raise forms.ValidationError(_('Unknown shop ID'))
        return shop_id

    def _clean_customerNumber(self):
        customer_id = self.cleaned_data['customerNumber']
        if customer_id != str(self.payment_obj.customer_id):
            raise forms.ValidationError(_('Unknown customer ID'))
        return customer_id

    def _clean_paymentType(self):
        payment_type = self.cleaned_data['paymentType']
        if self.payment_obj.payment_type and payment_type != str(self.payment_obj.payment_type):
            raise forms.ValidationError(
                _('Unknown or unsupported payment method'))
        return payment_type

    def clean(self):
        data = super(ShopIdForm, self).clean()
        if self.payment_obj is not None:
            for item in ('customerNumber', 'paymentType'):
                if item not in data:
                    continue

                try:
                    data[item] = getattr(self, '_clean_{}'.format(item))()
                except forms.ValidationError as e:
                    self._errors[item] = self.error_class(e.messages)
                    del self.cleaned_data[item]

        return data


class PaymentForm(ShopIdForm):
    scid = forms.IntegerField(initial=conf.SCID, widget=readonly_widget)

    sum = forms.DecimalField(min_value=0, widget=readonly_widget)

    cps_email = forms.EmailField(required=False, widget=readonly_widget)
    cps_phone = forms.CharField(max_length=15, required=False,
                                widget=readonly_widget)

    shopFailURL = forms.URLField(initial=conf.FAIL_URL, widget=readonly_widget)
    shopSuccessURL = forms.URLField(initial=conf.SUCCESS_URL,
                                    widget=readonly_widget)

    use_required_attribute = False

    def __init__(self, *args, **kwargs):
        super(PaymentForm, self).__init__(*args, **kwargs)

        if not conf.DEBUG:
            for name in self.fields:
                if name not in conf.DISPLAY_FIELDS:
                    self.fields[name].widget = forms.HiddenInput()

    def clean(self):
        raise forms.ValidationError(_('This form cannot be validated'))

    @property
    def target(self):
        return conf.TARGET


class PaymentProcessingForm(ShopIdForm):
    ACTION_CHECK = 'checkOrder'
    ACTION_CPAYMENT = 'paymentAviso'

    ACTION_CHOICES = (
        (ACTION_CHECK, ACTION_CHECK),
        (ACTION_CPAYMENT, ACTION_CPAYMENT),
    )
    MD5_KEY_ORDER = ['action', 'orderSumAmount', 'orderSumCurrencyPaycash',
                     'orderSumBankPaycash', 'shopId', 'invoiceId',
                     'customerNumber']

    ERROR_CODE_MD5 = 1
    ERROR_CODE_UNKNOWN_ORDER = 100
    ERROR_CODE_INTERNAL = 200

    md5 = forms.CharField(min_length=32, max_length=32)
    invoiceId = forms.IntegerField(min_value=1)
    orderSumAmount = forms.DecimalField(min_value=0, decimal_places=2)
    orderSumCurrencyPaycash = forms.IntegerField()
    orderSumBankPaycash = forms.IntegerField()
    shopSumAmount = forms.DecimalField(min_value=0, decimal_places=2)
    shopSumCurrencyPaycash = forms.IntegerField()
    shopArticleId = forms.IntegerField(required=False)
    paymentPayerCode = forms.CharField(max_length=33, required=False)
    action = forms.ChoiceField(choices=ACTION_CHOICES)

    def __init__(self, *args, **kwargs):
        super(PaymentProcessingForm, self).__init__(*args, **kwargs)

        self._error_code = None
        self._error_message = None

    def _make_md5(self):
        """
        action;orderSumAmount;orderSumCurrencyPaycash;orderSumBankPaycash;shopId;invoiceId;customerNumber;shopPassword
        """
        md5_base = ';'.join(str(self.cleaned_data.get(key, ''))
                            for key in self.MD5_KEY_ORDER)
        md5_base = '{};{}'.format(md5_base, conf.SHOP_PASSWORD).encode('utf-8')
        return md5(md5_base).hexdigest().upper()

    def set_error(self, code, message, raise_error=False):
        self._error_code = code
        self._error_message = message
        if raise_error:
            raise forms.ValidationError(message)

    @staticmethod
    def _round(paysum):
        paysum = float(paysum)
        return int(round(paysum / 10, 0)) * 10

    def clean(self):
        data = super(PaymentProcessingForm, self).clean()
        if self.errors:
            if 'md5' in self.errors:
                self.set_error(self.ERROR_CODE_MD5, _('MD5 is incorrect'))
            elif 'customerNumber' in self.errors or \
                    'orderNumber' in self.errors:
                self.set_error(self.ERROR_CODE_UNKNOWN_ORDER,
                               _('No such order'))
            else:
                self.set_error(self.ERROR_CODE_INTERNAL,
                               _('Cannot process payment'))

            return data

        if self._make_md5() != data['md5']:
            self.set_error(self.ERROR_CODE_MD5, _('MD5 is incorrect'),
                           raise_error=True)

        if self._round(self.payment_obj.order_sum) != self._round(
                data['orderSumAmount']):
            self.set_error(self.ERROR_CODE_UNKNOWN_ORDER,
                           _("Sum doesn't match"), raise_error=True)

        return data

    @property
    def error_code(self):
        return self._error_code

    @property
    def error_message(self):
        return self._error_message


class FinalPaymentStateForm(forms.Form):
    ACTION_FAIL = 'payment_fail'
    ACTION_CONFIRM = 'payment_confirm'

    ACTION_CHOICES = (
        (ACTION_FAIL, ACTION_FAIL),
        (ACTION_CONFIRM, ACTION_CONFIRM),
    )
    cr_action = forms.ChoiceField(choices=ACTION_CHOICES)
    cr_order_number = forms.CharField(min_length=1, max_length=64)

    @cached_property
    def payment_obj(self):
        """
        :rtype: yandex_cash_register.models.Payment
        """
        payment_model = apps.get_model(YandexMoneyConfig.name, 'Payment')
        order_number = self.cleaned_data.get('cr_order_number')
        try:
            return payment_model.objects.select_for_update().get(
                order_id=order_number)
        except payment_model.DoesNotExist:
            return None
