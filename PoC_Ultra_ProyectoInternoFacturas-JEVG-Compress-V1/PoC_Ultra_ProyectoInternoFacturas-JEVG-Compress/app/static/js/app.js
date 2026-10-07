document.querySelectorAll('input[type=file]').forEach(input => input.addEventListener('change', () => {
  const label = input.closest('label')?.querySelector('.file-name');
  if (label) label.textContent = input.files[0]?.name || 'Ningun archivo seleccionado';
}));
// Alta de factura: el servidor solo envia los contratos del proveedor del usuario; se copian proyecto y lider.
const contract = document.querySelector('#contract');
function syncProject() { const o = contract?.selectedOptions[0]; if (o) { document.querySelector('#project').value = o.dataset.project || ''; document.querySelector('#leader').value = o.dataset.leader || ''; } }
contract?.addEventListener('change', syncProject); syncProject();

// Doble envio: varios POST responden despues de mandar su correo (la cancelacion tarda segundos) y un segundo clic en
// ese lapso repetiria la operacion, que el servidor ya encuentra hecha (409). Tras el primer envio el formulario ignora
// los siguientes y deshabilita sus botones en la siguiente vuelta: deshabilitarlos dentro del evento submit quitaria
// del envio el name/value del boton pulsado (la decision del PMO). El evento solo llega si el formulario es valido; los
// que su script envia por fetch (preventDefault) no se bloquean. Al volver con Atras (bfcache) se rehabilitan.
document.addEventListener('submit', event => {
  const form = event.target;
  if (event.defaultPrevented || form.method !== 'post') return;
  if (form.dataset.submitting) {
    event.preventDefault();
    return;
  }
  form.dataset.submitting = 'true';
  setTimeout(() => [...form.elements].filter(el => el.matches('button, input[type=submit]') && !el.disabled).forEach(el => {
    el.disabled = true;
    el.dataset.submitLocked = 'true';
  }));
});
window.addEventListener('pageshow', event => {
  if (!event.persisted) return;
  document.querySelectorAll('form[data-submitting]').forEach(form => delete form.dataset.submitting);
  document.querySelectorAll('[data-submit-locked]').forEach(el => {
    el.disabled = false;
    delete el.dataset.submitLocked;
  });
});

// Vista previa del correo (HU-05): el iframe toma la altura del correo. Sin JavaScript conserva la de app.css.
document.querySelectorAll('iframe.email-preview').forEach(frame => {
  const fit = () => { const body = frame.contentDocument?.body; if (body?.firstElementChild) frame.style.height = `${body.scrollHeight + 2}px`; };
  frame.addEventListener('load', fit); window.addEventListener('resize', fit); fit();
});
