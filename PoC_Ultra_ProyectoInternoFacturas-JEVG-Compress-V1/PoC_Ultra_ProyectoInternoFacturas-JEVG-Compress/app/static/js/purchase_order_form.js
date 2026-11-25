// Alta y edicion de ordenes de compra (Ferromex). Agrega y quita partidas a partir de la plantilla #po-item-template y
// propone el total (suma de cantidad x precio neto) y los impuestos (IVA 16 %). En el alta los montos se recalculan
// mientras el usuario no los escriba (data-auto="1"); en la edicion solo con "Calcular con las partidas". Sin
// JavaScript el formulario se envia igual con las partidas que ya muestra.
(() => {
  const form = document.querySelector('#po-form');
  if (!form) return;
  const rows = form.querySelector('#po-item-rows');
  const template = form.querySelector('#po-item-template');
  const total = form.querySelector('#po-total');
  const taxes = form.querySelector('#po-taxes');
  const IVA = 0.16;

  function refreshRemoveButtons() {
    const buttons = rows.querySelectorAll('.po-remove');
    buttons.forEach(button => { button.disabled = buttons.length === 1; });
  }

  function itemsSubtotal() {
    let sum = 0;
    rows.querySelectorAll('.po-item').forEach(row => {
      const quantity = parseFloat(row.querySelector('.po-quantity')?.value);
      const price = parseFloat(row.querySelector('.po-price')?.value);
      if (Number.isFinite(quantity) && Number.isFinite(price)) sum += quantity * price;
    });
    return Math.round(sum * 100) / 100;
  }

  function calculate(force) {
    const subtotal = itemsSubtotal();
    if (subtotal <= 0) return;
    if (force || total.dataset.auto === '1') total.value = subtotal.toFixed(2);
    if (force || taxes.dataset.auto === '1') taxes.value = (Math.round(subtotal * IVA * 100) / 100).toFixed(2);
  }

  form.querySelector('#po-add-item').addEventListener('click', () => {
    const row = template.content.firstElementChild.cloneNode(true);
    rows.appendChild(row);
    refreshRemoveButtons();
    row.querySelector('input, select')?.focus();
  });

  rows.addEventListener('click', event => {
    const button = event.target.closest('.po-remove');
    if (!button || rows.querySelectorAll('.po-item').length === 1) return;
    button.closest('.po-item').remove();
    refreshRemoveButtons();
    calculate(false);
  });

  rows.addEventListener('input', event => {
    if (event.target.matches('.po-quantity, .po-price')) calculate(false);
  });

  [total, taxes].forEach(field => {
    field.addEventListener('input', () => { field.dataset.auto = '0'; });
  });

  form.querySelector('#po-calculate').addEventListener('click', () => calculate(true));
  refreshRemoveButtons();
})();
