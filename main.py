from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, BackgroundTasks, Form
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.concurrency import run_in_threadpool
from typing import Optional, List
from datetime import datetime, timezone
import os
import tempfile
from pydantic import BaseModel, Field

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
    update_ppa_payment
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

# Models
class Customer(BaseModel):
    name: str
    email: str
    address: str

class SystemSpecificationsRequest(BaseModel):
    capacity_kw: float = Field(..., description="System capacity in kilowatts")
    panel_type: str = Field(..., description="Type of solar panels (e.g., Monocrystalline, Polycrystalline)")
    inverter_type: str = Field(..., description="Type of inverter (e.g., String Inverter, Microinverter)")
    installation_date: datetime = Field(..., description="Date when the system was/will be installed")
    estimated_annual_production: float = Field(..., description="Estimated annual energy production in kWh")

class BillingTermsRequest(BaseModel):
    tariff_rate: float = Field(..., description="Base tariff rate per kWh")
    escalation_rate: float = Field(..., description="Annual escalation rate (e.g., 0.02 for 2%)")
    billing_cycle: str = Field(..., description="Billing cycle (monthly/quarterly/annually)")
    payment_terms: str = Field(..., description="Payment terms (net15/net30/net45/net60)")

class PPACreateRequest(BaseModel):
    customer_id: str = Field(..., description="ID of the customer")
    system_specs: SystemSpecificationsRequest = Field(..., description="System specifications")
    billing_terms: BillingTermsRequest = Field(..., description="Billing and payment terms")
    start_date: datetime = Field(..., description="Start date of the agreement")
    end_date: datetime = Field(..., description="End date of the agreement")

    def ensure_timezone(self):
        """Ensure all datetime fields are timezone-aware"""
        if self.start_date.tzinfo is None:
            self.start_date = self.start_date.replace(tzinfo=timezone.utc)
        if self.end_date.tzinfo is None:
            self.end_date = self.end_date.replace(tzinfo=timezone.utc)
        if self.system_specs.installation_date.tzinfo is None:
            self.system_specs.installation_date = self.system_specs.installation_date.replace(tzinfo=timezone.utc)

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
@app.post("/ppas", response_model=PPA)
async def create_ppa(
    ppa_request: PPACreateRequest,
    current_user: dict = Depends(get_current_user)
):
    """Create a new PPA with all necessary specifications and terms"""
    if not FIREBASE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database service unavailable")
    
    # Ensure all datetime fields are timezone-aware
    ppa_request.ensure_timezone()
    
    # Verify customer exists
    customer_ref = db.collection('customers').document(ppa_request.customer_id)
    customer = await run_in_threadpool(customer_ref.get)
    if not customer.exists:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    try:
        # Convert request models to internal models
        system_specs = SystemSpecifications(
            capacity_kw=ppa_request.system_specs.capacity_kw,
            panel_type=ppa_request.system_specs.panel_type,
            inverter_type=ppa_request.system_specs.inverter_type,
            installation_date=ppa_request.system_specs.installation_date,
            estimated_annual_production=ppa_request.system_specs.estimated_annual_production
        )
        
        billing_terms = BillingTerms(
            tariff_rate=ppa_request.billing_terms.tariff_rate,
            escalation_rate=ppa_request.billing_terms.escalation_rate,
            billing_cycle=ppa_request.billing_terms.billing_cycle,
            payment_terms=ppa_request.billing_terms.payment_terms
        )
        
        # Generate PPA
        ppa = await generate_ppa(
            customer_id=ppa_request.customer_id,
            system_specs=system_specs,
            billing_terms=billing_terms,
            start_date=ppa_request.start_date,
            end_date=ppa_request.end_date
        )
        return ppa
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
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
    usage: EnergyUsage,
    current_user: dict = Depends(get_current_user)
):
    """Add energy usage data for a PPA"""
    ppa = await get_ppa_by_id(ppa_id)
    if not ppa:
        raise HTTPException(status_code=404, detail="PPA not found")
    
    if not ppa.is_active():
        raise HTTPException(status_code=400, detail="PPA is not active")
    
    # Update PPA with new energy production
    await update_ppa_energy_production(ppa_id, usage.kwh_used)
    
    # Save energy usage record
    usage_ref = db.collection('energy_usage').document()
    usage_dict = usage.model_dump()
    usage_dict['id'] = usage_ref.id
    usage_dict['ppa_id'] = ppa_id
    await run_in_threadpool(usage_ref.set, usage_dict)
    
    return usage_dict

# Invoice endpoints
@app.post("/ppas/{ppa_id}/invoices/generate")
async def create_invoice(
    ppa_id: str,
    usage: EnergyUsage,
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
    current_tariff = ppa.calculate_current_tariff(datetime.now())
    
    # Generate invoice
    invoice = await generate_invoice(usage, current_tariff)
    invoice.ppa_id = ppa_id
    
    # Update PPA billing information
    await update_ppa_billing(ppa_id, invoice.amount)
    
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
    
    if invoice.ppa_id != ppa_id:
        raise HTTPException(status_code=400, detail="Invoice does not belong to this PPA")
    
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
    
    if invoice.ppa_id != ppa_id:
        raise HTTPException(status_code=400, detail="Invoice does not belong to this PPA")
    
    # Mark invoice as paid
    paid_invoice = await mark_invoice_as_paid(invoice_id)
    
    # Update PPA payment information
    await update_ppa_payment(ppa_id, paid_invoice.amount)
    
    return paid_invoice

def cleanup_file(path: str):
    try:
        os.remove(path)
    except OSError:
        pass

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)