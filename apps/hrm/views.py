from django.db import DatabaseError
from django.shortcuts import render
from django.views.generic import TemplateView, View, CreateView, UpdateView
from django.forms.models import model_to_dict
from django.http import JsonResponse
from http import HTTPStatus
from .models import *
from apps.sales.models import *
from apps.comercial.models import *
from .forms import *
import json
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models.fields.files import ImageFieldFile
from django.template import loader
from datetime import datetime
from django.contrib.auth.hashers import make_password


class Home(TemplateView):
    template_name = 'home.html'

    def get_context_data(self, **kwargs):

        # subsidiary = Subsidiary.objects.filter(establishment__worker_user=user_obj)
        text = '12345678.'
        password = make_password(text)
        context = {
            'subsidiaries': Subsidiary.objects.all(),
            'employees': Employee.objects.all(),
            'products': Product.objects.all(),
            'sales': Product.objects.all(),
            'towings': Towing.objects.all(),
            'users': User.objects.all(),
            'pass': password
        }
        return context

    def get(self, request, *args, **kwargs):
        return render(request, self.template_name, self.get_context_data())

# FUNCION PARA RECUPERAR EL USUARIO DE UNA SUCURSAL


def get_subsidiary_by_user(user_obj):

    worker_obj = Worker.objects.get(user=user_obj)
    establishment_obj = Establishment.objects.filter(worker=worker_obj).last()
    subsidiary = Subsidiary.objects.filter(establishment=establishment_obj).first()
    return subsidiary


# Create your views here.
class EmployeeList(View):
    model = Employee
    form_class = FormEmployee
    template_name = 'hrm/employee_list.html'

    def get_queryset(self):
        return self.model.objects.all().order_by("created_at")

    def get_context_data(self, **kwargs):
        contexto = {}
        contexto['employees'] = self.get_queryset()  # agregamos la consulta al contexto
        contexto['form'] = self.form_class
        return contexto

    def get(self, request, *args, **kwargs):
        return render(request, self.template_name, self.get_context_data())


class JsonEmployeeList(View):
    def get(self, request):
        employees = Employee.objects.all().order_by("created_at")
        t = loader.get_template('hrm/employee_grid_list.html')
        c = ({'employees': employees})
        return JsonResponse({'result': t.render(c)})


class JsonEmployeeCreate(CreateView):
    model = Employee
    form_class = FormEmployee
    template_name = 'hrm/employee_create.html'

    def post(self, request):
        # Recibe como parámetro una representación de un diccionario
        data = dict()
        # if not request.POST._mutable:
        #     request.POST._mutable = True
        # if request.POST['address_1_road_type'] == '0':
        #     request.POST['address_1_road_type'] = ''
        form = FormEmployee(request.POST, request.FILES)

        if form.is_valid():
            print('isvalid()')
            employee = form.save()
            # converting a database model to a dictionary...
            data['employee'] = model_to_dict(employee)
            # Encode into JSON formatted Data
            result = json.dumps(data, cls=ExtendedEncoder)
            # Para pasar cualquier otro objeto serializable JSON, debe establecer el parámetro seguro en False.
            response = JsonResponse(result, safe=False)
            # change status code in JsonResponse
            response.status_code = HTTPStatus.OK
        else:
            # use form.errors to add the error msg as a dictonary
            data['error'] = "form not valid!"
            data['form_invalid'] = form.errors
            # Por defecto, el primer parámetro de JsonResponse, debe ser una instancia dict.
            # Para pasar cualquier otro objeto serializable JSON, debe establecer el parámetro seguro en False.
            response = JsonResponse(data)
            # change status code in JsonResponse
            response.status_code = HTTPStatus.INTERNAL_SERVER_ERROR
        return response


class JsonEmployeeUpdate(UpdateView):
    model = Employee
    form_class = FormEmployee
    template_name = 'hrm/employee_update.html'

    def post(self, request, pk):
        data = dict()
        employee = self.model.objects.get(pk=pk)
        # form = SnapForm(request.POST, request.FILES, instance=instance)
        form = self.form_class(instance=employee, data=request.POST, files=request.FILES)
        if form.is_valid():
            employee = form.save()
            data['employee'] = model_to_dict(employee)
            result = json.dumps(data, cls=ExtendedEncoder)
            response = JsonResponse(result, safe=False)
            response.status_code = HTTPStatus.OK
        else:
            data['error'] = "form not valid!"
            data['form_invalid'] = form.errors
            response = JsonResponse(data)
            response.status_code = HTTPStatus.INTERNAL_SERVER_ERROR
        return response


class ExtendedEncoder(DjangoJSONEncoder):
    def default(self, o):
        if isinstance(o, ImageFieldFile):
            return str(o)
        else:
            return super().default(o)


def get_worker_designation(request):
    if request.method == 'GET':
        data = dict()
        pk = request.GET.get('pk', '')
        try:
            employee_obj = Employee.objects.get(id=pk)
        except Employee.DoesNotExist:
            data['error'] = "empleado no existe!"
            response = JsonResponse(data)
            response.status_code = HTTPStatus.INTERNAL_SERVER_ERROR
            return response
        # Worker_obj = Worker.objects.get(employee=employee_obj)
        form_obj = FormWorker()
        form_period_obj = FormPeriod()
        form_establishment_obj = FormEstablishment()
        form_payment_account_data_obj = FormPaymentAccountData()
        current_date = datetime.now()
        worker_types = WorkerType.objects.all()
        pensioner_regimes = PensionerRegime.objects.all()
        labor_regimes = LaborRegime.objects.all()
        occupational_categories = OccupationalCategory.objects.all()
        formatdate = current_date.strftime("%Y-%m-%d")
        print(formatdate)
        t = loader.get_template('hrm/employee_worker_designation.html')
        c = ({
            'employee': employee_obj,
            'form': form_obj,
            'form_period': form_period_obj,
            'formatdate': formatdate,
            'form_establishment': form_establishment_obj,
            'form_payment_account_data': form_payment_account_data_obj,
            'worker_types': worker_types,
            'pensioner_regimes': pensioner_regimes,
            'labor_regimes': labor_regimes,
            'occupational_categories': occupational_categories,
        })

        return JsonResponse({
            'success': True,
            'form': t.render(c, request),
        })


def create_worker(request):
    if request.method == 'POST':

        employee = request.POST.get('employee')
        employee_obj = Employee.objects.get(id=int(employee))

        period_start_date = request.POST.get('period_start_date')
        period_end_date = request.POST.get('period_end_date')
        reason_for_withdrawal = request.POST.get('reason_for_withdrawal')

        worker_type = request.POST.get('worker_type')
        worker_type_obj = WorkerType.objects.get(id=worker_type)

        worker_type_start_date = request.POST.get('worker_type_start_date')
        worker_type_end_date = request.POST.get('worker_type_end_date')

        labor_regime = request.POST.get('labor_regime')
        labor_regime_obj = LaborRegime.objects.get(id=labor_regime)
        occupational_category = request.POST.get('occupational_category')
        occupational_category_obj = OccupationalCategory.objects.get(id=occupational_category)

        occupation_private_sector = request.POST.get('occupation_private_sector')
        occupation_public_sector = request.POST.get('occupation_public_sector')
        occupation_public_sector_obj = None
        occupation_private_sector_obj = None
        if labor_regime == '01':
            if occupation_private_sector != '':
                occupation_private_sector_obj = OccupationPrivateSector.objects.get(id=occupation_private_sector)
            else:
                response = JsonResponse({'error': "Elija ocupacion del sector privado."})
                response.status_code = HTTPStatus.INTERNAL_SERVER_ERROR
                return response

        else:
            if labor_regime == '02':

                if occupation_public_sector != '':
                    occupation_public_sector_obj = OccupationPublicSector.objects.get(id=occupation_public_sector)
                else:
                    response = JsonResponse({'error': "Elija ocupacion del sector publico."})
                    response.status_code = HTTPStatus.INTERNAL_SERVER_ERROR
                    return response

        contract_type = request.POST.get('contract_type')
        if contract_type != '':
            contract_type_obj = ContractType.objects.get(id=contract_type)
        else:
            response = JsonResponse({'error': "Elija tipo de contrato."})
            response.status_code = HTTPStatus.INTERNAL_SERVER_ERROR
            return response

        payment_type = request.POST.get('payment_type')
        periodicity = request.POST.get('periodicity')

        initial_basic_remuneration = request.POST.get('initial_basic_remuneration')

        subject_to_maximum_working_day = 0
        if request.POST.get('subject_to_maximum_working_day') is not None:
            subject_to_maximum_working_day = 1

        subject_to_atypical_regime = 0
        if request.POST.get('subject_to_atypical_regime') is not None:
            subject_to_atypical_regime = 1

        subject_to_night_time = 0
        if request.POST.get('subject_to_night_time') is not None:
            subject_to_night_time = 1

        special_situation = request.POST.get('special_situation')
        special_situation_obj = SpecialSituation.objects.get(id=special_situation)

        disability = 0
        if request.POST.get('disability') is not None:
            disability = 1

        is_unionized = 0
        if request.POST.get('is_unionized') is not None:
            is_unionized = 1

        situation = request.POST.get('situation')

        situation_obj = Situation.objects.get(id=situation)

        health_insurance_regime = request.POST.get('health_insurance_regime')
        health_insurance_regime_obj = HealthInsuranceRegime.objects.get(id=health_insurance_regime)
        health_insurance_regime_start_date = request.POST.get('health_insurance_regime_start_date')
        health_insurance_regime_end_date = request.POST.get('health_insurance_regime_end_date')

        pensioner_regime = request.POST.get('pensioner_regime')
        pensioner_regime_obj = PensionerRegime.objects.get(id=pensioner_regime)
        cuspp = request.POST.get('cuspp')
        pensioner_regime_start_date = request.POST.get('pensioner_regime_start_date')
        pensioner_regime_end_date = request.POST.get('pensioner_regime_end_date')

        sctr_pension = request.POST.get('sctr_pension', '0')
        sctr_health_start_date = request.POST.get('sctr_health_start_date')
        sctr_health_end_date = request.POST.get('sctr_health_end_date')

        educational_situation = request.POST.get('educational_situation')
        educational_situation_obj = EducationalSituation.objects.get(id=educational_situation)

        exempted_5th_category_rent = 0
        if request.POST.get('exempted_5th_category_rent') is not None:
            exempted_5th_category_rent = 1

        agreement_to_avoid_double_taxation = 0
        if request.POST.get('agreement_to_avoid_double_taxation') is not None:
            agreement_to_avoid_double_taxation = 1

        subsidiary = request.POST.get('subsidiary')
        subsidiary_obj = Subsidiary.objects.get(id=subsidiary)

        financial_system_entity = request.POST.get('financial_system_entity')
        account_number_where_the_remuneration_is_paid = request.POST.get(
            'account_number_where_the_remuneration_is_paid')

        user = request.POST.get('user', '')
        create_user = 0
        if request.POST.get('create_user') is not None:
            create_user = 1

        user_obj = None
        if user != '':
            user_obj = User.objects.get(id=user)
            if user_obj.employee is not None:
                response = JsonResponse({'error': "Este usuario ya esta siendo utilizado por otro empleado."})
                response.status_code = HTTPStatus.INTERNAL_SERVER_ERROR
                return response
        else:
            if bool(create_user):
                username = employee_obj.names.lower()[:1] + employee_obj.paternal_last_name.lower() + str(employee_obj.id)
                user_email = username + '@user.com'
                user_obj = User(
                    username=username,
                    email=user_email,
                )
                user_obj.set_password(employee_obj.document_number)
                user_obj.save()

        worker_obj = Worker(
            employee=employee_obj,  # oblig
            labor_regime=labor_regime_obj,  # oblig
            educational_situation=educational_situation_obj,  # oblig
            occupation_public_sector=occupation_public_sector_obj,  #
            occupation_private_sector=occupation_private_sector_obj,  # oblig
            disability=bool(int(disability)),  # oblig
            cuspp=cuspp,  #
            sctr_pension=sctr_pension,  #
            contract_type=contract_type_obj,  # oblig
            subject_to_atypical_regime=bool(int(subject_to_atypical_regime)),  # oblig
            subject_to_maximum_working_day=bool(int(subject_to_maximum_working_day)),  # oblig
            subject_to_night_time=bool(int(subject_to_night_time)),  # oblig
            is_unionized=bool(int(is_unionized)),  # oblig
            periodicity=periodicity,  # oblig
            initial_basic_remuneration=float(initial_basic_remuneration),  # oblig
            situation=situation_obj,  # oblig
            exempted_5th_category_rent=bool(int(exempted_5th_category_rent)),  # oblig
            special_situation=special_situation_obj,  # oblig
            payment_type=payment_type,  # oblig
            occupational_category=occupational_category_obj,  #
            agreement_to_avoid_double_taxation=agreement_to_avoid_double_taxation,  # oblig
            user=user_obj
        )
        # print(worker_obj)
        worker_obj.save()

        period_obj1 = Period(
            worker=worker_obj,
            category='1',  # Trabajador
            register_type='1',  # Período
            start_or_restart_date=period_start_date,
        )
        period_obj1.save()

        period_obj2 = Period(
            worker=worker_obj,
            category='1',  # Trabajador
            register_type='2',  # Tipo de trabajador
            start_or_restart_date=worker_type_start_date,
            indicator_of_the_type_of_registration=str(worker_type_obj.id),
            worker_type=worker_type_obj
        )
        period_obj2.save()

        period_obj3 = Period(
            worker=worker_obj,
            category='1',  # Trabajador
            register_type='3',  # Régimen de Aseguramiento de Salud
            start_or_restart_date=health_insurance_regime_start_date,
            indicator_of_the_type_of_registration=str(health_insurance_regime_obj.id),
            health_insurance_regime=health_insurance_regime_obj
        )
        period_obj3.save()

        period_obj4 = Period(
            worker=worker_obj,
            category='1',  # Trabajador
            register_type='4',  # Régimen pensionario
            start_or_restart_date=pensioner_regime_start_date,
            indicator_of_the_type_of_registration=str(pensioner_regime_obj.id),
            pensioner_regime=pensioner_regime_obj
        )
        period_obj4.save()

        establishment_obj = Establishment(
            worker=worker_obj,
            subsidiary=subsidiary_obj,
            ruc_own=subsidiary_obj.ruc,
        )
        establishment_obj.save()

        if financial_system_entity != '':
            financial_system_entity_obj = FinancialSystemEntity.objects.get(id=financial_system_entity)
            payment_account_data_obj = PaymentAccountData(
                worker=worker_obj,
                financial_system_entity=financial_system_entity_obj,
                account_number_where_the_remuneration_is_paid=account_number_where_the_remuneration_is_paid,
            )
            payment_account_data_obj.save()

        return JsonResponse({
            'success': True,
            # 'form': t.render(c),
        }, status=HTTPStatus.OK)


def get_establishment_code(request):
    if request.method == 'GET':
        id_subsidiary = request.GET.get('subsidiary', '')
        subsidiary_obj = Subsidiary.objects.get(id=int(id_subsidiary))
        return JsonResponse({
            'serial': subsidiary_obj.serial,
            'address': subsidiary_obj.address,
            'message': 'Codigo de sede recuperado.',
        }, status=HTTPStatus.OK)


def get_worker_establishment(request):
    if request.method == 'GET':
        pk = request.GET.get('pk', '')
        worker_obj = Worker.objects.get(id=pk)
        form_establishment_obj = FormEstablishment()
        t = loader.get_template('hrm/worker_establishment.html')
        c = ({
            'worker': worker_obj,
            'form': form_establishment_obj,
        })
        return JsonResponse({
            'success': True,
            'form': t.render(c, request),
        })


def update_worker_establishment(request):
    if request.method == 'POST':

        worker = request.POST.get('worker')
        worker_obj = Worker.objects.get(id=int(worker))

        subsidiary = request.POST.get('subsidiary')
        subsidiary_obj = Subsidiary.objects.get(id=subsidiary)

        establishment_obj = Establishment.objects.filter(worker=worker_obj).last()

        establishment_obj.subsidiary = subsidiary_obj
        establishment_obj.ruc_own = subsidiary_obj.ruc
        establishment_obj.save()

        return JsonResponse({
            'success': True,
            # 'form': t.render(c),
        }, status=HTTPStatus.OK)
    data = {'error': 'Peticion incorrecta'}
    response = JsonResponse(data)
    response.status_code = HTTPStatus.INTERNAL_SERVER_ERROR
    return response


def get_worker_user(request):
    if request.method == 'GET':
        pk = request.GET.get('pk', '')
        worker_obj = Worker.objects.get(id=pk)
        t = loader.get_template('hrm/worker_user.html')
        c = ({
            'worker': worker_obj,
        })
        return JsonResponse({
            'success': True,
            'form': t.render(c, request),
        })


def update_worker_user(request):
    if request.method == 'POST':

        worker = request.POST.get('worker')
        worker_obj = Worker.objects.get(id=int(worker))

        username = request.POST.get('username')
        password = request.POST.get('key')
        is_staff = False
        if request.POST.get('is_staff') is not None:
            is_staff = bool(request.POST.get('is_staff'))

        try:
            user_obj = User.objects.get(worker=worker_obj)
        except User.DoesNotExist:
            user_obj = None

        if user_obj is not None:
            if len(username) > 0:
                if user_obj.username != username:
                    user_obj.username = username
            if len(password) >= 6:
                user_obj.set_password(password)
        else:
            user_email = username + '@user.com'
            user_obj = User(
                username=username,
                email=user_email,
            )
            user_obj.set_password(password)
        user_obj.is_staff = is_staff
        try:
            user_obj.save()
        except DatabaseError as e:
            data = {'error': str(e)}
            response = JsonResponse(data)
            response.status_code = HTTPStatus.INTERNAL_SERVER_ERROR
            return response
        worker_obj.user = user_obj
        worker_obj.save()
        return JsonResponse({
            'success': True,
            # 'form': t.render(c),
        }, status=HTTPStatus.OK)
    data = {'error': 'Peticion incorrecta'}
    response = JsonResponse(data)
    response.status_code = HTTPStatus.INTERNAL_SERVER_ERROR
    return response


def edit_worker_designation(request):
    if request.method == 'GET':
        data = dict()
        pk = request.GET.get('pk', '')
        try:
            worker_obj = Worker.objects.get(id=pk)
        except Worker.DoesNotExist:
            data['error'] = "empleado no existe!"
            response = JsonResponse(data)
            response.status_code = HTTPStatus.INTERNAL_SERVER_ERROR
            return response
        # Período
        period_obj1 = Period.objects.filter(worker=worker_obj, category='1', register_type='1').last()
        # Tipo de trabajador
        period_obj2 = Period.objects.filter(worker=worker_obj, category='1', register_type='2').last()
        # Régimen de Aseguramiento de Salud
        period_obj3 = Period.objects.filter(worker=worker_obj, category='1', register_type='3').last()
        # Régimen pensionario
        period_obj4 = Period.objects.filter(worker=worker_obj, category='1', register_type='4').last()

        establishment_obj = Establishment.objects.filter(worker=worker_obj).last()
        payment_account_data_obj = PaymentAccountData.objects.filter(worker=worker_obj).last()

        form_obj = FormWorker()
        form_period_obj = FormPeriod()
        form_establishment_obj = FormEstablishment()
        form_payment_account_data_obj = FormPaymentAccountData()
        current_date = datetime.now()
        worker_types = WorkerType.objects.all()
        pensioner_regimes = PensionerRegime.objects.all()
        labor_regimes = LaborRegime.objects.all()
        occupational_categories = OccupationalCategory.objects.all()
        formatdate = current_date.strftime("%Y-%m-%d")

        t = loader.get_template('hrm/employee_worker_update_designation.html')
        c = ({
            'worker': worker_obj,
            'period1': period_obj1,
            'period2': period_obj2,
            'period3': period_obj3,
            'period4': period_obj4,
            'establishment': establishment_obj,
            'payment_account': payment_account_data_obj,
            'form': form_obj,
            'form_period': form_period_obj,
            'formatdate': formatdate,
            'form_establishment': form_establishment_obj,
            'form_payment_account_data': form_payment_account_data_obj,
            'worker_types': worker_types,
            'pensioner_regimes': pensioner_regimes,
            'labor_regimes': labor_regimes,
            'occupational_categories': occupational_categories,
        })

        return JsonResponse({
            'success': True,
            'form': t.render(c, request),
        })


def update_worker(request):
    if request.method == 'POST':

        worker = request.POST.get('worker')
        worker_obj = Worker.objects.get(id=int(worker))

        period_start_date = request.POST.get('period_start_date')
        period_end_date = request.POST.get('period_end_date')
        reason_for_withdrawal = request.POST.get('reason_for_withdrawal')

        worker_type = request.POST.get('worker_type')
        worker_type_obj = WorkerType.objects.get(id=worker_type)

        worker_type_start_date = request.POST.get('worker_type_start_date')
        worker_type_end_date = request.POST.get('worker_type_end_date')

        labor_regime = request.POST.get('labor_regime')
        labor_regime_obj = LaborRegime.objects.get(id=labor_regime)
        occupational_category = request.POST.get('occupational_category')
        occupational_category_obj = OccupationalCategory.objects.get(id=occupational_category)

        occupation_private_sector = request.POST.get('occupation_private_sector')
        occupation_public_sector = request.POST.get('occupation_public_sector')
        occupation_public_sector_obj = None
        occupation_private_sector_obj = None
        if labor_regime == '01':
            if occupation_private_sector != '':
                occupation_private_sector_obj = OccupationPrivateSector.objects.get(id=occupation_private_sector)
            else:
                response = JsonResponse({'error': "Elija ocupacion del sector privado."})
                response.status_code = HTTPStatus.INTERNAL_SERVER_ERROR
                return response

        else:
            if labor_regime == '02':

                if occupation_public_sector != '':
                    occupation_public_sector_obj = OccupationPublicSector.objects.get(id=occupation_public_sector)
                else:
                    response = JsonResponse({'error': "Elija ocupacion del sector publico."})
                    response.status_code = HTTPStatus.INTERNAL_SERVER_ERROR
                    return response

        contract_type = request.POST.get('contract_type')
        if contract_type != '':
            contract_type_obj = ContractType.objects.get(id=contract_type)
        else:
            response = JsonResponse({'error': "Elija tipo de contrato."})
            response.status_code = HTTPStatus.INTERNAL_SERVER_ERROR
            return response

        payment_type = request.POST.get('payment_type')
        periodicity = request.POST.get('periodicity')

        initial_basic_remuneration = request.POST.get('initial_basic_remuneration')

        subject_to_maximum_working_day = 0
        if request.POST.get('subject_to_maximum_working_day') is not None:
            subject_to_maximum_working_day = 1

        subject_to_atypical_regime = 0
        if request.POST.get('subject_to_atypical_regime') is not None:
            subject_to_atypical_regime = 1

        subject_to_night_time = 0
        if request.POST.get('subject_to_night_time') is not None:
            subject_to_night_time = 1

        special_situation = request.POST.get('special_situation')
        special_situation_obj = SpecialSituation.objects.get(id=special_situation)

        disability = 0
        if request.POST.get('disability') is not None:
            disability = 1

        is_unionized = 0
        if request.POST.get('is_unionized') is not None:
            is_unionized = 1

        situation = request.POST.get('situation')

        situation_obj = Situation.objects.get(id=situation)

        health_insurance_regime = request.POST.get('health_insurance_regime')
        health_insurance_regime_obj = HealthInsuranceRegime.objects.get(id=health_insurance_regime)
        health_insurance_regime_start_date = request.POST.get('health_insurance_regime_start_date')
        health_insurance_regime_end_date = request.POST.get('health_insurance_regime_end_date')

        pensioner_regime = request.POST.get('pensioner_regime')
        pensioner_regime_obj = PensionerRegime.objects.get(id=pensioner_regime)
        cuspp = request.POST.get('cuspp')
        pensioner_regime_start_date = request.POST.get('pensioner_regime_start_date')
        pensioner_regime_end_date = request.POST.get('pensioner_regime_end_date')

        sctr_pension = request.POST.get('sctr_pension', '0')
        sctr_health_start_date = request.POST.get('sctr_health_start_date')
        sctr_health_end_date = request.POST.get('sctr_health_end_date')

        educational_situation = request.POST.get('educational_situation')
        educational_situation_obj = EducationalSituation.objects.get(id=educational_situation)

        exempted_5th_category_rent = 0
        if request.POST.get('exempted_5th_category_rent') is not None:
            exempted_5th_category_rent = 1

        agreement_to_avoid_double_taxation = 0
        if request.POST.get('agreement_to_avoid_double_taxation') is not None:
            agreement_to_avoid_double_taxation = 1

        subsidiary = request.POST.get('subsidiary')
        subsidiary_obj = Subsidiary.objects.get(id=subsidiary)

        financial_system_entity = request.POST.get('financial_system_entity')
        account_number_where_the_remuneration_is_paid = request.POST.get(
            'account_number_where_the_remuneration_is_paid')

        worker_obj.labor_regime = labor_regime_obj  # oblig
        worker_obj.educational_situation = educational_situation_obj  # oblig
        worker_obj.occupation_public_sector = occupation_public_sector_obj  #
        worker_obj.occupation_private_sector = occupation_private_sector_obj  # oblig
        worker_obj.disability = bool(int(disability))  # oblig
        worker_obj.cuspp = cuspp  #
        worker_obj.sctr_pension = sctr_pension  #
        worker_obj.contract_type = contract_type_obj  # oblig
        worker_obj.subject_to_atypical_regime = bool(int(subject_to_atypical_regime))  # oblig
        worker_obj.subject_to_maximum_working_day = bool(int(subject_to_maximum_working_day))  # oblig
        worker_obj.subject_to_night_time = bool(int(subject_to_night_time))  # oblig
        worker_obj.is_unionized = bool(int(is_unionized))  # oblig
        worker_obj.periodicity = periodicity  # oblig
        worker_obj.initial_basic_remuneration = float(initial_basic_remuneration)  # oblig
        worker_obj.situation = situation_obj  # oblig
        worker_obj.exempted_5th_category_rent = bool(int(exempted_5th_category_rent))  # oblig
        worker_obj.special_situation = special_situation_obj  # oblig
        worker_obj.payment_type = payment_type  # oblig
        worker_obj.occupational_category = occupational_category_obj  #
        worker_obj.agreement_to_avoid_double_taxation = agreement_to_avoid_double_taxation  # oblig
        worker_obj.save()

        # Período
        period_obj1 = Period.objects.filter(worker=worker_obj, category='1', register_type='1').last()
        # Tipo de trabajador
        period_obj2 = Period.objects.filter(worker=worker_obj, category='1', register_type='2').last()
        # Régimen de Aseguramiento de Salud
        period_obj3 = Period.objects.filter(worker=worker_obj, category='1', register_type='3').last()
        # Régimen pensionario
        period_obj4 = Period.objects.filter(worker=worker_obj, category='1', register_type='4').last()

        establishment_obj = Establishment.objects.filter(worker=worker_obj).last()
        payment_account_data_obj = PaymentAccountData.objects.filter(worker=worker_obj).last()

        period_obj1.start_or_restart_date = period_start_date
        period_obj1.save()

        period_obj2.start_or_restart_date = worker_type_start_date
        period_obj2.indicator_of_the_type_of_registration = str(worker_type_obj.id)
        period_obj2.worker_type = worker_type_obj
        period_obj2.save()

        period_obj3.start_or_restart_date = health_insurance_regime_start_date
        period_obj3.indicator_of_the_type_of_registration = str(health_insurance_regime_obj.id)
        period_obj3.health_insurance_regime = health_insurance_regime_obj
        period_obj3.save()

        period_obj4.start_or_restart_date = pensioner_regime_start_date
        period_obj4.indicator_of_the_type_of_registration = str(pensioner_regime_obj.id)
        period_obj4.pensioner_regime = pensioner_regime_obj
        period_obj4.save()

        establishment_obj.subsidiary = subsidiary_obj
        establishment_obj.ruc_own = subsidiary_obj.ruc
        establishment_obj.save()

        if financial_system_entity != '':
            financial_system_entity_obj = FinancialSystemEntity.objects.get(id=financial_system_entity)
            if payment_account_data_obj:
                payment_account_data_obj.financial_system_entity = financial_system_entity_obj
                payment_account_data_obj.account_number_where_the_remuneration_is_paid = account_number_where_the_remuneration_is_paid
            else:
                payment_account_data_obj = PaymentAccountData(
                    worker=worker_obj,
                    financial_system_entity=financial_system_entity_obj,
                    account_number_where_the_remuneration_is_paid=account_number_where_the_remuneration_is_paid,
                )
            payment_account_data_obj.save()

        return JsonResponse({
            'success': True,
            # 'form': t.render(c),
        }, status=HTTPStatus.OK)
