document.querySelectorAll('input[type=file]').forEach(input => input.addEventListener('change', () => {
  const label = input.closest('label')?.querySelector('.file-name');
  if (label) label.textContent = input.files[0]?.name || 'Ningun archivo seleccionado';
}));
// Alta de factura: el servidor solo envia los contratos del proveedor del usuario; se copian proyecto y lider.
const contract = document.querySelector('#contract');
function syncProject() { const o = contract?.selectedOptions[0]; if (o) { document.querySelector('#project').value = o.dataset.project || ''; document.querySelector('#leader').value = o.dataset.leader || ''; } }
contract?.addEventListener('change', syncProject); syncProject();

