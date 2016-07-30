# coding=utf-8
from __future__ import absolute_import, unicode_literals

from django.dispatch import Signal


payment_process = Signal()
payment_success = Signal()
payment_fail = Signal()
