# from django.db import connection


def total_remaining_repay_loan(order_detail_set=None):
    response = 0

    for d in order_detail_set:

        multiply = d.quantity_sold * d.price_unit

        if d.unit.name == 'G' or d.unit.name == 'GBC':
            loan_payment_set = d.loanpayment_set.all()
            response += (multiply - repay_loan(loan_payment_set))

    return response


def total_remaining_return_loan(order_detail_set=None):
    response = 0
    product__array = [1, 12, 2, 3]
    for d in order_detail_set:
        if d.unit.name == 'B' and d.product.id in product__array:
            loan_payment_set = d.loanpayment_set.all()
            response += (d.quantity_sold - return_loan(loan_payment_set))
    return response


def repay_loan(loan_payment_set=None):
    response = 0

    for lp in loan_payment_set:

        if lp.quantity == 0:
            response += lp.price

    return response


def return_loan(loan_payment_set=None):
    response = 0

    for lp in loan_payment_set:

        response += lp.quantity

    return response


def total_repay_loan(order_detail_set=None):
    response = 0
    for d in order_detail_set:
        loan_payment_set = d.loanpayment_set.all()
        response = response + repay_loan(loan_payment_set=loan_payment_set)

    return response


def total_repay_loan_with_vouchers(order_detail_set=None):
    response = 0
    for d in order_detail_set:
        loan_payment_set = d.loanpayment_set.all()
        response = response + repay_loan_with_vouchers(loan_payment_set)
    return response


def repay_loan_with_vouchers(loan_payment_set=None):
    response = 0
    for lp in loan_payment_set:
        if lp.price > 0:
            transaction_payment_set = lp.transactionpayment_set.all()
            for t in transaction_payment_set:
                if t.type == 'F':
                    response = response + t.number_of_vouchers
    return response


def total_return_loan(order_detail_set=None):
    response = 0
    for d in order_detail_set:
        loan_payment_set = d.loanpayment_set.all()
        response = response + return_loan(loan_payment_set)
    return response


def total_remaining_repay_loan_ball(order_detail_set=None):
    response = 0
    for d in order_detail_set:
        if d.unit.name == 'B':
            multiply = d.quantity_sold * d.price_unit
            loan_payment_set = d.loanpayment_set.all()
            response = response + (multiply - repay_loan_ball(loan_payment_set))
    return response


def repay_loan_ball(loan_payment_set=None):
    response = 0
    for lp in loan_payment_set:
        response = response + (lp.quantity * (lp.price + lp.discount))
    return response


def total_ball_changes(order_detail_set=None):
    response = 0
    for d in order_detail_set:
        ballchange_set = d.ballchange_set.all()
        response = response + ball_changes(ballchange_set)
    return response


def ball_changes(ballchange_set=None):
    response = 0
    for ball in ballchange_set:
        response = response + ball.quantity
    return response


def total_cash_flow_spending(cashflow_set=None):
    response = 0
    for cf in cashflow_set:
        response = response + cf.total
    return response


def get_cash_flow(order=None, transactionpayment=None):
    response = None
    if transactionpayment.type == 'D':
        for cf in order.cashflow_set.all():
            if cf.type == 'D':
                response = cf
                break
    return response




