from django.urls import path
from django.contrib.auth.decorators import login_required

from apps.inventory.views import (
    kardex_valorizado_glp_page,
    get_kardex_valorizado_glp,
    get_list_kardex_valorizado_glp,
    save_glp_kardex_salida_factura,
    save_glp_kardex_salida_boleta,
)
from apps.inventory.purchase_views import (
    glp_purchase_list_page,
    get_glp_purchase_list,
    glp_purchase_create_page,
    glp_purchase_detail_page,
    get_glp_purchase_invoice_modal,
    get_glp_purchase_summary_modal,
    get_glp_purchase_programming_modal,
    get_glp_purchase_warehouse_modal,
    get_glp_purchase_expense_modal,
    get_glp_programming_detail,
    save_purchase_header_view,
    save_purchase_detail_view,
    save_purchase_programming_view,
    save_purchase_travel_expense_view,
    save_purchase_transfer_view,
)

urlpatterns = [
    # Kardex valorizado
    path('kardex_valorizado_glp/', login_required(kardex_valorizado_glp_page), name='kardex_valorizado_glp'),
    path('get_kardex_valorizado_glp/', get_kardex_valorizado_glp, name='get_kardex_valorizado_glp'),
    path('get_list_kardex_valorizado_glp/', get_list_kardex_valorizado_glp, name='get_list_kardex_valorizado_glp'),
    path('save_glp_kardex_salida_factura/', login_required(save_glp_kardex_salida_factura), name='save_glp_kardex_salida_factura'),
    path('save_glp_kardex_salida_boleta/', login_required(save_glp_kardex_salida_boleta), name='save_glp_kardex_salida_boleta'),

    # Compras GLP
    path('purchases/', login_required(glp_purchase_list_page), name='glp_purchase_list'),
    path('purchases/new/', login_required(glp_purchase_create_page), name='glp_purchase_new'),
    path('purchases/<int:pk>/', login_required(glp_purchase_detail_page), name='glp_purchase_detail'),
    path('get_glp_purchase_list/', login_required(get_glp_purchase_list), name='get_glp_purchase_list'),
    path('get_glp_purchase_invoice_modal/', login_required(get_glp_purchase_invoice_modal), name='get_glp_purchase_invoice_modal'),
    path('get_glp_purchase_summary_modal/', login_required(get_glp_purchase_summary_modal), name='get_glp_purchase_summary_modal'),
    path('get_glp_purchase_programming_modal/', login_required(get_glp_purchase_programming_modal), name='get_glp_purchase_programming_modal'),
    path('get_glp_purchase_warehouse_modal/', login_required(get_glp_purchase_warehouse_modal), name='get_glp_purchase_warehouse_modal'),
    path('get_glp_purchase_expense_modal/', login_required(get_glp_purchase_expense_modal), name='get_glp_purchase_expense_modal'),
    path('get_glp_programming_detail/<int:pk>/', login_required(get_glp_programming_detail), name='get_glp_programming_detail'),
    path('save_purchase_header/', login_required(save_purchase_header_view), name='save_purchase_header'),
    path('save_purchase_detail/', login_required(save_purchase_detail_view), name='save_purchase_detail'),
    path('save_purchase_programming/', login_required(save_purchase_programming_view), name='save_purchase_programming'),
    path('save_purchase_travel_expense/', login_required(save_purchase_travel_expense_view), name='save_purchase_travel_expense'),
    path('save_purchase_transfer/', login_required(save_purchase_transfer_view), name='save_purchase_transfer'),
]
