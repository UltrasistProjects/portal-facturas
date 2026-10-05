import { expect, type Page } from '@playwright/test';
import type { EjecucionHU } from './hu';
import { clicNavegando, texto } from './portal';

/** Escenario comun de las tres pantallas de Requisitos minimos: crear un tipo temporal, editarlo desde su fila,
 * cancelar y confirmar su eliminacion. `crear` llena y envia el formulario de alta de la pantalla con `nombre`. */
export async function escenarioEditarEliminar(
  hu: EjecucionHU,
  admin: Page,
  opciones: { url: string; nombre: string; avisoEditado: string; crear: (nombre: string) => Promise<void> },
): Promise<void> {
  const { url, nombre, avisoEditado, crear } = opciones;
  const editado = `${nombre} editado`;
  const fila = (texto: string) => admin.locator('.requirements-table tbody tr').filter({ has: admin.getByText(texto, { exact: true }) });

  await hu.escenario('Editar y eliminar un tipo desde su fila', async () => {
    await hu.paso(
      admin,
      `Crear el tipo temporal "${nombre}"`,
      'La fila del tipo muestra las acciones "Editar" y "Eliminar"; las filas de los tipos del sistema no las muestran.',
      async () => {
        await admin.goto(url);
        await crear(nombre);
        const acciones = fila(nombre).locator('.type-actions');
        await expect(acciones.getByRole('link', { name: 'Editar' })).toBeVisible();
        await expect(acciones.locator('summary', { hasText: 'Eliminar' })).toBeVisible();
        const sistema = await admin.locator('.requirements-table tbody tr').filter({ hasNot: admin.locator('.type-actions') }).count();
        await hu.captura(admin, 'acciones-editar-eliminar', `Fila de "${nombre}" con las acciones Editar y Eliminar.`, { enfocar: fila(nombre) });
        return `Fila "${nombre}" con Editar y Eliminar; ${sistema} filas del sistema sin acciones.`;
      },
    );
    await hu.paso(admin, `Pulsar "Editar" y renombrarlo a "${editado}"`, `Se abre su formulario de edición y, al guardar, el portal responde "${avisoEditado}".`, async () => {
      await clicNavegando(admin, fila(nombre).getByRole('link', { name: 'Editar' }));
      const formulario = admin.locator('details.admin-create[open]').filter({ hasText: nombre });
      await expect(formulario).toHaveCount(1);
      await formulario.locator('input[name=name]').fill(editado);
      await hu.captura(admin, 'formulario-edicion', 'Formulario de edición abierto desde la fila.', { enfocar: formulario });
      await clicNavegando(admin, formulario.getByRole('button', { name: 'Guardar cambios' }));
      await expect(admin.locator('.alert-success')).toHaveText(avisoEditado);
      await expect(fila(editado)).toHaveCount(1);
      return `Aviso "${await texto(admin, '.alert-success')}"; la fila ahora dice "${editado}".`;
    });
    await hu.paso(admin, 'Pulsar "Eliminar" y no confirmar', 'Aparece la confirmación con el nombre del tipo; al cerrarla el tipo sigue en la tabla.', async () => {
      const confirmar = fila(editado).locator('details.delete-confirm');
      await confirmar.locator('summary').click();
      await expect(confirmar).toContainText(`¿Eliminar «${editado}»?`);
      await hu.captura(admin, 'confirmacion-eliminar', 'Confirmación antes de eliminar.', { enfocar: confirmar });
      await confirmar.locator('summary').click();
      await admin.reload();
      await expect(fila(editado)).toHaveCount(1);
      return `Confirmación "¿Eliminar «${editado}»?" mostrada y cerrada; el tipo sigue listado.`;
    });
    await hu.paso(admin, 'Pulsar "Eliminar" y confirmar', 'El portal responde "Tipo eliminado" y el tipo desaparece de la pantalla.', async () => {
      const confirmar = fila(editado).locator('details.delete-confirm');
      await confirmar.locator('summary').click();
      await clicNavegando(admin, confirmar.getByRole('button', { name: 'Sí, eliminar' }));
      await expect(admin.locator('.alert-success')).toHaveText('Tipo eliminado');
      await expect(admin.getByText(editado, { exact: true })).toHaveCount(0);
      await hu.captura(admin, 'tipo-eliminado', 'Aviso "Tipo eliminado".');
      return `Aviso "${await texto(admin, '.alert-success')}"; "${editado}" ya no aparece.`;
    });
  });
}
