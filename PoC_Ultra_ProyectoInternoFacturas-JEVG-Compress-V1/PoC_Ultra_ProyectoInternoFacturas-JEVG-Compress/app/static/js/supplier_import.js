// Carga masiva de proveedores (HU-01). El archivo se queda en el navegador: si hay filas con errores y el
// Administrador elige agregar las validas, se reenvia el mismo archivo en modo "partial" con el SHA-256 que devolvio
// la validacion, y el servidor lo valida de nuevo. Los datos del archivo se pintan siempre con textContent.
(() => {
  const form = document.querySelector('#supplier-import-form');
  if (!form) return;
  const submit = document.querySelector('#supplier-import-submit');
  const message = document.querySelector('#supplier-import-message');
  const summary = document.querySelector('#supplier-import-summary');
  const summaryText = document.querySelector('#supplier-import-summary-text');
  const skipped = document.querySelector('#supplier-import-skipped');
  const errors = document.querySelector('#supplier-import-errors');
  const errorsTitle = document.querySelector('#supplier-import-errors-title');
  const hiddenErrors = document.querySelector('#supplier-import-hidden');
  const modalElement = document.querySelector('#supplier-import-confirm');
  const modal = new bootstrap.Modal(modalElement);
  const fixButton = document.querySelector('#supplier-import-fix');
  const partialButton = document.querySelector('#supplier-import-partial');
  let pending = null;
  let partialChosen = false;

  function reset() {
    message.hidden = true;
    summary.hidden = true;
    errors.hidden = true;
  }

  function showMessage(text, kind) {
    message.className = `alert alert-${kind}`;
    message.textContent = text;
    message.hidden = false;
  }

  function showErrors(data, title) {
    const items = data.errors.map(error => {
      const item = document.createElement('li');
      item.textContent = error.text;
      return item;
    });
    errors.querySelector('ul').replaceChildren(...items);
    errorsTitle.textContent = title;
    hiddenErrors.textContent = `y ${data.hidden_errors} errores más`;
    hiddenErrors.hidden = !data.hidden_errors;
    errors.hidden = items.length === 0;
  }

  function showSummary(data) {
    summaryText.textContent = data.summary;
    const rows = data.skipped.map(entry => {
      const row = document.createElement('tr');
      [entry.row, entry.identifier, entry.business_name].forEach(value => {
        const cell = document.createElement('td');
        cell.textContent = value;
        row.append(cell);
      });
      return row;
    });
    skipped.querySelector('tbody').replaceChildren(...rows);
    skipped.hidden = rows.length === 0;
    summary.hidden = false;
    if (data.invalid) showErrors(data, 'Filas no registradas por errores');
  }

  async function send(mode, sha256) {
    reset();  // los resultados anteriores no deben quedar a la vista mientras se procesa otro envio
    const body = new FormData(form);
    body.set('mode', mode);
    if (sha256) body.set('expected_sha256', sha256);
    submit.disabled = true;
    try {
      const response = await fetch(form.action, {
        method: 'POST', body, headers: {Accept: 'application/json'}, credentials: 'same-origin',
      });
      if (!(response.headers.get('content-type') || '').includes('application/json')) {
        return {status: 0, data: {detail: 'No se pudo completar la carga. Recargue la página e intente de nuevo.'}};
      }
      return {status: response.status, data: await response.json()};
    } catch {
      return {status: 0, data: {detail: 'No se pudo conectar con el servidor. Intente de nuevo.'}};
    } finally {
      submit.disabled = false;
    }
  }

  function handle({status, data}) {
    reset();
    if (status === 200) {
      showSummary(data);
    } else if (status === 400 && Array.isArray(data.errors)) {
      if (data.registrable > 0) {
        pending = data;
        partialChosen = false;
        modal.show();
      } else {
        showMessage(data.detail, 'danger');
        showErrors(data, 'Filas con errores');
      }
    } else {
      showMessage(data.detail || 'No se pudo completar la carga.', 'danger');
    }
  }

  form.addEventListener('submit', async event => {
    event.preventDefault();
    handle(await send('strict'));
  });
  modalElement.addEventListener('shown.bs.modal', () => fixButton.focus());
  partialButton.addEventListener('click', () => {
    partialChosen = true;
    modal.hide();
  });
  // Corregir primero, cerrar la ventana o pulsar Esc: el catalogo no cambia y se muestran los errores.
  modalElement.addEventListener('hidden.bs.modal', async () => {
    const data = pending;
    pending = null;
    if (!data) return;
    if (partialChosen) {
      handle(await send('partial', data.sha256));
    } else {
      showMessage(data.detail, 'danger');
      showErrors(data, 'Filas con errores');
    }
  });
})();
