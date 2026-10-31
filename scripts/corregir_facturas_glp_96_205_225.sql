-- Correccion de tres facturas GLP segun el documento fisico.
-- El 96 y el 205 luego entran al kardex. El 225 se corrige aqui y no entra
-- al kardex porque no tiene guia de ingreso.
-- Montos en dolares de la factura. Soles = dolares x tipo de cambio.

BEGIN;

UPDATE buys_requirementdetail_buys AS d
SET quantity = 58844.00,
    price = 0.59414044,
    amount = 34961.60,
    change_coin = 3.743,
    price_pen = 0.59414044 * 3.743,
    amount_pen = 34961.60 * 3.743
FROM buys_requirement_buys AS r
WHERE d.requirement_buys_id = r.id
  AND r.id = 96
  AND r.invoice = 'F024-50067';

UPDATE buys_requirementdetail_buys AS d
SET quantity = 94000.00,
    price = 0.78235787,
    amount = 73541.64,
    change_coin = 3.644,
    price_pen = 0.78235787 * 3.644,
    amount_pen = 73541.64 * 3.644
FROM buys_requirement_buys AS r
WHERE d.requirement_buys_id = r.id
  AND r.id = 205
  AND r.invoice = 'F045-16740';

UPDATE buys_requirementdetail_buys AS d
SET quantity = 94000.00,
    price = 0.76701798,
    amount = 72099.69,
    change_coin = 3.646,
    price_pen = 0.76701798 * 3.646,
    amount_pen = 72099.69 * 3.646
FROM buys_requirement_buys AS r
WHERE d.requirement_buys_id = r.id
  AND r.id = 225
  AND r.invoice = 'F030-12971';

COMMIT;
