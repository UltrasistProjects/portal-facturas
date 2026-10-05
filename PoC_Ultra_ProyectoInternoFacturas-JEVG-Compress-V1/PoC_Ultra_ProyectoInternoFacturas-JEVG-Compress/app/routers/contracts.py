from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session, contains_eager, selectinload

from app.core.constants import CONTRACT_STATUS_LABELS, ContractStatus, Role
from app.core.database import get_db
from app.core.errors import BusinessRuleError, InvalidInputError
from app.core.security import require_roles, validate_csrf
from app.models import Contract, ContractAmendment, Document, Supplier
from app.repositories.pagination import back_to, list_query, paginate, search
from app.routers.common import templates
from app.schemas import ContractAmendmentCreate, ContractCreate, validation_message
from app.services import contract_requirements_service as requirements
from app.services.audit_service import audit
from app.services.contract_service import amend_authorized_amount
from app.services.file_service import LocalFileStorage, log_upload, safe_download_name

router = APIRouter(prefix="/contracts")


CONTRACTS_URL = "/contracts"
CONTRACT_NOTICES = {"created": "Contrato creado"}
CONTRACT_DETAIL_NOTICES = {
    "created": "Contrato creado. Cargue sus requisitos para activarlo.",
    "activated": "Contrato activado",
    "uploaded": "Documento guardado",
}


@router.get("")
def list_contracts(
    request: Request,
    q: str = "",
    page: int = 1,
    ok: str = "",
    db: Session = Depends(get_db),
    user=Depends(require_roles(Role.PMO, Role.ADMINISTRADOR)),
):
    return _contracts_page(request, db, user, q=q, page=page, notice=CONTRACT_NOTICES.get(ok))


def _contracts_page(
    request: Request,
    db: Session,
    user,
    error: str | None = None,
    status_code: int = 200,
    q: str = "",
    page: int = 1,
    notice: str | None = None,
):
    # Del mas reciente al mas antiguo, con busqueda y paginacion en SQL (listados-paginados). El proveedor llega en
    # el mismo JOIN de la busqueda; las enmiendas de la pagina, en una consulta; los requisitos pendientes de la
    # pagina, en dos (HU-22).
    q = q.strip()
    stmt = (
        select(Contract)
        .join(Contract.supplier)
        .options(
            contains_eager(Contract.supplier),
            selectinload(Contract.amendments).selectinload(ContractAmendment.author),
        )
        .order_by(Contract.id.desc())
    )
    result = paginate(db, search(stmt, q, Contract.project_name, Supplier.business_name), page)
    context = {
        "user": user,
        "contracts": result.items,
        "pending": requirements.pending_requirements(db, result.items),
        "status_labels": CONTRACT_STATUS_LABELS,
        "page": result,
        "q": q,
        "base_query": list_query(q=q),
        "notice": notice,
        "suppliers": list(db.scalars(select(Supplier).order_by(Supplier.business_name))),
        "error": error,
    }
    return templates.TemplateResponse(request, "contracts/list.html", context, status_code=status_code)


@router.post("")
async def create_contract(
    request: Request,
    supplier_id: int = Form(...),
    project_name: str = Form(...),
    project_leader: str = Form(...),
    authorized_technology: str = Form(...),
    authorized_amount: str = Form(...),
    currency: str = Form("MXN"),
    start_date: str = Form(...),
    end_date: str = Form(...),
    db: Session = Depends(get_db),
    user=Depends(require_roles(Role.ADMINISTRADOR)),
):
    await validate_csrf(request)
    try:
        data = ContractCreate(
            supplier_id=supplier_id,
            project_name=project_name,
            project_leader=project_leader,
            authorized_technology=authorized_technology,
            authorized_amount=authorized_amount,
            currency=currency,
            start_date=start_date,
            end_date=end_date,
        )
    except ValidationError as exc:
        return _contracts_page(request, db, user, validation_message(exc), 400)
    if db.get(Supplier, data.supplier_id) is None:
        return _contracts_page(request, db, user, "Proveedor inexistente.", 400)
    # Nace Registrado: no se factura contra el hasta activarlo con sus requisitos completos (HU-22).
    contract = Contract(**data.model_dump(), status=ContractStatus.REGISTERED, created_by=user.id, updated_by=user.id)
    db.add(contract)
    db.flush()
    audit(db, "CONTRACT_CREATED", "Contract", contract.id, user.id)
    db.commit()
    # El alta lleva al expediente del contrato, que pide sus requisitos (listados-paginados, HU-22).
    return RedirectResponse(f"{CONTRACTS_URL}/{contract.id}?ok=created", status_code=303)


@router.post("/{contract_id}/amendments")
async def amend_contract(
    contract_id: int,
    request: Request,
    new_amount: str = Form(...),
    reason: str = Form(""),
    db: Session = Depends(get_db),
    user=Depends(require_roles(Role.ADMINISTRADOR)),
):
    await validate_csrf(request)
    contract = db.get(Contract, contract_id)
    if contract is None:
        raise HTTPException(404, "Contrato no encontrado")
    try:
        data = ContractAmendmentCreate(new_amount=new_amount, reason=reason)
    except ValidationError as exc:
        return _contracts_page(request, db, user, validation_message(exc), 400)
    amend_authorized_amount(db, contract, data.new_amount, data.reason, user.id)
    db.commit()
    return RedirectResponse(back_to(CONTRACTS_URL, await request.form()), status_code=303)


# --- Expediente del contrato (HU-22) ------------------------------------------------------------------------------


def _contract_page(
    request: Request,
    db: Session,
    user,
    contract: Contract,
    error: str | None = None,
    status_code: int = 200,
    notice: str | None = None,
):
    checklist = requirements.checklist(db, contract)
    can_edit = user.role == Role.ADMINISTRADOR
    registered = contract.status == ContractStatus.REGISTERED
    context = {
        "user": user,
        "contract": contract,
        "checklist": checklist,
        "status_labels": CONTRACT_STATUS_LABELS,
        "can_upload": can_edit and contract.status in requirements.UPLOAD_STATUSES and bool(checklist.rows),
        # Documentos que un requisito con varios archivos puede reemplazar ("Reemplaza a").
        "replaceable": [
            (row.document_type, document)
            for row in checklist.rows
            if row.document_type.allows_multiple
            for document in row.documents
        ],
        "can_activate": can_edit and registered,
        "activation_blocker": requirements.activation_blocker(db, contract) if can_edit and registered else None,
        "notice": notice,
        "error": error,
    }
    return templates.TemplateResponse(request, "contracts/detail.html", context, status_code=status_code)


def _contract_or_404(db: Session, contract_id: int) -> Contract:
    contract = db.get(Contract, contract_id)
    if contract is None:
        raise HTTPException(404, "Contrato no encontrado")
    return contract


def _contract_error(request: Request, db: Session, user, contract_id: int, exc: BusinessRuleError):
    db.rollback()  # nada se guarda y se liberan los bloqueos antes de volver a pintar
    return _contract_page(request, db, user, _contract_or_404(db, contract_id), exc.message, exc.status_code)


@router.get("/{contract_id}")
def contract_detail(
    contract_id: int,
    request: Request,
    ok: str = "",
    db: Session = Depends(get_db),
    user=Depends(require_roles(Role.PMO, Role.ADMINISTRADOR)),
):
    contract = _contract_or_404(db, contract_id)
    return _contract_page(request, db, user, contract, notice=CONTRACT_DETAIL_NOTICES.get(ok))


@router.post("/{contract_id}/documents")
async def upload_contract_document(
    contract_id: int,
    request: Request,
    document_type: str = Form(...),
    replaces_document_id: str = Form(""),
    upload: UploadFile = File(...),
    db: Session = Depends(get_db),
    user=Depends(require_roles(Role.ADMINISTRADOR)),
):
    await validate_csrf(request)
    contract = _contract_or_404(db, contract_id)
    try:
        replaces = int(replaces_document_id) if replaces_document_id.strip() else None
    except ValueError:
        replaces = -1  # no corresponde a ningun documento: el servicio responde 400
    try:
        # Antes de escribir el archivo: estatus del contrato, requisito que aplica y documento a reemplazar.
        document_type_row, replaced = requirements.prepare_upload(db, contract, document_type, replaces)
    except BusinessRuleError as exc:
        return _contract_error(request, db, user, contract.id, exc)
    try:
        stored = await LocalFileStorage().save_contract_file(contract.id, upload)
    except ValueError as exc:  # extension, contenido o tamano (almacenamiento-documentos)
        return _contract_error(request, db, user, contract.id, InvalidInputError(str(exc)))
    requirements.record_upload(db, contract, document_type_row, replaced, stored, user.id)
    log_upload(document_type_row.code, stored, contract_id=contract.id)
    db.commit()
    return RedirectResponse(f"{CONTRACTS_URL}/{contract.id}?ok=uploaded", status_code=303)


@router.get("/{contract_id}/documents/{document_id}/download")
def download_contract_document(
    contract_id: int,
    document_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_roles(Role.PMO, Role.ADMINISTRADOR)),
):
    doc = db.get(Document, document_id)
    if not doc or doc.contract_id != contract_id:
        raise HTTPException(404, "Documento no encontrado")
    try:
        path = LocalFileStorage().resolve(doc.path)
    except FileNotFoundError:
        raise HTTPException(404, "Archivo no disponible") from None
    if not path.is_file():
        raise HTTPException(404, "Archivo no disponible")
    # Nunca el MIME almacenado: la descarga no debe interpretarse en el navegador (junto con nosniff).
    return FileResponse(path, filename=safe_download_name(doc.original_filename), media_type="application/octet-stream")


@router.post("/{contract_id}/activate")
async def activate_contract(
    contract_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_roles(Role.ADMINISTRADOR)),
):
    await validate_csrf(request)
    _contract_or_404(db, contract_id)
    try:
        requirements.activate(db, contract_id, user.id)
    except BusinessRuleError as exc:
        return _contract_error(request, db, user, contract_id, exc)
    db.commit()
    return RedirectResponse(f"{CONTRACTS_URL}/{contract_id}?ok=activated", status_code=303)
