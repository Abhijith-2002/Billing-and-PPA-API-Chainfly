from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, BackgroundTasks
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.concurrency import run_in_threadpool
from typing import Optional, List
from datetime import datetime
import os
import tempfile
from pydantic import BaseModel

from firebase_config import verify_token, db
from invoice_generator import (
    EnergyUsage, Invoice, generate_invoice,
    get_customer_invoices, get_invoice_by_id,
    mark_invoice_as_paid
)
from utils.pdf_generator import create_invoice_pdf

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
    tariff_rate: float

class Contract(BaseModel):
    customer_id: str
    start_date: datetime
    end_date: datetime
    status: str = "active"
    file_path: Optional[str] = None

# Authentication dependency
async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    user = await run_in_threadpool(verify_token, credentials.credentials)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user

# Customer endpoints
@app.post("/customers")
async def create_customer(customer: Customer, current_user: dict = Depends(get_current_user)):
    customer_ref = db.collection('customers').document()
    customer_dict = customer.model_dump()
    customer_dict['id'] = customer_ref.id
    await run_in_threadpool(customer_ref.set, customer_dict)
    return customer_dict

@app.get("/customers")
async def list_customers(current_user: dict = Depends(get_current_user)):
    customers_ref = db.collection('customers')
    customers = await run_in_threadpool(customers_ref.get)
    return [doc.to_dict() for doc in customers]

# Energy usage endpoints
@app.post("/energy-usage")
## FIX: The model for this endpoint should be consistent with what `generate_invoice` expects.
## Using `EnergyUsage` from invoice_generator ensures consistency.
async def add_energy_usage(usage: EnergyUsage, current_user: dict = Depends(get_current_user)):
    usage_ref = db.collection('energy_usage').document()
    usage_dict = usage.model_dump()
    usage_dict['id'] = usage_ref.id
    await run_in_threadpool(usage_ref.set, usage_dict)
    return usage_dict

# Invoice endpoints
@app.post("/invoices/generate")
async def create_invoice(usage: EnergyUsage, current_user: dict = Depends(get_current_user)):
    customer_ref = db.collection('customers').document(usage.customer_id)
    customer = await run_in_threadpool(customer_ref.get)
    if not customer.exists:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    customer_data = customer.to_dict()
    ## IMPROVEMENT: Use .get() for safe dictionary access to prevent KeyError.
    tariff_rate = customer_data.get('tariff_rate')
    if tariff_rate is None:
        raise HTTPException(status_code=404, detail=f"Tariff rate not found for customer {usage.customer_id}")

    # The generate_invoice function is assumed to be corrected in invoice_generator.py
    invoice = await generate_invoice(usage, tariff_rate)
    return invoice

@app.get("/invoices")
async def list_invoices(customer_id: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    if customer_id:
        return await get_customer_invoices(customer_id)
    
    invoices_ref = db.collection('invoices')
    invoices = await run_in_threadpool(invoices_ref.get)
    return [doc.to_dict() for doc in invoices]

def cleanup_file(path: str):
    try:
        os.remove(path)
    except OSError:
        pass

@app.get("/invoices/{invoice_id}/pdf")
async def get_invoice_pdf(invoice_id: str, background_tasks: BackgroundTasks, current_user: dict = Depends(get_current_user)):
    invoice = await get_invoice_by_id(invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    
    customer_ref = db.collection('customers').document(invoice.customer_id)
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

# Contract endpoints
@app.post("/contracts")
async def upload_contract(
    customer_id: str,
    start_date: datetime,
    end_date: datetime,
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    file_path = f"contracts/{customer_id}_{file.filename}"
    await run_in_threadpool(os.makedirs, "contracts", exist_ok=True)
    
    try:
        with open(file_path, "wb") as buffer:
            await run_in_threadpool(buffer.write, await file.read())
    except Exception:
        raise HTTPException(status_code=500, detail="Could not save file.")

    contract = Contract(
        customer_id=customer_id,
        start_date=start_date,
        end_date=end_date,
        file_path=file_path
    )
    
    contract_ref = db.collection('contracts').document()
    contract_dict = contract.model_dump()
    contract_dict['id'] = contract_ref.id
    await run_in_threadpool(contract_ref.set, contract_dict)
    
    return contract_dict

@app.get("/contracts")
async def list_contracts(customer_id: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    if customer_id:
        contracts_ref = db.collection('contracts').where('customer_id', '==', customer_id)
    else:
        contracts_ref = db.collection('contracts')
    
    contracts = await run_in_threadpool(contracts_ref.get)
    return [doc.to_dict() for doc in contracts]

@app.get("/contracts/{contract_id}")
async def get_contract(contract_id: str, current_user: dict = Depends(get_current_user)):
    contract_ref = db.collection('contracts').document(contract_id)
    contract = await run_in_threadpool(contract_ref.get)
    
    if not contract.exists:
        raise HTTPException(status_code=404, detail="Contract not found")
    
    contract_data = contract.to_dict()
    file_path = contract_data.get('file_path')
    if file_path:
        ## IMPROVEMENT: Use non-blocking check for file existence.
        file_exists = await run_in_threadpool(os.path.exists, file_path)
        if not file_exists:
             raise HTTPException(status_code=404, detail="Contract file not found on server disk.")
        return FileResponse(
            file_path,
            media_type='application/pdf',
            filename=os.path.basename(file_path)
        )
    
    return contract_data

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)