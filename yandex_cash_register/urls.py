# coding=utf-8
from __future__ import absolute_import, unicode_literals

from django.conf.urls import url

from . import views

urlpatterns = [
    url(r'^order-check/$', views.CheckOrderView.as_view(),
        name='money_check_order'),
    url(r'^payment-aviso/$', views.PaymentAvisoView.as_view(),
        name='money_payment_aviso'),
    url(r'^finish/$', views.PaymentFinishView.as_view(),
        name='money_payment_finish'),
]
