# coding=utf-8
import os

from setuptools import setup

setup(
    name='django-yandex-cash-register',
    version='0.1.5',
    zip_safe=False,
    description='Generic Yandex.Kassa application for Django',
    long_description=open(os.path.join(os.path.dirname(__file__),
                                       'README.rst')).read(),
    author='Evgeny Barbashov',
    author_email='evgenybarbashov@yandex.ru',
    url='https://github.com/bzzzzzz/django-yandex-cash-register',
    packages=[
        'yandex_cash_register',
        'yandex_cash_register.tests',
        'yandex_cash_register.migrations',
    ],
    package_data={
        'yandex_cash_register': [
            'templates/*/*.*',
            'locale/*/LC_MESSAGES/*.po',
        ]
    },
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Web Environment',
        'Framework :: Django',
        'Framework :: Django :: 1.8',
        'Framework :: Django :: 1.9',
        'Framework :: Django :: 1.10',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Topic :: Utilities',
    ],
    install_requires=[
        'django>=1.8',
        'lxml>=3.5,<=3.6.4',
    ],
)
