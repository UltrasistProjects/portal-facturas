// Total del Invoice (ajustes-finales-configuracion): subtotal + impuestos, recalculado al capturar. Solo es una ayuda
// visual: el servidor lo vuelve a calcular con Decimal e ignora cualquier total enviado. La suma se hace en centavos
// enteros para no arrastrar errores de punto flotante.
(() => {
  const total = document.querySelector('[data-amount-total]');
  if (!total) return;
  const inputs = [...document.querySelectorAll('[data-amount]')];

  const cents = text => {
    const plain = text.replace(/[$,\s]/g, '');
    const match = /^(\d+)(?:\.(\d{1,2}))?$/.exec(plain);
    if (!match) return null;
    return BigInt(match[1]) * 100n + BigInt((match[2] || '').padEnd(2, '0'));
  };
  const format = value => {
    const whole = (value / 100n).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    return `${whole}.${(value % 100n).toString().padStart(2, '0')}`;
  };
  const update = () => {
    const values = inputs.map(input => cents(input.value));
    total.value = values.every(value => value !== null) ? format(values.reduce((a, b) => a + b, 0n)) : '';
  };

  inputs.forEach(input => input.addEventListener('input', update));
  update();
})();
