from fastapi import FastAPI, HTTPException, Depends, Header, UploadFile, File
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
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

app = FastAPI(title="Solar Billing API")

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
async def get_current_user(authorization: str = Header(...)):
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")
    token = authorization.split(" ")[1]
    user = verify_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user

# Customer endpoints
@app.post("/customers")
async def create_customer(customer: Customer, current_user: dict = Depends(get_current_user)):
    customer_ref = db.collection('customers').document()
    customer_dict = customer.model_dump()
    customer_dict['id'] = customer_ref.id
    await customer_ref.set(customer_dict)
    return customer_dict

@app.get("/customers")
async def list_customers(current_user: dict = Depends(get_current_user)):
    customers_ref = db.collection('customers')
    customers = await customers_ref.get()
    return [doc.to_dict() for doc in customers]

# Energy usage endpoints
@app.post("/energy-usage")
async def add_energy_usage(usage: EnergyUsage, current_user: dict = Depends(get_current_user)):
    usage_ref = db.collection('energy_usage').document()
    usage_dict = usage.model_dump()
    usage_dict['id'] = usage_ref.id
    await usage_ref.set(usage_dict)
    return usage_dict

# Invoice endpoints
@app.post("/invoices/generate")
async def create_invoice(usage: EnergyUsage, current_user: dict = Depends(get_current_user)):
    # Get customer tariff rate
    customer_ref = db.collection('customers').document(usage.customer_id)
    customer = await customer_ref.get()
    if not customer.exists:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    tariff_rate = customer.to_dict()['tariff_rate']
    invoice = await generate_invoice(usage, tariff_rate)
    return invoice

@app.get("/invoices")
async def list_invoices(customer_id: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    if customer_id:
        return await get_customer_invoices(customer_id)
    
    invoices_ref = db.collection('invoices')
    invoices = await invoices_ref.get()
    return [doc.to_dict() for doc in invoices]

@app.get("/invoices/{invoice_id}/pdf")
async def get_invoice_pdf(invoice_id: str, current_user: dict = Depends(get_current_user)):
    invoice = await get_invoice_by_id(invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    
    # Get customer details
    customer_ref = db.collection('customers').document(invoice.customer_id)
    customer = await customer_ref.get()
    if not customer.exists:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    # Create temporary file for PDF
    with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
        pdf_path = create_invoice_pdf(invoice, customer.to_dict()['name'], tmp.name)
    
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
    # Save contract file
    file_path = f"contracts/{customer_id}_{file.filename}"
    os.makedirs("contracts", exist_ok=True)
    
    with open(file_path, "wb") as buffer:
        content = await file.read()
        buffer.write(content)
    
    # Create contract record
    contract = Contract(
        customer_id=customer_id,
        start_date=start_date,
        end_date=end_date,
        file_path=file_path
    )
    
    contract_ref = db.collection('contracts').document()
    contract_dict = contract.model_dump()
    contract_dict['id'] = contract_ref.id
    await contract_ref.set(contract_dict)
    
    return contract_dict

@app.get("/contracts")
async def list_contracts(customer_id: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    if customer_id:
        contracts_ref = db.collection('contracts').where('customer_id', '==', customer_id)
    else:
        contracts_ref = db.collection('contracts')
    
    contracts = await contracts_ref.get()
    return [doc.to_dict() for doc in contracts]

@app.get("/contracts/{contract_id}")
async def get_contract(contract_id: str, current_user: dict = Depends(get_current_user)):
    contract_ref = db.collection('contracts').document(contract_id)
    contract = await contract_ref.get()
    
    if not contract.exists:
        raise HTTPException(status_code=404, detail="Contract not found")
    
    contract_data = contract.to_dict()
    if contract_data.get('file_path'):
        return FileResponse(
            contract_data['file_path'],
            media_type='application/pdf',
            filename=os.path.basename(contract_data['file_path'])
        )
    
    return contract_data

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 