# coding=utf-8
from __future__ import absolute_import, unicode_literals

from django.conf.urls import url, include

urlpatterns = [
    url(r'^kassa/', include('yandex_cash_register.urls',
                            namespace='yandex_cash_register',
                            app_name='yandex_cash_register')),
]
