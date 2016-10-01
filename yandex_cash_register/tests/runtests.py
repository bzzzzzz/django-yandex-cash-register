#!/usr/bin/env python
# coding=utf-8
"""A standalone test runner script, configuring the minimum settings
required for django-yandex-cash-register tests to execute.
Re-use at your own risk: many Django applications will require full
settings and/or templates in order to execute their tests, while
django-yandex-cash-register does not.
"""
from __future__ import absolute_import, unicode_literals

import os
import sys


# Make sure the app is (at least temporarily) on the import path.
APP_DIR = os.path.abspath(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
sys.path.insert(0, APP_DIR)

# Minimum settings required for django-yandex-cash-register to work.
SETTINGS_DICT = {
    'BASE_DIR': APP_DIR,
    'INSTALLED_APPS': (
        'yandex_cash_register',
        'django.contrib.auth',
        'django.contrib.contenttypes',
        'django.contrib.sites',
    ),
    'ROOT_URLCONF': 'yandex_cash_register.tests.urls',
    'DATABASES': {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': os.path.join(APP_DIR, 'db.sqlite3'),
        },
    },
    'MIDDLEWARE_CLASSES': (
        'django.middleware.common.CommonMiddleware',
        'django.middleware.csrf.CsrfViewMiddleware',
    ),
    'TEMPLATE_DIRS': (
        os.path.join(APP_DIR, 'yandex_cash_register', 'templates'),
    ),
    'TEMPLATES': [
        {
            'BACKEND': 'django.template.backends.django.DjangoTemplates',
            'APP_DIRS': True,
            'DIRS': [
                os.path.join(APP_DIR, 'yandex_cash_register', 'templates'),
            ],
        },
    ],
    'SITE_ID': 1,
    'DEFAULT_FROM_EMAIL': 'contact@example.com',
    'MANAGERS': [('Manager', 'noreply@example.com')],

    'YANDEX_CR_SHOP_DOMAIN': 'http://example.com',
    'YANDEX_CR_SCID': 1,
    'YANDEX_CR_SHOP_ID': 2,
    'YANDEX_CR_SHOP_PASSWORD': '3',
    'YANDEX_CR_ORDER_MODEL': 'testapp.TestOrder',

    'DEBUG': False
}


def run_tests():
    # Making Django run this way is a two-step process. First, call
    # settings.configure() to give Django settings to work with:
    from django.conf import settings
    settings.configure(**SETTINGS_DICT)

    # Then, call django.setup() to initialize the application cache
    # and other bits:
    import django
    if hasattr(django, 'setup'):
        django.setup()

    # Now we instantiate a test runner...
    from django.test.utils import get_runner
    TestRunner = get_runner(settings)

    # And then we run tests and return the results.
    test_runner = TestRunner(verbosity=1, interactive=True)
    failures = test_runner.run_tests(['yandex_cash_register.tests'])
    sys.exit(bool(failures))

if __name__ == '__main__':
    run_tests()
