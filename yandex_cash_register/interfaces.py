# coding=utf-8
from __future__ import absolute_import, unicode_literals


class IPayableOrder(object):
    def get_absolute_url(self):
        """Django's method to find models absolute url"""

    def get_payment_complete_url(self, success):
        """Generate url to show user with provided result of payment

        :type success: bool
        :param success: whether payment succeeded or not

        :return: an URL to redirect to
        """

    @classmethod
    def get_by_order_id(cls, order_id):
        """Find order associated with payment by order_id provided

        :type order_id: basestring
        :param order_id: an order id, which was saved on payment creation

        :return: An order object
        """
