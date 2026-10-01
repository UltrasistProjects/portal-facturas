// Panel de decision del PMO (HU-20). Sin JavaScript el formulario funciona igual: el campo de observaciones queda
// visible y el servidor valida. Con JavaScript, el campo aparece al elegir Rechazar u Observaciones (RN-HU20-01) y
// Autorizar pide confirmacion en un modal. Al aceptar se vuelve a pulsar el mismo boton: el navegador envia su
// decision y valida igual que cuando se confirmaba con window.confirm.
document.addEventListener("DOMContentLoaded", () => {
  const form = document.querySelector(".decision-form");
  if (!form) {
    return;
  }
  const field = form.querySelector(".observations-field");
  const observations = form.querySelector("textarea[name=comments]");
  const modalElement = document.querySelector("#decision-confirm");
  const modal = new bootstrap.Modal(modalElement);
  const text = document.querySelector("#decision-confirm-text");
  const accept = document.querySelector("#decision-confirm-accept");
  let pending = null;
  let confirmed = false;
  field.hidden = true;
  form.querySelectorAll("button[name=decision]").forEach((button) => {
    button.addEventListener("click", (event) => {
      if (button.hasAttribute("data-needs-observations")) {
        observations.required = true;
        if (field.hidden) {
          // Primer clic: se despliega el campo para capturar la causa, sin enviar.
          field.hidden = false;
          observations.focus();
          event.preventDefault();
        }
        return;
      }
      observations.required = false;
      // Si las observaciones mostraban "Capture las observaciones.", el mensaje ya no aplica (form_validation.js).
      window.portalValidation?.refresh(form);
      if (button.dataset.confirm && !confirmed) {
        event.preventDefault();
        pending = button;
        text.textContent = button.dataset.confirm;
        modal.show();
      }
      confirmed = false;
    });
  });
  modalElement.addEventListener("shown.bs.modal", () => accept.focus());
  accept.addEventListener("click", () => {
    confirmed = true;
    modal.hide();
  });
  // Cancelar, cerrar o Esc: no se envia nada y el foco vuelve al boton.
  modalElement.addEventListener("hidden.bs.modal", () => {
    const button = pending;
    pending = null;
    if (!button) {
      return;
    }
    if (confirmed) {
      button.click();
    } else {
      button.focus();
    }
  });
});
