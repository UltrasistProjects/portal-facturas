// Errores de validacion junto al campo (interfaz-sin-dialogos-nativos). El navegador sigue evaluando las reglas que
// declara cada campo (required, pattern, minlength, maxlength, min, max, step y type) y bloqueando el envio; este
// script solo cambia como se muestran. Cancela el evento invalid, asi el navegador no pinta su burbuja ni mueve el
// foco pero aborta el envio igual, y escribe el mensaje en espanol debajo del campo con las clases de Bootstrap.
// Fuera del envio solo lee control.validity: checkValidity() dispararia invalid. Sin JavaScript queda la validacion
// nativa. Los textos se pintan siempre con textContent.
(() => {
  const CONTROLS = 'input, select, textarea';
  const feedbacks = new WeakMap();
  let counter = 0;
  let firstInvalid = null;

  function formatDate(value) {
    const [year, month, day] = value.split('-');
    return `${day}/${month}/${year}`;
  }

  // Decimales que admite un step de la forma 0.0...1 (".01" -> 2); null para cualquier otro step.
  function decimals(step) {
    const match = /^0*\.(0*)1$/.exec(step || '');
    return match ? match[1].length + 1 : null;
  }

  function message(control) {
    const validity = control.validity;
    const custom = control.dataset;
    const type = control.type;
    // Primero la entrada incompleta: un numero o una fecha a medias tambien dejan el valor vacio (valueMissing).
    if (validity.badInput && type === 'number') return 'Escriba un número válido.';
    if (validity.badInput && type === 'date') return 'Escriba una fecha válida.';
    if (validity.valueMissing) {
      if (custom.errorRequired) return custom.errorRequired;
      if (type === 'checkbox' || type === 'radio') return 'Marque la casilla para continuar.';
      if (type === 'file') return 'Seleccione un archivo.';
      if (control.tagName === 'SELECT') return 'Seleccione una opción.';
      return 'Este campo es obligatorio.';
    }
    if (validity.typeMismatch && type === 'email') {
      return 'Escriba un correo electrónico válido, por ejemplo nombre@empresa.com.';
    }
    if (validity.patternMismatch && custom.errorPattern) return custom.errorPattern;
    if (validity.tooShort) return `Escriba al menos ${control.minLength} caracteres.`;
    if (validity.tooLong) return `Escriba como máximo ${control.maxLength} caracteres.`;
    if (validity.rangeUnderflow) {
      return type === 'date'
        ? `La fecha no puede ser anterior al ${formatDate(control.min)}.`
        : `El valor mínimo es ${control.min}.`;
    }
    const places = validity.stepMismatch && decimals(control.getAttribute('step'));
    if (places) return `Use como máximo ${places} decimales.`;
    return control.validationMessage;
  }

  // Un campo dentro de un label (la zona de arrastre, con el input de archivo oculto) se senala en el label.
  function box(control) {
    return control.type === 'checkbox' || control.type === 'radio' ? null : control.closest('label');
  }

  function place(control, feedback) {
    const check = control.closest('.form-check');
    if (check && (control.type === 'checkbox' || control.type === 'radio')) {
      check.append(feedback);
    } else {
      (box(control) || control).after(feedback);
    }
  }

  function mark(control, id, invalid) {
    control.classList.toggle('is-invalid', invalid);
    box(control)?.classList.toggle('is-invalid', invalid);
    const ids = (control.getAttribute('aria-describedby') || '').split(' ').filter(item => item && item !== id);
    if (invalid) {
      ids.push(id);
      control.setAttribute('aria-invalid', 'true');
    } else {
      control.removeAttribute('aria-invalid');
    }
    if (ids.length) {
      control.setAttribute('aria-describedby', ids.join(' '));
    } else {
      control.removeAttribute('aria-describedby');
    }
  }

  function show(control) {
    let feedback = feedbacks.get(control);
    if (!feedback) {
      feedback = document.createElement('div');
      feedback.className = 'invalid-feedback';
      feedback.id = control.id ? `${control.id}-error` : `form-error-${++counter}`;
      place(control, feedback);
      feedbacks.set(control, feedback);
    }
    feedback.textContent = message(control);
    mark(control, feedback.id, true);
  }

  function hide(control) {
    const feedback = feedbacks.get(control);
    if (!feedback) return;
    feedback.textContent = '';
    mark(control, feedback.id, false);
  }

  function shows(control) {
    return feedbacks.has(control) && control.classList.contains('is-invalid');
  }

  function update(control) {
    if (control.willValidate && !control.validity.valid) {
      show(control);
    } else {
      hide(control);
    }
  }

  // Los campos del formulario que muestran error: uno que otro script deshabilita o deja de exigir pierde su mensaje.
  function refresh(form) {
    [...form.elements].filter(shows).forEach(update);
  }

  function reveal(control) {
    if (control.getClientRects().length) {
      control.focus();
    } else {
      (box(control) || control.closest('.field') || control.parentElement).scrollIntoView({block: 'center'});
    }
  }

  // Envio con errores: el navegador dispara invalid en cada campo, en orden, antes de abortar el envio.
  document.addEventListener('invalid', event => {
    const control = event.target;
    if (!(control instanceof Element) || !control.matches(CONTROLS)) return;
    event.preventDefault();
    show(control);
    if (!firstInvalid) {
      firstInvalid = control;
      setTimeout(() => {
        reveal(firstInvalid);
        firstInvalid = null;
      });
    }
  }, true);

  // change: el usuario confirmo un valor (salio del campo cambiado o eligio una opcion o archivo).
  // input: solo actualiza los campos que ya muestran error, para que el mensaje desaparezca al corregir.
  function edited(event, committed) {
    const control = event.target;
    if (!(control instanceof Element) || !control.matches(CONTROLS)) return;
    if (committed || shows(control)) update(control);
    if (control.form) refresh(control.form);
  }

  document.addEventListener('change', event => edited(event, true));
  document.addEventListener('input', event => edited(event, false));

  window.portalValidation = {refresh};
})();
