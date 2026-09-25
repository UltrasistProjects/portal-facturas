// Autorizacion masiva de proveedores (HU-02). Agrega "seleccionar todos", el contador y la confirmacion: sin
// JavaScript el formulario se envia igual, sin confirmacion. Los textos se pintan siempre con textContent.
(() => {
  const form = document.querySelector('#authorize-form');
  if (!form) return;
  const all = document.querySelector('#authorize-all');
  const count = document.querySelector('#authorize-count');
  const submit = document.querySelector('#authorize-submit');
  const text = document.querySelector('#authorize-confirm-text');
  const accept = document.querySelector('#authorize-confirm-accept');
  const modal = new bootstrap.Modal(document.querySelector('#authorize-confirm'));
  const checks = () => [...form.querySelectorAll('input.authorize-check')];
  const selected = () => checks().filter(check => check.checked).length;
  let confirmed = false;

  function refresh() {
    const total = checks().length;
    const chosen = selected();
    count.textContent = chosen === 1 ? '1 seleccionado' : `${chosen} seleccionados`;
    submit.disabled = chosen === 0;
    all.disabled = total === 0;
    all.checked = total > 0 && chosen === total;
    all.indeterminate = chosen > 0 && chosen < total;
  }

  all.addEventListener('change', () => {
    checks().forEach(check => { check.checked = all.checked; });
    refresh();
  });
  form.addEventListener('change', event => {
    if (event.target.classList.contains('authorize-check')) refresh();
  });
  form.addEventListener('submit', event => {
    if (confirmed) return;
    event.preventDefault();
    const chosen = selected();
    if (chosen === 0) return;
    text.textContent = chosen === 1
      ? 'Se autorizará 1 proveedor y se le enviará su usuario y contraseña temporal por correo.'
      : `Se autorizarán ${chosen} proveedores y se enviará a cada uno su usuario y contraseña temporal por correo.`;
    modal.show();
  });
  accept.addEventListener('click', () => {
    confirmed = true;
    accept.disabled = true;
    form.submit();
  });
  refresh();
})();
