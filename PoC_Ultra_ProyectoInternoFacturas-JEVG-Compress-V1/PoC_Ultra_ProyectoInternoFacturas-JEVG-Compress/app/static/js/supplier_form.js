// Alta de proveedor. Sin JavaScript el formulario se envia igual y el servidor valida cada combinacion. Con
// JavaScript, un elemento con data-depends-on="<campo>" y data-applies-when="<valor> [<valor>...]" solo aplica
// mientras el selector <campo> del mismo formulario tenga uno de esos valores. Si no aplica, se oculta y sus controles
// se limpian y se deshabilitan: el navegador no los valida ni los envia. Si vuelve a aplicar, se muestra y sus
// controles con data-required vuelven a ser obligatorios. Si el formulario no tiene el selector (la edicion, donde el
// origen y el tipo de persona no cambian), el elemento queda como lo pinto el servidor.
document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("form").forEach((form) => {
    const rules = [...form.querySelectorAll("[data-depends-on]")]
      .map((element) => ({ element, parent: form.elements.namedItem(element.dataset.dependsOn) }))
      .filter(({ parent }) => parent instanceof HTMLSelectElement);
    if (!rules.length) {
      return;
    }
    const refresh = () => {
      rules.forEach(({ element, parent }) => {
        const applies = element.dataset.appliesWhen.split(" ").includes(parent.value);
        element.hidden = !applies;
        element.querySelectorAll("input, select, textarea").forEach((control) => {
          if (!applies) {
            clear(control);
          }
          control.disabled = !applies;
          control.required = applies && control.hasAttribute("data-required");
        });
      });
    };
    new Set(rules.map(({ parent }) => parent)).forEach((parent) => parent.addEventListener("change", refresh));
    refresh();
  });
});

function clear(control) {
  if (control.type === "checkbox" || control.type === "radio") {
    control.checked = false;
  } else {
    control.value = "";
  }
}
