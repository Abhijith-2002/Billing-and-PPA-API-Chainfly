from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, BackgroundTasks, Form, Request
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.concurrency import run_in_threadpool
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
import os
import tempfile
from pydantic import BaseModel, Field, validator
from enum import Enum
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
import requests

# Import Firebase configuration with error handling
try:
    from firebase_config import verify_token, db
    FIREBASE_AVAILABLE = True
except Exception as e:
    print(f"Firebase not available: {str(e)}")
    FIREBASE_AVAILABLE = False
    db = None

from invoice_generator import (
    EnergyUsage, Invoice, generate_invoice,
    get_customer_invoices, get_invoice_by_id,
    mark_invoice_as_paid
)
from utils.pdf_generator import create_invoice_pdf
from ppa_generator import (
    PPA, SystemSpecifications, BillingTerms,
    generate_ppa, get_ppa_by_id, get_customer_ppas,
    mark_ppa_as_signed, create_ppa_pdf,
    update_ppa_energy_production, update_ppa_billing,
    update_ppa_payment, SystemLocation, Signatory
)

security = HTTPBearer()

app = FastAPI(
    title="Solar Billing API",
    description="API for managing solar client billing and Power Purchase Agreements",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static directory for JS/CSS if needed
if not os.path.exists('static'):
    os.makedirs('static')
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# --- ENUMS (match ppa_generator.py) ---
class CustomerType(str, Enum):
    residential = "residential"
    commercial = "commercial"
    ci = "C&I"
    industrial = "industrial"
    government = "government"
    other = "other"

class ContractType(str, Enum):
    net_metering = "net_metering"
    gross_metering = "gross_metering"
    open_access = "open_access"

class ContractStatus(str, Enum):
    draft = "draft"
    active = "active"
    expired = "expired"
    terminated = "terminated"

# Models
class Customer(BaseModel):
    name: str
    email: str
    address: str

class SlabRequest(BaseModel):
    min: float
    max: float
    rate: float
    unit: str

class ToURateRequest(BaseModel):
    timeRange: str
    rate: float
    unit: str

class BillingTermsRequest(BaseModel):
    tariff_rate: float = Field(..., description="Base tariff rate per kWh")
    escalation_rate: float = Field(..., description="Annual escalation rate (e.g., 0.02 for 2%)")
    billing_cycle: str = Field(..., description="Billing cycle (monthly/quarterly/annually)")
    payment_terms: str = Field(..., description="Payment terms (net15/net30/net45/net60)")
    slabs: Optional[List[SlabRequest]] = None
    touRates: Optional[List[ToURateRequest]] = None
    taxRate: Optional[float] = 0
    latePaymentPenaltyRate: Optional[float] = 0
    currency: str = "INR"
    subsidySchemeId: Optional[str] = None
    autoInvoice: bool = False
    gracePeriodDays: int = 0

    @validator('latePaymentPenaltyRate')
    def penalty_max_10(cls, v):
        if v is not None and v > 10:
            raise ValueError("latePaymentPenaltyRate cannot exceed 10%")
        return v

class SystemLocationRequest(BaseModel):
    lat: float
    long: float

class SystemSpecificationsRequest(BaseModel):
    capacity_kw: float
    panel_type: str
    inverter_type: str
    installation_date: datetime
    estimated_annual_production: float
    systemLocation: Optional[SystemLocationRequest] = None
    moduleManufacturer: Optional[str] = None
    inverterBrand: Optional[str] = None
    expectedGeneration: Optional[float] = None
    actualGeneration: Optional[float] = None
    systemAgeInMonths: Optional[int] = None

class CustomerRequest(BaseModel):
    name: str
    email: str
    address: str
    customerType: CustomerType
    gstNumber: Optional[str] = None
    linkedPPAs: List[str] = Field(default_factory=list)

class SignatoryRequest(BaseModel):
    name: str
    role: str
    signedAt: Optional[datetime] = None

class PPACreateRequest(BaseModel):
    customer_id: str
    system_specs: SystemSpecificationsRequest
    billing_terms: BillingTermsRequest
    start_date: datetime
    end_date: datetime
    contractType: ContractType = ContractType.net_metering
    signatories: Optional[List[SignatoryRequest]] = None
    terminationClause: Optional[str] = None
    paymentTerms: Optional[str] = None
    curtailmentClauses: Optional[str] = None
    generationGuarantees: Optional[str] = None
    createdBy: Optional[str] = None

    def ensure_timezone(self):
        if self.start_date.tzinfo is None:
            self.start_date = self.start_date.replace(tzinfo=timezone.utc)
        if self.end_date.tzinfo is None:
            self.end_date = self.end_date.replace(tzinfo=timezone.utc)
        if self.system_specs.installation_date.tzinfo is None:
            self.system_specs.installation_date = self.system_specs.installation_date.replace(tzinfo=timezone.utc)

class EnergyUsageRequest(BaseModel):
    ppa_id: str
    kwh_used: float
    reading_date: datetime
    source: Optional[str] = None
    unit: str = "kWh"
    timestampStart: Optional[datetime] = None
    timestampEnd: Optional[datetime] = None
    importEnergy: Optional[float] = None
    exportEnergy: Optional[float] = None

class HTTPValidationError(BaseModel):
    detail: Any
    errorCode: Optional[str] = None
    documentationLink: Optional[str] = None

class ValidationError(BaseModel):
    loc: List[str]
    msg: str
    type: str
    errorCode: Optional[str] = None
    documentationLink: Optional[str] = None

# Authentication dependency
async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if not FIREBASE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Authentication service unavailable")
    
    user = await run_in_threadpool(verify_token, credentials.credentials)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user

# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "firebase_available": FIREBASE_AVAILABLE,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

# Customer endpoints
@app.post("/customers")
async def create_customer(customer: Customer, current_user: dict = Depends(get_current_user)):
    if not FIREBASE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database service unavailable")
    
    customer_ref = db.collection('customers').document()
    customer_dict = customer.model_dump()
    customer_dict['id'] = customer_ref.id
    await run_in_threadpool(customer_ref.set, customer_dict)
    return customer_dict

@app.get("/customers")
async def list_customers(current_user: dict = Depends(get_current_user)):
    if not FIREBASE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database service unavailable")
    
    customers_ref = db.collection('customers')
    customers = await run_in_threadpool(customers_ref.get)
    return [doc.to_dict() for doc in customers]

# PPA endpoints
@app.post("/ppas", response_model=PPA, responses={422: {"model": HTTPValidationError}})
async def create_ppa(
    ppa_request: PPACreateRequest,
    current_user: dict = Depends(get_current_user)
):
    """Create a new PPA with all necessary specifications and terms, enforcing overlap and audit trail."""
    if not FIREBASE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database service unavailable")
    
    # Ensure all datetime fields are timezone-aware
    ppa_request.ensure_timezone()
    
    # Overlapping contract check
    overlap = await check_overlapping_ppa(
        ppa_request.customer_id, ppa_request.start_date, ppa_request.end_date, db
    )
    if overlap:
        raise HTTPException(
            status_code=422,
            detail={
                "detail": "Overlapping active/draft PPA exists for this customer/site.",
                "errorCode": "PPA_OVERLAP",
                "documentationLink": "https://docs.yourapi.com/errors#PPA_OVERLAP"
            }
        )
    
    # Verify customer exists
    customer_ref = db.collection('customers').document(ppa_request.customer_id)
    customer = await run_in_threadpool(customer_ref.get)
    if not customer.exists:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    try:
        # Convert nested request models to response models
        system_location = None
        if ppa_request.system_specs.systemLocation:
            loc = ppa_request.system_specs.systemLocation
            system_location = SystemLocation(lat=loc.lat, long=loc.long)
        system_specs = SystemSpecifications(
            capacity_kw=ppa_request.system_specs.capacity_kw,
            panel_type=ppa_request.system_specs.panel_type,
            inverter_type=ppa_request.system_specs.inverter_type,
            installation_date=ppa_request.system_specs.installation_date,
            estimated_annual_production=ppa_request.system_specs.estimated_annual_production,
            systemLocation=system_location,
            moduleManufacturer=ppa_request.system_specs.moduleManufacturer,
            inverterBrand=ppa_request.system_specs.inverterBrand,
            expectedGeneration=ppa_request.system_specs.expectedGeneration,
            actualGeneration=ppa_request.system_specs.actualGeneration,
            systemAgeInMonths=ppa_request.system_specs.systemAgeInMonths
        )
        
        billing_terms = BillingTerms(
            tariff_rate=ppa_request.billing_terms.tariff_rate,
            escalation_rate=ppa_request.billing_terms.escalation_rate,
            billing_cycle=ppa_request.billing_terms.billing_cycle,
            payment_terms=ppa_request.billing_terms.payment_terms,
            slabs=[s.dict() for s in ppa_request.billing_terms.slabs] if ppa_request.billing_terms.slabs else None,
            touRates=[t.dict() for t in ppa_request.billing_terms.touRates] if ppa_request.billing_terms.touRates else None,
            taxRate=ppa_request.billing_terms.taxRate,
            latePaymentPenaltyRate=ppa_request.billing_terms.latePaymentPenaltyRate,
            currency=ppa_request.billing_terms.currency,
            subsidySchemeId=ppa_request.billing_terms.subsidySchemeId,
            autoInvoice=ppa_request.billing_terms.autoInvoice,
            gracePeriodDays=ppa_request.billing_terms.gracePeriodDays
        )
        
        signatories = [Signatory(**s.dict()) for s in (ppa_request.signatories or [])]
        
        # Generate PPA
        ppa = await generate_ppa(
            customer_id=ppa_request.customer_id,
            system_specs=system_specs,
            billing_terms=billing_terms,
            start_date=ppa_request.start_date,
            end_date=ppa_request.end_date
        )
        # Set additional fields
        ppa.contractType = ppa_request.contractType
        ppa.signatories = signatories
        ppa.terminationClause = ppa_request.terminationClause
        ppa.paymentTerms = ppa_request.paymentTerms
        ppa.curtailmentClauses = ppa_request.curtailmentClauses
        ppa.generationGuarantees = ppa_request.generationGuarantees
        ppa.createdBy = ppa_request.createdBy or (current_user.get('uid') if current_user else None)
        ppa.updatedBy = ppa_request.createdBy or (current_user.get('uid') if current_user else None)
        ppa.updated_at = datetime.now(timezone.utc)
        # Save updated PPA
        ppa_ref = db.collection('ppas').document(ppa.id)
        await run_in_threadpool(ppa_ref.set, ppa.model_dump())
        return ppa
    except ValueError as e:
        raise HTTPException(
            status_code=422,
            detail={
                "detail": str(e),
                "errorCode": "VALIDATION_ERROR",
                "documentationLink": "https://docs.yourapi.com/errors#VALIDATION_ERROR"
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating PPA: {str(e)}")

@app.get("/ppas")
async def list_ppas(customer_id: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    """List all PPAs or PPAs for a specific customer"""
    if customer_id:
        return await get_customer_ppas(customer_id)
    
    ppas_ref = db.collection('ppas')
    ppas = await run_in_threadpool(ppas_ref.get)
    return [doc.to_dict() for doc in ppas]

@app.get("/ppas/{ppa_id}")
async def get_ppa(ppa_id: str, current_user: dict = Depends(get_current_user)):
    """Get a specific PPA by ID"""
    ppa = await get_ppa_by_id(ppa_id)
    if not ppa:
        raise HTTPException(status_code=404, detail="PPA not found")
    return ppa

@app.post("/ppas/{ppa_id}/sign")
async def sign_ppa(ppa_id: str, current_user: dict = Depends(get_current_user)):
    """Mark a PPA as signed and activate it"""
    ppa = await mark_ppa_as_signed(ppa_id)
    if not ppa:
        raise HTTPException(status_code=404, detail="PPA not found")
    return ppa

@app.get("/ppas/{ppa_id}/pdf")
async def get_ppa_pdf(ppa_id: str, background_tasks: BackgroundTasks, current_user: dict = Depends(get_current_user)):
    """Generate and download PPA PDF"""
    ppa = await get_ppa_by_id(ppa_id)
    if not ppa:
        raise HTTPException(status_code=404, detail="PPA not found")
    
    customer_ref = db.collection('customers').document(ppa.customer_id)
    customer = await run_in_threadpool(customer_ref.get)
    if not customer.exists:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
        pdf_path = tmp.name
    
    await run_in_threadpool(create_ppa_pdf, ppa, customer.to_dict()['name'], pdf_path)
    
    background_tasks.add_task(cleanup_file, pdf_path)
    
    return FileResponse(
        pdf_path,
        media_type='application/pdf',
        filename=f'ppa_{ppa_id}.pdf'
    )

# Energy usage endpoints
@app.post("/ppas/{ppa_id}/energy-usage")
async def add_energy_usage(
    ppa_id: str,
    usage: EnergyUsageRequest,
    current_user: dict = Depends(get_current_user)
):
    """Add energy usage data for a PPA"""
    if not FIREBASE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database service unavailable")
    
    ppa = await get_ppa_by_id(ppa_id)
    if not ppa:
        raise HTTPException(status_code=404, detail="PPA not found")
    
    if not ppa.is_active():
        raise HTTPException(status_code=400, detail="PPA is not active")
    
    # Update PPA with new energy production
    await update_ppa_energy_production(ppa_id, usage.kwh_used)
    
    # Save energy usage record
    usage_ref = db.collection('energy_usage').document()
    usage_dict = usage.dict()
    usage_dict['id'] = usage_ref.id
    usage_dict['ppa_id'] = ppa_id
    await run_in_threadpool(usage_ref.set, usage_dict)
    
    return usage_dict

# Invoice endpoints
@app.post("/ppas/{ppa_id}/invoices/generate")
async def create_invoice(
    ppa_id: str,
    usage: EnergyUsageRequest,
    current_user: dict = Depends(get_current_user)
):
    """Generate an invoice for a PPA"""
    ppa = await get_ppa_by_id(ppa_id)
    if not ppa:
        raise HTTPException(status_code=404, detail="PPA not found")
    
    if not ppa.is_active():
        raise HTTPException(status_code=400, detail="PPA is not active")
    
    if not ppa.should_generate_invoice():
        raise HTTPException(status_code=400, detail="No invoice needed at this time")
    
    # Calculate current tariff rate
    current_tariff = ppa.calculate_current_tariff(datetime.now(timezone.utc))

    # Construct EnergyUsage object with customer_id from PPA
    energy_usage = EnergyUsage(
        customer_id=ppa.customer_id,
        month=usage.reading_date.month,
        year=usage.reading_date.year,
        kwh_used=usage.kwh_used,
        timestamp=usage.reading_date
    )
    
    # Generate invoice
    invoice = await generate_invoice(energy_usage, current_tariff)
    
    # Update PPA billing information
    await update_ppa_billing(ppa_id, invoice.total_amount)
    
    return invoice

@app.get("/ppas/{ppa_id}/invoices")
async def list_ppa_invoices(ppa_id: str, current_user: dict = Depends(get_current_user)):
    """List all invoices for a PPA"""
    ppa = await get_ppa_by_id(ppa_id)
    if not ppa:
        raise HTTPException(status_code=404, detail="PPA not found")
    
    invoices_ref = db.collection('invoices').where('ppa_id', '==', ppa_id)
    invoices = await run_in_threadpool(invoices_ref.get)
    return [doc.to_dict() for doc in invoices]

@app.get("/ppas/{ppa_id}/invoices/{invoice_id}/pdf")
async def get_invoice_pdf(
    ppa_id: str,
    invoice_id: str,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user)
):
    """Generate and download invoice PDF"""
    ppa = await get_ppa_by_id(ppa_id)
    if not ppa:
        raise HTTPException(status_code=404, detail="PPA not found")
    
    invoice = await get_invoice_by_id(invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    
    customer_ref = db.collection('customers').document(ppa.customer_id)
    customer = await run_in_threadpool(customer_ref.get)
    if not customer.exists:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
        pdf_path = tmp.name
    
    await run_in_threadpool(create_invoice_pdf, invoice, customer.to_dict()['name'], pdf_path)
    
    background_tasks.add_task(cleanup_file, pdf_path)
    
    return FileResponse(
        pdf_path,
        media_type='application/pdf',
        filename=f'invoice_{invoice_id}.pdf'
    )

@app.post("/ppas/{ppa_id}/invoices/{invoice_id}/pay")
async def pay_invoice(
    ppa_id: str,
    invoice_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Mark an invoice as paid and update PPA payment information"""
    ppa = await get_ppa_by_id(ppa_id)
    if not ppa:
        raise HTTPException(status_code=404, detail="PPA not found")
    
    invoice = await get_invoice_by_id(invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    
    # Mark invoice as paid
    paid_invoice = await mark_invoice_as_paid(invoice_id)
    
    # Update PPA payment information
    await update_ppa_payment(ppa_id, paid_invoice.total_amount)
    
    return paid_invoice

def cleanup_file(path: str):
    try:
        os.remove(path)
    except OSError:
        pass

# --- ERROR MODELS ---


# --- BUSINESS LOGIC: Overlapping PPA check ---
async def check_overlapping_ppa(customer_id: str, start_date: datetime, end_date: datetime, db):
    # Query for active PPAs for this customer
    ppas_ref = db.collection('ppas').where('customer_id', '==', customer_id)
    ppas = await run_in_threadpool(ppas_ref.get)
    for doc in ppas:
        ppa = doc.to_dict()
        # Only check for active/draft
        if ppa.get('contractStatus') in ["active", "draft"]:
            # If date ranges overlap
            if not (end_date <= ppa['start_date'] or start_date >= ppa['end_date']):
                return True
    return False

@app.get("/", response_class=HTMLResponse)
def serve_frontend(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

FIREBASE_API_KEY = os.environ.get("FIREBASE_API_KEY")
if not FIREBASE_API_KEY:
    raise RuntimeError("FIREBASE_API_KEY environment variable must be set for authentication.")

@app.post("/auth/login")
def login_auth(data: dict):
    email = data.get("email")
    password = data.get("password")
    if not email or not password:
        return {"error": "Email and password required."}
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FIREBASE_API_KEY}"
    payload = {
        "email": email,
        "password": password,
        "returnSecureToken": True
    }
    resp = requests.post(url, json=payload)
    return resp.json()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)