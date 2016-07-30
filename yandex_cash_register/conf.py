# coding=utf-8
from __future__ import absolute_import, unicode_literals

from django.conf import settings


DEBUG = getattr(settings, 'YANDEX_CR_DEBUG', False)

if DEBUG:
    MONEY_URL = 'https://demomoney.yandex.ru'
else:
    MONEY_URL = 'https://money.yandex.ru'

TARGET = MONEY_URL + '/eshop.xml'

LOCAL_URL = getattr(settings, 'YANDEX_CR_LOCAL_URL', 'kassa')
SUCCESS_URL = getattr(settings, 'YANDEX_CR_SUCCESS_URL')
FAIL_URL = getattr(settings, 'YANDEX_CR_FAIL_URL', SUCCESS_URL)

SCID = getattr(settings, 'YANDEX_CR_SCID')
SHOP_ID = getattr(settings, 'YANDEX_CR_SHOP_ID')
SHOP_PASSWORD = getattr(settings, 'YANDEX_CR_SHOP_PASSWORD')

DISPLAY_FIELDS = getattr(settings, 'YANDEX_CR_DISPLAY_FIELDS',
                         ['paymentType'])

PAYMENT_TYPE_ALFA_CLICK = 'AB'
PAYMENT_TYPE_CARD = 'AC'
PAYMENT_TYPE_TERMINAL_CACHE = 'GP'
PAYMENT_TYPE_MASTER_PASS = 'MA'
PAYMENT_TYPE_MOBILE_ACCOUNT = 'MC'
PAYMENT_TYPE_PROMSVYASBANK = 'PB'
PAYMENT_TYPE_YANDEX_MONEY = 'PC'
PAYMENT_TYPE_SBERBANK = 'SB'
PAYMENT_TYPE_WEBMONEY = 'WM'
PAYMENT_TYPE_QIWI_WALLET = 'QS'

BASE_PAYMENT_TYPE_CHOICES = (
    (PAYMENT_TYPE_ALFA_CLICK, 'Альфа-Клик'),
    (PAYMENT_TYPE_CARD, 'Банковская карта'),
    (PAYMENT_TYPE_TERMINAL_CACHE, 'Наличные через терминал'),
    (PAYMENT_TYPE_MASTER_PASS, 'MasterPass'),
    (PAYMENT_TYPE_MOBILE_ACCOUNT, 'Счет мобильного телефона'),
    (PAYMENT_TYPE_PROMSVYASBANK, 'Интернет-банк Промсвязьбанка'),
    (PAYMENT_TYPE_YANDEX_MONEY, 'Кошелек Яндекс.Денег'),
    (PAYMENT_TYPE_SBERBANK, 'Сбербанк Онлайн'),
    (PAYMENT_TYPE_WEBMONEY, 'Кошелек WebMoney'),
    (PAYMENT_TYPE_QIWI_WALLET, 'QiWi кошелёк'),
)

PAYMENT_TYPES = getattr(settings, 'YANDEX_CR_PAYMENT_TYPE',
                        ['AB', 'AC', 'GP', 'PB', 'PC', 'WM'])
PAYMENT_TYPES = [str(x).upper() for x in PAYMENT_TYPES]
PAYMENT_TYPE_CHOICES = [c for c in BASE_PAYMENT_TYPE_CHOICES
                        if c[0] in PAYMENT_TYPES]

MODEL = getattr(settings, 'YANDEX_CR_ORDER_MODEL').split('.')
