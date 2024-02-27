import calendar
import decimal
from collections import defaultdict
from http import HTTPStatus

import pytz
from django.db.models import Q, Max, F, Prefetch, Window
from django.db.models.functions import Lag
from django.shortcuts import render
from django.utils import timezone
from django.views.generic import View, TemplateView, UpdateView, CreateView
from django.views.decorators.csrf import csrf_exempt
from .models import *
from apps.hrm.models import Subsidiary, Employee
from django.http import JsonResponse
from .forms import *
from django.urls import reverse_lazy
from apps.sales.models import Product, SubsidiaryStore, ProductStore, ProductDetail, ProductRecipe, \
    ProductSubcategory, ProductSupplier, \
    TransactionPayment, Order, LoanPayment, Kardex
from apps.sales.views import kardex_ouput, kardex_input, kardex_initial, calculate_minimum_unit, Supplier
from apps.hrm.models import Subsidiary
import json
from django.db import DatabaseError, IntegrityError
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models.fields.files import ImageFieldFile
from django.template import loader
from datetime import datetime
from datetime import timedelta
from django.db import DatabaseError, IntegrityError
from django.core import serializers
from datetime import date
# Create your views here.
from .. import sales
from ..accounting.models import CashFlow, Cash
from ..buys.models import Purchase
from ..hrm.views import get_subsidiary_by_user
from ..sales.funtions import get_orders_for_status_account


class Index(TemplateView):
    # template_name = 'dashboard.html'
    # template_name = 'vetstore/home.html'
    template_name = 'comercial/../../templates/main.html'


# ---------------------------------------Truck-----------------------------------
class TruckList(View):
    model = Truck
    form_class = FormTruck
    template_name = 'comercial/truck_list.html'

    def get_queryset(self):
        return self.model.objects.all()

    def get_context_data(self, **kwargs):
        contexto = {}
        contexto['trucks'] = self.get_queryset()  # agregamos la consulta al contexto
        contexto['form'] = self.form_class
        return contexto

    def get(self, request, *args, **kwargs):
        return render(request, self.template_name, self.get_context_data())


class TruckCreate(CreateView):
    model = Truck
    form_class = FormTruck
    template_name = 'comercial/truck_create.html'
    success_url = reverse_lazy('comercial:truck_list')

    def get_context_data(self, **kwargs):
        ctx = super(TruckCreate, self).get_context_data(**kwargs)
        ctx['brands'] = TruckBrand.objects.all()
        ctx['models'] = TruckModel.objects.all()
        return ctx


class TruckUpdate(UpdateView):
    model = Truck
    form_class = FormTruck
    template_name = 'comercial/truck_update.html'
    success_url = reverse_lazy('comercial:truck_list')

    def get_context_data(self, **kwargs):
        ctx = super(TruckUpdate, self).get_context_data(**kwargs)
        ctx['brands'] = TruckBrand.objects.all()
        ctx['models'] = TruckModel.objects.all()
        return ctx


# -------------------------------------- Towing -----------------------------------


class TowingList(View):
    model = Towing
    form_class = FormTowing
    template_name = 'comercial/towing_list.html'

    def get_queryset(self):
        return self.model.objects.all()

    def get_context_data(self, **kwargs):
        contexto = {}
        contexto['towings'] = self.get_queryset()  # agregamos la consulta al contexto
        contexto['form'] = self.form_class
        return contexto

    def get(self, request, *args, **kwargs):
        return render(request, self.template_name, self.get_context_data())


class TowingCreate(CreateView):
    model = Towing
    form_class = FormTowing
    template_name = 'comercial/towing_create.html'
    success_url = reverse_lazy('comercial:towing_list')

    def get_context_data(self, **kwargs):
        ctx = super(TowingCreate, self).get_context_data(**kwargs)
        ctx['brands'] = TowingBrand.objects.all()
        ctx['models'] = TowingModel.objects.all()
        return ctx


class TowingUpdate(UpdateView):
    model = Towing
    form_class = FormTowing
    template_name = 'comercial/towing_update.html'
    success_url = reverse_lazy('comercial:towing_list')

    def get_context_data(self, **kwargs):
        ctx = super(TowingUpdate, self).get_context_data(**kwargs)
        ctx['brands'] = TowingBrand.objects.all()
        ctx['models'] = TowingModel.objects.all()
        return ctx


# ----------------------------------------Programming-------------------------------


class ProgrammingCreate(CreateView):
    model = Programming
    form_class = FormProgramming
    template_name = 'comercial/programming_list.html'
    success_url = reverse_lazy('comercial:programming_list')


class ProgrammingList(View):
    model = Programming
    form_class = FormProgramming
    template_name = 'comercial/programming_create.html'

    def get_context_data(self, **kwargs):
        user_id = self.request.user.id
        user_obj = User.objects.get(pk=int(user_id))
        subsidiary_obj = get_subsidiary_by_user(user_obj)

        my_date = datetime.now()
        formatdate = my_date.strftime("%Y-%m-%d")
        context = {
            'subsidiaries': Subsidiary.objects.exclude(name=subsidiary_obj.name),
            'employees': Employee.objects.all(),
            'trucks': Truck.objects.all(),
            'towings': Towing.objects.all(),
            'choices_status': Programming._meta.get_field('status').choices,
            'form': self.form_class,
            'current_date': formatdate,
            'subsidiary_origin': subsidiary_obj,
            'programmings': get_programmings(need_rendering=False, subsidiary_obj=subsidiary_obj)
        }
        return context

    def get(self, request, *args, **kwargs):
        return render(request, self.template_name, self.get_context_data())


@csrf_exempt
def new_programming(request):
    if request.method == 'POST':

        weight = 0
        if len(request.POST.get('weight', 0)) > 0:
            weight = float(request.POST.get('weight', 0))

        truck = request.POST.get('truck', '')
        departure_date = request.POST.get('departure_date')

        arrival_date = None
        if len(request.POST.get('arrival_date', '')):
            arrival_date = request.POST.get('arrival_date', '')

        status = request.POST.get('status', '')
        towing = request.POST.get('towing', '')
        subsidiary_origin = request.POST.get('origin', '')
        subsidiary_destiny = request.POST.get('destiny', '')
        observation = request.POST.get('observation', '')
        order = request.POST.get('order', '')
        km_initial = request.POST.get('km_initial', '')
        km_ending = request.POST.get('km_ending', '')
        pilot = request.POST.get('pilot', '')
        copilot = request.POST.get('copilot', '')

        pilot_obj = Employee.objects.get(pk=int(pilot))

        if len(truck) > 0:
            truck_obj = Truck.objects.get(id=truck)
            towing_obj = None
            if len(towing) > 0:
                towing_obj = Towing.objects.get(id=towing)
            subsidiary_origin_obj = Subsidiary.objects.get(id=subsidiary_origin)
            subsidiary_destiny_obj = Subsidiary.objects.get(id=subsidiary_destiny)
            data_programming = {
                'departure_date': departure_date,
                'arrival_date': arrival_date,
                'status': status,
                'type': 'G',
                'weight': weight,
                'truck': truck_obj,
                'towing': towing_obj,
                'subsidiary': subsidiary_origin_obj,
                'order': order,
                'km_initial': km_initial,
                'km_ending': km_ending,
                'observation': observation,
            }
            programming_obj = Programming.objects.create(**data_programming)
            programming_obj.save()

            set_employee_pilot_obj = SetEmployee(
                programming=programming_obj,
                employee=pilot_obj,
                function='P',
            )
            set_employee_pilot_obj.save()

            if copilot != '0':
                copilot_obj = Employee.objects.get(pk=int(copilot))
                set_employee_copilot_obj = SetEmployee(
                    programming=programming_obj,
                    employee=copilot_obj,
                    function='C',
                )
                set_employee_copilot_obj.save()

            route_origin_obj = Route(
                programming=programming_obj,
                subsidiary=subsidiary_origin_obj,
                type='O',
            )
            route_origin_obj.save()

            route_destiny_obj = Route(
                programming=programming_obj,
                subsidiary=subsidiary_destiny_obj,
                type='D',
            )
            route_destiny_obj.save()

            user_id = request.user.id
            user_obj = User.objects.get(pk=int(user_id))
            subsidiary_obj = get_subsidiary_by_user(user_obj)

            return JsonResponse({
                'success': True,
                'message': 'La Programacion se guardo correctamente.',
                'grid': get_programmings(need_rendering=True, subsidiary_obj=subsidiary_obj),
            })
    return JsonResponse({'error': True, 'message': 'Error de peticion.'})


def get_programming(request):
    if request.method == 'GET':
        id_programming = request.GET.get('programming', '')
        programming_obj = Programming.objects.get(id=int(id_programming))
        tpl = loader.get_template('comercial/programming_form.html')
        user_id = request.user.id
        user_obj = User.objects.get(pk=int(user_id))
        subsidiary_obj = get_subsidiary_by_user(user_obj)

        print('origin')
        print(programming_obj.route_set.all())
        print(programming_obj.route_set.filter(type='O'))
        print(programming_obj.route_set.filter(type='O').first())
        print(programming_obj.setemployee_set.filter(function='P').first())

        context = ({
            'programming_obj': programming_obj,
            'origin': programming_obj.route_set.filter(type='O').first(),
            'destiny': programming_obj.route_set.filter(type='D').first(),
            'pilot': programming_obj.setemployee_set.filter(function='P').first(),
            'copilot': programming_obj.setemployee_set.filter(function='C').first(),
            'subsidiary_origin': subsidiary_obj,
            'subsidiaries': Subsidiary.objects.all(),
            'employees': Employee.objects.all(),
            'trucks': Truck.objects.all(),
            'towings': Towing.objects.all(),
            'choices_status': Programming._meta.get_field('status').choices,
        })

        return JsonResponse({
            'grid': tpl.render(context),
        }, status=HTTPStatus.OK)


def update_programming(request):
    print(request.method)
    data = {}
    if request.method == 'POST':
        id_programming = request.POST.get('programming', '')
        programming_obj = Programming.objects.get(id=int(id_programming))

        id_subsidiary_origin = request.POST.get('origin', '')
        id_subsidiary_destiny = request.POST.get('destiny', '')
        id_pilot = request.POST.get('pilot', '')
        id_copilot = request.POST.get('copilot', '')
        id_truck = request.POST.get('truck', '')
        id_towing = request.POST.get('towing', '')
        departure_date = request.POST.get('departure_date')
        arrival_date = request.POST.get('arrival_date', '')
        status = request.POST.get('status', '')
        order = request.POST.get('order', '')
        km_initial = request.POST.get('km_initial', '')
        km_ending = request.POST.get('km_ending', '')
        weight = request.POST.get('weight', 0)
        observation = request.POST.get('observation', '')

        set_employee_obj = SetEmployee.objects.filter(programming=programming_obj)
        old_pilot_obj = set_employee_obj.filter(function='P').first()
        old_copilot_obj = set_employee_obj.filter(function='C').first()

        new_pilot_obj = Employee.objects.get(pk=int(id_pilot))
        if new_pilot_obj != old_pilot_obj:
            set_employee_obj.filter(function='P').delete()
            SetEmployee(employee=new_pilot_obj, function='P', programming=programming_obj).save()

        if id_copilot != '0':
            new_copilot_obj = Employee.objects.get(pk=int(id_copilot))
            if new_copilot_obj != old_copilot_obj:
                set_employee_obj.filter(function='C').delete()
                SetEmployee(employee=new_copilot_obj, function='C', programming=programming_obj).save()

        if len(id_truck) > 0:
            truck_obj = Truck.objects.get(id=int(id_truck))
            programming_obj.truck = truck_obj

        if len(id_towing) > 0:
            towing_obj = Towing.objects.get(id=int(id_towing))
            programming_obj.towing = towing_obj

        new_subsidiary_origin_obj = None
        new_subsidiary_destiny_obj = None

        if len(id_subsidiary_origin) > 0:
            new_subsidiary_origin_obj = Subsidiary.objects.get(pk=int(id_subsidiary_origin))
        if len(id_subsidiary_destiny) > 0:
            new_subsidiary_destiny_obj = Subsidiary.objects.get(pk=int(id_subsidiary_destiny))

        routes_obj = Route.objects.filter(programming=programming_obj)
        old_subsidiary_origin_obj = routes_obj.filter(type='O').first()
        old_subsidiary_destiny_obj = routes_obj.filter(type='D').first()

        if new_subsidiary_origin_obj != old_subsidiary_origin_obj:
            routes_obj.filter(type='O').delete()
            Route(subsidiary=new_subsidiary_origin_obj, type='O', programming=programming_obj).save()

        if new_subsidiary_destiny_obj != old_subsidiary_destiny_obj:
            routes_obj.filter(type='D').delete()
            Route(subsidiary=new_subsidiary_destiny_obj, type='D', programming=programming_obj).save()

        programming_obj.weight = float(weight)
        programming_obj.status = status
        programming_obj.departure_date = departure_date
        programming_obj.arrival_date = arrival_date
        programming_obj.km_initial = km_initial
        programming_obj.km_ending = km_ending

        if len(order) > 0:
            programming_obj.order = int(order)
        programming_obj.observation = observation
        programming_obj.save()

        user_id = request.user.id
        user_obj = User.objects.get(pk=int(user_id))
        subsidiary_obj = get_subsidiary_by_user(user_obj)

        return JsonResponse({
            'success': True,
            'message': 'La Programacion se guardo correctamente.',
            'grid': get_programmings(need_rendering=True, subsidiary_obj=subsidiary_obj),
        })
    return JsonResponse({'error': True, 'message': 'Error de peticion.'})


def get_programmings(need_rendering, subsidiary_obj=None):
    my_date = datetime.now()
    formatdate = my_date.strftime("%Y-%m-%d")
    if subsidiary_obj is None:
        # programmings = Programming.objects.all().order_by('id')
        programmings = Programming.objects.filter(departure_date__gte=formatdate, status__in=['P', 'R']).order_by('id')
    else:
        # programmings = Programming.objects.filter(subsidiary=subsidiary_obj).order_by('id')
        programmings = Programming.objects.filter(subsidiary=subsidiary_obj, departure_date__gte=formatdate,
                                                  status__in=['P', 'R']).order_by('id')
    print(programmings)
    # programmings = Programming.objects.filter(departure_date__gte=formatdate, status__in=['P', 'R']).order_by('id')
    if need_rendering:
        tpl = loader.get_template('comercial/programming_list.html')
        context = ({'programmings': programmings, })
        return tpl.render(context)
    return programmings


# ----------------------------------------Guide------------------------------------

def new_guide(request):
    user_id = request.user.id
    user_obj = User.objects.get(id=user_id)
    subsidiary_obj = get_subsidiary_by_user(user_obj)
    form_obj = FormGuide()
    programmings = Programming.objects.filter(status__in=['P'], subsidiary=subsidiary_obj).order_by('id')
    return render(request, 'comercial/guide.html', {
        'form': form_obj,
        'programmings': programmings
    })


def get_programming_guide(request):
    if request.method == 'GET':
        id_programming = request.GET.get('programming', '')
        programming_obj = Programming.objects.get(id=int(id_programming))
        pilot = programming_obj.setemployee_set.filter(function='P').first().employee
        name = pilot.names + ' ' + pilot.paternal_last_name

        # print(programming_obj.route_set.filter(type='O').first().subsidiary.name)

        user_id = request.user.id
        user_obj = User.objects.get(id=user_id)
        subsidiary_obj = get_subsidiary_by_user(user_obj)
        subsidiary_store_obj = SubsidiaryStore.objects.filter(subsidiary=subsidiary_obj, category='V').first()
        products = Product.objects.filter(productstore__subsidiary_store=subsidiary_store_obj)

        tpl = loader.get_template('comercial/detail_guide.html')
        context = ({
            'products': products,
            'type': GuideDetail._meta.get_field('type').choices,
        })
        return JsonResponse({
            'origin': programming_obj.route_set.filter(type='O').first().subsidiary.name,
            'destiny': programming_obj.route_set.filter(type='D').first().subsidiary.name,
            'pilot': name,
            'departure_date': programming_obj.departure_date,
            'products_grids': tpl.render(context),
            'license_plate': programming_obj.truck.license_plate,
            'truck_brand': programming_obj.truck.truck_model.truck_brand.name,
            'truck_serial': programming_obj.truck.serial,
            'license': programming_obj.setemployee_set.filter(function='P').first().employee.n_license,
            'license_type': programming_obj.setemployee_set.filter(
                function='P').first().employee.get_license_type_display(),

        }, status=HTTPStatus.OK)


def get_quantity_product(request):
    if request.method == 'GET':
        id_product = request.GET.get('pk', '')
        # print(id_product)
        product_obj = Product.objects.get(pk=int(id_product))
        # print(product_obj)
        user = request.user.id
        user_obj = User.objects.get(id=user)
        subsidiary_obj = get_subsidiary_by_user(user_obj)
        # print(subsidiary_obj)
        subsidiary_store_obj = SubsidiaryStore.objects.filter(subsidiary=subsidiary_obj, category='V').first()
        # print(subsidiary_store_obj)
        product_store_obj = ProductStore.objects.get(product__id=id_product, subsidiary_store=subsidiary_store_obj)
        # print(product_store_obj)
        units_obj = Unit.objects.filter(productdetail__product=product_obj)
        # print(units_obj)
        serialized_units = serializers.serialize('json', units_obj)
        return JsonResponse({
            'quantity': product_store_obj.stock,
            'units': serialized_units,
            'id_product_store': product_store_obj.id
        }, status=HTTPStatus.OK)


def create_guide(request):
    if request.method == 'GET':
        guides_request = request.GET.get('guides', '')
        data_guides = json.loads(guides_request)
        print(data_guides)
        user_id = request.user.id
        user_obj = User.objects.get(pk=int(user_id))
        serial = str(data_guides["Serial"])
        code = str(data_guides["Code"])
        minimal_cost = float(data_guides["Minimal_cost"])
        programming = int(data_guides["Programming"])
        programming_obj = Programming.objects.get(pk=programming)

        new_guide = {
            'serial': serial,
            'code': code,
            'minimal_cost': minimal_cost,
            'user': user_obj,
            'programming': programming_obj,
        }
        guide_obj = Guide.objects.create(**new_guide)
        guide_obj.save()

        for detail in data_guides['Details']:
            quantity = int(detail['Quantity'])

            # recuperamos del producto
            product_id = int(detail['Product'])
            product_obj = Product.objects.get(id=product_id)

            # recuperamos la unidad
            unit_id = int(detail['Unit'])
            unit_obj = Unit.objects.get(id=unit_id)
            _type = detail["type"]
            new_detail_guide = {
                'guide': guide_obj,
                'product': product_obj,
                'quantity': quantity,
                'unit_measure': unit_obj,
                'type': _type,

            }
            new_detail_guide_obj = GuideDetail.objects.create(**new_detail_guide)
            new_detail_guide_obj.save()

            # recuperamos del almacen
            store_id = int(detail['Store'])

            kardex_ouput(store_id, quantity, guide_detail_obj=new_detail_guide_obj)
        return JsonResponse({
            'message': 'Se guardo la guia correctamente.',
            'programming': programming_obj.id,
            'guide': guide_obj.id
        }, status=HTTPStatus.OK)


def guide_detail_list(request):
    # programmings = Programming.objects.filter(status__in=['P'], guide__isnull=False).order_by('id')
    user = request.user.id
    user_obj = User.objects.get(id=user)
    date_now = datetime.now().strftime("%Y-%m-%d")
    subsidiaries = Subsidiary.objects.all()
    current_subsidiary_obj = get_subsidiary_by_user(user_obj)
    return render(request, 'comercial/guide_detail_programming.html', {
        'date': date_now,
        'subsidiaries': subsidiaries,
        'current_subsidiary_obj': current_subsidiary_obj,
        'programmings': None
    })


def report_guide_by_plate(request):
    if request.method == 'GET':
        date = datetime.now()
        date_now = date.strftime("%Y-%m-%d")
        truck_set = Truck.objects.all()

        return render(request, 'comercial/report_guides_by_plate.html', {
            'date_now': date_now,
            'trucks': truck_set,
        })
    return JsonResponse({'error': True, 'message': 'Error de peticion.'})


def report_guides_by_plate_grid(request):
    if request.method == 'POST':
        start_date = request.POST.get('start-date', '')
        end_date = request.POST.get('end-date', '')
        truck_plate = request.POST.get('plate', '')

        programmings_set = Programming.objects.filter(status__in=['F'], departure_date__range=(start_date, end_date),
                                                      guide__isnull=False, truck=truck_plate).order_by('departure_date')

        return JsonResponse({
            'grid': get_dict_programming_guides_queries(programmings_set),
        }, status=HTTPStatus.OK)


def get_dict_programming_guides_queries(programmings_set):
    dictionary = []

    guide_items = []
    count = 0
    for p in programmings_set:
        count = programmings_set.count()
        new = {
            'id': p.id,
            'truck': p.truck.license_plate,
            'pilot': p.get_pilot().full_name,
            'departure_date': p.departure_date,
            'arrival_date': p.arrival_date,
            'origin': p.route_set.first().subsidiary.name,
            'destiny': p.route_set.last().subsidiary.name,
            'guide_items': [],
            'rowspan': 0
        }
        if p.guide_set.all:
            counter = 0
            for g in p.guide_set.all():
                counter = g.guidedetail_set.count()
                guide_items = {
                    'id': g.id,
                    'serial': g.serial,
                    'code': g.code,
                    'minimal_cost': g.minimal_cost,
                    'status': g.status,
                    'counter': counter,
                    'detail_guide': []
                }
                for gd in g.guidedetail_set.all():
                    guide_detail_item = {
                        'id': gd.id,
                        'product': gd.product,
                        'quantity': gd.quantity,
                        'unit': gd.unit_measure,
                        'type': gd.get_type_display(),
                        'weight': gd.weight,
                        'rowspan': g.guidedetail_set.count(),
                    }
                    guide_items.get('detail_guide').append(guide_detail_item)
            new['rowspan'] = counter
            new.get('guide_items').append(guide_items)
        dictionary.append(new)
    tpl = loader.get_template('comercial/report_guide_by_plate_grid.html')
    context = ({
        'dictionary': dictionary,
        'count': count,
    })

    return tpl.render(context)


def guide_by_programming(request):
    if request.method == 'GET':
        id_programming = request.GET.get('programming', '')
        programming_obj = Programming.objects.get(id=int(id_programming))
        guide_obj = Guide.objects.filter(programming=programming_obj).first()
        details = GuideDetail.objects.filter(guide=guide_obj)

        tpl = loader.get_template('comercial/guide_detail_list.html')
        context = ({'guide': guide_obj, 'details': details})
        return JsonResponse({
            # 'message': 'guias recuperadas',
            'grid': tpl.render(context),
        }, status=HTTPStatus.OK)


def programmings_by_date(request):
    if request.method == 'GET':
        start_date = request.GET.get('start_date', '')
        end_date = request.GET.get('end_date', '')
        subsidiary_id = int(request.GET.get('subsidiary_id', '0'))

        programmings = Programming.objects.filter(
            status__in=['F'],
            departure_date__range=(start_date, end_date),
            guide__isnull=False
        )

        if subsidiary_id > 0:
            subsidiary_obj = Subsidiary.objects.get(id=int(subsidiary_id))
            programmings = programmings.filter(subsidiary=subsidiary_obj)
        programmings = programmings.order_by('id')

        user = request.user.id
        user_obj = User.objects.get(id=user)
        date_now = datetime.now().strftime("%Y-%m-%d")
        subsidiaries = Subsidiary.objects.all()
        current_subsidiary_obj = get_subsidiary_by_user(user_obj)

        tpl = loader.get_template('comercial/guide_detail_programming_list.html')
        context = ({
            'date': date_now,
            'subsidiaries': subsidiaries,
            'current_subsidiary_obj': current_subsidiary_obj,
            'programmings': programmings
        })
        return JsonResponse({
            'grid': tpl.render(context),
        }, status=HTTPStatus.OK)


def programming_receive_by_sucursal(request):
    if request.method == 'GET':
        user_id = request.user.id
        user_obj = User.objects.get(id=user_id)
        subsidiary_obj = get_subsidiary_by_user(user_obj)
        routes = Route.objects.filter(type='D', subsidiary=subsidiary_obj)
        # programmings = Programming.objects.filter(status__in=['P'], guide__isnull=False, route__in=routes).order_by('id')
        programmings = Programming.objects.filter(status__in=['P'], route__in=routes).order_by('id')

        status_obj = Programming._meta.get_field('status').choices
        return render(request, 'comercial/programming_receive.html', {
            'programmings': programmings,
            'choices_status': status_obj,

        })


def programming_receive_by_sucursal_detail_guide(request):
    if request.method == 'GET':
        id_programming = request.GET.get('programming', '')
        programming_obj = Programming.objects.get(id=int(id_programming))
        guide_obj = Guide.objects.filter(programming=programming_obj).first()
        details = GuideDetail.objects.filter(guide=guide_obj)
        user_id = request.user.id
        user_obj = User.objects.get(id=user_id)
        subsidiary_obj = get_subsidiary_by_user(user_obj)
        subsidiaries_store_obj = SubsidiaryStore.objects.filter(subsidiary=subsidiary_obj)
        # product_store_obj = ProductStore.objects.get(subsidiary_store=subsidiaries_store_obj)

        tpl = loader.get_template('comercial/programming_receive_detail.html')
        context = ({
            'guide': guide_obj,
            'details': details,
            'subsidiaries_store': subsidiaries_store_obj,

        })

        return JsonResponse({
            'message': 'guias recuperadas',
            'grid': tpl.render(context),
        }, status=HTTPStatus.OK)


def get_stock_by_store(request):
    if request.method == 'GET':
        id_product = request.GET.get('ip', '')
        id_subsidiary_store = request.GET.get('iss', '')
        print(id_product)
        print(id_subsidiary_store)
        product_obj = Product.objects.get(pk=int(id_product))
        print(product_obj)
        subsidiary_store_obj = SubsidiaryStore.objects.get(id=int(id_subsidiary_store))
        print(subsidiary_store_obj)

        quantity = ''
        id_product_store = 0
        product_store_obj = None
        try:
            product_store_obj = ProductStore.objects.get(product=product_obj, subsidiary_store=subsidiary_store_obj)
        except ProductStore.DoesNotExist:
            quantity = 'SP'
        if product_store_obj is not None:
            print(product_store_obj)
            quantity = str(product_store_obj.stock)
            id_product_store = product_store_obj.id

        return JsonResponse({
            'quantity': quantity,
            'id_product_store': id_product_store
        }, status=HTTPStatus.OK)


def update_stock_from_programming(request):
    if request.method == 'GET':
        programming_request = request.GET.get('programming', '')
        data_programming = json.loads(programming_request)
        programming = int(data_programming["id_programming"])
        programming_obj = Programming.objects.get(pk=programming)
        programming_obj.status = 'F'
        programming_obj.save()

        for detail in data_programming['Details']:
            quantity = decimal.Decimal((detail['Quantity']).replace(',', '.'))
            product_id = int(detail['Product'])
            detail_id = int(detail['detail_id'])
            product_obj = Product.objects.get(id=product_id)
            detail_guide_obj = GuideDetail.objects.get(id=detail_id)
            type = str(detail['Type'])
            unit = str(detail['Unit']).strip()
            unit_obj = Unit.objects.get(description=unit)
            # product_detail_obj = ProductDetail.objects.get(product=product_obj, unit=unit_obj)
            user = request.user.id
            user_obj = User.objects.get(id=user)
            subsidiary_obj = get_subsidiary_by_user(user_obj)
            if type == '1':
                subsidiary_store_obj = SubsidiaryStore.objects.filter(subsidiary=subsidiary_obj, category='I').first()
                subcategory_obj = ProductSubcategory.objects.get(name='FIERRO', product_category__name='FIERRO')
                product_recipe_obj = ProductRecipe.objects.filter(product=product_obj,
                                                                  product_input__product_subcategory=subcategory_obj)
                product_obj = product_recipe_obj.first().product_input

            if type == '2':
                subsidiary_store_obj = SubsidiaryStore.objects.filter(subsidiary=subsidiary_obj, category='V').first()

            if type == '3':
                subsidiary_store_obj = SubsidiaryStore.objects.filter(subsidiary=subsidiary_obj, category='R').first()

            if type == '4':
                subsidiary_store_obj = SubsidiaryStore.objects.filter(subsidiary=subsidiary_obj, category='R').first()
                subcategory_obj = ProductSubcategory.objects.get(name='FIERRO', product_category__name='FIERRO')
                product_recipe_obj = ProductRecipe.objects.filter(product=product_obj,
                                                                  product_input__product_subcategory=subcategory_obj)
                product_obj = product_recipe_obj.first().product_input

            try:
                product_store_obj = ProductStore.objects.get(product__id=product_obj.id,
                                                             subsidiary_store=subsidiary_store_obj)
            except ProductStore.DoesNotExist:
                product_store_obj = None
                # unit_min_detail_product = ProductDetail.objects.get(product=product_obj, unit=unit_obj).quantity_minimum
            quantity_minimum_unit = calculate_minimum_unit(quantity, unit_obj, product_obj)

            if product_store_obj is None:
                new_product_store_obj = ProductStore(
                    product=product_obj,
                    subsidiary_store=subsidiary_store_obj,
                    stock=quantity_minimum_unit
                )
                new_product_store_obj.save()
                kardex_initial(new_product_store_obj, quantity_minimum_unit,
                               product_obj.calculate_minimum_price_sale(),
                               guide_detail_obj=detail_guide_obj)
            else:
                kardex_input(product_store_obj.id, quantity_minimum_unit,
                             product_obj.calculate_minimum_price_sale(),
                             guide_detail_obj=detail_guide_obj)
    return JsonResponse({
        'message': 'Se guardo la guia correctamente.',
    }, status=HTTPStatus.OK)


def output_guide(request):
    # programmings = Programming.objects.filter(status__in=['P'], guide__isnull=False).order_by('id')
    motives = GuideMotive.objects.filter(type='S')
    user_id = request.user.id
    user_obj = User.objects.get(pk=int(user_id))
    subsidiary_obj = get_subsidiary_by_user(user_obj)
    my_date = datetime.now()
    formatdate = my_date.strftime("%Y-%m-%d")
    product_set = Product.objects.filter(productstore__subsidiary_store__subsidiary=subsidiary_obj)

    return render(request, 'comercial/output_guide.html', {
        'motives': motives,
        'subsidiaries': Subsidiary.objects.exclude(name=subsidiary_obj.name),
        'current_date': formatdate,
        'subsidiary_origin': subsidiary_obj,
        'product_set': product_set,
        'choices_document_type_attached': Guide._meta.get_field('document_type_attached').choices,
    })


def input_guide(request):
    # programmings = Programming.objects.filter(status__in=['P'], guide__isnull=False).order_by('id')
    motives = GuideMotive.objects.filter(type='E')
    my_date = datetime.now()
    formatdate = my_date.strftime("%Y-%m-%d")
    user_id = request.user.id
    user_obj = User.objects.get(pk=int(user_id))
    subsidiary_obj = get_subsidiary_by_user(user_obj)
    product_set = Product.objects.all()

    return render(request, 'comercial/input_guide.html', {
        'motives': motives,
        'current_date': formatdate,
        'product_set': product_set,
        'subsidiary_origin': subsidiary_obj,
        'choices_document_type_attached': Guide._meta.get_field('document_type_attached').choices,
    })


def get_products_by_subsidiary_store(request):
    if request.method == 'GET':
        pk = request.GET.get('pk', '')
        is_table = bool(int(request.GET.get('is_table')))
        subsidiary_store_obj = SubsidiaryStore.objects.get(id=int(pk))
        product_set = Product.objects.filter(productstore__subsidiary_store=subsidiary_store_obj)
        tpl = loader.get_template('comercial/io_guide_list.html')
        context = ({
            'product_set': product_set,
            'is_table': is_table,
            'subsidiary_store': subsidiary_store_obj,
        })

        product_stores = [(
            ps.pk,
            ps.product.id,
            ps.product.name,
            ps.stock,
            ps.product.calculate_minimum_unit(),
            ps.product.productdetail_set.filter(quantity_minimum=ps.product.calculate_minimum_unit()).first().unit.id,
        ) for ps in ProductStore.objects.filter(subsidiary_store=subsidiary_store_obj).order_by('product__name')]

        return JsonResponse({
            'success': True,
            'subsidiary_store': subsidiary_store_obj.name,
            'grid': tpl.render(context),
            # 'product_store_set_serialized': serializers.serialize('json', product_stores),
            'product_store_set_serialized': product_stores,
        }, status=HTTPStatus.OK)


def create_output_transfer(request):
    if request.method == 'GET':
        output_request = request.GET.get('transfer')
        data_transfer = json.loads(output_request)

        user_id = request.user.id
        user_obj = User.objects.get(id=user_id)
        subsidiary_obj = get_subsidiary_by_user(user_obj)
        document_number = str(data_transfer["Document"])
        total = decimal.Decimal((data_transfer["Total"]).replace(',', '.'))
        document_type_attached = str(data_transfer["DocumentTypeAttached"])
        motive = int(data_transfer["Motive"])
        observation = str(data_transfer["Observation"])
        # Outputs: 1, 3, 6, 7
        # Transfers: 4
        a = [1, 3, 4, 6, 7]
        if motive not in a:
            data = {'error': "solo se permite traspase entre almacenes de la misma sede y/o salidas permitidas."}
            response = JsonResponse(data)
            response.status_code = HTTPStatus.INTERNAL_SERVER_ERROR
            return response

        motive_obj = GuideMotive.objects.get(id=motive)
        origin = int(data_transfer["Origin"])
        origin_obj = SubsidiaryStore.objects.get(id=origin)

        destiny = int(data_transfer["Destiny"])
        destiny_obj = None
        if destiny != 0:
            destiny_obj = SubsidiaryStore.objects.get(id=destiny)
        if motive == 4 and destiny_obj is None:
            data = {'error': "no selecciono almacen destino."}
            response = JsonResponse(data)
            response.status_code = HTTPStatus.INTERNAL_SERVER_ERROR
            return response

        function = 'S'
        status = '1'  # En transito
        if motive != 4:  # if is not transfer
            function = 'A'
            status = '5'  # Extraido

        new_guide_obj = Guide(
            serial=subsidiary_obj.serial,
            document_number=document_number,
            document_type_attached=document_type_attached,
            minimal_cost=total,
            observation=observation.strip(),
            user=user_obj,
            guide_motive=motive_obj,
            status=status,
            subsidiary=subsidiary_obj,
        )
        new_guide_obj.save()

        new_origin_route_obj = Route(
            guide=new_guide_obj,
            subsidiary_store=origin_obj,
            type='O',
        )
        new_origin_route_obj.save()

        if destiny_obj is not None:
            new_destiny_route_obj = Route(
                guide=new_guide_obj,
                subsidiary_store=destiny_obj,
                type='D',
            )
            new_destiny_route_obj.save()

        new_guide_employee_obj = GuideEmployee(
            guide=new_guide_obj,
            user=user_obj,
            function=function,
        )
        new_guide_employee_obj.save()

        for details in data_transfer['Details']:
            product_id = int(details["Product"])
            product_store_id = int(details["ProductStore"])
            unit_id = int(details["Unit"])
            quantity_request = decimal.Decimal(details["Quantity"])
            price = decimal.Decimal(details["Price"])

            product_obj = Product.objects.get(id=product_id)
            unit_obj = Unit.objects.get(id=unit_id)

            new_guide_detail_obj = GuideDetail(
                guide=new_guide_obj,
                product=product_obj,
                quantity_request=quantity_request,
                quantity_sent=quantity_request,
                quantity=quantity_request,
                unit_measure=unit_obj,
            )
            new_guide_detail_obj.save()

            if motive != 4:
                product_store_obj = ProductStore.objects.get(id=product_store_id)
                kardex_ouput(product_store_obj.id, quantity_request, guide_detail_obj=new_guide_detail_obj)

        return JsonResponse({
            'message': 'La operación se Realizo correctamente.',
            'guide_id': new_guide_obj.id,
        }, status=HTTPStatus.OK)


def output_change_status(request):
    if request.method == 'GET':
        guide_id = request.GET.get('pk', '')
        status_id = request.GET.get('status', '')
        guide_obj = Guide.objects.get(id=int(guide_id))
        user_id = request.user.id
        user_obj = User.objects.get(id=user_id)

        if status_id == '2':  # Approve
            guide_obj.status = status_id
            guide_obj.save()
            new_guide_employee_obj = GuideEmployee(
                guide=guide_obj,
                user=user_obj,
                function='A',
            )
            new_guide_employee_obj.save()

        elif status_id == '4':  # Cancel
            guide_obj.status = status_id
            guide_obj.save()
            new_guide_employee_obj = GuideEmployee(
                guide=guide_obj,
                user=user_obj,
                function='C',
            )
            new_guide_employee_obj.save()

        return JsonResponse({
            'message': 'Se cambio el estado correctamente.',
        }, status=HTTPStatus.OK)


def output_workflow(request):
    user_id = request.user.id
    user_obj = User.objects.get(id=user_id)
    subsidiary_obj = get_subsidiary_by_user(user_obj)
    date_now = datetime.now().strftime("%Y-%m-%d")
    a = [1, 3, 4, 6, 7]
    guides_set = Guide.objects.filter(subsidiary=subsidiary_obj,
                                      guide_motive__type='S',
                                      guide_motive__id__in=a)
    if request.method == 'GET':
        guides_set = guides_set.filter(created_at__date=date_now)
    elif request.method == 'POST':
        date_initial = request.POST.get('date_initial', '')
        date_final = request.POST.get('date_final', '')
        guides_set = guides_set.filter(created_at__date__range=(date_initial, date_final))
    return render(request, 'comercial/output_workflow.html', {
        'guides': guides_set,
        'status': Guide._meta.get_field('status').choices,
        'date_now': date_now,
    })


def input_workflow(request):
    user_id = request.user.id
    user_obj = User.objects.get(id=user_id)
    subsidiary_obj = get_subsidiary_by_user(user_obj)
    date_now = datetime.now().strftime("%Y-%m-%d")
    guides_set = Guide.objects.filter(subsidiary=subsidiary_obj, guide_motive__type='E')
    if request.method == 'GET':
        guides_set = guides_set.filter(created_at__date=date_now)
    elif request.method == 'POST':
        date_initial = request.POST.get('date_initial', '')
        date_final = request.POST.get('date_final', '')
        guides_set = guides_set.filter(created_at__date__range=(date_initial, date_final))
    return render(request, 'comercial/input_workflow.html', {
        'guides': guides_set,
        'status': Guide._meta.get_field('status').choices,
        'date_now': date_now,
    })


def input_workflow_from_output(request):
    user_id = request.user.id
    user_obj = User.objects.get(id=user_id)
    subsidiary_obj = get_subsidiary_by_user(user_obj)
    date_now = datetime.now().strftime("%Y-%m-%d")
    # Outputs: 1, 3, 6, 7
    # Transfers: 4
    a = [4]
    guides_set = Guide.objects.filter(route__type='D',
                                      route__subsidiary_store__subsidiary=subsidiary_obj,
                                      guide_motive__type='S', guide_motive__id__in=a)
    if request.method == 'GET':
        guides_set = guides_set.filter(created_at__date=date_now)
    elif request.method == 'POST':
        date_initial = request.POST.get('date_initial', '')
        date_final = request.POST.get('date_final', '')
        guides_set = guides_set.filter(created_at__date__range=(date_initial, date_final))
    return render(request, 'comercial/input_workflow_from_output.html', {
        'guides': guides_set,
        'status': Guide._meta.get_field('status').choices,
        'date_now': date_now,
    })


def create_input_transfer(request):
    if request.method == 'GET':
        production_request = request.GET.get('transfer')
        data_transfer = json.loads(production_request)

        user_id = request.user.id
        user_obj = User.objects.get(id=user_id)
        subsidiary_obj = get_subsidiary_by_user(user_obj)
        document_number = str(data_transfer["Document"])
        total = decimal.Decimal((data_transfer["Total"]).replace(',', '.'))
        document_type_attached = str(data_transfer["DocumentTypeAttached"])
        motive = int(data_transfer["Motive"])
        # if motive != 4:
        #     data = {'error': "solo se permite traspase entre almacenes de la misma sede."}
        #     response = JsonResponse(data)
        #     response.status_code = HTTPStatus.INTERNAL_SERVER_ERROR
        #     return response
        motive_obj = GuideMotive.objects.get(id=motive)
        destiny = int(data_transfer["Destiny"])
        destiny_obj = SubsidiaryStore.objects.get(id=destiny)
        observation = str(data_transfer["Observation"])

        new_guide_obj = Guide(
            serial=subsidiary_obj.serial,
            document_number=document_number,
            document_type_attached=document_type_attached,
            minimal_cost=total,
            observation=observation.strip(),
            user=user_obj,
            guide_motive=motive_obj,
            status='2',
            subsidiary=subsidiary_obj,
        )
        new_guide_obj.save()

        new_destiny_route_obj = Route(
            guide=new_guide_obj,
            subsidiary_store=destiny_obj,
            type='D',
        )
        new_destiny_route_obj.save()

        new_guide_employee_obj = GuideEmployee(
            guide=new_guide_obj,
            user=user_obj,
            function='A',
        )
        new_guide_employee_obj.save()

        for details in data_transfer['Details']:
            product_id = int(details["Product"])
            unit_id = int(details["Unit"])
            quantity = decimal.Decimal(details["Quantity"])
            price = decimal.Decimal(details["Price"])

            product_obj = Product.objects.get(id=product_id)
            unit_obj = Unit.objects.get(id=unit_id)

            new_guide_detail_obj = GuideDetail(
                guide=new_guide_obj,
                product=product_obj,
                quantity=quantity,
                unit_measure=unit_obj,
            )
            new_guide_detail_obj.save()

            product_store_obj = ProductStore.objects.filter(product=product_obj, subsidiary_store=destiny_obj).last()
            if product_store_obj:
                kardex_input(product_store_obj.id, quantity, price, guide_detail_obj=new_guide_detail_obj)
            else:
                product_store_obj = ProductStore(product=product_obj, subsidiary_store=destiny_obj, stock=quantity)
                product_store_obj.save()
                kardex_initial(product_store_obj, stock=quantity, price_unit=price,
                               guide_detail_obj=new_guide_detail_obj)

        return JsonResponse({
            'message': 'La operación se Realizo correctamente.',
            'guide_id': new_guide_obj.id,

        }, status=HTTPStatus.OK)


def get_merchandise_of_output(request):
    if request.method == 'GET':
        pk = request.GET.get('pk', '')

        guide_obj = Guide.objects.get(id=int(pk))

        if guide_obj.status != '1':
            data = {'error': "Solo puede recepcionar mercaderia en transito!"}
            response = JsonResponse(data)
            response.status_code = HTTPStatus.INTERNAL_SERVER_ERROR
            return response

        t = loader.get_template('comercial/receive_merchandise.html')
        c = ({
            'guide': guide_obj,
        })

        return JsonResponse({
            'success': True,
            'form': t.render(c, request),
        })


def new_input_from_output(request):
    if request.method == 'GET':
        transfer_request = request.GET.get('transfer', '')
        data = json.loads(transfer_request)

        output_guide_id = int(data['Guide'])
        output_guide_obj = Guide.objects.get(pk=output_guide_id)

        user_id = request.user.id
        user_obj = User.objects.get(id=user_id)

        observation = str(data["Observation"])

        subsidiary_store_destiny_obj = output_guide_obj.get_destiny()
        subsidiary_store_origin_obj = output_guide_obj.get_origin()
        motive_obj = GuideMotive.objects.get(id=15)  # transfer

        # register new guide
        input_guide_obj = Guide(
            serial=subsidiary_store_destiny_obj.subsidiary.serial,
            document_number=output_guide_obj.get_serial(),
            document_type_attached=output_guide_obj.document_type_attached,
            # minimal_cost=total,
            observation=observation.strip(),
            user=user_obj,
            guide_motive=motive_obj,
            status='2',
            subsidiary=subsidiary_store_destiny_obj.subsidiary,
        )
        input_guide_obj.save()

        new_destiny_route_obj = Route(
            guide=input_guide_obj,
            subsidiary_store=subsidiary_store_destiny_obj,
            type='D',
        )
        new_destiny_route_obj.save()

        new_guide_employee_obj = GuideEmployee(
            guide=input_guide_obj,
            user=user_obj,
            function='A',
        )
        new_guide_employee_obj.save()
        # register new guide

        for detail in data['Details']:
            detail_id = int(detail["Detail"])
            quantity = decimal.Decimal(str(detail["Quantity"]).replace(',', '.'))

            if quantity > 0:

                # update output guide detail
                output_guide_detail_obj = GuideDetail.objects.get(id=detail_id)
                output_guide_detail_obj.quantity = quantity
                output_guide_detail_obj.save()
                # update output guide detail

                # output kardex
                output_product_store_obj = ProductStore.objects.get(
                    product=output_guide_detail_obj.product, subsidiary_store=subsidiary_store_origin_obj)
                kardex_ouput(output_product_store_obj.id, quantity, guide_detail_obj=output_guide_detail_obj)
                # output kardex

                # register input guide detail
                input_guide_detail_obj = GuideDetail(
                    guide=input_guide_obj,
                    product=output_guide_detail_obj.product,
                    quantity=quantity,
                    unit_measure=output_guide_detail_obj.unit_measure,
                )
                input_guide_detail_obj.save()
                # register input guide detail

                # input kardex
                input_product_store_obj = ProductStore.objects.filter(
                    product=output_guide_detail_obj.product, subsidiary_store=subsidiary_store_destiny_obj).last()
                if input_product_store_obj:
                    kardex_input(input_product_store_obj.id,
                                 quantity,
                                 output_guide_detail_obj.product.calculate_minimum_price_sale(),
                                 guide_detail_obj=input_guide_detail_obj)
                else:
                    input_product_store_obj = ProductStore(product=output_guide_detail_obj.product,
                                                           subsidiary_store=subsidiary_store_destiny_obj,
                                                           stock=quantity)
                    input_product_store_obj.save()
                    kardex_initial(input_product_store_obj,
                                   stock=quantity,
                                   price_unit=output_guide_detail_obj.product.calculate_minimum_price_sale(),
                                   guide_detail_obj=input_guide_detail_obj)
                # input kardex
        output_guide_obj.status = '3'
        output_guide_obj.observation = observation
        output_guide_obj.save()

        new_guide_employee_obj = GuideEmployee(
            guide=output_guide_obj,
            user=user_obj,
            function='A',
        )
        new_guide_employee_obj.save()
        return JsonResponse({
            'message': 'La operación se Realizo correctamente.',
            'guide_id': input_guide_obj.id,
        }, status=HTTPStatus.OK)


def distribution_movil_list(request):
    truck_obj = Truck.objects.all()
    user_id = request.user.id
    user_obj = User.objects.get(id=user_id)
    subsidiary_obj = get_subsidiary_by_user(user_obj)
    subsidiary_store_obj = SubsidiaryStore.objects.filter(subsidiary=subsidiary_obj, category='V').first()
    products = Product.objects.filter(productstore__subsidiary_store=subsidiary_store_obj)

    return render(request, 'comercial/distribution_movil.html', {
        'truck_obj': truck_obj,
        'product_obj': products,

    })


def distribution_mobil_save(request):
    if request.method == 'GET':
        distribution_request = request.GET.get('distribution', '')
        data_distribution = json.loads(distribution_request)
        user_id = request.user.id
        user_obj = User.objects.get(pk=int(user_id))
        date_distribution = (data_distribution["date_distribution"])
        id_truck = int(data_distribution["id_truck"])
        truck_obj = Truck.objects.get(id=id_truck)
        id_pilot = int(data_distribution["id_pilot"])
        guide = str(data_distribution["number_guide"])
        employee_obj = Employee.objects.get(id=id_pilot)
        subsidiary_obj = get_subsidiary_by_user(user_obj)

        new_distribution = {
            'truck': truck_obj,
            'pilot': employee_obj,
            'date_distribution': date_distribution,
            'subsidiary': subsidiary_obj,
            'user': user_obj,
            'guide_number': guide,
        }
        distribution_obj = DistributionMobil.objects.create(**new_distribution)
        distribution_obj.save()
        status = ''
        for detail in data_distribution['Details']:
            quantity = decimal.Decimal(detail['Quantity'])
            quantity_total = decimal.Decimal(detail['Quantity_total'])
            product_id = int(detail['Product'])
            type = str(detail['Type'])
            status = str(detail['Status'])
            product_obj = Product.objects.get(id=product_id)
            unit_id = int(detail['Unit'])
            unit_obj = Unit.objects.get(id=unit_id)

            new_detail_distribution = {
                'product': product_obj,
                'distribution_mobil': distribution_obj,
                'quantity': quantity_total,
                'unit': unit_obj,
                'type': type,
                'status': 'E',
            }
            new_detail_distribution = DistributionDetail.objects.create(**new_detail_distribution)
            new_detail_distribution.save()

            if quantity > 0:
                if unit_obj.name == 'BG':
                    subsidiary_store_obj = SubsidiaryStore.objects.filter(subsidiary=subsidiary_obj,
                                                                          category='V').first()
                    product_store_obj = ProductStore.objects.get(product=product_obj,
                                                                 subsidiary_store=subsidiary_store_obj)
                    quantity_minimum_unit = calculate_minimum_unit(quantity, unit_obj, product_obj)
                    kardex_ouput(product_store_obj.id, quantity_minimum_unit,
                                 distribution_detail_obj=new_detail_distribution)
                elif unit_obj.name == 'B':
                    subsidiary_store_obj = SubsidiaryStore.objects.filter(subsidiary=subsidiary_obj,
                                                                          category='I').first()
                    subcategory_obj = ProductSubcategory.objects.get(name='FIERRO', product_category__name='FIERRO')
                    product_recipe_obj = ProductRecipe.objects.filter(product=product_obj,
                                                                      product_input__product_subcategory=subcategory_obj)
                    productr_obj = product_recipe_obj.first().product_input
                    product_store_obj = ProductStore.objects.get(product=productr_obj,
                                                                 subsidiary_store=subsidiary_store_obj)
                    quantity_minimum_unit = calculate_minimum_unit(quantity, unit_obj, product_obj)
                    kardex_ouput(product_store_obj.id, quantity_minimum_unit,
                                 distribution_detail_obj=new_detail_distribution)

        return JsonResponse({
            'message': 'DISTRIBUCION REALIZADA.',
        }, status=HTTPStatus.OK)


def output_distribution_list(request):
    user_id = request.user.id
    user_obj = User.objects.get(id=user_id)
    subsidiary_obj = get_subsidiary_by_user(user_obj)
    distribution_mobil = DistributionMobil.objects.filter(subsidiary=subsidiary_obj, status='P')
    return render(request, 'comercial/output_distribution_list.html', {
        'distribution_mobil': distribution_mobil
    })


def get_details_by_distributions_mobil(request):
    if request.method == 'GET':
        distribution_mobil_id = request.GET.get('ip', '')
        distribution_mobil_obj = DistributionMobil.objects.get(pk=int(distribution_mobil_id))
        details_distribution_mobil = DistributionDetail.objects.filter(
            distribution_mobil=distribution_mobil_obj
        ).select_related('product', 'unit')
        t = loader.get_template('comercial/table_details_output_distribution.html')
        c = ({
            'details': details_distribution_mobil,
        })
        return JsonResponse({
            'grid': t.render(c, request),
        }, status=HTTPStatus.OK)


def get_distribution_mobil_return(request):
    if request.method == 'GET':
        pk = int(request.GET.get('pk', ''))

        distribution_mobil_obj = DistributionMobil.objects.get(id=pk)
        if distribution_mobil_obj.status == 'F':
            return JsonResponse({
                'error': 'LA PROGRAMACION YA ESTA FINALIZADA, POR FAVOR SELECCIONE OTRA',
            })
        # distribution_mobil_detail = DistributionDetail.objects.filter(distribution_mobil=distribution_mobil_obj)
        user_id = request.user.id
        user_obj = User.objects.get(id=user_id)
        subsidiary_obj = get_subsidiary_by_user(user_obj)
        product_obj = Product.objects.filter(productstore__subsidiary_store__subsidiary=subsidiary_obj,
                                             productstore__subsidiary_store__category='V')

        # product_serialized_obj = serializers.serialize('json', product)

        t = loader.get_template('comercial/distribution_mobil_return.html')
        c = ({
            'distribution_mobil': distribution_mobil_obj,
            'product': product_obj,
            'type': DistributionDetail._meta.get_field('type').choices,
        })
        return JsonResponse({
            'success': True,
            'form': t.render(c, request),
        })


def get_units_by_products_distribution_mobil(request):
    if request.method == 'GET':
        product_id = request.GET.get('ip', '')
        unit_obj = Unit.objects.filter(productdetail__product_id=int(product_id))
        units_serialized_obj = serializers.serialize('json', unit_obj)

        return JsonResponse({
            'units': units_serialized_obj,
        }, status=HTTPStatus.OK)


def get_units_and_sotck_by_product(request):
    if request.method == 'GET':
        id_product = request.GET.get('ip', '')
        category = request.GET.get('_category', '')
        product_obj = Product.objects.get(pk=int(id_product))
        units = Unit.objects.filter(productdetail__product=product_obj)
        units_serialized_obj = serializers.serialize('json', units)

        user_id = request.user.id
        user_obj = User.objects.get(id=user_id)
        subsidiary_obj = get_subsidiary_by_user(user_obj)
        product_store_obj = ProductStore.objects.filter(product_id=id_product,
                                                        subsidiary_store__subsidiary=subsidiary_obj,
                                                        subsidiary_store__category=category).first()
        return JsonResponse({
            'units': units_serialized_obj,
            'stock': product_store_obj.stock,

        }, status=HTTPStatus.OK)


@csrf_exempt
def return_detail_distribution_mobil_store(request):
    if request.method == 'GET':
        detail_distribution_mobil_request = request.GET.get('details_distribution_mobil', '')
        data_distribution_mobil = json.loads(detail_distribution_mobil_request)
        distribution_mobil_id = int(data_distribution_mobil["distribution_id_"])
        distribution_mobil_obj = DistributionMobil.objects.get(id=distribution_mobil_id)
        if distribution_mobil_obj.status == 'F':
            data = {'error': 'Reparto retornado.'}
            response = JsonResponse(data)
            response.status_code = HTTPStatus.INTERNAL_SERVER_ERROR
            return response
        user_id = request.user.id
        user_obj = User.objects.get(id=int(user_id))
        subsidiary_obj = get_subsidiary_by_user(user_obj)

        for detail in data_distribution_mobil['Details']:
            quantity = decimal.Decimal(detail['quantity_'])
            product_id = int(detail['product_id_'])
            product_obj = Product.objects.get(id=product_id)
            type_id = detail['type_id_']  # V: Vacio, L: Lleno, M: Malogrado
            unit_id = int(detail['unit_id_'])
            unit_obj = Unit.objects.get(id=unit_id)
            status = 'D'
            new_detail_distribution = {
                'product': product_obj,
                'distribution_mobil': distribution_mobil_obj,
                'quantity': quantity,
                'unit': unit_obj,
                'status': status,
                'type': type_id,
            }
            new_detail_distribution = DistributionDetail.objects.create(**new_detail_distribution)
            new_detail_distribution.save()

            try:
                if new_detail_distribution.type == 'V':
                    subsidiary_store_obj = SubsidiaryStore.objects.get(subsidiary=subsidiary_obj, category='I')
                    # productrecipe_obj = ProductRecipe.objects.filter(product_id=product_obj.id)

                    # product_obj = Product.objects.filter(product_id=productrecipe_obj,subcategory='FIERROS')
                    subcategory_obj = ProductSubcategory.objects.get(name='FIERRO', product_category__name='FIERRO')
                    product_insume_set = ProductRecipe.objects.filter(product=product_obj,
                                                                      product_input__product_subcategory=subcategory_obj)
                    product_obj = product_insume_set.first().product_input

                    # fierro_obj=Product.objects.get(product=product_obj)
                elif new_detail_distribution.type == 'L':
                    subsidiary_store_obj = SubsidiaryStore.objects.get(subsidiary=subsidiary_obj, category='V')
                elif new_detail_distribution.type == 'M':
                    subsidiary_store_obj = SubsidiaryStore.objects.get(subsidiary=subsidiary_obj, category='R')
            except SubsidiaryStore.DoesNotExist:
                data = {'error': 'No existe el almacen correspondiente'}
                response = JsonResponse(data)
                response.status_code = HTTPStatus.INTERNAL_SERVER_ERROR
                return response

            try:
                product_store_obj = ProductStore.objects.get(product=product_obj, subsidiary_store=subsidiary_store_obj)
            except ProductStore.DoesNotExist:
                product_store_obj = None
            # unit_min_detail_product = ProductDetail.objects.get(product=product_obj, unit=unit_obj).quantity_minimum
            quantity_minimum_unit = calculate_minimum_unit(quantity, unit_obj, product_obj)

            if product_store_obj is None:
                new_product_store_obj = ProductStore(
                    product=product_obj,
                    subsidiary_store=subsidiary_store_obj,
                    stock=quantity_minimum_unit
                )
                new_product_store_obj.save()
                kardex_initial(new_product_store_obj, quantity_minimum_unit,
                               product_obj.calculate_minimum_price_sale(),
                               distribution_detail_obj=new_detail_distribution)
            else:
                kardex_input(product_store_obj.id, quantity_minimum_unit,
                             product_obj.calculate_minimum_price_sale(),
                             distribution_detail_obj=new_detail_distribution)

        return JsonResponse({
            'message': True,

        }, status=HTTPStatus.OK)


@csrf_exempt
def c_return_distribution_mobil_detail(request):
    if request.method == 'GET':
        _c_distribution_mobil = request.GET.get('c_distribution_mobil', '')
        _c_detail = json.loads(_c_distribution_mobil)
        _c_distribution_mobil_id = int(_c_detail["c_distribution_id"])
        _c_distribution_mobil_obj = DistributionMobil.objects.get(id=_c_distribution_mobil_id)

        if _c_distribution_mobil_obj.status == 'F':
            data = {'error': 'Reparto retornado.'}
            response = JsonResponse(data)
            response.status_code = HTTPStatus.INTERNAL_SERVER_ERROR
            return response

        for detail in _c_detail['c_detail']:
            _c_quantity = decimal.Decimal(detail['c_quantity'])
            _c_product_id = int(detail['c_product_id'])
            _c_product_obj = Product.objects.get(id=_c_product_id)
            _c_type_id = detail['c_type_id']
            _c_unit = detail['c_unit']
            _c_unit_obj = Unit.objects.get(name=str(_c_unit))
            _c_status = 'C'

            _c_new_detail_distribution = {
                'product': _c_product_obj,
                'distribution_mobil': _c_distribution_mobil_obj,
                'quantity': _c_quantity,
                'unit': _c_unit_obj,
                'status': _c_status,
                'type': _c_type_id,
            }
            _c_new_detail_distribution = DistributionDetail.objects.create(**_c_new_detail_distribution)
            _c_new_detail_distribution.save()
        _c_distribution_mobil_obj.status = 'F'
        _c_distribution_mobil_obj.save()
        return JsonResponse({
            'message': 'Productos retornados correctamente',

        }, status=HTTPStatus.OK)


def get_distribution_list(request):
    if request.method == 'GET':
        user_id = request.user.id
        user_obj = User.objects.get(id=user_id)
        subsidiary_obj = get_subsidiary_by_user(user_obj)
        date_distribution = request.GET.get('_date', '')
        if date_distribution != '':

            distribution_mobil = DistributionMobil.objects.filter(
                subsidiary=subsidiary_obj, date_distribution=date_distribution).prefetch_related(
                Prefetch('distributiondetail_set')
            ).select_related('truck')
            tpl = loader.get_template('comercial/distribution_grid_list.html')
            context = ({
                'distribution_mobil': distribution_mobil,
            })
            return JsonResponse({
                'success': True,
                'grid': tpl.render(context),
            }, status=HTTPStatus.OK)
        else:
            my_date = datetime.now()
            date_now = my_date.strftime("%Y-%m-%d")
            # distribution_mobil_set = DistributionMobil.objects.annotate(id=Max('date_distribution')).filter(subsidiary=subsidiary_obj, date_distribution=F('max_date'))
            # if distribution_mobil_set.exists():
            #     date_now = distribution_mobil_set.first().date_distribution.strftime("%Y-%m-%d")
            return render(request, 'comercial/distribution_list.html', {
                'date_now': date_now,
            })


def get_mantenimient_product_list(request):
    if request.method == 'GET':
        user_id = request.user.id
        user_obj = User.objects.get(id=user_id)
        subsidiary_obj = get_subsidiary_by_user(user_obj)
        date_mantenimient = request.GET.get('_date', '')
        if date_mantenimient != '':

            mantenimient_product = MantenimentProduct.objects.filter(subsidiary=subsidiary_obj,
                                                                     date_programing=date_mantenimient)
            tpl = loader.get_template('comercial/manteniment_product.html')
            context = ({
                'mantenimient_product': mantenimient_product,
            })
            return JsonResponse({
                'success': True,
                'grid': tpl.render(context),
            }, status=HTTPStatus.OK)
        else:
            my_date = datetime.now()
            date_now = my_date.strftime("%Y-%m-%d")
            return render(request, 'comercial/manteniment_product_list.html', {
                'date_now': date_now,
            })


def output_distribution(request):
    if request.method == 'GET':
        trucks_set = Truck.objects.all()
        user_id = request.user.id
        user_obj = User.objects.get(id=user_id)
        subsidiary_obj = get_subsidiary_by_user(user_obj)
        my_date = datetime.now()
        date_now = my_date.strftime("%Y-%m-%d")
        subsidiary_store_obj = SubsidiaryStore.objects.filter(subsidiary=subsidiary_obj, category='V').first()
        products_set = Product.objects.filter(productstore__subsidiary_store=subsidiary_store_obj,
                                              product_subcategory__id=4)
        t = loader.get_template('comercial/distribution_output.html')
        c = ({
            'truck_set': trucks_set,
            'product_set': products_set,
            'employees': Employee.objects.all(),
            'type_set': DistributionDetail._meta.get_field('type').choices,
            'date_now': date_now
        })
        return JsonResponse({
            'form': t.render(c, request),
        })


def get_quantity_last_distribution(request):
    if request.method == 'GET':
        id_pilot = request.GET.get('ip', '')
        employee_obj = Employee.objects.get(id=int(id_pilot))
        user_id = request.user.id
        user_obj = User.objects.get(id=user_id)
        subsidiary_obj = get_subsidiary_by_user(user_obj)
        distribution_mobil = DistributionMobil.objects.filter(pilot=employee_obj, status='F',
                                                              subsidiary=subsidiary_obj).aggregate(Max('id'))
        if distribution_mobil['id__max'] is not None:
            truck = DistributionMobil.objects.get(id=distribution_mobil['id__max']).truck
            truck_obj = Truck.objects.get(license_plate=truck)

            list_distribution_last = DistributionDetail.objects.filter(status='C',
                                                                       distribution_mobil=distribution_mobil['id__max'])
            list_serialized_obj = serializers.serialize('json', list_distribution_last)
            if list_distribution_last.exists():
                t = loader.get_template('comercial/table_distribution_last.html')
                c = ({
                    'details': list_distribution_last,

                })
                return JsonResponse({
                    'message': True,
                    'truck': truck_obj.id,
                    'grid': t.render(c, request),
                    'list': list_serialized_obj,
                }, status=HTTPStatus.OK)
            else:
                return JsonResponse({
                    'truck': truck_obj.id,
                    'message': False,
                }, status=HTTPStatus.OK)
        else:
            return JsonResponse({
                'message': False,
            }, status=HTTPStatus.OK)
        # try:
        # except DistributionMobil.DoesNotExist:


def mantenimient_product(request):
    if request.method == 'GET':
        trucks_set = Truck.objects.all()
        user_id = request.user.id
        user_obj = User.objects.get(id=user_id)
        subsidiary_obj = get_subsidiary_by_user(user_obj)
        subsidiary_store_obj = SubsidiaryStore.objects.filter(subsidiary=subsidiary_obj, category='R').first()
        products_set = Product.objects.filter(productstore__subsidiary_store=subsidiary_store_obj)
        t = loader.get_template('comercial/mantenimient_create.html')
        c = ({

            'product_set': products_set,
            'employees': Employee.objects.all(),
            'type_mantenimient': MantenimentProduct._meta.get_field('type').choices,
            'type_fuction': MantenimentProductDetail._meta.get_field('type').choices,

        })
        return JsonResponse({
            'form': t.render(c, request),
        })


def get_distribution_mobil_sales(request):
    if request.method == 'GET':
        pk = int(request.GET.get('pk', ''))

        user_id = request.user.id
        user_obj = User.objects.get(id=user_id)
        subsidiary_obj = get_subsidiary_by_user(user_obj)
        clients = Client.objects.all()
        product_set = Product.objects.filter(productstore__subsidiary_store__subsidiary=subsidiary_obj,
                                             productstore__subsidiary_store__category='V')
        t = loader.get_template('comercial/distribution_sales.html')
        c = ({
            'client_set': clients,
            'product_set': product_set,
            'choices_payments': TransactionPayment._meta.get_field('type').choices

        })
        return JsonResponse({
            'success': True,
            'form': t.render(c, request),
        })


def get_fuel_request_list(request):
    if request.method == 'GET':
        user_id = request.user.id
        user_obj = User.objects.get(id=user_id)
        subsidiary_obj = get_subsidiary_by_user(user_obj)
        license_plate_id = request.GET.get('license_plate_', '')
        if license_plate_id != '':
            month_fuel = request.GET.get('month_', '')
            date_time_obj = datetime.strptime(month_fuel, '%Y-%m')
            new_year = date_time_obj.year
            new_month = date_time_obj.month
            fuel_programming_set = FuelProgramming.objects.filter(subsidiary=subsidiary_obj,
                                                                  date_fuel__year=new_year,
                                                                  date_fuel__month=new_month,
                                                                  programming__truck_id=license_plate_id)
            tpl = loader.get_template('comercial/fuel_request_grid_list.html')
            context = ({
                'fuel_programming_set': fuel_programming_set,
            })
            return JsonResponse({
                'success': True,
                'grid': tpl.render(context),
            }, status=HTTPStatus.OK)
        else:
            truck_set = Truck.objects.all()
            my_date = datetime.now()
            date_now = my_date.strftime("%Y-%m")
            return render(request, 'comercial/fuel_request_list.html', {
                'date_now': date_now,
                'truck_set': truck_set,
            })


def fuel_request(request):
    if request.method == 'GET':
        supplier_set = Supplier.objects.all().order_by('-id')
        programming_set = Programming.objects.filter(status='P')
        my_date = datetime.now()
        date_now = my_date.strftime("%Y-%m-%d")
        t = loader.get_template('comercial/fuel_request.html')
        c = ({
            'programming_set': programming_set,
            'supplier_set': supplier_set,
            'date_now': date_now,
        })
        return JsonResponse({
            'form': t.render(c, request),
        })


def get_products_by_supplier(request):
    if request.method == 'GET':
        supplier_id = request.GET.get('ip', '')
        supplier_obj = Supplier.objects.get(pk=int(supplier_id))
        product_set = Product.objects.filter(productsupplier__supplier=supplier_obj)
        products_supplier_obj = ProductSupplier.objects.filter(
            product=product_set.first(), supplier=supplier_obj)

        product_serialized_obj = serializers.serialize('json', product_set)

        return JsonResponse({
            'price': products_supplier_obj[0].price_purchase,
            'products': product_serialized_obj,

        }, status=HTTPStatus.OK)


def get_programming_by_license_plate(request):
    id_programming = request.GET.get('ip', '')
    programming_obj = Programming.objects.get(pk=int(id_programming))
    print(programming_obj)
    name = ''
    document = ''
    employee_obj = programming_obj.get_pilot()
    if employee_obj is not None:
        # name = employee_obj.full_name
        name = '{} {} {}'.format(employee_obj.names, employee_obj.paternal_last_name, employee_obj.maternal_last_name)
        document = employee_obj.document_number

    return JsonResponse({
        'employee_name': name,
        'employee_document': document,
    }, status=HTTPStatus.OK)


@csrf_exempt
def save_fuel_programming(request):
    if request.method == 'POST':
        user_id = request.user.id
        user_obj = User.objects.get(id=int(user_id))
        subsidiary_obj = get_subsidiary_by_user(user_obj)
        _quantity_fuel = request.POST.get('quantity', '')
        _date_fuel = request.POST.get('date-fuel', '')
        _price_fuel = request.POST.get('price', '')
        _product_id = request.POST.get('product', '')
        _programming_id = request.POST.get('license_plate', '')
        _supplier_id = request.POST.get('supplier', '')
        _unit_fuel_id = request.POST.get('unit', '')

        product_obj = Product.objects.get(id=int(_product_id))
        programming_obj = Programming.objects.get(id=int(_programming_id))
        supplier_obj = Supplier.objects.get(id=int(_supplier_id))
        unit_obj = Unit.objects.get(id=int(_unit_fuel_id))

        fuel_programming_obj = FuelProgramming(
            quantity_fuel=_quantity_fuel,
            date_fuel=_date_fuel,
            price_fuel=_price_fuel,
            product=product_obj,
            programming=programming_obj,
            supplier=supplier_obj,
            unit_fuel=unit_obj,
            subsidiary=subsidiary_obj
        )
        fuel_programming_obj.save()

        return JsonResponse({
            'success': True,
            'id': fuel_programming_obj.id,
        }, status=HTTPStatus.OK)


def get_stock_by_product_type(request):
    if request.method == 'GET':
        data = {}
        id_product = request.GET.get('id_product_', '')
        id_type = request.GET.get('id_type_', '')

        if id_type == '':
            data['error'] = "Ingrese un tipo."
            response = JsonResponse(data)
            response.status_code = HTTPStatus.INTERNAL_SERVER_ERROR
            return response

        product_obj = Product.objects.get(pk=int(id_product))
        user = request.user.id
        user_obj = User.objects.get(id=user)
        subsidiary_obj = get_subsidiary_by_user(user_obj)
        product_store_obj = ''
        if int(id_type) == 1:
            subsidiary_store_obj = SubsidiaryStore.objects.filter(subsidiary=subsidiary_obj, category='I').first()
            subcategory_obj = ProductSubcategory.objects.get(name='FIERRO', product_category__name='FIERRO')
            product_recipe_obj = ProductRecipe.objects.filter(product=product_obj,
                                                              product_input__product_subcategory=subcategory_obj)
            product_obj = product_recipe_obj.first().product_input
            product_store_obj = ProductStore.objects.get(product__id=product_obj.id,
                                                         subsidiary_store=subsidiary_store_obj)
        if int(id_type) == 2:
            subsidiary_store_obj = SubsidiaryStore.objects.filter(subsidiary=subsidiary_obj, category='V').first()
            product_store_obj = ProductStore.objects.get(product__id=id_product, subsidiary_store=subsidiary_store_obj)
        if int(id_type) == 3:
            subsidiary_store_obj = SubsidiaryStore.objects.filter(subsidiary=subsidiary_obj, category='R').first()
            product_store_obj = ProductStore.objects.get(product__id=id_product, subsidiary_store=subsidiary_store_obj)
        if int(id_type) == 4:
            subsidiary_store_obj = SubsidiaryStore.objects.filter(subsidiary=subsidiary_obj, category='R').first()
            subcategory_obj = ProductSubcategory.objects.get(name='FIERRO', product_category__name='FIERRO')
            product_recipe_obj = ProductRecipe.objects.filter(product=product_obj,
                                                              product_input__product_subcategory=subcategory_obj)
            product_obj = product_recipe_obj.first().product_input
            product_store_obj = ProductStore.objects.get(product__id=product_obj.id,
                                                         subsidiary_store=subsidiary_store_obj)

        return JsonResponse({
            'quantity': product_store_obj.stock,
            'id_product_store': product_store_obj.id,
            'product_store_name': product_store_obj.subsidiary_store.name
        }, status=HTTPStatus.OK)
    else:
        return JsonResponse({'error': True, 'message': 'Error de peticion.'})


def get_stock_unit_by_product_type(request):
    if request.method == 'GET':
        data = {}
        id_product = request.GET.get('id_product', '')
        id_type = request.GET.get('id_type', '')

        if id_type == '0' or id_type == '':
            data['error'] = "Ingrese un tipo."
            response = JsonResponse(data)
            response.status_code = HTTPStatus.INTERNAL_SERVER_ERROR
            return response

        product_obj = Product.objects.get(pk=int(id_product))
        user = request.user.id
        user_obj = User.objects.get(id=user)
        subsidiary_obj = get_subsidiary_by_user(user_obj)
        unit_obj = None
        product_store_obj = ''
        try:
            if id_type == 'V':
                subsidiary_store_obj = SubsidiaryStore.objects.filter(subsidiary=subsidiary_obj, category='I').first()
                subcategory_obj = ProductSubcategory.objects.get(name='FIERRO', product_category__name='FIERRO')
                product_recipe_obj = ProductRecipe.objects.filter(product=product_obj,
                                                                  product_input__product_subcategory=subcategory_obj)
                product_obj = product_recipe_obj.first().product_input
                product_store_obj = ProductStore.objects.get(product__id=product_obj.id,
                                                             subsidiary_store=subsidiary_store_obj)
                unit_obj = product_recipe_obj.first().unit
            elif id_type == 'L':
                subsidiary_store_obj = SubsidiaryStore.objects.filter(subsidiary=subsidiary_obj, category='V').first()
                product_store_obj = ProductStore.objects.get(product__id=id_product,
                                                             subsidiary_store=subsidiary_store_obj)
                unit_obj = Unit.objects.filter(name='BG', productdetail__product=product_obj).first()
            elif id_type == 'M':
                subsidiary_store_obj = SubsidiaryStore.objects.filter(subsidiary=subsidiary_obj, category='R').first()
                product_store_obj = ProductStore.objects.get(product__id=id_product,
                                                             subsidiary_store=subsidiary_store_obj)
                unit_obj = Unit.objects.filter(name='BG', productdetail__product=product_obj).first()
            elif id_type == 'VM':
                subsidiary_store_obj = SubsidiaryStore.objects.filter(subsidiary=subsidiary_obj, category='R').first()
                subcategory_obj = ProductSubcategory.objects.get(name='FIERRO', product_category__name='FIERRO')
                product_recipe_obj = ProductRecipe.objects.filter(product=product_obj,
                                                                  product_input__product_subcategory=subcategory_obj)
                product_obj = product_recipe_obj.first().product_input
                product_store_obj = ProductStore.objects.get(product__id=product_obj.id,
                                                             subsidiary_store=subsidiary_store_obj)
                unit_obj = product_recipe_obj.first().unit

            return JsonResponse({
                'quantity': product_store_obj.stock,
                'unit': unit_obj.id,
                'unit_name': unit_obj.description,
                'id_product_store': product_store_obj.id,
                'product_store_name': product_store_obj.subsidiary_store.name
            }, status=HTTPStatus.OK)

        except Exception as e:
            return JsonResponse({
                'quantity': decimal.Decimal(0.00),
                'unit': 0,
                'unit_name': "SIN DATOS",
                'id_product_store': 0,
                'product_store_name': "SIN ALMACEN"
            }, status=HTTPStatus.OK)
    else:
        return JsonResponse({'error': True, 'message': 'Error de peticion.'})


def get_consecutive_years():
    current_year = datetime.now().year
    years = [current_year - 1, current_year, current_year + 1]
    return years


def get_spanish_month_names():
    month_names = [
        'ENERO', 'FEBRERO', 'MARZO', 'ABRIL', 'MAYO', 'JUNIO', 'JULIO',
        'AGOSTO', 'SEPTIEMBRE', 'OCTUBRE', 'NOVIEMBRE', 'DICIEMBRE'
    ]

    return month_names


def get_previous_balls_recovered_in_distribution(selected_datetime=None, truck_id=None, product__id=None):
    q3 = DistributionDetail.objects.filter(
        distribution_mobil__date_distribution__lt=selected_datetime.date(),
        distribution_mobil__truck__id=truck_id,
        status='R',
        type='V',
        product__id=product__id
    ).values('product__id').annotate(sum_quantity_recovered_b=Sum(F('quantity'))).values(
        'sum_quantity_recovered_b'
    )

    sum_quantity_recovered_b = 0
    if q3.exists():
        result2 = q3[0]
        sum_quantity_recovered_b = result2.get('sum_quantity_recovered_b', 0)
    return sum_quantity_recovered_b


def get_previous_balls_recovered_in_plant(selected_datetime=None, truck_id=None, product__id=None):
    q2 = LoanPayment.objects.filter(
        order_detail__order__distribution_mobil__date_distribution__lt=selected_datetime.date(),
        order_detail__order__distribution_mobil__truck__id=truck_id,
        order_detail__unit__name__in=['B'],
        product__id=product__id,
        distribution_mobil__isnull=True
    ).values('product__id').annotate(sum_quantity_recovered_b=Sum(F('quantity'))).values(
        'sum_quantity_recovered_b'
    )
    # print(q2.query)
    sum_quantity_recovered_b = 0
    if q2.exists():
        result2 = q2[0]
        sum_quantity_recovered_b = result2.get('sum_quantity_recovered_b', 0)
    return sum_quantity_recovered_b


def get_previous_debt_for_borrowed_balls(selected_datetime=None, truck_id=None, product__id=None):
    q = OrderDetail.objects.filter(
        order__distribution_mobil__date_distribution__lt=selected_datetime.date(),
        order__distribution_mobil__truck__id=truck_id,
        unit__name__in=['B'],
        product__id=product__id
    ).values('product__id').annotate(sum_quantity_sold_b=Sum(F('quantity_sold'))).values(
        'sum_quantity_sold_b'
    )

    # q2 = LoanPayment.objects.filter(
    #     order_detail__order__distribution_mobil__date_distribution__lt=selected_datetime.date(),
    #     order_detail__order__distribution_mobil__truck__id=truck_id,
    #     order_detail__unit__name__in=['B'],
    #     product__id=product__id
    # ).values('product__id').annotate(sum_quantity_recovered_b=Sum(F('quantity'))).values(
    #     'sum_quantity_recovered_b'
    # )

    sum_quantity_sold_b = 0
    # sum_quantity_recovered_b = 0

    if q.exists():
        result = q[0]
        sum_quantity_sold_b = result.get('sum_quantity_sold_b', 0)

    # if q2.exists():
    #     result2 = q2[0]
    #     sum_quantity_recovered_b = result2.get('sum_quantity_recovered_b', 0)

    # return sum_quantity_sold_b - sum_quantity_recovered_b
    return sum_quantity_sold_b


def get_ball_recovered_in_plant(product_id=None, distribution_mobil_id=None):
    recovered_in_plant_set = LoanPayment.objects.filter(
        order_detail__order__distribution_mobil__id=distribution_mobil_id,
        order_detail__unit__name__in=['B'],
        product__id=product_id,
        distribution_mobil__isnull=True
    ).values('product__id').annotate(sum_quantity_recovered_in_plant_b=Sum(F('quantity'))).values(
        'sum_quantity_recovered_in_plant_b'
    )
    if 44 == distribution_mobil_id:
        print(recovered_in_plant_set.query)

    quantity_recovered_in_plant_b = 0

    if recovered_in_plant_set.exists():
        recovered_in_plant_obj = recovered_in_plant_set[0]
        quantity_recovered_in_plant_b = recovered_in_plant_obj.get('sum_quantity_recovered_in_plant_b', 0)
    return quantity_recovered_in_plant_b


def get_previous_debt_for_in_the_car_balls(distribution_mobil_set=None, truck_id=None, product__id=None, type_id=None):
    remaining_in_the_car_bg = 0

    if distribution_mobil_set.exists():
        last_distribution_set = DistributionMobil.objects.filter(
            id__lte=distribution_mobil_set[0].id, truck__id=truck_id
        ).annotate(
            previous_distribution_id=Window(expression=Lag('id', default=0), order_by=('date_distribution', 'id'))
        ).order_by('date_distribution', 'id')

        if last_distribution_set.exists():

            last_distribution_detail_set = DistributionDetail.objects.filter(
                distribution_mobil__id=last_distribution_set.last().previous_distribution_id,
                status='C',
                type=type_id,
                product__id=product__id
            )
            if last_distribution_detail_set.exists():
                last_distribution_detail_obj = last_distribution_detail_set.last()
                remaining_in_the_car_bg = int(last_distribution_detail_obj.quantity)

    return remaining_in_the_car_bg


def get_credits_from_clients_by_subsidiary(request):
    if request.method == 'GET':
        user_id = request.user.id
        user_obj = User.objects.get(pk=int(user_id))
        subsidiary_obj = get_subsidiary_by_user(user_obj)

        return render(request, 'comercial/credits_from_clients_by_subsidiary_list.html', {
            'subsidiary_obj': subsidiary_obj
        })
    elif request.method == 'POST':
        type_debt = str(request.POST.get('type-debt'))
        user_id = request.user.id
        user_obj = User.objects.get(id=user_id)
        subsidiary_obj = get_subsidiary_by_user(user_obj)
        d = get_orders_for_status_account(subsidiary_obj=subsidiary_obj)
        client_dict = d['client_dict']
        summary_sum_total_remaining_repay_loan = d['summary_sum_total_remaining_repay_loan']
        summary_sum_total_remaining_return_loan = d['summary_sum_total_remaining_return_loan']
        array_p_p = []

        if len(client_dict) > 0:

            for k, st in client_dict.items():
                client_name = st['client_names']
                if type_debt == "E":
                    total = float(round(st['sum_total_remaining_repay_loan'], 2))
                else:
                    total = float(round(st['sum_total_remaining_return_loan'], 0))
                purchase_dict = {
                    'label': client_name,
                    'y': total
                }
                array_p_p.append(purchase_dict)
            tpl = loader.get_template('comercial/credits_from_clients_by_subsidiary_grid_list.html')
            context = ({
                'type_debt': type_debt,
                'client_dict': client_dict,
                'summary_sum_total_remaining_repay_loan': round(summary_sum_total_remaining_repay_loan, 2),
                'summary_sum_total_remaining_return_loan': round(summary_sum_total_remaining_return_loan),
                'array_p_p': array_p_p,
                'subsidiary_obj': subsidiary_obj,
            })

            return JsonResponse({
                'grid': tpl.render(context)
            }, status=HTTPStatus.OK)
        else:
            data = {'error': "No hay operaciones registradas"}
            response = JsonResponse(data)
            response.status_code = HTTPStatus.INTERNAL_SERVER_ERROR
            return response


def get_expenses_by_licence_plate(request):
    if request.method == 'GET':
        truck_set = Truck.objects.filter(distributionmobil__isnull=False).distinct('license_plate').order_by(
            'license_plate')
        my_date = datetime.now()
        formatdate = my_date.strftime("%Y-%m-%d")
        return render(request, 'comercial/expenses_by_licence_plate_list.html', {
            'formatdate': formatdate,
            'truck_set': truck_set
        })
    elif request.method == 'POST':
        truck_id = int(request.POST.get('truck'))
        start_date = str(request.POST.get('start-date'))
        end_date = str(request.POST.get('end-date'))

        base_query_set = CashFlow.objects.filter(
            transaction_date__date__range=[start_date, end_date], distribution_mobil__isnull=False, type='S'
        )
        if truck_id > 0:
            base_query_set = base_query_set.filter(distribution_mobil__truck__id=truck_id)

        pilots = list(base_query_set.values_list('distribution_mobil__pilot__id', flat=True).distinct())

        if pilots:
            grouped_by_pilot = defaultdict(
                lambda: {
                    'pilot_id': '', 'pilot_name': '',
                    'expense_1': 0, 'expense_2': 0, 'expense_3': 0, 'expense_4': 0, 'expense_5': 0, 'total_expenses': 0,
                    'date_expense_1': "", 'date_expense_2': "", 'date_expense_3': "", 'date_expense_4': "",
                    'date_expense_5': ""
                }
            )

            for pilot_id in pilots:
                data_obj = grouped_by_pilot[pilot_id]
                pilot_obj = Employee.objects.get(id=pilot_id)
                data_obj['pilot_id'] = pilot_id
                data_obj['pilot_name'] = pilot_obj.full_name()
                total_expenses = 0
                for expense in base_query_set:
                    if expense.description == "PETROLEO":
                        data_obj["expense_1"] += round(expense.total, 1)
                        date_str = expense.transaction_date.strftime('%d-%b').upper()
                        data_obj['date_expense_1'] = date_str.replace('JAN', 'ENE')
                    if expense.description == "VIATICO":
                        data_obj["expense_2"] += round(expense.total, 1)
                        date_str = expense.transaction_date.strftime('%d-%b').upper()
                        data_obj['date_expense_2'] = date_str.replace('JAN', 'ENE')
                    if expense.description == "FERIADO Y SUELDO":
                        data_obj["expense_3"] += round(expense.total, 1)
                        date_str = expense.transaction_date.strftime('%d-%b').upper()
                        data_obj['date_expense_3'] = date_str.replace('JAN', 'ENE')
                    if expense.description == "MANTENIMIENTO":
                        data_obj["expense_4"] += round(expense.total, 1)
                        date_str = expense.transaction_date.strftime('%d-%b').upper()
                        data_obj['date_expense_4'] = date_str.replace('JAN', 'ENE')
                    if expense.description == "OTROS GASTOS":
                        data_obj["expense_5"] += round(expense.total, 1)
                        date_str = expense.transaction_date.strftime('%d-%b').upper()
                        data_obj['date_expense_5'] = date_str.replace('JAN', 'ENE')
                    total_expenses += round(expense.total, 1)
                data_obj['total_expenses'] = total_expenses

            pilots_with_expenses = list(grouped_by_pilot.values())

            tpl = loader.get_template('comercial/expenses_by_licence_plate_grid_list.html')
            context = ({
                'pilots_with_expenses': pilots_with_expenses,
            })
            return JsonResponse({
                'grid': tpl.render(context)
            }, status=HTTPStatus.OK)
        else:
            data = {'error': "No hay operaciones registradas"}
            response = JsonResponse(data)
            response.status_code = HTTPStatus.INTERNAL_SERVER_ERROR
            return response


def get_monthly_distribution_by_licence_plate(request):
    if request.method == 'GET':
        truck_set = Truck.objects.filter(distributionmobil__isnull=False).distinct('license_plate').order_by(
            'license_plate')
        my_date = datetime.now()
        formatdate = my_date.strftime("%Y-%m-%d")
        return render(request, 'comercial/monthly_distribution_by_licence_plate_list.html', {
            'month_set': get_spanish_month_names(),
            'current_year': datetime.now().year,
            'current_month': datetime.now().month,
            'year_set': get_consecutive_years(),
            'formatdate': formatdate,
            'truck_set': truck_set
        })
    elif request.method == 'POST':
        truck_id = int(request.POST.get('truck'))
        # month = int(request.POST.get('month'))
        # year = int(request.POST.get('year'))
        start_date = str(request.POST.get('start-date'))
        end_date = str(request.POST.get('end-date'))

        timezone_peru = pytz.timezone('America/Lima')

        start_date_sin_timezone = datetime.strptime(start_date, '%Y-%m-%d')
        # start_date_con_timezone = timezone.make_aware(start_date_sin_timezone, timezone=timezone_peru)
        end_date_sin_timezone = datetime.strptime(end_date, '%Y-%m-%d')
        # end_date_con_timezone = timezone.make_aware(end_date_sin_timezone, timezone=timezone_peru)

        # selected_datetime = datetime(year, month, 1)

        previous_debt_for_borrowed_balls_b10 = get_previous_debt_for_borrowed_balls(
            selected_datetime=start_date_sin_timezone, truck_id=truck_id, product__id=1)
        previous_debt_for_borrowed_balls_b5 = get_previous_debt_for_borrowed_balls(
            selected_datetime=start_date_sin_timezone, truck_id=truck_id, product__id=2)
        previous_debt_for_borrowed_balls_b45 = get_previous_debt_for_borrowed_balls(
            selected_datetime=start_date_sin_timezone, truck_id=truck_id, product__id=3)
        previous_debt_for_borrowed_balls_b15 = get_previous_debt_for_borrowed_balls(
            selected_datetime=start_date_sin_timezone, truck_id=truck_id, product__id=12)

        previous_balls_recovered_in_distribution_b10 = get_previous_balls_recovered_in_distribution(
            selected_datetime=start_date_sin_timezone, truck_id=truck_id, product__id=1)
        previous_balls_recovered_in_distribution_b5 = get_previous_balls_recovered_in_distribution(
            selected_datetime=start_date_sin_timezone, truck_id=truck_id, product__id=2)
        previous_balls_recovered_in_distribution_b45 = get_previous_balls_recovered_in_distribution(
            selected_datetime=start_date_sin_timezone, truck_id=truck_id, product__id=3)
        previous_balls_recovered_in_distribution_b15 = get_previous_balls_recovered_in_distribution(
            selected_datetime=start_date_sin_timezone, truck_id=truck_id, product__id=12)

        previous_balls_recovered_in_plant_b10 = get_previous_balls_recovered_in_plant(
            selected_datetime=start_date_sin_timezone, truck_id=truck_id, product__id=1)
        previous_balls_recovered_in_plant_b5 = get_previous_balls_recovered_in_plant(
            selected_datetime=start_date_sin_timezone, truck_id=truck_id, product__id=2)
        previous_balls_recovered_in_plant_b45 = get_previous_balls_recovered_in_plant(
            selected_datetime=start_date_sin_timezone, truck_id=truck_id, product__id=3)
        previous_balls_recovered_in_plant_b15 = get_previous_balls_recovered_in_plant(
            selected_datetime=start_date_sin_timezone, truck_id=truck_id, product__id=12)

        distribution_mobil_set = DistributionMobil.objects.filter(
            # date_distribution__month=month,
            # date_distribution__year=year,
            date_distribution__range=[start_date_sin_timezone.date(), end_date_sin_timezone.date()],
            truck__id=truck_id
        ).annotate(
            previous_distribution_id=Window(expression=Lag('id', default=0),
                                            order_by=(F('date_distribution').asc(), F('id').asc()))
        ).order_by('date_distribution', 'id')

        remaining_in_the_car_bg10 = get_previous_debt_for_in_the_car_balls(
            distribution_mobil_set=distribution_mobil_set, truck_id=truck_id, product__id=1, type_id='L')
        remaining_in_the_car_bg5 = get_previous_debt_for_in_the_car_balls(
            distribution_mobil_set=distribution_mobil_set, truck_id=truck_id, product__id=2, type_id='L')
        remaining_in_the_car_bg45 = get_previous_debt_for_in_the_car_balls(
            distribution_mobil_set=distribution_mobil_set, truck_id=truck_id, product__id=3, type_id='L')
        remaining_in_the_car_bg15 = get_previous_debt_for_in_the_car_balls(
            distribution_mobil_set=distribution_mobil_set, truck_id=truck_id, product__id=12, type_id='L')

        remaining_in_the_car_b10 = get_previous_debt_for_in_the_car_balls(
            distribution_mobil_set=distribution_mobil_set, truck_id=truck_id, product__id=1, type_id='V')
        remaining_in_the_car_b5 = get_previous_debt_for_in_the_car_balls(
            distribution_mobil_set=distribution_mobil_set, truck_id=truck_id, product__id=2, type_id='V')
        remaining_in_the_car_b45 = get_previous_debt_for_in_the_car_balls(
            distribution_mobil_set=distribution_mobil_set, truck_id=truck_id, product__id=3, type_id='V')
        remaining_in_the_car_b15 = get_previous_debt_for_in_the_car_balls(
            distribution_mobil_set=distribution_mobil_set, truck_id=truck_id, product__id=12, type_id='V')

        remaining_borrowed_b10 = int(previous_debt_for_borrowed_balls_b10) - int(
            previous_balls_recovered_in_distribution_b10) - int(previous_balls_recovered_in_plant_b10)
        remaining_borrowed_b5 = int(previous_debt_for_borrowed_balls_b5) - int(
            previous_balls_recovered_in_distribution_b5) - int(previous_balls_recovered_in_plant_b5)
        remaining_borrowed_b45 = int(previous_debt_for_borrowed_balls_b45) - int(
            previous_balls_recovered_in_distribution_b45) - int(previous_balls_recovered_in_plant_b45)
        remaining_borrowed_b15 = int(previous_debt_for_borrowed_balls_b15) - int(
            previous_balls_recovered_in_distribution_b15) - int(previous_balls_recovered_in_plant_b15)

        initial_remaining_in_the_car_bg10 = remaining_in_the_car_bg10
        initial_remaining_in_the_car_bg5 = remaining_in_the_car_bg5
        initial_remaining_in_the_car_bg45 = remaining_in_the_car_bg45
        initial_remaining_in_the_car_bg15 = remaining_in_the_car_bg15

        initial_remaining_in_the_car_b10 = remaining_in_the_car_b10
        initial_remaining_in_the_car_b5 = remaining_in_the_car_b5
        initial_remaining_in_the_car_b45 = remaining_in_the_car_b45
        initial_remaining_in_the_car_b15 = remaining_in_the_car_b15

        initial_remaining_borrowed_b10 = remaining_borrowed_b10
        initial_remaining_borrowed_b5 = remaining_borrowed_b5
        initial_remaining_borrowed_b45 = remaining_borrowed_b45
        initial_remaining_borrowed_b15 = remaining_borrowed_b15

        distributions = []

        # 1: "BALON DE 10 KG"
        # 2: "BALON DE 5KG"
        # 3: "BALON DE 45 KG"
        # 12: "BALON DE 15 KG"
        # 14: "BALONES DE 3 KG"

        base_query_set = OrderDetail.objects.filter(
            # order__distribution_mobil__date_distribution__month=month,
            # order__distribution_mobil__date_distribution__year=year,
            order__distribution_mobil__date_distribution__range=[start_date_sin_timezone.date(),
                                                                 end_date_sin_timezone.date()],
            order__distribution_mobil__truck__id=truck_id,
            unit__name__in=['G', 'GBC']
        )

        header_b10 = list(base_query_set.filter(product__id=1).values_list('price_unit', flat=True).distinct())
        header_b5 = list(base_query_set.filter(product__id=2).values_list('price_unit', flat=True).distinct())
        header_b45 = list(base_query_set.filter(product__id=3).values_list('price_unit', flat=True).distinct())
        header_b15 = list(base_query_set.filter(product__id=12).values_list('price_unit', flat=True).distinct())

        if len(header_b10) == 0:
            header_b10 = [""]
        if len(header_b5) == 0:
            header_b5 = [""]
        if len(header_b45) == 0:
            header_b45 = [""]
        if len(header_b15) == 0:
            header_b15 = [""]

        grouped_by_date = defaultdict(
            lambda: {
                'date': '',
                'B5': {
                    'extracted_bg': 0, 'returned_b': 0, 'ruined_returned_bg': 0, 'quantity_sold_g': 0,
                    'quantity_sold_b': 0, 'quantity_sold': 0, 'in_the_car_bg': 0, 'in_the_car_b': 0,
                    'prices': {h: {'quantity': 0, 'price': 0, 'subtotal': 0} for h in header_b5}, 'total_sales': 0,
                    'remaining_in_the_car_bg': 0, 'recovered_b': 0, 'recovered_in_plant_b': 0,
                    'advanced_b': 0, 'remaining_borrowed_b': 0
                },
                'B10': {
                    'extracted_bg': 0, 'returned_b': 0, 'ruined_returned_bg': 0, 'quantity_sold_g': 0,
                    'quantity_sold_b': 0, 'quantity_sold': 0, 'in_the_car_bg': 0, 'in_the_car_b': 0,
                    'prices': {h: {'quantity': 0, 'price': 0, 'subtotal': 0} for h in header_b10}, 'total_sales': 0,
                    'remaining_in_the_car_bg': 0, 'recovered_b': 0, 'recovered_in_plant_b': 0,
                    'advanced_b': 0, 'remaining_borrowed_b': 0
                },
                'B45': {
                    'extracted_bg': 0, 'returned_b': 0, 'ruined_returned_bg': 0, 'quantity_sold_g': 0,
                    'quantity_sold_b': 0, 'quantity_sold': 0, 'in_the_car_bg': 0, 'in_the_car_b': 0,
                    'prices': {h: {'quantity': 0, 'price': 0, 'subtotal': 0} for h in header_b45}, 'total_sales': 0,
                    'remaining_in_the_car_bg': 0, 'recovered_b': 0, 'recovered_in_plant_b': 0,
                    'advanced_b': 0, 'remaining_borrowed_b': 0
                },
                'B15': {
                    'extracted_bg': 0, 'returned_b': 0, 'ruined_returned_bg': 0, 'quantity_sold_g': 0,
                    'quantity_sold_b': 0, 'quantity_sold': 0, 'in_the_car_bg': 0, 'in_the_car_b': 0,
                    'prices': {h: {'quantity': 0, 'price': 0, 'subtotal': 0} for h in header_b15}, 'total_sales': 0,
                    'remaining_in_the_car_bg': 0, 'recovered_b': 0, 'recovered_in_plant_b': 0,
                    'advanced_b': 0, 'remaining_borrowed_b': 0
                },
                'B3': {
                    'extracted_bg': 0, 'returned_b': 0, 'ruined_returned_bg': 0, 'quantity_sold_g': 0,
                    'quantity_sold_b': 0, 'quantity_sold': 0, 'in_the_car_bg': 0, 'in_the_car_b': 0,
                    'prices': {}, 'total_sales': 0,
                    'remaining_in_the_car_bg': 0, 'recovered_b': 0, 'recovered_in_plant_b': 0,
                    'advanced_b': 0, 'remaining_borrowed_b': 0
                },
                'total_sold_by_date': 0,
                'expense_1': 0, 'expense_2': 0, 'expense_3': 0, 'expense_4': 0, 'expense_5': 0,
                'total_to_deposit': 0,
                'remaining_total_to_deposit': 0,
                'deposited': 0, 'balance': 0, 'bank': "", 'date_deposit': "", 'code_deposit': ""
            }
        )

        remaining_total_to_deposit = 0

        for distribution in distribution_mobil_set:

            date_str = distribution.date_distribution.strftime('%d-%b').upper()
            distribution_obj = grouped_by_date[date_str]
            distribution_obj['date'] = date_str.replace('JAN', 'ENE')

            quantity_recovered_in_plant_b10 = get_ball_recovered_in_plant(
                product_id=1, distribution_mobil_id=distribution.id)
            quantity_recovered_in_plant_b5 = get_ball_recovered_in_plant(
                product_id=2, distribution_mobil_id=distribution.id)
            quantity_recovered_in_plant_b45 = get_ball_recovered_in_plant(
                product_id=3, distribution_mobil_id=distribution.id)
            quantity_recovered_in_plant_b15 = get_ball_recovered_in_plant(
                product_id=12, distribution_mobil_id=distribution.id)

            if quantity_recovered_in_plant_b10 > 0:
                distribution_obj["B10"]["recovered_in_plant_b"] += int(quantity_recovered_in_plant_b10)
                distribution_obj["B10"]["remaining_borrowed_b"] = remaining_borrowed_b10 - int(
                    quantity_recovered_in_plant_b10)
                remaining_borrowed_b10 -= int(quantity_recovered_in_plant_b10)

            if quantity_recovered_in_plant_b5 > 0:
                distribution_obj["B5"]["recovered_in_plant_b"] += int(quantity_recovered_in_plant_b5)
                distribution_obj["B5"]["remaining_borrowed_b"] = remaining_borrowed_b5 - int(
                    quantity_recovered_in_plant_b5)
                remaining_borrowed_b5 -= int(quantity_recovered_in_plant_b5)

            if quantity_recovered_in_plant_b45 > 0:
                distribution_obj["B45"]["recovered_in_plant_b"] += int(quantity_recovered_in_plant_b45)
                distribution_obj["B45"]["remaining_borrowed_b"] = remaining_borrowed_b45 - int(
                    quantity_recovered_in_plant_b45)
                remaining_borrowed_b45 -= int(quantity_recovered_in_plant_b45)

            if quantity_recovered_in_plant_b15 > 0:
                distribution_obj["B15"]["recovered_in_plant_b"] += int(quantity_recovered_in_plant_b15)
                distribution_obj["B15"]["remaining_borrowed_b"] = remaining_borrowed_b15 - int(
                    quantity_recovered_in_plant_b15)
                remaining_borrowed_b15 -= int(quantity_recovered_in_plant_b15)

            for detail in distribution.distributiondetail_set.all():
                # last_distribution_detail_in_the_car_obj = None
                # if distribution.previous_distribution_id > 0:
                #
                #     last_distribution_detail_in_the_car_set = DistributionDetail.objects.filter(
                #         distribution_mobil__id=distribution.previous_distribution_id,
                #         status='C',
                #         product=detail.product
                #     )
                #     if last_distribution_detail_in_the_car_set.exists():
                #         last_distribution_detail_in_the_car_obj = last_distribution_detail_in_the_car_set.last()

                product_id = detail.product.id

                ball = None
                in_the_car_bg = 0

                if product_id == 1:  # B10KG
                    ball = distribution_obj["B10"]
                elif product_id == 2:  # B5KG
                    ball = distribution_obj["B5"]
                elif product_id == 3:  # B45KG
                    ball = distribution_obj["B45"]
                elif product_id == 12:  # B15KG
                    ball = distribution_obj["B15"]

                # if last_distribution_detail_in_the_car_obj is not None:
                # ball["in_the_car_bg"] = int(last_distribution_detail_in_the_car_obj.quantity)
                if detail.status == "C" and detail.type == "L":
                    ball["in_the_car_bg"] = int(detail.quantity)
                if detail.status == "C" and detail.type == "V":
                    ball["in_the_car_b"] = int(detail.quantity)
                    ball["remaining_borrowed_b"] = remaining_borrowed_b10 + int(detail.quantity)
                if detail.status == "E" and detail.type == "L":
                    kardex_set = Kardex.objects.filter(distribution_detail=detail)
                    if kardex_set.exists():
                        kardex_obj = kardex_set.last()
                        ball["extracted_bg"] += int(kardex_obj.quantity)
                    else:
                        ball["extracted_bg"] += int(detail.quantity)

                if detail.status == "D" and detail.type == "V":
                    ball["returned_b"] += int(detail.quantity)
                if detail.status == "D" and detail.type == "M":
                    ball["ruined_returned_bg"] += int(detail.quantity)
                if detail.status == "R" and detail.type == "V":
                    ball["recovered_b"] += int(detail.quantity)
                    if product_id == 1:

                        ball["remaining_borrowed_b"] = remaining_borrowed_b10 - int(detail.quantity)
                        remaining_borrowed_b10 -= int(detail.quantity)
                    elif product_id == 2:

                        ball["remaining_borrowed_b"] = remaining_borrowed_b5 - int(detail.quantity)
                        remaining_borrowed_b5 -= int(detail.quantity)
                    elif product_id == 3:

                        ball["remaining_borrowed_b"] = remaining_borrowed_b45 - int(detail.quantity)
                        remaining_borrowed_b45 -= int(detail.quantity)
                    elif product_id == 12:

                        ball["remaining_borrowed_b"] = remaining_borrowed_b15 - int(detail.quantity)
                        remaining_borrowed_b15 -= int(detail.quantity)
                if detail.status == "A" and detail.type == "V":
                    ball["advanced_b"] += int(detail.quantity)

            total_sales_by_date = 0
            for order in distribution.order_set.all():

                for od in order.orderdetail_set.all():
                    product_id = od.product.id
                    ball = None
                    value = od.price_unit
                    if product_id == 1:  # B10KG
                        ball = distribution_obj["B10"]
                        if value not in header_b10:
                            value = 0
                    elif product_id == 2:  # B5KG
                        ball = distribution_obj["B5"]
                        if value not in header_b5:
                            value = 0
                    elif product_id == 3:  # B45KG
                        ball = distribution_obj["B45"]
                        if value not in header_b45:
                            value = 0
                    elif product_id == 12:  # B15KG
                        ball = distribution_obj["B15"]
                        if value not in header_b15:
                            value = 0

                    if value > 0:
                        ball['prices'][value]["quantity"] += int(od.quantity_sold)
                        ball['prices'][value]['subtotal'] = ball['prices'][value]['quantity'] * od.price_unit
                        ball["total_sales"] += round(od.quantity_sold * od.price_unit, 1)
                        total_sales_by_date += round(od.quantity_sold * od.price_unit, 1)

                    if od.unit.name in ['G', 'GBC']:
                        ball["quantity_sold_g"] += int(od.quantity_sold)
                        ball["quantity_sold"] += int(od.quantity_sold)
                    if od.unit.name == 'B':
                        ball["quantity_sold_b"] += int(od.quantity_sold)
                        ball["quantity_sold"] += int(od.quantity_sold)
                        if product_id == 1:
                            ball["remaining_borrowed_b"] = int(remaining_borrowed_b10) + int(od.quantity_sold)
                            remaining_borrowed_b10 += int(od.quantity_sold)
                        elif product_id == 2:
                            ball["remaining_borrowed_b"] = int(remaining_borrowed_b5) + int(od.quantity_sold)
                            remaining_borrowed_b5 += int(od.quantity_sold)
                        elif product_id == 3:
                            ball["remaining_borrowed_b"] = int(remaining_borrowed_b45) + int(od.quantity_sold)
                            remaining_borrowed_b45 += int(od.quantity_sold)
                        elif product_id == 12:
                            ball["remaining_borrowed_b"] = int(remaining_borrowed_b15) + int(od.quantity_sold)
                            remaining_borrowed_b15 += int(od.quantity_sold)

            if distribution_obj["B10"]["remaining_borrowed_b"] == 0:
                distribution_obj["B10"]["remaining_borrowed_b"] = int(remaining_borrowed_b10)
            if distribution_obj["B5"]["remaining_borrowed_b"] == 0:
                distribution_obj["B5"]["remaining_borrowed_b"] = int(remaining_borrowed_b5)
            if distribution_obj["B45"]["remaining_borrowed_b"] == 0:
                distribution_obj["B45"]["remaining_borrowed_b"] = int(remaining_borrowed_b45)
            if distribution_obj["B15"]["remaining_borrowed_b"] == 0:
                distribution_obj["B15"]["remaining_borrowed_b"] = int(remaining_borrowed_b15)

            total_expenses = 0
            for expense in distribution.cashflow_set.filter(type='S'):
                if expense.description == "PETROLEO":
                    distribution_obj["expense_1"] += round(expense.total, 1)
                if expense.description == "VIATICO":
                    distribution_obj["expense_2"] += round(expense.total, 1)
                if expense.description == "FERIADO Y SUELDO":
                    distribution_obj["expense_3"] += round(expense.total, 1)
                if expense.description == "MANTENIMIENTO":
                    distribution_obj["expense_4"] += round(expense.total, 1)
                if expense.description == "OTROS GASTOS":
                    distribution_obj["expense_5"] += round(expense.total, 1)
                total_expenses += round(expense.total, 1)

            total_deposited = 0
            bank = []
            dates_of_deposit = []
            codes_of_deposit = []
            for deposit in distribution.cashflow_set.filter(type__in=['D', 'E']):
                distribution_obj["deposited"] += round(deposit.total, 1)
                total_deposited += round(deposit.total, 1)
                bank.append(deposit.cash.name)
                dates_of_deposit.append(str(deposit.transaction_date.date()))
                codes_of_deposit.append(str(deposit.operation_code))

            distribution_obj['total_sold_by_date'] += total_sales_by_date

            distribution_obj['total_to_deposit'] = total_sales_by_date - total_expenses

            distribution_obj['balance'] += (total_sales_by_date - total_expenses - total_deposited)

            remaining_total_to_deposit += (total_sales_by_date - total_expenses - total_deposited)
            distribution_obj['remaining_total_to_deposit'] = remaining_total_to_deposit

            bank_without_duplicates = list(set(bank))
            string_of_banks = ", ".join(bank_without_duplicates)
            dates_of_deposit_without_duplicates = list(set(dates_of_deposit))
            string_of_dates_of_deposit = ", ".join(dates_of_deposit_without_duplicates)
            codes_of_deposit_without_duplicates = list(set(codes_of_deposit))
            string_of_codes_of_deposit = ", ".join(codes_of_deposit_without_duplicates)

            distribution_obj['bank'] = string_of_banks
            distribution_obj['date_deposit'] = string_of_dates_of_deposit
            distribution_obj['code_deposit'] = string_of_codes_of_deposit

        distributions = list(grouped_by_date.values())
        tpl = loader.get_template('comercial/monthly_distribution_by_licence_plate_grid_list.html')
        context = ({
            'user_id': request.user.id,
            'distributions': distributions,
            'header_b10': header_b10,
            'header_b5': header_b5,
            'header_b45': header_b45,
            'header_b15': header_b15,
            'initial_remaining_in_the_car_bg10': int(initial_remaining_in_the_car_bg10),
            'initial_remaining_in_the_car_bg5': int(initial_remaining_in_the_car_bg5),
            'initial_remaining_in_the_car_bg45': int(initial_remaining_in_the_car_bg45),
            'initial_remaining_in_the_car_bg15': int(initial_remaining_in_the_car_bg15),

            'initial_remaining_in_the_car_b10': int(initial_remaining_in_the_car_b10),
            'initial_remaining_in_the_car_b5': int(initial_remaining_in_the_car_b5),
            'initial_remaining_in_the_car_b45': int(initial_remaining_in_the_car_b45),
            'initial_remaining_in_the_car_b15': int(initial_remaining_in_the_car_b15),

            'initial_remaining_borrowed_b10': int(initial_remaining_borrowed_b10),
            'initial_remaining_borrowed_b5': int(initial_remaining_borrowed_b5),
            'initial_remaining_borrowed_b45': int(initial_remaining_borrowed_b45),
            'initial_remaining_borrowed_b15': int(initial_remaining_borrowed_b15),

            'initial_debt_for_borrowed_balls_b10': int(previous_debt_for_borrowed_balls_b10),
            'initial_debt_for_borrowed_balls_b5': int(previous_debt_for_borrowed_balls_b5),
            'initial_debt_for_borrowed_balls_b45': int(previous_debt_for_borrowed_balls_b45),
            'initial_debt_for_borrowed_balls_b15': int(previous_debt_for_borrowed_balls_b15),

            'initial_recovered_in_distribution_b10': int(previous_balls_recovered_in_distribution_b10),
            'initial_recovered_in_distribution_b5': int(previous_balls_recovered_in_distribution_b5),
            'initial_recovered_in_distribution_b45': int(previous_balls_recovered_in_distribution_b45),
            'initial_recovered_in_distribution_b15': int(previous_balls_recovered_in_distribution_b15),

            'initial_recovered_in_plant_b10': int(previous_balls_recovered_in_plant_b10),
            'initial_recovered_in_plant_b5': int(previous_balls_recovered_in_plant_b5),
            'initial_recovered_in_plant_b45': int(previous_balls_recovered_in_plant_b45),
            'initial_recovered_in_plant_b15': int(previous_balls_recovered_in_plant_b15),
        })

        if distribution_mobil_set:
            return JsonResponse({
                'grid': tpl.render(context)
            }, status=HTTPStatus.OK)
        else:
            data = {'error': "No hay operaciones registradas"}
            response = JsonResponse(data)
            response.status_code = HTTPStatus.INTERNAL_SERVER_ERROR
            return response


def get_distribution_query(request):
    if request.method == 'GET':
        my_date = datetime.now()
        formatdate = my_date.strftime("%Y-%m-%d")
        truck_set = Truck.objects.filter(distributionmobil__isnull=False).distinct('license_plate').order_by(
            'license_plate')
        user_id = request.user.id
        user_obj = User.objects.get(pk=int(user_id))
        subsidiary_obj = get_subsidiary_by_user(user_obj)

        return render(request, 'comercial/distribution_queries.html', {
            'formatdate': formatdate,
            'subsidiary_obj': subsidiary_obj,
            'truck_set': truck_set,
        })
    elif request.method == 'POST':
        id_truck = int(request.POST.get('truck'))
        start_date = str(request.POST.get('start-date'))
        end_date = str(request.POST.get('end-date'))

        if start_date == end_date:
            distribution_mobil_set = DistributionMobil.objects.filter(date_distribution=start_date,
                                                                      truck__id=id_truck).order_by('date_distribution')
        else:
            distribution_mobil_set = DistributionMobil.objects.filter(date_distribution__range=[start_date, end_date],
                                                                      truck__id=id_truck).order_by('date_distribution')
        if distribution_mobil_set:
            return JsonResponse({
                'grid': get_dict_distribution_queries(distribution_mobil_set, is_pdf=False),
            }, status=HTTPStatus.OK)
        else:
            data = {'error': "No hay operaciones registradas"}
            response = JsonResponse(data)
            response.status_code = HTTPStatus.INTERNAL_SERVER_ERROR
            return response


def get_dict_distribution_queries(distribution_mobil_set, is_pdf=False):
    dictionary = []
    _sum_expenses = 0
    _sum_payments = 0
    for distribution in distribution_mobil_set:
        details = distribution.distributiondetail_set
        number_details = details.count()

        distribution_detail_set_count = distribution.distributiondetail_set.count()
        if number_details > 0:
            inputs = details.filter(status='D')
            outputs = details.filter(status='E')
            number_inputs = inputs.count()
            number_outputs = outputs.count()
            product_dict = {}
            for _input in inputs:
                _search_value = _input.product.id
                if _search_value in product_dict.keys():
                    _product = product_dict[_input.product.id]
                    _void = _product.get('i_void')
                    _filled = _product.get('i_filled')
                    _ruined = _product.get('i_ruined')
                    if _input.type == 'V':
                        product_dict[_input.product.id]['i_void'] = _void + _input.quantity
                    elif _input.type == 'L':
                        product_dict[_input.product.id]['i_filled'] = _filled + _input.quantity
                    elif _input.type == 'M':
                        product_dict[_input.product.id]['i_ruined'] = _ruined + _input.quantity
                else:
                    if _input.type == 'V':
                        product_dict[_input.product.id] = {'sold': 0, 'borrowed': 0,
                                                           'i_void': _input.quantity, 'i_filled': 0, 'i_ruined': 0,
                                                           'o_filled': 0, 'pk': _input.product.id,
                                                           'name': _input.product.name}
                    elif _input.type == 'L':
                        product_dict[_input.product.id] = {'sold': 0, 'borrowed': 0,
                                                           'i_void': 0, 'i_filled': _input.quantity, 'i_ruined': 0,
                                                           'o_filled': 0, 'pk': _input.product.id,
                                                           'name': _input.product.name}
                    elif _input.type == 'M':
                        product_dict[_input.product.id] = {'sold': 0, 'borrowed': 0,
                                                           'i_void': 0, 'i_filled': 0, 'i_ruined': _input.quantity,
                                                           'o_filled': 0, 'pk': _input.product.id,
                                                           'name': _input.product.name}
            for _output in outputs:
                _search_value = _output.product.id
                if _search_value in product_dict.keys():
                    _product = product_dict[_output.product.id]
                    _filled = _product.get('o_filled')
                    if _output.type == 'L':
                        product_dict[_output.product.id]['o_filled'] = _filled + _output.quantity
                else:
                    if _output.type == 'L':
                        product_dict[_output.product.id] = {'sold': 0, 'borrowed': 0,
                                                            'i_void': 0, 'i_filled': 0, 'i_ruined': 0,
                                                            'o_filled': _output.quantity, 'pk': _output.product.id,
                                                            'name': _output.product.name}

            new = {
                'id': distribution.id,
                'truck': distribution.truck.license_plate,
                'date': distribution.date_distribution,
                'input_distribution_detail': [],
                'output_distribution_detail': [],
                'sales': [],
                'products': [],
                'status': distribution.get_status_display(),
                'subsidiary': distribution.subsidiary.name,
                'pilot': distribution.pilot,
                'details_count': distribution_detail_set_count,
                'number_inputs': number_inputs,
                'number_outputs': number_outputs,
                'number_products': 0,
                'height': 0,
                'rows': 0,
                'number_sales': 0,
                'number_order_details': 0,
                'number_expenses': 0,
                'number_payments': 0,
                'is_multi_detail': False,
                'is_multi_expenses': False,
                'is_multi_payments': False,
            }

            for d in DistributionDetail.objects.filter(distribution_mobil=distribution):
                distribution_detail = {
                    'id': d.id,
                    'status': d.get_status_display(),
                    'product': d.product.name,
                    'quantity': d.quantity,
                    'unit': d.unit.name,
                    'distribution_mobil': d.distribution_mobil.id,
                    'type': d.get_type_display(),
                }
                if d.status == 'D':
                    new.get('input_distribution_detail').append(distribution_detail)
                elif d.status == 'E':
                    new.get('output_distribution_detail').append(distribution_detail)

            dictionary.append(new)
            _sales = Order.objects.filter(distribution_mobil=distribution).exclude(type='E')
            number_sales = _sales.count()
            new['number_sales'] = number_sales

            for o in _sales:
                _order_detail = o.orderdetail_set.all()

                for _detail in _order_detail:
                    _search_value = _detail.product.id
                    if _search_value in product_dict.keys():
                        _product = product_dict[_detail.product.id]
                        _sold = _product.get('sold')
                        _borrowed = _product.get('borrowed')
                        if _detail.unit.name == 'B':
                            product_dict[_detail.product.id]['borrowed'] = _borrowed + _detail.quantity_sold
                        elif _detail.unit.name == 'G':
                            product_dict[_detail.product.id]['sold'] = _sold + _detail.quantity_sold

                    else:
                        if _detail.unit.name == 'B':
                            product_dict[_detail.product.id] = {'sold': 0, 'borrowed': _detail.quantity_sold,
                                                                'i_void': 0, 'i_filled': 0, 'i_ruined': 0,
                                                                'o_filled': 0, 'pk': _detail.product.id,
                                                                'name': _detail.product.name}
                        elif _detail.unit.name == 'G':
                            product_dict[_detail.product.id] = {'sold': _detail.quantity_sold, 'borrowed': 0,
                                                                'i_void': 0, 'i_filled': 0, 'i_ruined': 0,
                                                                'o_filled': 0, 'pk': _detail.product.id,
                                                                'name': _detail.product.name}

                _expenses = o.cashflow_set.filter(type='S')
                _payments = o.cashflow_set.filter(Q(type='E') | Q(type='D'))

                number_order_details = _order_detail.count()
                if number_order_details == 0:
                    number_order_details = 1
                else:
                    if number_order_details > 1 and new['is_multi_detail'] is False:
                        new['is_multi_detail'] = True
                number_expenses = _expenses.count()
                if number_expenses == 0:
                    number_expenses = 1
                else:
                    _expenses_set = _expenses.values('order').annotate(totals=Sum('total'))
                    _sum_expenses = _sum_expenses + _expenses_set[0].get('totals')
                    if number_expenses > 1 and new['is_multi_expenses'] is False:
                        new['is_multi_expenses'] = True
                number_payments = _payments.count()
                if number_payments == 0:
                    number_payments = 1
                else:
                    _payments_set = _payments.values('order').annotate(totals=Sum('total'))
                    _sum_payments = _sum_payments + _payments_set[0].get('totals')
                    if number_payments > 1 and new['is_multi_payments'] is False:
                        new['is_multi_payments'] = True

                if (number_order_details >= number_expenses) and (number_order_details >= number_payments):
                    tbl2_height = number_order_details
                elif (number_expenses >= number_order_details) and (number_expenses >= number_payments):
                    tbl2_height = number_expenses
                else:
                    tbl2_height = number_payments

                new['number_order_details'] = new['number_order_details'] + number_order_details
                new['number_expenses'] = new['number_expenses'] + number_expenses
                new['number_payments'] = new['number_payments'] + number_payments

                new['rows'] = new['rows'] + tbl2_height

                largest = largest_among(new['number_order_details'], new['number_expenses'], new['number_payments'])

                order = {
                    'id': o.id,
                    'status': o.get_status_display(),
                    'client': o.client,
                    'total': o.total,
                    'create_at': o.create_at,
                    'order_detail': _order_detail,
                    'expenses': _expenses,
                    'payments': _payments,
                    'largest': largest,
                    'height': tbl2_height,
                    'number_order_details': number_order_details,
                    'number_expenses': number_expenses,
                    'number_payments': number_payments,
                    'distribution_mobil': distribution.id,
                    'type': o.type,
                }
                new.get('sales').append(order)
            _count_products = 0
            for key in product_dict:
                _vp = product_dict[key]['sold'] - product_dict[key]['borrowed']
                _recovered = product_dict[key]['i_void'] - _vp
                _owe = product_dict[key]['o_filled'] - (
                        product_dict[key]['sold'] + product_dict[key]['i_filled'] + product_dict[key]['i_ruined'])
                product = {
                    'pk': key,
                    'name': product_dict[key]['name'],
                    'sold': product_dict[key]['sold'],
                    'borrowed': product_dict[key]['borrowed'],
                    'recovered': _recovered,
                    'owe': _owe,
                }
                new.get('products').append(product)
                _count_products = _count_products + 1
            new['number_products'] = _count_products

            if (number_outputs >= number_inputs) and (number_outputs >= _count_products):
                tbl1_height = number_outputs
            elif (number_inputs >= number_outputs) and (number_inputs >= _count_products):
                tbl1_height = number_inputs
            else:
                tbl1_height = _count_products
            new['height'] = tbl1_height

            if new['rows'] < new['height']:
                new['rows'] = new['height']

    tpl = loader.get_template('comercial/distribution_queries_grid_list.html')
    context = ({
        'dictionary': dictionary,
        'sum_expenses': _sum_expenses,
        'sum_payments': _sum_payments,
        'dif_pe': _sum_payments - _sum_expenses,
        'is_pdf': is_pdf,
    })
    return tpl.render(context)


def largest_among(num1, num2, num3):
    largest = 0
    if (num1 >= num2) and (num1 >= num3):
        largest = num1
    elif (num2 >= num1) and (num2 >= num3):
        largest = num2
    else:
        largest = num3
    return largest


def get_distribution_mobil_recovered(request):
    if request.method == 'GET':
        pk = int(request.GET.get('pk', ''))

        distribution_mobil_obj = DistributionMobil.objects.get(id=pk)
        if distribution_mobil_obj.status == 'F':
            return JsonResponse({
                'error': 'LA PROGRAMACION YA ESTA FINALIZADA, POR FAVOR SELECCIONE OTRA',
            })
        # distribution_mobil_detail = DistributionDetail.objects.filter(distribution_mobil=distribution_mobil_obj)
        user_id = request.user.id
        user_obj = User.objects.get(id=user_id)
        subsidiary_obj = get_subsidiary_by_user(user_obj)
        # client_set = Client.objects.filter(order__distribution_mobil=distribution_mobil_obj.id,
        #                                  order__subsidiary_store__subsidiary=subsidiary_obj).distinct('id')
        # product_serialized_obj = serializers.serialize('json', product)
        client_set = Client.objects.filter(clientassociate__subsidiary=subsidiary_obj)
        t = loader.get_template('comercial/distribution_mobil_recovered.html')
        c = ({
            'distribution_mobil': distribution_mobil_obj,
            'client_set': client_set,
        })
        return JsonResponse({
            'success': True,
            'form': t.render(c, request),
        })


def get_order_detail_by_client(request):
    if request.method == 'GET':
        client_id = request.GET.get('client_id', '')
        # distribution_mobil_id = int(request.GET.get('pk', ''))
        # distribution_mobil_obj = DistributionMobil.objects.get(id=distribution_mobil_id)
        client_obj = Client.objects.get(pk=int(client_id))
        order_set = Order.objects.filter(client=client_obj).filter(Q(type='R') | Q(type='V')).order_by('id')

        return JsonResponse({
            'grid': get_dict_orders_details(order_set, client_obj),
        }, status=HTTPStatus.OK)


def get_dict_orders_details(order_set, client_obj):
    tpl = loader.get_template('comercial/table_orderdetail_client.html')
    context = ({
        'order_set': order_set,
        'client_obj': client_obj,
    })

    return tpl.render(context)


def save_recovered_b(request):
    if request.method == 'GET':
        distribution_mobil_id = int(request.GET.get('distribution_mobil', ''))
        order_id = int(request.GET.get('order', ''))
        detail_order_id = int(request.GET.get('detail_order_id', ''))
        product = int(request.GET.get('product', ''))
        unit = int(request.GET.get('unit', ''))
        quantity_recover = request.GET.get('quantity_recover', '')
        distribution_mobil_obj = DistributionMobil.objects.get(id=distribution_mobil_id)
        order_obj = Order.objects.get(id=order_id)
        order_detail_obj = OrderDetail.objects.get(id=detail_order_id)
        product_obj = Product.objects.get(id=product)
        unit_obj = Unit.objects.get(id=unit)
        search_r_detail_distribution = DistributionDetail.objects.filter(distribution_mobil=distribution_mobil_obj,
                                                                         product=product_obj,
                                                                         status='R')

        if search_r_detail_distribution.count() > 0:
            item_with_qr = search_r_detail_distribution.last()
            item_with_qr.quantity = item_with_qr.quantity + decimal.Decimal(quantity_recover)
            item_with_qr.save()
        else:
            _r_new_detail_distribution = {
                'product': product_obj,
                'distribution_mobil': distribution_mobil_obj,
                'quantity': decimal.Decimal(quantity_recover),
                'unit': unit_obj,
                'status': 'R',
                'type': 'V',
            }
            _r_new_detail_distribution = DistributionDetail.objects.create(**_r_new_detail_distribution)
            _r_new_detail_distribution.save()

        loan_payment_obj = LoanPayment(
            price=order_detail_obj.price_unit,
            quantity=decimal.Decimal(quantity_recover),
            product=product_obj,
            order_detail=order_detail_obj,
            operation_date=datetime.now().date(),
            distribution_mobil=distribution_mobil_obj
        )
        loan_payment_obj.save()

        client_obj = order_obj.client
        order_set = Order.objects.filter(client=client_obj, type='R').order_by('id')
        return JsonResponse({
            'success': True,
            'message': 'Devolución realizada',
            'grid': get_dict_orders_details(order_set, client_obj),
        }, status=HTTPStatus.OK)


def get_advancement_client(request):
    if request.method == 'GET':
        pk = (request.GET.get('pk', ''))
        user_id = request.user.id
        user_obj = User.objects.get(id=user_id)
        subsidiary_obj = get_subsidiary_by_user(user_obj)
        client_obj = Client.objects.filter(clientassociate__subsidiary=subsidiary_obj)
        my_date = datetime.now()
        formatdate = my_date.strftime("%Y-%m-%d")
        product_obj = Product.objects.filter(productstore__subsidiary_store__subsidiary=subsidiary_obj,
                                             productstore__subsidiary_store__category='I')
        if pk != '':
            distribution_mobil_obj = DistributionMobil.objects.get(id=int(pk))
            t = loader.get_template('comercial/client_advancement.html')
            c = ({
                'distribution_mobil': distribution_mobil_obj,
                'client_set': client_obj,
                'format': formatdate,
                'product_set': product_obj,
            })
            return JsonResponse({
                'form': t.render(c, request),
            })
        else:
            return render(request, 'comercial/subsidiary_advancement_client.html', {
                'client_set': client_obj,
                'format': formatdate,
                'product_set': product_obj,
            })


def get_distribution_expense(request):
    if request.method == 'GET':
        pk = (request.GET.get('pk', ''))
        my_date = datetime.now()
        formatdate = my_date.strftime("%Y-%m-%d")
        distribution_mobil_obj = DistributionMobil.objects.get(id=int(pk))

        t = loader.get_template('comercial/distribution_expense.html')
        c = ({
            'distribution_mobil': distribution_mobil_obj,
            'format': formatdate,
        })
        return JsonResponse({
            'form': t.render(c, request),
        })


def get_distribution_deposit(request):
    if request.method == 'GET':
        pk = (request.GET.get('pk', ''))
        my_date = datetime.now()
        formatdate = my_date.strftime("%Y-%m-%d")
        distribution_mobil_obj = DistributionMobil.objects.get(id=int(pk))
        user_id = request.user.id
        user_obj = User.objects.get(id=user_id)
        subsidiary_obj = get_subsidiary_by_user(user_obj)

        cash_set = Cash.objects.filter(
            Q(accounting_account__code__startswith='1041', subsidiary__id=1) |
            Q(accounting_account__code__startswith='101', subsidiary=subsidiary_obj)
        )
        t = loader.get_template('comercial/distribution_deposit.html')
        c = ({
            'distribution_mobil': distribution_mobil_obj,
            'cash_set': cash_set,
            'format': formatdate,
        })
        return JsonResponse({
            'form': t.render(c, request),
        })


def get_distribution_mobil_by_date(request):
    if request.method == 'GET':

        user_id = request.user.id
        user_obj = User.objects.get(id=user_id)
        subsidiary_obj = get_subsidiary_by_user(user_obj)

        date_distribution = request.GET.get('distributionDate', '')
        subsidiary_destiny_id = int(request.GET.get('subsidiaryDestinyId', '0'))
        if date_distribution != '' and subsidiary_destiny_id > 0:
            distribution_mobil_set = DistributionMobil.objects.filter(
                subsidiary_id=subsidiary_destiny_id,
                status='F',
                date_distribution=date_distribution).select_related('truck', 'pilot')

            array_of_distributions = [{
                'id': dm.id,
                'truckLicensePlate': dm.truck.license_plate,
                'pilotFullName': dm.pilot.full_name()
            } for dm in distribution_mobil_set]

            return JsonResponse({
                'success': True,
                'distributions': array_of_distributions,
            }, status=HTTPStatus.OK)


def get_distribution_mobil_fields(request):
    if request.method == 'GET':
        pk = int(request.GET.get('pk', '0'))
        deposited = 0
        expensed = 0
        if pk > 0:
            distribution_obj = DistributionMobil.objects.get(id=pk)
            deposited = distribution_obj.calculate_total_deposits()
            expensed = distribution_obj.calculate_total_expenses()
        return JsonResponse({
            'deposited': deposited,
            'expensed': expensed,
        })


def get_associate_deposit_or_expense(request):
    if request.method == 'GET':
        pk = (request.GET.get('pk', ''))
        my_date = datetime.now()
        formatdate = my_date.strftime("%Y-%m-%d")
        guide_obj = Guide.objects.get(id=int(pk))
        subsidiary_destiny_obj = guide_obj.programming.get_destiny()
        # date_sin_timezone = datetime.strptime(guide_obj.programming.arrival_date, '%Y-%m-%d')
        distribution_mobil_set = DistributionMobil.objects.filter(
            subsidiary=subsidiary_destiny_obj,
            date_distribution=guide_obj.programming.arrival_date
        )

        user_id = request.user.id
        user_obj = User.objects.get(id=user_id)
        subsidiary_obj = get_subsidiary_by_user(user_obj)

        cash_set = Cash.objects.filter(
            Q(accounting_account__code__startswith='1041', subsidiary__id=1) |
            Q(accounting_account__code__startswith='101', subsidiary=subsidiary_obj)
        )
        t = loader.get_template('comercial/associate_deposit_or_expense.html')
        c = ({
            'guide_obj': guide_obj,
            'distribution_mobil_set': distribution_mobil_set,
            'subsidiary_destiny_obj': subsidiary_destiny_obj,
            'distribution_date': guide_obj.programming.arrival_date.strftime("%Y-%m-%d"),
            'format': formatdate,
        })
        return JsonResponse({
            'form': t.render(c, request),
        })


def save_distribution_expense(request):
    if request.method == 'GET':
        expense_request = request.GET.get('expense', '')
        data_expense = json.loads(expense_request)
        user_id = request.user.id
        user_obj = User.objects.get(pk=int(user_id))
        distribution_mobil_id = int(data_expense["distributionId"])
        distribution_mobil_obj = DistributionMobil.objects.get(id=distribution_mobil_id)
        total_expense = decimal.Decimal(data_expense["totalExpense"])
        date_expense = str(data_expense["dateExpense"])
        type_expense = str(data_expense["typeExpense"])

        description = ""
        observation = ""
        if type_expense == '1':
            description = "PETROLEO"
        elif type_expense == '2':
            description = "VIATICO"
        elif type_expense == '3':
            description = "FERIADO Y SUELDO"
        elif type_expense == '4':
            description = "MANTENIMIENTO"
        elif type_expense == '5':
            description = "OTROS GASTOS"
            observation = str(data_expense["observation"]).strip()

        date_sin_timezone = datetime.strptime(date_expense, '%Y-%m-%d')
        timezone_peru = pytz.timezone('America/Lima')
        date_con_timezone = timezone.make_aware(date_sin_timezone, timezone=timezone_peru)
        cash_flow_obj, _ = CashFlow.objects.update_or_create(
            distribution_mobil=distribution_mobil_obj,
            description=description,
            type='S'
        )
        cash_flow_obj.transaction_date = date_con_timezone
        cash_flow_obj.total = total_expense
        cash_flow_obj.user = user_obj
        cash_flow_obj.observation = observation
        cash_flow_obj.save()

        return JsonResponse({
            'message': 'GASTO REGISTRADO CORRECTAMENTE.',
        }, status=HTTPStatus.OK)


def save_associate_distribution(request):
    if request.method == 'GET':
        user_id = request.user.id
        user_obj = User.objects.get(pk=int(user_id))

        associate_request = request.GET.get('associateDistribution', '')
        data_associate = json.loads(associate_request)

        distribution_mobil_id = int(data_associate["distributionId"])
        guide_id = int(data_associate["guideId"])

        # distribution_mobil_id = int(request.GET.get('distributionId', '0'))
        # guide_id = int(request.GET.get('guideId', '0'))
        if guide_id > 0 and distribution_mobil_id > 0:
            guide_obj = Guide.objects.get(id=guide_id)
            cash_flow_set = CashFlow.objects.filter(distribution_mobil=distribution_mobil_id)
            for cf in cash_flow_set:
                guide_cash_flow_obj, _ = GuideCashFlow.objects.update_or_create(
                    guide=guide_obj,
                    cash_flow=cf
                )
            return JsonResponse({
                'message': 'ASOCIACION REGISTRADA',
            }, status=HTTPStatus.OK)
        else:
            print('distribution_mobil_id', distribution_mobil_id)
            print('guide_id', guide_id)
            return JsonResponse({
                'message': 'ASOCIACION EN PROBLEMAS',
            }, status=HTTPStatus.OK)


def save_distribution_deposit(request):
    if request.method == 'GET':
        deposit_request = request.GET.get('deposit', '')
        data_deposit = json.loads(deposit_request)
        user_id = request.user.id
        user_obj = User.objects.get(pk=int(user_id))
        distribution_mobil_id = int(data_deposit["distributionId"])
        cash_id = int(data_deposit["cashId"])
        distribution_mobil_obj = DistributionMobil.objects.get(id=distribution_mobil_id)
        cash_obj = Cash.objects.get(id=cash_id)
        total_deposit = decimal.Decimal(data_deposit["totalDeposit"])
        date_deposit = str(data_deposit["dateDeposit"])
        operation_code = str(data_deposit["operationCode"])
        description = "DEPOSITO A CAJA"

        date_sin_timezone = datetime.strptime(date_deposit, '%Y-%m-%d')
        timezone_peru = pytz.timezone('America/Lima')
        date_con_timezone = timezone.make_aware(date_sin_timezone, timezone=timezone_peru)

        # Q(accounting_account__code__startswith='1041') | Q(accounting_account__code__startswith='101')
        operation_type = ''
        message = ''
        _type = ''
        allow_save = False
        if cash_obj.accounting_account.code.startswith('101'):  # cash

            check_closed_set = CashFlow.objects.filter(
                type='C',
                transaction_date__date=date_con_timezone.date(),
                cash=cash_obj)
            if check_closed_set.exists():
                message = "CAJA CERRADA"
                allow_save = False
            else:
                check_opened_set = CashFlow.objects.filter(
                    cash=cash_obj, transaction_date__date=date_con_timezone.date(), type='A'
                )
                if check_opened_set.exists():
                    message = "CAJA ABIERTA"
                    allow_save = True
                else:
                    message = "CAJA SIN APERTURAR"
                    allow_save = False

            operation_type = '0'
            _type = 'E'
        else:  # bank
            operation_type = '1'
            _type = 'D'
            allow_save = True

        if allow_save:
            new_deposit = {
                'transaction_date': date_con_timezone,
                'distribution_mobil': distribution_mobil_obj,
                'description': description,
                'type': _type,
                'total': total_deposit,
                'cash': cash_obj,
                'user': user_obj,
                'operation_type': operation_type,
                'operation_code': operation_code
            }
            deposit_obj = CashFlow.objects.create(**new_deposit)
            deposit_obj.save()

            message = 'GASTO REGISTRADO CORRECTAMENTE.'

        return JsonResponse({
            'message': message, 'allowSave': allow_save
        }, status=HTTPStatus.OK)


def save_advancement_client(request):
    if request.method == 'GET':
        advancement_request = request.GET.get('advancement', '')
        data_advancement = json.loads(advancement_request)
        user_id = request.user.id
        user_obj = User.objects.get(pk=int(user_id))
        distribution_mobil_id = (data_advancement["_distribution_mobil"])
        if distribution_mobil_id != 0:
            distribution_mobil_obj = DistributionMobil.objects.get(id=int(distribution_mobil_id))
            _type = 'R'
        else:
            _type = 'S'
            distribution_mobil_obj = None
        date_advancement = (data_advancement["_date_advancement"])
        observation = (data_advancement["_observation"])

        id_client = int(data_advancement["_client"])
        client_obj = Client.objects.get(id=id_client)
        subsidiary_obj = get_subsidiary_by_user(user_obj)

        new_client_advancement = {
            'type': _type,
            'distribution_mobil': distribution_mobil_obj,
            'observation': observation,
            'date_create': date_advancement,
            'client': client_obj,
            'subsidiary': subsidiary_obj,
            'user': user_obj,
        }
        client_advancement_obj = ClientAdvancement.objects.create(**new_client_advancement)
        client_advancement_obj.save()

        for detail in data_advancement['Details']:
            quantity = decimal.Decimal(detail['Quantity'])
            product_id = int(detail['Product'])
            product_obj = Product.objects.get(id=product_id)
            unit_id = int(detail['Unit'])
            unit_obj = Unit.objects.get(id=unit_id)
            new_client_advancement_detail = {
                'client_advancement': client_advancement_obj,
                'product': product_obj,
                'quantity': decimal.Decimal(quantity),
                'unit': unit_obj,
            }
            new_client_advancement_detail_obj = ClientAdvancementDetail.objects.create(**new_client_advancement_detail)
            new_client_advancement_detail_obj.save()

            search_product_client = ClientProduct.objects.filter(product=product_obj, client=client_obj, unit=unit_obj)
            if search_product_client.count() > 0:
                search_product_client_q = search_product_client.last()
                search_product_client_q.quantity = search_product_client_q.quantity + decimal.Decimal(quantity)
                search_product_client_q.save()
            else:
                new_client_product = {
                    'quantity': decimal.Decimal(quantity),
                    'product': product_obj,
                    'unit': unit_obj,
                    'client': client_obj,
                }
                new_client_product_obj = ClientProduct.objects.create(**new_client_product)
                new_client_product_obj.save()

            subsidiary_store_obj = SubsidiaryStore.objects.filter(subsidiary=subsidiary_obj, category='I').first()
            if subsidiary_store_obj is not None and client_advancement_obj.type == 'S':
                product_store_obj = ProductStore.objects.get(product=product_obj,
                                                             subsidiary_store=subsidiary_store_obj)
                quantity_minimum_unit = calculate_minimum_unit(quantity, unit_obj, product_obj)
                kardex_input(product_store_obj.id, quantity_minimum_unit, product_obj.calculate_minimum_price_sale(),
                             advance_detail_obj=new_client_advancement_detail_obj)
            else:
                if client_advancement_obj.type == 'R':
                    new_product_obj = ProductRecipe.objects.get(product_input=product_obj).product
                    search_distribution_detail = DistributionDetail.objects.filter(product=new_product_obj,
                                                                                   distribution_mobil=distribution_mobil_obj,
                                                                                   unit=unit_obj, status='A')
                    if search_distribution_detail.count() > 0:
                        search_distribution_detail_p = search_distribution_detail.last()
                        search_distribution_detail_p.quantity = search_distribution_detail_p.quantity + decimal.Decimal(
                            quantity)
                        search_distribution_detail_p.save()
                    else:
                        _a_new_detail_distribution = {
                            'product': new_product_obj,
                            'distribution_mobil': distribution_mobil_obj,
                            'quantity': decimal.Decimal(quantity),
                            'unit': unit_obj,
                            'status': 'A',
                            'type': 'V',
                        }
                        _a_new_detail_distribution = DistributionDetail.objects.create(**_a_new_detail_distribution)
                        _a_new_detail_distribution.save()

        return JsonResponse({
            'message': 'ADELANTO DE BALONES REGISTRADO CORRECTAMENTE.',
        }, status=HTTPStatus.OK)


def get_output_distributions(request):
    if request.method == 'GET':
        pk = request.GET.get('pk', '')
        if pk != '':
            dates_request = request.GET.get('dates', '')
            data_dates = json.loads(dates_request)
            date_initial = (data_dates["date_initial"])
            date_final = (data_dates["date_final"])
            user_id = request.user.id
            user_obj = User.objects.get(id=user_id)
            subsidiary_obj = get_subsidiary_by_user(user_obj)
            purchases_store = Purchase.objects.filter(subsidiary=subsidiary_obj, status='A',
                                                      purchase_date__range=(
                                                          date_initial, date_final)).distinct('id')
            tpl = loader.get_template('buys/purchase_store_grid_list.html')
            context = ({
                'purchases_store': purchases_store,
            })
            return JsonResponse({
                'success': True,
                'form': tpl.render(context, request),
            })
        else:
            my_date = datetime.now()
            date_now = my_date.strftime("%Y-%m-%d")
            return render(request, 'comercial/report_quantity_output_distribution.html', {
                'date_now': date_now,
            })


def get_inclusive_report_on_gas_cylinders(request):
    if request.method == 'GET':
        my_date = datetime.now()
        date_now = my_date.strftime("%Y-%m-%d")
        return render(request, 'comercial/inclusive_report_on_gas_cylinders_list.html', {
            'formatdate': date_now,
        })
    elif request.method == 'POST':
        user_id = request.user.id
        user_obj = User.objects.get(id=user_id)
        subsidiary_obj = get_subsidiary_by_user(user_obj)
        programming_date = str(request.POST.get('programming-date'))
        programming_date_sin_timezone = datetime.strptime(programming_date, '%Y-%m-%d')
        programming_ids = Programming.objects.filter(
            departure_date=programming_date_sin_timezone.date(), subsidiary=subsidiary_obj).values_list('id', flat=True)
        guide_set = Guide.objects.filter(
            programming_id__in=programming_ids).select_related('programming__truck').prefetch_related(
            Prefetch('guideemployee_set__user')
        )

        outputs = []
        total_filled_gas_cylinders = {'B10': 0, 'B45': 0, 'B15': 0, 'B5': 0}
        total_deposits_and_expenses = {'total_deposits': 0, 'total_expenses': 0}
        for g in guide_set:
            pilot_name = ''
            destiny = ''
            if g.programming:
                if g.programming.setemployee_set.exists():
                    pilot_name = g.programming.setemployee_set.filter(function='P').last().employee.full_name()

                if g.programming.route_set.exists():
                    destiny = g.programming.route_set.filter(type='D').last().subsidiary.name
            programming = {
                'id': g.id,
                'type': 'Guide',
                'guideCode': g.code,
                'licensePlate': g.programming.truck.license_plate,
                'pilot': pilot_name,
                'destiny': destiny,
                'client': 'GARAJE',
                'gasCylinders': {'B10': 0, 'B45': 0, 'B15': 0, 'B5': 0},
                'deposits': [],
                'expenses': []
            }
            for gd in g.guidedetail_set.all():
                product_id = gd.product.id
                ball = None
                if product_id == 1:  # B10KG
                    ball = 'B10'
                elif product_id == 2:  # B5KG
                    ball = 'B5'
                elif product_id == 3:  # B5KG
                    ball = 'B45'
                elif product_id == 12:  # B5KG
                    ball = 'B15'

                if gd.unit_measure.name in ['BG']:
                    programming['gasCylinders'][ball] += int(gd.quantity)
                    total_filled_gas_cylinders[ball] += int(gd.quantity)

            cash_flow_set = CashFlow.objects.filter(guidecashflow__guide=g,
                                                    guidecashflow__cash_flow__type__in=['E', 'D'])
            for cf in cash_flow_set:
                cash_flow = {
                    'transactionType': cf.cash.name,
                    'transactionCode': cf.operation_code,
                    'transactionPayment': round(float(cf.total), 2)
                }
                programming['deposits'].append(cash_flow)
                total_deposits_and_expenses['total_deposits'] += round(float(cf.total), 2)
            cash_flow_set = CashFlow.objects.filter(guidecashflow__guide=g, guidecashflow__cash_flow__type__in=['S'])

            for cf in cash_flow_set:
                cash_flow = {
                    'transactionType': cf.description,
                    'transactionCode': cf.operation_code,
                    'transactionPayment': round(float(cf.total), 2)
                }
                programming['expenses'].append(cash_flow)
                total_deposits_and_expenses['total_expenses'] += round(float(cf.total), 2)

            outputs.append(programming)

        distribution_set = DistributionMobil.objects.filter(
            date_distribution=programming_date_sin_timezone.date(), subsidiary=subsidiary_obj
        ).prefetch_related(
            Prefetch('distributiondetail_set')
        )
        for dm in distribution_set:
            filled = {'B10': 0, 'B45': 0, 'B15': 0, 'B5': 0}
            void = {'B10': 0, 'B45': 0, 'B15': 0, 'B5': 0}
            for dd in dm.distributiondetail_set.all():
                product_id = dd.product.id
                ball = None
                if product_id == 1:  # B10KG
                    ball = "B10"
                elif product_id == 2:  # B5KG
                    ball = "B5"
                elif product_id == 3:  # B45KG
                    ball = "B45"
                elif product_id == 12:  # B15KG
                    ball = "B15"
                if dd.status == "E" and dd.type == "L":
                    kardex_set = Kardex.objects.filter(distribution_detail=dd)
                    if kardex_set.exists():
                        kardex_obj = kardex_set.last()
                        filled[ball] += int(kardex_obj.quantity)
                        total_filled_gas_cylinders[ball] += int(kardex_obj.quantity)
                    else:
                        filled[ball] += int(dd.quantity)
                        total_filled_gas_cylinders[ball] += int(dd.quantity)
                if dd.status == "E" and dd.type == "V":
                    kardex_set = Kardex.objects.filter(distribution_detail=dd)
                    if kardex_set.exists():
                        kardex_obj = kardex_set.last()
                        void[ball] += int(kardex_obj.quantity)
                    else:
                        void[ball] += int(dd.quantity)
            if filled['B10'] > 0 or filled['B5'] > 0 or filled['B45'] > 0 or filled['B15'] > 0:
                distribution = {
                    'id': dm.id,
                    'type': 'Distribution',
                    'guideCode': dm.guide_number,
                    'licensePlate': dm.truck.license_plate,
                    'pilot': dm.pilot.full_name(),
                    'destiny': 'NA',
                    'client': 'RUTA PLANTA',
                    'gasCylinders': filled,
                    'deposits': [],
                    'expenses': []
                }
                cash_flow_set = CashFlow.objects.filter(distribution_mobil=dm, type__in=['E', 'D'])
                for cf in cash_flow_set:
                    cash_flow = {
                        'transactionType': cf.cash.name,
                        'transactionCode': cf.operation_code,
                        'transactionPayment': round(float(cf.total), 2)
                    }
                    distribution['deposits'].append(cash_flow)
                    total_deposits_and_expenses['total_deposits'] += round(float(cf.total), 2)
                cash_flow_set = CashFlow.objects.filter(distribution_mobil=dm, type__in=['S'])

                for cf in cash_flow_set:
                    cash_flow = {
                        'transactionType': cf.description,
                        'transactionCode': cf.operation_code,
                        'transactionPayment': round(float(cf.total), 2)
                    }
                    distribution['expenses'].append(cash_flow)
                    total_deposits_and_expenses['total_expenses'] += round(float(cf.total), 2)
                outputs.append(distribution)
            if void['B10'] > 0 or void['B5'] > 0 or void['B45'] > 0 or void['B15'] > 0:
                distribution = {
                    'type': 'Distribution',
                    'guideCode': dm.guide_number,
                    'licensePlate': dm.truck.license_plate,
                    'pilot': dm.pilot.full_name(),
                    'destiny': 'NA',
                    'client': 'VACIOS',
                    'gasCylinders': void,
                    'deposits': []
                }
                outputs.append(distribution)

        order_set = Order.objects.filter(
            create_at__date=programming_date_sin_timezone.date(),
            type='V',
            subsidiary=subsidiary_obj
        ).prefetch_related(
            Prefetch('orderdetail_set')
        )
        for o in order_set:
            order = {
                'id': o.id,
                'type': 'Order',
                'guideCode': o.id,
                'licensePlate': 'NA',
                'pilot': 'VENTA',
                'destiny': o.subsidiary.name,
                'client': o.client.names,
                'gasCylinders': {'B10': 0, 'B45': 0, 'B15': 0, 'B5': 0},
                'deposits': []
            }
            for d in o.orderdetail_set.all():
                product_id = d.product.id
                ball = None
                if product_id == 1:  # B10KG
                    ball = 'B10'
                elif product_id == 2:  # B5KG
                    ball = 'B5'
                elif product_id == 3:  # B5KG
                    ball = 'B45'
                elif product_id == 12:  # B5KG
                    ball = 'B15'

                if d.unit.name in ['G', 'GBC', 'BG']:
                    order['gasCylinders'][ball] += int(d.quantity_sold)
                    total_filled_gas_cylinders[ball] += int(d.quantity_sold)
            transaction_payment_set = TransactionPayment.objects.filter(loan_payment__order_detail__order=o)
            for tp in transaction_payment_set:
                transaction_payment = {
                    'transactionType': tp.get_type_display(),
                    'transactionCode': tp.operation_code,
                    'transactionPayment': tp.payment
                }
                order['deposits'].append(transaction_payment)
                total_deposits_and_expenses['total_deposits'] += round(float(tp.payment), 2)

            outputs.append(order)

        tpl = loader.get_template('comercial/inclusive_report_on_gas_cylinders_grid_list.html')
        context = ({
            'programming_date_sin_timezone': programming_date_sin_timezone,
            'outputs': outputs,
            'total_filled_gas_cylinders': total_filled_gas_cylinders,
            'total_deposits_and_expenses': total_deposits_and_expenses,
        })
        return JsonResponse({
            'grid': tpl.render(context)
        }, status=HTTPStatus.OK)
    return JsonResponse({'message': 'Error de peticion.'}, status=HTTPStatus.BAD_REQUEST)


def distribution_category(request):
    if request.method == 'GET':
        my_date = datetime.now()
        date_now = my_date.strftime("%Y-%m-%d")

        return render(request, 'comercial/report_distribution_category.html', {
            'formatdate': date_now,
            'category_set': Supplier._meta.get_field('sector').choices,
        })
    elif request.method == 'POST':
        user_id = request.user.id
        user_obj = User.objects.get(id=user_id)
        subsidiary_obj = get_subsidiary_by_user(user_obj)
        init = request.POST.get('init')
        end = request.POST.get('end')
        category = request.POST.get('category')

        query_set = Truck.objects.filter(purchase__purchase_date__range=[init, end],
                                         purchase__supplier__sector=category)
        query = query_set.annotate(
            total=Sum(F('purchase__purchasedetail__quantity') * F('purchase__purchasedetail__price_unit')))

        dictionary = []
        total_purchase = decimal.Decimal(0.00)
        total_detail = decimal.Decimal(0.00)
        for t in query:
            row = {
                'license_plate': t.license_plate,
                'total': t.total,
                'purchase': [],
            }
            total_purchase += t.total
            for p in t.purchase_set.filter(purchase_date__range=[init, end],
                                           supplier__sector=category).order_by('purchase_date'):
                item = {
                    'bill_number': p.bill_number,
                    'purchase_date': p.purchase_date,
                    'total': p.total(),
                    'detail': []
                }
                total_detail += p.total()
                for d in p.purchasedetail_set.all():
                    det = {
                        'product': d.product.name,
                        'quantity': d.quantity,
                        'unit': d.unit.description,
                        'price': d.price_unit
                    }
                    item['detail'].append(det)
                row['purchase'].append(item)
            dictionary.append(row)

        tpl = loader.get_template('comercial/report_distribution_category_grid.html')
        context = ({
            'trucks': dictionary,
            'total_purchase': total_purchase,
            'total_detail': total_detail,
        })
        return JsonResponse({
            'success': True,
            'grid': tpl.render(context)
        }, status=HTTPStatus.OK)
    return JsonResponse({'message': 'Error de peticion.'}, status=HTTPStatus.BAD_REQUEST)
