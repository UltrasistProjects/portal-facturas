// Autorizacion de proveedores (HU-02). En el listado agrega "seleccionar todos", el contador y la confirmacion; en el
// expediente de un proveedor (HU-21) el formulario trae su texto de confirmacion en data-confirm. Sin JavaScript el
// formulario se envia igual, sin confirmacion. Los textos se pintan siempre con textContent.
(() => {
  const form = document.querySelector('#authorize-form');
  if (!form) return;
  const text = document.querySelector('#authorize-confirm-text');
  const accept = document.querySelector('#authorize-confirm-accept');
  const modal = new bootstrap.Modal(document.querySelector('#authorize-confirm'));
  let confirmed = false;

  function confirmWith(message) {
    text.textContent = message;
    modal.show();
  }

  function setupSelection() {
    const all = document.querySelector('#authorize-all');
    const count = document.querySelector('#authorize-count');
    const submit = document.querySelector('#authorize-submit');
    const checks = () => [...form.querySelectorAll('input.authorize-check')];
    const selected = () => checks().filter(check => check.checked).length;

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
    refresh();
    return () => {
      const chosen = selected();
      if (chosen === 0) return null;
      return chosen === 1
        ? 'Se autorizará 1 proveedor y se le enviará su usuario y contraseña temporal por correo.'
        : `Se autorizarán ${chosen} proveedores y se enviará a cada uno su usuario y contraseña temporal por correo.`;
    };
  }

  const single = form.dataset.confirm;
  const message = single === undefined ? setupSelection() : () => single;
  form.addEventListener('submit', event => {
    if (confirmed) return;
    event.preventDefault();
    const confirmation = message();
    if (confirmation) confirmWith(confirmation);
  });
  accept.addEventListener('click', () => {
    confirmed = true;
    accept.disabled = true;
    form.submit();
  });
})();
