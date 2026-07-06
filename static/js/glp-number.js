/**
 * Formato numérico GLP: miles con coma, decimales con punto (1,234.567)
 */
(function (window) {
    'use strict';

    const TON_TO_KG = 1000;

    function fmt(v, d) {
        const n = parseFloat(v);
        if (isNaN(n)) {
            return d === 3 ? '0.000' : '0.00';
        }
        const parts = n.toFixed(d).split('.');
        parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',');
        return parts.join('.');
    }

    function parse(s) {
        if (!s && s !== 0) return '0';
        return String(s).trim().replace(/\s/g, '').replace(/,/g, '');
    }

    function toKg(tons) {
        return parseFloat(parse(tons)) * TON_TO_KG;
    }

    window.GlpNumber = {
        fmt: fmt,
        parse: parse,
        toKg: toKg,
        TON_TO_KG: TON_TO_KG,
    };
})(window);
