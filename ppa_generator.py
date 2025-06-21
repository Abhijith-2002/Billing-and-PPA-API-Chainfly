from datetime import datetime, timedelta, timezone
from typing import Optional, List
from pydantic import BaseModel, Field
from fastapi.concurrency import run_in_threadpool
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import HexColor

from firebase_config import db

class SystemSpecifications(BaseModel):
    """System specifications for the solar installation"""
    capacity_kw: float = Field(..., description="System capacity in kilowatts")
    panel_type: str = Field(..., description="Type of solar panels")
    inverter_type: str = Field(..., description="Type of inverter")
    installation_date: datetime = Field(..., description="Date when the system was/will be installed")
    estimated_annual_production: float = Field(..., description="Estimated annual energy production in kWh")

class BillingTerms(BaseModel):
    """Billing and payment terms for the PPA"""
    tariff_rate: float = Field(..., description="Base tariff rate per kWh")
    escalation_rate: float = Field(..., description="Annual escalation rate")
    billing_cycle: str = Field(..., description="Billing cycle (monthly/quarterly/annually)")
    payment_terms: str = Field(..., description="Payment terms (net15/net30/net45/net60)")

class PPA(BaseModel):
    """Power Purchase Agreement - Indian Standard Format"""
    id: Optional[str] = None
    customer_id: str
    system_specs: SystemSpecifications
    billing_terms: BillingTerms
    start_date: datetime
    end_date: datetime
    status: str = "draft"  # draft, signed, active, expired, terminated
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    signed_at: Optional[datetime] = None
    total_energy_produced: float = 0
    total_billed: float = 0
    total_paid: float = 0
    last_billing_date: Optional[datetime] = None
    contract_duration_years: float
    current_tariff_rate: float
    next_escalation_date: datetime
    payment_history: List[dict] = Field(default_factory=list)
    energy_production_history: List[dict] = Field(default_factory=list)
    billing_history: List[dict] = Field(default_factory=list)
    file_path: Optional[str] = None

    def is_active(self) -> bool:
        """Check if the PPA is currently active"""
        now = datetime.now(timezone.utc)
        return (
            self.status == "active" and
            self.start_date <= now <= self.end_date
        )

    def should_generate_invoice(self) -> bool:
        """Check if an invoice should be generated based on billing cycle"""
        if not self.is_active():
            return False
        
        now = datetime.now(timezone.utc)
        if not self.last_billing_date:
            return True
        
        if self.billing_terms.billing_cycle == "monthly":
            return (now - self.last_billing_date).days >= 30
        elif self.billing_terms.billing_cycle == "quarterly":
            return (now - self.last_billing_date).days >= 90
        elif self.billing_terms.billing_cycle == "annually":
            return (now - self.last_billing_date).days >= 365
        
        return False

    def calculate_current_tariff(self, current_date: datetime) -> float:
        """Calculate the current tariff rate based on escalation"""
        if not self.is_active():
            return 0
        
        years_elapsed = (current_date - self.start_date).days / 365.25
        escalation_periods = int(years_elapsed)
        
        current_rate = self.billing_terms.tariff_rate
        for _ in range(escalation_periods):
            current_rate *= (1 + self.billing_terms.escalation_rate)
        
        return round(current_rate, 4)

    def add_energy_production(self, kwh: float, reading_date: datetime):
        """Add energy production record"""
        self.energy_production_history.append({
            "kwh": kwh,
            "date": reading_date,
            "tariff_rate": self.calculate_current_tariff(reading_date)
        })
        self.total_energy_produced += kwh

    def add_billing_record(self, amount: float, billing_date: datetime):
        """Add billing record"""
        self.billing_history.append({
            "amount": amount,
            "date": billing_date,
            "tariff_rate": self.calculate_current_tariff(billing_date)
        })
        self.total_billed += amount
        self.last_billing_date = billing_date

    def add_payment_record(self, amount: float, payment_date: datetime):
        """Add payment record"""
        self.payment_history.append({
            "amount": amount,
            "date": payment_date
        })
        self.total_paid += amount

def create_ppa_pdf(ppa: PPA, customer_name: str, output_path: str) -> str:
    """Generate a professional PDF PPA document following Indian standards"""
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.colors import HexColor, black, white
    
    # Create the PDF document
    doc = SimpleDocTemplate(output_path, pagesize=A4, rightMargin=72, leftMargin=72, topMargin=72, bottomMargin=18)
    story = []
    
    # Define styles
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=16,
        spaceAfter=30,
        alignment=TA_CENTER,
        textColor=HexColor('#2E86AB')
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=12,
        spaceAfter=12,
        spaceBefore=12,
        textColor=HexColor('#2E86AB')
    )
    
    normal_style = styles['Normal']
    
    # Title
    story.append(Paragraph("POWER PURCHASE AGREEMENT", title_style))
    story.append(Spacer(1, 12))
    
    # Agreement Details
    story.append(Paragraph("1. AGREEMENT DETAILS", heading_style))
    
    agreement_data = [
        ["Agreement Number", f"PPA-{ppa.id}"],
        ["Customer Name", customer_name],
        ["Customer ID", ppa.customer_id],
        ["Agreement Date", ppa.created_at.strftime("%d/%m/%Y")],
        ["Start Date", ppa.start_date.strftime("%d/%m/%Y")],
        ["End Date", ppa.end_date.strftime("%d/%m/%Y")],
        ["Contract Duration", f"{ppa.contract_duration_years:.1f} years"],
        ["Status", ppa.status.upper()]
    ]
    
    agreement_table = Table(agreement_data, colWidths=[2*inch, 4*inch])
    agreement_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), HexColor('#2E86AB')),
        ('TEXTCOLOR', (0, 0), (-1, 0), white),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), HexColor('#F8F9FA')),
        ('GRID', (0, 0), (-1, -1), 1, black),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [HexColor('#F8F9FA'), white])
    ]))
    story.append(agreement_table)
    story.append(Spacer(1, 20))
    
    # System Specifications
    story.append(Paragraph("2. SYSTEM SPECIFICATIONS", heading_style))
    
    system_data = [
        ["Capacity", f"{ppa.system_specs.capacity_kw} kW"],
        ["Panel Type", ppa.system_specs.panel_type],
        ["Inverter Type", ppa.system_specs.inverter_type],
        ["Installation Date", ppa.system_specs.installation_date.strftime("%d/%m/%Y")],
        ["Estimated Annual Production", f"{ppa.system_specs.estimated_annual_production:,.0f} kWh"]
    ]
    
    system_table = Table(system_data, colWidths=[2*inch, 4*inch])
    system_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), HexColor('#2E86AB')),
        ('TEXTCOLOR', (0, 0), (-1, 0), white),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), HexColor('#F8F9FA')),
        ('GRID', (0, 0), (-1, -1), 1, black),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [HexColor('#F8F9FA'), white])
    ]))
    story.append(system_table)
    story.append(Spacer(1, 20))
    
    # Billing Terms
    story.append(Paragraph("3. BILLING TERMS", heading_style))
    
    billing_data = [
        ["Base Tariff Rate", f"₹{ppa.billing_terms.tariff_rate:.2f}/kWh"],
        ["Annual Escalation Rate", f"{ppa.billing_terms.escalation_rate*100:.1f}%"],
        ["Billing Cycle", ppa.billing_terms.billing_cycle.capitalize()],
        ["Payment Terms", ppa.billing_terms.payment_terms.upper()],
        ["Next Escalation Date", ppa.next_escalation_date.strftime("%d/%m/%Y")]
    ]
    
    billing_table = Table(billing_data, colWidths=[2*inch, 4*inch])
    billing_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), HexColor('#2E86AB')),
        ('TEXTCOLOR', (0, 0), (-1, 0), white),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), HexColor('#F8F9FA')),
        ('GRID', (0, 0), (-1, -1), 1, black),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [HexColor('#F8F9FA'), white])
    ]))
    story.append(billing_table)
    story.append(Spacer(1, 20))
    
    # Terms and Conditions
    story.append(Paragraph("4. TERMS AND CONDITIONS", heading_style))
    
    terms = [
        "• This agreement is valid for the entire contract duration specified above.",
        "• The tariff rate will escalate annually as per the specified escalation rate.",
        "• Billing will be done according to the specified billing cycle.",
        "• Payment must be made within the specified payment terms.",
        "• The agreement can be terminated with 30 days written notice.",
        "• Force majeure events will be handled as per standard industry practices.",
        "• Disputes will be resolved through mutual discussion or legal means.",
        "• This agreement is subject to applicable Indian laws and regulations."
    ]
    
    for term in terms:
        story.append(Paragraph(term, normal_style))
        story.append(Spacer(1, 6))
    
    story.append(Spacer(1, 20))
    
    # Signature Blocks
    story.append(Paragraph("5. SIGNATURES", heading_style))
    
    signature_data = [
        ["Customer Signature", "Company Representative Signature"],
        ["", ""],
        ["", ""],
        ["Date: ___________", "Date: ___________"],
        ["Name: ___________", "Name: ___________"],
        ["Designation: ___________", "Designation: ___________"]
    ]
    
    signature_table = Table(signature_data, colWidths=[3*inch, 3*inch])
    signature_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('GRID', (0, 0), (-1, -1), 1, black),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('VALIGN', (0, 0), (-1, -1), 'TOP')
    ]))
    story.append(signature_table)
    
    # Build the PDF
    doc.build(story)
    return output_path

async def generate_ppa(
    customer_id: str,
    system_specs: SystemSpecifications,
    billing_terms: BillingTerms,
    start_date: datetime,
    end_date: datetime
) -> PPA:
    """Generate a new PPA with all necessary values"""
    # Validate dates
    if start_date >= end_date:
        raise ValueError("Start date must be before end date")
    
    now = datetime.now(timezone.utc)
    
    # Allow start dates up to 1 year in the past for existing installations
    # and up to 2 years in the future for planned installations
    min_start_date = now - timedelta(days=365)  # 1 year ago
    max_start_date = now + timedelta(days=730)  # 2 years from now
    
    if start_date < min_start_date:
        raise ValueError("Start date cannot be more than 1 year in the past")
    
    if start_date > max_start_date:
        raise ValueError("Start date cannot be more than 2 years in the future")
    
    # Validate system specifications
    if system_specs.capacity_kw <= 0:
        raise ValueError("System capacity must be greater than 0")
    
    if not system_specs.panel_type:
        raise ValueError("Panel type is required")
    
    if not system_specs.inverter_type:
        raise ValueError("Inverter type is required")
    
    # Validate billing terms
    if billing_terms.tariff_rate <= 0:
        raise ValueError("Tariff rate must be greater than 0")
    
    if billing_terms.escalation_rate < 0:
        raise ValueError("Escalation rate cannot be negative")
    
    if not billing_terms.billing_cycle in ["monthly", "quarterly", "annually"]:
        raise ValueError("Invalid billing cycle")
    
    if not billing_terms.payment_terms in ["net15", "net30", "net45", "net60"]:
        raise ValueError("Invalid payment terms")
    
    # Create PPA document
    ppa_ref = db.collection('ppas').document()
    
    # Calculate contract duration in years
    duration_years = (end_date - start_date).days / 365.25
    
    # Determine initial status based on start date
    if start_date <= now:
        initial_status = "active"  # If start date is in the past or today, mark as active
    else:
        initial_status = "draft"   # If start date is in the future, keep as draft
    
    # Create PPA object with all necessary values
    ppa = PPA(
        id=ppa_ref.id,
        customer_id=customer_id,
        system_specs=system_specs,
        billing_terms=billing_terms,
        start_date=start_date,
        end_date=end_date,
        status=initial_status,
        created_at=now,
        signed_at=None,
        total_energy_produced=0,
        total_billed=0,
        total_paid=0,
        last_billing_date=None,
        contract_duration_years=duration_years,
        current_tariff_rate=billing_terms.tariff_rate,
        next_escalation_date=start_date.replace(year=start_date.year + 1),
        payment_history=[],
        energy_production_history=[],
        billing_history=[],
        file_path=None
    )
    
    # Save to Firestore
    await run_in_threadpool(ppa_ref.set, ppa.model_dump())
    
    return ppa

async def get_ppa_by_id(ppa_id: str) -> Optional[PPA]:
    """Get a specific PPA by ID"""
    ppa_ref = db.collection('ppas').document(ppa_id)
    ppa_doc = await run_in_threadpool(ppa_ref.get)
    
    if ppa_doc.exists:
        return PPA(**ppa_doc.to_dict())
    return None

async def get_customer_ppas(customer_id: str) -> list[PPA]:
    """Get all PPAs for a customer"""
    ppas_ref = db.collection('ppas').where('customer_id', '==', customer_id)
    query_snapshot = await run_in_threadpool(ppas_ref.get)
    
    return [PPA(**doc.to_dict()) for doc in query_snapshot]

async def mark_ppa_as_signed(ppa_id: str) -> Optional[PPA]:
    """Mark a PPA as signed and activate it"""
    ppa_ref = db.collection('ppas').document(ppa_id)
    ppa_doc = await run_in_threadpool(ppa_ref.get)
    
    if not ppa_doc.exists:
        return None
        
    update_data = {
        'status': 'active',
        'signed_at': datetime.now(timezone.utc)
    }
    
    await run_in_threadpool(ppa_ref.update, update_data)
    
    # Return the updated PPA data
    updated_ppa_data = {**ppa_doc.to_dict(), **update_data}
    return PPA(**updated_ppa_data)

async def update_ppa_energy_production(ppa_id: str, energy_produced: float) -> Optional[PPA]:
    """Update the total energy production for a PPA"""
    ppa_ref = db.collection('ppas').document(ppa_id)
    ppa_doc = await run_in_threadpool(ppa_ref.get)
    
    if not ppa_doc.exists:
        return None
    
    ppa = PPA(**ppa_doc.to_dict())
    ppa.total_energy_produced += energy_produced
    
    update_data = {
        'total_energy_produced': ppa.total_energy_produced
    }
    
    await run_in_threadpool(ppa_ref.update, update_data)
    return ppa

async def update_ppa_billing(ppa_id: str, amount: float) -> Optional[PPA]:
    """Update the billing information for a PPA"""
    ppa_ref = db.collection('ppas').document(ppa_id)
    ppa_doc = await run_in_threadpool(ppa_ref.get)
    
    if not ppa_doc.exists:
        return None
    
    ppa = PPA(**ppa_doc.to_dict())
    ppa.total_billed += amount
    
    update_data = {
        'total_billed': ppa.total_billed,
        'last_billing_date': datetime.now(timezone.utc)
    }
    
    # Calculate next billing date
    if ppa.billing_terms.billing_cycle == "monthly":
        next_date = ppa.last_billing_date + timedelta(days=32)
        update_data['next_billing_date'] = next_date.replace(day=1)
    elif ppa.billing_terms.billing_cycle == "quarterly":
        next_date = ppa.last_billing_date + timedelta(days=92)
        update_data['next_billing_date'] = next_date.replace(day=1)
    
    await run_in_threadpool(ppa_ref.update, update_data)
    return ppa

async def update_ppa_payment(ppa_id: str, amount: float) -> Optional[PPA]:
    """Update the payment information for a PPA"""
    ppa_ref = db.collection('ppas').document(ppa_id)
    ppa_doc = await run_in_threadpool(ppa_ref.get)
    
    if not ppa_doc.exists:
        return None
    
    ppa = PPA(**ppa_doc.to_dict())
    ppa.total_paid += amount
    
    update_data = {
        'total_paid': ppa.total_paid
    }
    
    await run_in_threadpool(ppa_ref.update, update_data)
    return ppa 