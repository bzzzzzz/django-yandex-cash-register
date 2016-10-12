Yandex.Kassa (Яндекс.Касса) generic app for Django
==================================================

.. image:: https://travis-ci.org/bzzzzzz/django-yandex-cash-register.svg?branch=master
    :target: https://travis-ci.org/bzzzzzz/django-yandex-cash-register

.. image:: https://codeclimate.com/github/bzzzzzz/django-yandex-cash-register/badges/gpa.svg
   :target: https://codeclimate.com/github/bzzzzzz/django-yandex-cash-register
   :alt: Code Climate

.. image:: https://codeclimate.com/github/bzzzzzz/django-yandex-cash-register/badges/coverage.svg
   :target: https://codeclimate.com/github/bzzzzzz/django-yandex-cash-register/coverage
   :alt: Test Coverage

.. note:: This application is suitable only for russian web services, so I don't
   provide English readme. If you need English docs, please contact me.

Простое приложение для подключения в Django оплаты через Яндекс.Кассу. Поддерживает
Python 2.7, 3.4 и 3.5. Совместимо со всеми версиями Django>=1.8.

В приложении реализован протокол интеграции, описанный в
`официальной документации <https://tech.yandex.ru/money/doc/payment-solution/About-docpage/>`_

Установка и настройка
---------------------

Перед тем приступить к настройке приложения, убедитесь, что у вас уже есть аккаунт в
`kassa.yandex.ru <https://kassa.yandex.ru>`_ и вы знаете SCID, ShopID и платежный
пароль.

1. Устанавливаем пакет:

   .. code-block:: sh

       pip install django-yandex-cash-register

2. Добавляем приложение ``yandex_cash_register`` в ``settings.INSTALLED_APPS``:

   .. code-block:: python

       INSTALLED_APPS = (
           ...
           'yandex_cash_register',
           ...
       )

3. Указываем в ``settings.py`` следующие настройки:

   .. code-block:: python

       # True - Использование тестого платежного сервиса, False - основного
       YANDEX_CR_DEBUG = False
       # Идентификатор магазина, полученный в Яндекс.Кассе
       YANDEX_CR_SCID = 12345
       # Идентификатор витрины магазина, полученный в Яндекс.Кассе
       YANDEX_CR_SHOP_ID = 123456
       # Платежный пароль магазина
       YANDEX_CR_SHOP_PASSWORD = 'password'
       # Идентификаторы используемых видов оплаты (https://tech.yandex.ru/money/doc/payment-solution/reference/payment-type-codes-docpage/)
       YANDEX_CR_PAYMENT_TYPE = ['pc', 'ac', 'wm']
       # Название модели заказа. Модель должна соответствовать
       # интерфейсу yandex_cash_register.interfaces.IPayableOrder
       YANDEX_CR_ORDER_MODEL = 'your_app.Order'
       # Публичный домен магазина
       YANDEX_CR_SHOP_DOMAIN = 'https://example.com'

4. Создаем таблицы в базе данных:

   .. code-block:: sh

       python manage.py migrate

5. Добавляем приложение в ``urls.py``, обязательно указывая ``namespace`` и ``app_name``:

   .. code-block:: python

       url(r'^money/', include('yandex_cash_register.urls',
                               namespace='yandex_cash_register',
                               app_name='yandex_cash_register')),

6. Если ваш домен `example.com` и вы указали `money` как урл приложения, то
   ваш `checkURL` в настройках должен быть `https://example.com/money/order-check/`,
   а `paymentAvisoURL` - `https://example.com/money/payment-aviso/`.
   URL успеха и провала платежа указывать не нужно.

Использование
-------------

1. Первым делом нужно имплементировать интерфейс ``yandex_cash_register.interfaces.IPayableOrder``
   в модели заказа своего приложения для того, чтобы по завершении платежа
   вернуть клиента на соответствующую страницу.

2. Для создания платежа достаточно знать уникальный идентификатор заказа,
   почтовый адрес и телефон клиента (требование Яндекс.Кассы), а также сумму
   заказа и (опционально) выбранный клиентом способ оплаты:

   .. code-block:: python

       from yandex_cash_register.models import Payment

       payment = Payment(
           order_sum=Decimal('100.50'),  # Сумма к оплате
           order_id='unique_id',  # Идентификатор заказа
           cps_email='customer@example.com',  # Почтовый адрес клиента
           cps_phone='70000000000',  # Телефон клиента, 11 цифр без символов
           payment_type='wm',  # Способ оплаты (опционален), если его не задать,
                               # клиент будет выбирать его на стороне Яндекс.Кассы
       )
       payment.save()

       # После создания заказа можно получить платежную форму, которую нужно отобразить клиенту
       # c method="post" и target="yandex_cash_register.conf.TARGET"
       # После ее сабмита (можно это сделать автоматически) клиент попадет в
       # интерфейс Яндекс.Кассы, где сможет завершить платеж
       form = payment.form()

3. Для получения информации о результатах оплаты, нужно начать слушать сигналы
   из модуля ``yandex_cash_register.signals``. В наличии три сигнала:

   - payment_process - отсылается при получении Яндекс.Кассой информации о платеже
   - payment_success - отсылается при успешном платеже
   - payment_fail - отсылается при ошибочном платеже

   В качестве sender сигнала выступает объект ``yandex_cash_register.Payment``,
   для которого этот сигнал актуален.
