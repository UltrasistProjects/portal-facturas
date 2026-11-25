// Programar pago (Ferromex). La ventana se abre con los atributos data-bs-* de Bootstrap; este script solo la vuelve a
// abrir cuando el servidor devolvio un error (data-open) y copia el JSON de la solicitud al portapapeles.
(() => {
  document.querySelectorAll('.payment-modal[data-open]').forEach(element => {
    bootstrap.Modal.getOrCreateInstance(element).show();
  });

  document.querySelectorAll('[data-copy-target]').forEach(button => {
    const label = button.querySelector('span');
    button.addEventListener('click', async () => {
      const source = document.querySelector(button.dataset.copyTarget);
      if (!source || !navigator.clipboard) return;
      try {
        await navigator.clipboard.writeText(source.textContent);
        if (label) label.textContent = 'Copiado';
      } catch {
        if (label) label.textContent = 'No se pudo copiar';
      }
      setTimeout(() => { if (label) label.textContent = 'Copiar'; }, 2000);
    });
  });
})();
