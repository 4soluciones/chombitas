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
from reportlab.rl_config import defaultPageSize
from functools import partial
from reportlab.lib.colors import PCMYKColor, PCMYKColorSep, Color, black, blue, red, pink, green
from .models import Product, Client, Order, OrderDetail, SubsidiaryStore, ProductStore, Kardex
from django.contrib.auth.models import User
from apps.hrm.views import get_subsidiary_by_user
from .views import get_context_kardex_glp, get_dict_orders, total_remaining_repay_loan, total_remaining_return_loan,\
    repay_loan, return_loan
from django.template import loader
from chombitas import settings
from datetime import datetime
from .format_dates import utc_to_local
from django.db.models import Sum
import io
import pdfkit
# Register Fonts
PAGE_HEIGHT = defaultPageSize[1]
PAGE_WIDTH = defaultPageSize[0]
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
            html = get_dict_orders(order_set, client_obj=client_obj, is_pdf=True,)
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

    subsidiary_obj = get_subsidiary_by_user(user_obj)
    # Title = Title + str(get_subsidiary_by_user(user_obj))
    summary_sum_total_remaining_repay_loan = 0
    summary_sum_total_remaining_return_loan = 0

    # for c in Client.objects.all().order_by('pk').values('id', 'names'):
    client_set = Order.objects.filter(subsidiary_store__subsidiary=subsidiary_obj).exclude(type='E').values(
        'client__id', 'client__names').distinct('client__id')
    # for c in Client.objects.filter(clientassociate__subsidiary=subsidiary_obj).order_by('names').values('id', 'names'):
    for c in client_set:
        sum_total_remaining_repay_loan = 0
        sum_total_remaining_return_loan = 0
        order_set = Order.objects.filter(client=c['client__id'], subsidiary_store__subsidiary=subsidiary_obj).exclude(
            type='E').values('id').order_by('id')
        # order_set = Order.objects.filter(client=c['id']).exclude(type='E').order_by('id')

        if order_set.count() > 0:

            a = a + 1
            for o in order_set:

            #     sum_total_remaining_repay_loan = sum_total_remaining_repay_loan + o.total_remaining_repay_loan()
            #     sum_total_remaining_return_loan = sum_total_remaining_return_loan + o.total_remaining_return_loan()
            # summary_sum_total_remaining_repay_loan = summary_sum_total_remaining_repay_loan + sum_total_remaining_repay_loan
            # summary_sum_total_remaining_return_loan = summary_sum_total_remaining_return_loan + sum_total_remaining_return_loan
                sum_total_remaining_repay_loan += total_remaining_repay_loan(o['id'])
                sum_total_remaining_return_loan += total_remaining_return_loan(o['id'])
            summary_sum_total_remaining_repay_loan += sum_total_remaining_repay_loan
            summary_sum_total_remaining_return_loan += sum_total_remaining_return_loan

        all_orders.append(
            (
                a,
                c['client__names'],

                # c.names.upper(),
                round(sum_total_remaining_repay_loan, 2),
                round(sum_total_remaining_return_loan),
            )
        )

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
    canvas.drawCentredString(PAGE_WIDTH/2.0, PAGE_HEIGHT-108, Title + str(custom_data.name))
    canvas.setFont('Times-Roman', 9)
    canvas.drawString(cm, 0.75 * cm, "Pagina 1 - %s" % pageinfo)
    canvas.drawString(16.5 * cm, 26.25 * cm, date_now)
    canvas.restoreState()

def all_account_order_list_later_pages(canvas, doc):

    canvas.saveState()
    canvas.setFont('Times-Roman', 9)
    canvas.drawString(cm, 0.75 * cm, "Pagina %d - %s" % (doc.page, pageinfo))
    canvas.restoreState()
