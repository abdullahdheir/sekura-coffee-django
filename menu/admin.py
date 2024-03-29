import json
import re
from django.contrib import admin
from django.template.response import TemplateResponse
from django.urls import reverse
from django.http import HttpRequest, JsonResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, get_list_or_404
from .models import (Item, Category, Order, OrderItem, Comment, Table, Notification)
from django.urls import path
from django.dispatch import receiver
from django.db.models.signals import post_save, pre_save
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from .forms import OrderForm
from django.views.decorators.csrf import csrf_exempt
from django.core.exceptions import ValidationError
from datetime import datetime
from django.contrib import messages
from menu.utils import generate_token_by_id


class OrderItemAdmin(admin.ModelAdmin):
    pass

#, this admin class provides basic functionalities for managing notifications in the Django Admin site, 
# including filtering, sorting, and performing custom admin actions on the selected notifications.
#  Additionally, it adds a new URL pattern for reading a notification and provides a custom view function 
# for handling the opening of a notification and redirecting to relevant admin pages.
class NotificationAdmin(admin.ModelAdmin):
    #method: A custom admin action method that sets the opened field of selected notifications to True.
    def make_opened(modeladmin, request, queryset):
        """Make all selected notifications opened"""
        queryset.update(opened=True)

    make_opened.short_description = "Mark selected notifications as opened"
    # property: A tuple that specifies the fields to be displayed in the list view of notifications.
    #  It includes the body, opened, and created_at fields.

    list_display = ('body', 'opened', 'created_at')
    # property: A tuple that specifies the fields to be used for filtering notifications in the list view.
    #  In this case, it includes only the opened field.
    list_filter = ["opened"]
    # property: A list that specifies the fields that can be used to sort notifications in the list view. It includes the opened and created_at fields.
    # actions property: A list of admin action methods that can be performed on the selected notifications in the list view. 
    # In this case, it includes only the make_opened method.
    sortable_by = ['opened', 'created_at']
    actions = [make_opened]
    # method: A custom method that returns the admin site's URL patterns for managing notifications.
    #  It adds a new URL pattern for reading a notification.
    def get_urls(self):
        urls = super().get_urls()
        my_urls = [
            path('<int:pk>', self.admin_site.admin_view(self.notification_read), name="notification_read")
        ]
        return urls + my_urls
    # method: A custom method that returns the admin site's URL patterns for managing notifications.
    #  It adds a new URL pattern for reading a notification.

    def notification_read(self, request: HttpRequest, **kwargs):
        notify = get_object_or_404(Notification, pk=kwargs['pk'])
        notify.opened = True
        notify.save()
        if notify.type == 1:
            table_id = re.sub(pattern='[^0-9]', repl='', string=notify.body)
            if not Table.objects.filter(pk=table_id).exists():
                return HttpResponseRedirect(reverse('home'))
            return HttpResponseRedirect(reverse('admin:table_orders', kwargs={'pk': table_id}))
        if notify.type == 2:
            order_id = re.sub(pattern='[^0-9]', repl='', string=notify.body)
            order = Order.objects.filter(pk=order_id)
            if not order.exists():
                return HttpResponseRedirect(reverse('home'))
            return HttpResponseRedirect(reverse('admin:table_order_details',
                                                kwargs={'pk': order.first().table_id, 'order_id': order.first().pk}))


class TableOrderAdmin(admin.ModelAdmin):
#The change_view method is overridden to redirect to a custom URL instead of the default change view URL. 
# When a TableOrder instance is clicked on in the admin interface,
#  the user will be redirected to the URL defined by the table_orders_listing view method, 
# passing the object_id (primary key) of the TableOrder instance in the URL
    def change_view(self, request, object_id, form_url="", extra_context=None):
        return HttpResponseRedirect(reverse('admin:table_orders', kwargs={'pk': object_id}))
#The get_urls method is overridden to add custom URL patterns to the admin interface.
#  These URL patterns map to view methods that handle requests to perform custom actions on TableOrder instances.
    def get_urls(self):
        urls = super().get_urls()
        my_urls = [
            path('<int:pk>/orders', self.admin_site.admin_view(self.table_orders_listing), name="table_orders"),
            path('<int:pk>/orders/<int:order_id>', self.admin_site.admin_view(self.table_orders_details),
                 name="table_order_details"),
            path('<int:pk>/orders/<int:order_id>/delete', self.admin_site.admin_view(self.table_order_delete),
                 name="table_order_delete"),
            path('<int:pk>/orders/delete_all', self.admin_site.admin_view(self.table_order_delete_all),
                 name="table_order_delete_all"),
        ]
        return my_urls + urls
    #The table_orders_details view method is responsible for displaying the details of a particular order associated with a TableOrder instance.
    #  It takes the primary key of the TableOrder instance and the primary key of the order as URL parameters,
    #  retrieves the order from the database, and displays its details in a template.

    def table_orders_details(self, request: HttpRequest, **kwargs):
        table = get_object_or_404(Table, pk=kwargs['pk'])
        order = get_object_or_404(Order, pk=kwargs['order_id'])
        context = dict(
            # Include common variables for rendering the admin template.
            self.admin_site.each_context(request),
            # Anything else you want in the context...
            order=order
        )
        return TemplateResponse(request, "admin/order_table_detail.html", context)
    #The table_order_delete view method is responsible for deleting a particular order associated with a TableOrder instance.
    #  It takes the primary key of the TableOrder instance and the primary key of the order as URL parameters, 
    # retrieves the order from the database, deletes it, and redirects back to the table_orders_listing view.

    def table_order_delete_all(self, request: HttpRequest, **kwargs):
        if request.method == 'POST':
            orders = get_list_or_404(Order, table_id=kwargs['pk'])
            order_count = 0
            for order in orders:
                order.delete(force_delete=True)
                order_count += 1
        messages.success(request, f"Successfully deleted {order_count} orders.")
        return HttpResponseRedirect(reverse('admin:table_orders', kwargs={'pk': kwargs['pk']}))
#The table_order_delete view method is responsible for deleting a particular order associated with a TableOrder instance. It takes the primary key of the TableOrder instance and the primary key of the order as URL parameters,
#  retrieves the order from the database, deletes it, and redirects back to the table_orders_listing view.
    def table_order_delete(self, request: HttpRequest, **kwargs):
        if request.method == 'POST':
            order = get_object_or_404(Order, pk=kwargs['order_id'])
            order.delete()
            messages.success(request, f'The order "{order}" was deleted successfully')
            return HttpResponseRedirect(reverse('admin:table_orders', kwargs={'pk': kwargs['pk']}))
    #The table_orders_listing view method is responsible for displaying a list of all orders associated with a particular TableOrder instance.
    #  It takes the primary key of the TableOrder instance as a URL parameter,
    #  retrieves all orders associated with that TableOrder instance, and displays them in a template.

    @csrf_exempt
    def table_orders_listing(self, request: HttpRequest, pk):
        try:
            table = get_object_or_404(Table, pk=pk)
            if request.method == "POST":
                order = Order.objects.get(pk=int(request.POST.get('order')))
                if order.table_id != pk:
                    raise ValueError()
                form = OrderForm(request.POST)
                if form.is_valid():
                    order.order_accept = True
                    order.receive_time = form.cleaned_data['receive_time']
                    order.save()
                    return JsonResponse({"status": 'success', 'message': 'Order has been accepted successfully'})
                else:
                    raise ValidationError(form.errors)
            orders = Order.objects.filter(table=table, ordered=True, created_at__date=datetime.today()).order_by(
                '-updated_at')

            context = dict(
                # Include common variables for rendering the admin template.
                self.admin_site.each_context(request),
                # Anything else you want in the context...
                orders=orders,
                table=table,
            )
            return TemplateResponse(request, "admin/order_table.html", context)
        except ValidationError as err:
            return JsonResponse({'status': 'error', "errors": err.messages}, status=500)
        except ValueError:
            return JsonResponse({"status": "error", 'message': "Please don't play on site"})


admin.site.register(Table, TableOrderAdmin)
admin.site.register(Category)
admin.site.register(Item)
admin.site.register(Order)
admin.site.register(OrderItem)
admin.site.register(Comment)
admin.site.register(Notification, NotificationAdmin)


@receiver(pre_save, sender=Order)
def handle_new_order(sender, instance, **kwargs):
    try:
        old_instance = sender.objects.get(pk=instance.pk)
        old_value = getattr(old_instance, 'ordered')
        payload = dict(url=reverse('admin:table_order_details',
                                   kwargs={'pk': getattr(instance, 'table_id'), 'order_id': getattr(instance, 'pk')}),
                       order_id=getattr(instance, 'pk'),
                       type='order',
                       items=[dict(image=order_item.item.image.url, name=order_item.item.name, count=order_item.count)
                              for order_item in getattr(instance, 'orderitem_set').all()])
        if not old_value:
            notify = Notification.objects.create(body=f'New order in table no. {instance.table_id}', type=1)
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                'orders_orders',
                {
                    'type': 'notification',
                    'data': {"payload": payload,
                             'url': reverse('admin:notification_read', kwargs={'pk': notify.pk}), "type": 1},
                    'message': notify.body
                }
            )
    except sender.DoesNotExist:
        return


@receiver(post_save, sender=Comment)
def handle_new_comment(sender, instance, created, **kwargs):
    if created and instance.order.ordered:
        # Trigger WebSocket consumer
        payload = dict(order_id=instance.order.pk, body=instance.body)
        notify = Notification.objects.create(body=f'New comment on order no. {instance.order.pk}', type=2)
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            'orders_orders',
            {
                'type': 'notification',
                'data': {"payload": payload,
                         'url': reverse('admin:notification_read', kwargs={'pk': notify.pk}),
                         "type": 2},
                'message': notify.body
            }
        )


@receiver(pre_save, sender=Order)
def handle_order_cancellation(sender, instance, **kwargs):
    try:
        old_instance = sender.objects.get(pk=instance.pk)
        old_value = getattr(old_instance, 'canceled')
        payload = dict(url=reverse('admin:table_order_details',
                                   kwargs={'pk': getattr(instance, 'table_id'), 'order_id': getattr(instance, 'pk')}),
                       order_id=getattr(instance, 'pk'),
                       table_id=getattr(instance, 'table_id'),
                       type='cancel'
                       )
        if not old_value and instance.canceled is True:
            # Trigger WebSocket consumer
            notify = Notification.objects.create(
                body=f'Order has been canceled in table no.{instance.table_id}', type=1)
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                'orders_orders',
                {
                    'type': 'notification',
                    'data': {"payload": payload,
                             'url': reverse('admin:notification_read', kwargs={'pk': notify.pk}), "type": 2},
                    'message': notify.body
                }
            )
    except sender.DoesNotExist:
        return


@receiver(pre_save, sender=Order)
def handle_order_acceptation(sender, instance, **kwargs):
    try:
        old_instance = sender.objects.get(pk=instance.pk)
        old_value = getattr(old_instance, 'order_accept')
        payload = dict(
            type='order',
        )
        if not old_value and instance.order_accept:
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                'orders_orders',
                {
                    'type': 'notification',
                    'data': {"payload": payload,
                             'token': instance.user_token,
                             },
                    'message': f"Order no.{instance.pk} was accepted",
                }
            )
    except sender.DoesNotExist:
        return
