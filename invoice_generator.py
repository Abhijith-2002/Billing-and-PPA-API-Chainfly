from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel
from fastapi.concurrency import run_in_threadpool # <--- 1. IMPORT THIS

from firebase_config import db

class EnergyUsage(BaseModel):
    customer_id: str
    month: int
    year: int
    kwh_used: float
    # The 'timestamp' field is fine, but it won't be saved to the Invoice model below.
    # To set a default value on creation, use `default_factory`.
    timestamp: datetime = datetime.now()

class Invoice(BaseModel):
    # It's good practice to include the ID in the model itself.
    id: Optional[str] = None
    customer_id: str
    month: int
    year: int
    kwh_used: float
    tariff_rate: float
    total_amount: float
    status: str = "pending"
    created_at: datetime = datetime.now()
    paid_at: Optional[datetime] = None

def calculate_invoice_amount(kwh_used: float, tariff_rate: float) -> float:
    """Calculate invoice amount based on usage and tariff"""
    return round(kwh_used * tariff_rate, 2)

async def generate_invoice(usage: EnergyUsage, tariff_rate: float) -> Invoice:
    """Generate a new invoice for energy usage"""
    total_amount = calculate_invoice_amount(usage.kwh_used, tariff_rate)
    
    invoice = Invoice(
        customer_id=usage.customer_id,
        month=usage.month,
        year=usage.year,
        kwh_used=usage.kwh_used,
        tariff_rate=tariff_rate,
        total_amount=total_amount
    )
    
    # Prepare to save to Firestore
    invoice_ref = db.collection('invoices').document()
    invoice.id = invoice_ref.id  # Assign the new ID to the model
    invoice_dict = invoice.model_dump()
    
    ## FIX: Use run_in_threadpool for the blocking .set() call
    await run_in_threadpool(invoice_ref.set, invoice_dict)
    
    return invoice

async def get_customer_invoices(customer_id: str) -> List[Invoice]:
    """Get all invoices for a customer"""
    invoices_ref = db.collection('invoices').where('customer_id', '==', customer_id)
    
    ## FIX: Use run_in_threadpool for the blocking .get() call
    query_snapshot = await run_in_threadpool(invoices_ref.get)
    
    return [Invoice(**doc.to_dict()) for doc in query_snapshot]

async def get_invoice_by_id(invoice_id: str) -> Optional[Invoice]:
    """Get a specific invoice by ID"""
    invoice_ref = db.collection('invoices').document(invoice_id)
    
    ## FIX: Use run_in_threadpool for the blocking .get() call
    invoice_doc = await run_in_threadpool(invoice_ref.get)
    
    if invoice_doc.exists:
        return Invoice(**invoice_doc.to_dict())
    return None

async def mark_invoice_as_paid(invoice_id: str) -> Optional[Invoice]:
    """Mark an invoice as paid"""
    invoice_ref = db.collection('invoices').document(invoice_id)
    
    ## FIX: Use run_in_threadpool for the blocking .get() call
    invoice_doc = await run_in_threadpool(invoice_ref.get)
    
    if not invoice_doc.exists:
        return None
        
    update_data = {
        'status': 'paid',
        'paid_at': datetime.now()
    }
    
    ## FIX: Use run_in_threadpool for the blocking .update() call
    await run_in_threadpool(invoice_ref.update, update_data)
    
    # Return the updated invoice data by merging the original data with the update
    updated_invoice_data = {**invoice_doc.to_dict(), **update_data}
    return Invoice(**updated_invoice_data)