document.querySelectorAll('[data-demo]').forEach(button => button.addEventListener('click', () => {
  const [email, password] = button.dataset.demo.split('|');
  document.querySelector('[name=email]').value = email;
  document.querySelector('[name=password]').value = password;
}));
document.querySelectorAll('input[type=file]').forEach(input => input.addEventListener('change', () => {
  const label = input.closest('label')?.querySelector('.file-name');
  if (label) label.textContent = input.files[0]?.name || 'Ningun archivo seleccionado';
}));
const supplier = document.querySelector('#supplier');
const contract = document.querySelector('#contract');
function syncContract() {
  if (!supplier || !contract) return;
  [...contract.options].forEach(o => o.hidden = o.dataset.supplier !== supplier.value);
  const visible = [...contract.options].find(o => !o.hidden); if (visible) contract.value = visible.value;
  syncProject();
}
function syncProject() { const o = contract?.selectedOptions[0]; if (o) { document.querySelector('#project').value = o.dataset.project || ''; document.querySelector('#leader').value = o.dataset.leader || ''; } }
supplier?.addEventListener('change', syncContract); contract?.addEventListener('change', syncProject); syncContract();

