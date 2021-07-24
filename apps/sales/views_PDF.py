import reportlab
from django.http import HttpResponse
from reportlab.lib.colors import black, white, gray, red, green, blue
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, TableStyle, Spacer, tables
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY, TA_RIGHT
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape, A4, A5, C7
from reportlab.lib.units import mm, cm, inch
from reportlab.platypus import Table, Flowable
from reportlab.lib.colors import HexColor
from reportlab.pdfgen import canvas
from reportlab.pdfgen.canvas import Canvas
# from reportlab.rl_config import defaultPageSize
from functools import partial
from reportlab.lib.colors import PCMYKColor, PCMYKColorSep, Color, black, blue, red, pink, green
from .models import Product, Client, Order, OrderDetail, SubsidiaryStore, ProductStore, Kardex, LoanPayment
from django.contrib.auth.models import User
from apps.hrm.views import get_subsidiary_by_user
from .views import get_context_kardex_glp, get_dict_orders, total_remaining_repay_loan, total_remaining_return_loan, \
    repay_loan, return_loan
from django.template import loader
from chombitas import settings
from datetime import datetime
from .format_dates import utc_to_local
from django.db.models import Sum, Max, Min, Sum, Q, Value as V, F, Prefetch
import io
import pdfkit

# Register Fonts
# PAGE_HEIGHT = defaultPageSize[1]
# PAGE_WIDTH = defaultPageSize[0]
styles = getSampleStyleSheet()
styleN = styles['Normal']
styleH = styles['Heading1']


def product_print(self, pk=None):
    response = HttpResponse(content_type='application/pdf')
    buff = io.BytesIO()
    doc = SimpleDocTemplate(buff,
                            pagesize=letter,
                            rightMargin=40,
                            leftMargin=40,
                            topMargin=60,
                            bottomMargin=18,
                            )
    products = []
    styles = getSampleStyleSheet()
    header = Paragraph("Listado de Productos", styles['Heading1'])
    products.append(header)
    headings = ('Id', 'Descrición', 'Activo', 'Creación')
    if not pk:
        all_products = [(p.id, p.name, p.is_enabled, p.code)
                        for p in Product.objects.all().order_by('pk')]
    else:
        all_products = [(p.id, p.name, p.is_enabled, p.code)
                        for p in Product.objects.filter(id=pk)]
    t = Table([headings] + all_products)
    t.setStyle(TableStyle(
        [
            ('GRID', (0, 0), (3, -1), 1, colors.dodgerblue),
            ('LINEBELOW', (0, 0), (-1, 0), 2, colors.darkblue),
            ('BACKGROUND', (0, 0), (-1, 0), colors.dodgerblue)
        ]
    ))

    products.append(t)
    doc.build(products)
    response.write(buff.getvalue())
    buff.close()
    return response


def kardex_glp_pdf(request, pk):
    user_id = request.user.id
    user_obj = User.objects.get(id=user_id)
    subsidiary_obj = get_subsidiary_by_user(user_obj)
    if request.method == 'GET':
        if pk != '':
            html = get_context_kardex_glp(subsidiary_obj, pk, is_pdf=True)
            options = {
                'page-size': 'A3',
                'orientation': 'Landscape',
                'encoding': "UTF-8",
            }
            path_wkhtmltopdf = r'C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe'
            config = pdfkit.configuration(wkhtmltopdf=path_wkhtmltopdf)

            pdf = pdfkit.from_string(html, False, options, configuration=config)
            response = HttpResponse(pdf, content_type='application/pdf')
            # response['Content-Disposition'] = 'attachment;filename="kardex_pdf.pdf"'
            return response


def account_order_list_pdf(request, pk):
    if request.method == 'GET':
        client_obj = Client.objects.get(pk=int(pk))

        order_set = Order.objects.filter(client=client_obj, type='R')

        if pk != '':
            html = get_dict_orders(order_set, client_obj=client_obj, is_pdf=True, )
            options = {
                'page-size': 'A3',
                'orientation': 'Landscape',
                'encoding': "UTF-8",
            }
            path_wkhtmltopdf = r'C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe'
            config = pdfkit.configuration(wkhtmltopdf=path_wkhtmltopdf)

            pdf = pdfkit.from_string(html, False, options, configuration=config)
            response = HttpResponse(pdf, content_type='application/pdf')
            # response['Content-Disposition'] = 'attachment;filename="kardex_pdf.pdf"'
            return response


Title = "ESTADO DE CUENTA DE "
pageinfo = "VICTORIA JUAN GAS S.A.C."
register_date_now = utc_to_local(datetime.now())
date_now = register_date_now.strftime("%d/%m/%y %H:%M")


# A4 CM 21.0 x 29.7


def all_account_order_list_pdf(self, pk=None):
    register_date_now = utc_to_local(datetime.now())
    date_now = register_date_now.strftime("%d/%m/%y %H:%M")

    user_obj = User.objects.get(id=int(pk))
    buff = io.BytesIO()
    ml = 2.5 * cm
    mr = 2.5 * cm
    ms = 3.0 * cm
    mi = 2.5 * cm
    a = 0

    doc = SimpleDocTemplate(buff,
                            pagesize=A4,
                            rightMargin=mr,
                            leftMargin=ml,
                            topMargin=ms,
                            bottomMargin=mi,
                            title='ESTADO DE CUENTAS DE ' + str(get_subsidiary_by_user(user_obj))
                            )
    Story = []

    Story.append(Spacer(1, 50))

    headings = (
        'N°'.upper(),
        'Cliente'.upper(),
        'Pago Faltante (Efectivo)'.upper(),
        'Cantidad Faltante (Fierros)'.upper(),
    )
    all_orders = []
    detail_orders = []
    client_dict = {}

    subsidiary_obj = get_subsidiary_by_user(user_obj)
    # Title = Title + str(get_subsidiary_by_user(user_obj))
    summary_sum_total_remaining_repay_loan = 0
    summary_sum_total_remaining_return_loan = 0

    # for c in Client.objects.all().order_by('pk').values('id', 'names'):
    # client_set = Order.objects.filter(subsidiary_store__subsidiary=subsidiary_obj).exclude(type='E').values(
    #     'client__id', 'client__names').distinct('client__id')

    client_set = Client.objects.filter(
        order__isnull=False,
        order__subsidiary=subsidiary_obj,
        order__type__in=['V', 'R']).distinct('id').values('id', 'names')

    # client_set = Client.objects.filter(
    #     order__isnull=False, order__subsidiary=subsidiary_obj, order__type__in=['V', 'R']
    # ).values('id', 'names').annotate(max=Max('id'))
    # for c in Client.objects.filter(clientassociate__subsidiary=subsidiary_obj).order_by('names').values('id', 'names'):

    order_set = Order.objects.filter(
        subsidiary=subsidiary_obj, type__in=['V', 'R'],
        client__id__in=[c['id'] for c in client_set]
    ).prefetch_related(
        Prefetch(
            'orderdetail_set', queryset=OrderDetail.objects.select_related('unit', 'product').prefetch_related(
                Prefetch(
                    'loanpayment_set',
                     queryset=LoanPayment.objects.only(
                         'id', 'order_detail__id', 'quantity', 'price', 'discount'
                     )
                )
            )
            .only(
                'id', 'order__id', 'quantity_sold', 'price_unit',
                'product__id', 'product__name', 'unit__id', 'unit__name'
            )
        )
    ).select_related('client')

    for o in order_set:

        key = o.client.id

        rpl = total_remaining_repay_loan(order_detail_set=o.orderdetail_set.all())
        rtl = total_remaining_return_loan(order_detail_set=o.orderdetail_set.all())

        if key in client_dict:
            client = client_dict[key]

            old_rpl = client.get('sum_total_remaining_repay_loan')
            old_rtl = client.get('sum_total_remaining_return_loan')

            client_dict[key]['sum_total_remaining_repay_loan'] = old_rpl + rpl
            client_dict[key]['sum_total_remaining_return_loan'] = old_rtl + rtl

        else:
            client_dict[key] = {
                'client_id': o.client.id,
                'client_names': o.client.names,
                'sum_total_remaining_repay_loan': rpl,
                'sum_total_remaining_return_loan': rtl,
            }

    for k, c in client_dict.items():
        all_orders.append(
            (
                c['client_id'],
                c['client_names'],
                # c.names.upper(),
                round(c['sum_total_remaining_repay_loan'], 2),
                round(c['sum_total_remaining_return_loan']),
            )
        )

        summary_sum_total_remaining_repay_loan += c['sum_total_remaining_repay_loan']
        summary_sum_total_remaining_return_loan += c['sum_total_remaining_return_loan']


    t = Table([headings] + all_orders)
    t.setStyle(TableStyle(
        [
            ('GRID', (0, 0), (-1, -1), 1, colors.lightgrey),
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),  # header
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),  # header
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),  # header
            ('FONTSIZE', (0, 0), (-1, 0), 8),  # header
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),  # header
            ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),  # row
            ('FONTSIZE', (0, 1), (-1, -1), 8),  # row
            ('ALIGN', (2, 1), (-1, -1), 'RIGHT'),  # row
        ]
    ))

    labeled = [

        ['TOTAL PAGO FALTANTE: ', str(round(summary_sum_total_remaining_repay_loan, 2)), '', ''],
        ['TOTAL CANTIDAD FALTANTE:', str(round(summary_sum_total_remaining_return_loan, 0)), '', ''],

    ]
    t_labeled = Table(labeled)

    t_summary = 0
    Story.append(t)
    Story.append(t_labeled)
    doc.build(Story,
              onFirstPage=partial(all_account_order_list_first_page, custom_data=get_subsidiary_by_user(user_obj)),
              # onFirstPage=all_account_order_list_first_page,
              onLaterPages=all_account_order_list_later_pages)
    response = HttpResponse(content_type='application/pdf')
    # response['Content-Disposition'] = 'attachment; filename="Estado_de_cuentas[{}].pdf"'.format(date_now)
    response.write(buff.getvalue())
    buff.close()
    return response


def all_account_order_list_first_page(canvas, doc, custom_data):
    register_date_now = datetime.now()
    date_now = register_date_now.strftime("%d/%m/%y %H:%M")
    canvas.saveState()
    canvas.line(2.5 * cm, 26.75 * cm, 18.5 * cm, 26.75 * cm)
    canvas.line(2.5 * cm, 25.5 * cm, 18.5 * cm, 25.5 * cm)
    canvas.line(2.5 * cm, 25.4 * cm, 18.5 * cm, 25.4 * cm)
    canvas.setFont('Helvetica-Bold', 16)
    canvas.drawCentredString(210 * mm / 2.0, 297 * mm - 108, Title + str(custom_data.name))
    canvas.setFont('Times-Roman', 9)
    canvas.drawString(cm, 0.75 * cm, "Pagina 1 - %s" % pageinfo)
    canvas.drawString(16.5 * cm, 26.25 * cm, date_now)
    canvas.restoreState()


def all_account_order_list_later_pages(canvas, doc):
    canvas.saveState()
    canvas.setFont('Times-Roman', 9)
    canvas.drawString(cm, 0.75 * cm, "Pagina %d - %s" % (doc.page, pageinfo))
    canvas.restoreState()
