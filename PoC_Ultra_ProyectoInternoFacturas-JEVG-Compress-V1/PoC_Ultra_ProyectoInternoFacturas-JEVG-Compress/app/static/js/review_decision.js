// Panel de decision del PMO (HU-20). Sin JavaScript el formulario funciona igual: el campo de observaciones queda
// visible y el servidor valida. Con JavaScript, el campo aparece al elegir Rechazar u Observaciones (RN-HU20-01) y
// Autorizar pide confirmacion.
document.addEventListener("DOMContentLoaded", () => {
  const form = document.querySelector(".decision-form");
  if (!form) {
    return;
  }
  const field = form.querySelector(".observations-field");
  const observations = form.querySelector("textarea[name=comments]");
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
      if (button.dataset.confirm && !window.confirm(button.dataset.confirm)) {
        event.preventDefault();
      }
    });
  });
});
