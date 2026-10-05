// Activacion del contrato (HU-22). El formulario trae su texto de confirmacion en data-confirm y se confirma en un
// modal de la pagina. Sin JavaScript el formulario se envia igual, sin confirmacion. El texto se pinta con textContent.
(() => {
  const form = document.querySelector('#activate-form');
  if (!form) return;
  const accept = document.querySelector('#activate-confirm-accept');
  const modal = new bootstrap.Modal(document.querySelector('#activate-confirm'));
  let confirmed = false;

  form.addEventListener('submit', event => {
    if (confirmed) return;
    event.preventDefault();
    document.querySelector('#activate-confirm-text').textContent = form.dataset.confirm;
    modal.show();
  });
  accept.addEventListener('click', () => {
    confirmed = true;
    accept.disabled = true;
    form.submit();
  });
})();
