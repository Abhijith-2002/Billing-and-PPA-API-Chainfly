from datetime import datetime
from typing import Optional
from pydantic import BaseModel
from firebase_config import db

class EnergyUsage(BaseModel):
    customer_id: str
    month: int
    year: int
    usage_kwh: float
    timestamp: datetime = datetime.now()

class Invoice(BaseModel):
    customer_id: str
    month: int
    year: int
    usage_kwh: float
    tariff_rate: float
    total_amount: float
    status: str = "pending"
    created_at: datetime = datetime.now()
    paid_at: Optional[datetime] = None

def calculate_invoice_amount(usage_kwh: float, tariff_rate: float) -> float:
    """Calculate invoice amount based on usage and tariff"""
    return round(usage_kwh * tariff_rate, 2)

async def generate_invoice(usage: EnergyUsage, tariff_rate: float) -> Invoice:
    """Generate a new invoice for energy usage"""
    total_amount = calculate_invoice_amount(usage.usage_kwh, tariff_rate)
    
    invoice = Invoice(
        customer_id=usage.customer_id,
        month=usage.month,
        year=usage.year,
        usage_kwh=usage.usage_kwh,
        tariff_rate=tariff_rate,
        total_amount=total_amount
    )
    
    # Save to Firestore
    invoice_ref = db.collection('invoices').document()
    invoice_dict = invoice.model_dump()
    invoice_dict['id'] = invoice_ref.id
    await invoice_ref.set(invoice_dict)
    
    return invoice

async def get_customer_invoices(customer_id: str) -> list[Invoice]:
    """Get all invoices for a customer"""
    invoices_ref = db.collection('invoices').where('customer_id', '==', customer_id)
    invoices = await invoices_ref.get()
    return [Invoice(**doc.to_dict()) for doc in invoices]

async def get_invoice_by_id(invoice_id: str) -> Optional[Invoice]:
    """Get a specific invoice by ID"""
    invoice_ref = db.collection('invoices').document(invoice_id)
    invoice_doc = await invoice_ref.get()
    if invoice_doc.exists:
        return Invoice(**invoice_doc.to_dict())
    return None

async def mark_invoice_as_paid(invoice_id: str) -> Optional[Invoice]:
    """Mark an invoice as paid"""
    invoice_ref = db.collection('invoices').document(invoice_id)
    invoice_doc = await invoice_ref.get()
    
    if not invoice_doc.exists:
        return None
        
    invoice_data = invoice_doc.to_dict()
    invoice_data['status'] = 'paid'
    invoice_data['paid_at'] = datetime.now()
    
    await invoice_ref.update(invoice_data)
    return Invoice(**invoice_data) 