# coding=utf-8
from __future__ import absolute_import, unicode_literals

from django.apps import AppConfig
from django.utils.translation import ugettext_lazy as _


class YandexMoneyConfig(AppConfig):
    name = 'yandex_cash_register'
    verbose_name = _('Yandex.Kassa payments')
