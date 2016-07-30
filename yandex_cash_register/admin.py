# coding=utf-8
from __future__ import absolute_import, unicode_literals

from django.contrib import admin
from .models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('order_id', 'is_completed_status', 'is_payed_status',
                    'order_sum', 'shop_sum', 'shop_currency',
                    'created')
    list_filter = ('state',)
    fields = (
        'customer_id', 'order_id', 'invoice_id', 'state',
        'payment_type', ('order_sum', 'order_currency'),
        ('shop_sum', 'shop_currency'),
        'payer_code', 'cps_email', 'cps_phone',
        'created', 'performed', 'completed',
    )
    readonly_fields = (
        'customer_id', 'order_id', 'invoice_id', 'state',
        'payment_type', 'order_sum', 'order_currency', 'shop_sum',
        'shop_currency', 'payer_code', 'cps_email', 'cps_phone',
        'created', 'performed', 'completed',
    )

    def is_completed_status(self, obj):
        return obj.is_completed
    is_completed_status.boolean = True
    is_completed_status.short_description = 'Завершен'

    def is_payed_status(self, obj):
        return obj.is_payed
    is_payed_status.boolean = True
    is_payed_status.short_description = 'Оплачен'

    def get_actions(self, request):
        actions = super(PaymentAdmin, self).get_actions(request)
        del actions['delete_selected']
        return actions

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
