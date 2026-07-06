import decimal
from django import template

register = template.Library()


@register.simple_tag(name='add')
def add(value1, value2):
    return value1 + value2


@register.filter
def divide(value, arg):
    try:
        return float(value) / float(arg)
    except (TypeError, ZeroDivisionError):
        return None


@register.filter
def differences(value1, value2):
    return float(value1) - float(value2)


@register.filter
def multiplication(value1, value2):
    return float(value1) * float(value2)


@register.filter(name='get')
def get(d, k):
    return d.get(k, None)


@register.filter(name='get_element')
def get_element(d, k):
    return d[k]


@register.filter(name='replace_round_separator')
def replace_round_separator(value):
    if value is not None and value != '':
        value = float(value)
        decimal_part = value - int(value)
        decimal_str = f"{decimal_part:.3f}"[2:]
        if int(decimal_str[2]) > 0:
            rounded_value = round(value, 3)
        else:
            rounded_value = round(decimal.Decimal(value), 2)
        formatted_value = '{:,.{}f}'.format(rounded_value, 3 if int(decimal_str[2]) > 0 else 2).replace(',', 'X').replace('.', ',').replace('X', '.')
        return formatted_value
    return value


@register.filter(name='format_amount_dot')
def format_amount_dot(value, decimals='2'):
    """Miles con coma y decimales con punto: 1,234.56"""
    if value is None or value == '':
        return '—'
    try:
        dec = int(decimals) if str(decimals).strip().isdigit() else 2
        val = float(value)
        return f'{val:,.{dec}f}'
    except (TypeError, ValueError):
        return value


@register.filter(name='format_tons')
def format_tons(value, decimals='3'):
    """Cantidad almacenada en KG → toneladas (T0) para mostrar."""
    if value is None or value == '':
        return '—'
    try:
        dec = int(decimals) if str(decimals).strip().isdigit() else 3
        val = float(value) / 1000.0
        return f'{val:,.{dec}f}'
    except (TypeError, ValueError):
        return value


@register.filter(name='format_amount')
def format_amount(value, decimals='2'):
    """Formato peruano: miles con punto y decimales con coma."""
    if value is None or value == '':
        return '—'
    try:
        dec = int(decimals) if str(decimals).strip().isdigit() else 2
        val = float(value)
        formatted = f'{val:,.{dec}f}'
        return formatted.replace(',', 'X').replace('.', ',').replace('X', '.')
    except (TypeError, ValueError):
        return value