from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, root_validator, validator
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
from enum import Enum

from firebase_config import db

# --- ENUMS ---
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

# --- BILLING TERMS ---
class Slab(BaseModel):
    min: float = Field(..., description="Minimum consumption for this slab (inclusive)")
    max: float = Field(..., description="Maximum consumption for this slab (exclusive)")
    rate: float = Field(..., description="Rate for this slab")
    unit: str = Field(..., description="Unit for this slab, e.g., kWh")

class ToURate(BaseModel):
    timeRange: str = Field(..., description="Time range, e.g., '22:00-06:00'")
    rate: float = Field(..., description="Rate for this time range")
    unit: str = Field(..., description="Unit, e.g., kWh")

class BillingTerms(BaseModel):
    tariff_rate: float = Field(..., description="Base tariff rate per kWh")
    escalation_rate: float = Field(..., description="Annual escalation rate")
    billing_cycle: str = Field(..., description="Billing cycle (monthly/quarterly/annually)")
    payment_terms: str = Field(..., description="Payment terms (net15/net30/net45/net60)")
    slabs: Optional[List[Slab]] = Field(None, description="Slab-based tariff structure")
    touRates: Optional[List[ToURate]] = Field(None, description="Time-of-Use pricing structure")
    taxRate: Optional[float] = Field(0, description="Tax rate as a percentage (e.g., 18 for 18%)")
    latePaymentPenaltyRate: Optional[float] = Field(0, description="Late payment penalty rate as a percentage (max 10%)")
    currency: str = Field("INR", description="Currency code, e.g., INR")
    subsidySchemeId: Optional[str] = Field(None, description="Linked subsidy or incentive scheme ID")
    autoInvoice: bool = Field(False, description="Whether to auto-generate invoices")
    gracePeriodDays: int = Field(0, description="Number of grace days before penalty applies")

    @validator('latePaymentPenaltyRate')
    def penalty_max_10(cls, v):
        if v is not None and v > 10:
            raise ValueError("latePaymentPenaltyRate cannot exceed 10%")
        return v

# --- SYSTEM SPECIFICATIONS ---
class SystemLocation(BaseModel):
    lat: float = Field(..., description="Latitude")
    long: float = Field(..., description="Longitude")

class SystemSpecifications(BaseModel):
    capacity_kw: float = Field(..., description="System capacity in kW")
    panel_type: str = Field(..., description="Type of solar panels")
    inverter_type: str = Field(..., description="Type of inverter")
    installation_date: datetime = Field(..., description="Date of installation")
    estimated_annual_production: float = Field(..., description="Estimated annual energy production in kWh")
    systemLocation: Optional[SystemLocation] = Field(None, description="System location (lat, long)")
    moduleManufacturer: Optional[str] = Field(None, description="Module manufacturer")
    inverterBrand: Optional[str] = Field(None, description="Inverter brand")
    expectedGeneration: Optional[float] = Field(None, description="Expected generation (kWh)")
    actualGeneration: Optional[float] = Field(None, description="Actual generation (kWh)")
    systemAgeInMonths: Optional[int] = Field(None, description="System age in months")

# --- CUSTOMER ---
class Customer(BaseModel):
    id: Optional[str] = None
    name: str
    email: str
    address: str
    customerType: CustomerType = Field(..., description="Type of customer")
    gstNumber: Optional[str] = Field(None, description="GST number or tax ID")
    linkedPPAs: List[str] = Field(default_factory=list, description="Array of active PPA IDs")

# --- ENERGY USAGE ---
class EnergyUsage(BaseModel):
    ppa_id: str
    kwh_used: float = Field(..., description="Energy used in kWh")
    reading_date: datetime = Field(..., description="Date of reading")
    source: Optional[str] = Field(None, description="Source of data, e.g., inverter, smart meter")
    unit: str = Field("kWh", description="Unit of measurement (kWh, MWh)")
    timestampStart: Optional[datetime] = Field(None, description="Start timestamp for interval")
    timestampEnd: Optional[datetime] = Field(None, description="End timestamp for interval")
    importEnergy: Optional[float] = Field(None, description="Imported energy (for net metering)")
    exportEnergy: Optional[float] = Field(None, description="Exported energy (for net metering)")

# --- SIGNATORY ---
class Signatory(BaseModel):
    name: str
    role: str
    signedAt: Optional[datetime] = None

# --- PPA ---
class PPA(BaseModel):
    id: Optional[str] = None
    customer_id: str
    system_specs: SystemSpecifications
    billing_terms: BillingTerms
    start_date: datetime
    end_date: datetime
    contractStatus: ContractStatus = ContractStatus.draft
    contractType: ContractType = ContractType.net_metering
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None
    createdBy: Optional[str] = None
    updatedBy: Optional[str] = None
    signed_at: Optional[datetime] = None
    signatories: List[Signatory] = Field(default_factory=list)
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
    pdfDownloadLink: Optional[str] = None
    terminationClause: Optional[str] = None
    paymentTerms: Optional[str] = None
    curtailmentClauses: Optional[str] = None
    generationGuarantees: Optional[str] = None
    subsidySchemeId: Optional[str] = None

    @property
    def status(self):
        return self.contractStatus

    def is_active(self) -> bool:
        """Check if the PPA is currently active"""
        now = datetime.now(timezone.utc)
        return (
            self.contractStatus == ContractStatus.active and
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
    """Generate a professional PDF PPA document following Indian standards and including all advanced fields."""
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.colors import HexColor, black, white
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.units import inch

    doc = SimpleDocTemplate(output_path, pagesize=A4, rightMargin=72, leftMargin=72, topMargin=72, bottomMargin=18)
    story = []
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('CustomTitle', parent=styles['Heading1'], fontSize=16, spaceAfter=30, alignment=TA_CENTER, textColor=HexColor('#2E86AB'))
    heading_style = ParagraphStyle('CustomHeading', parent=styles['Heading2'], fontSize=12, spaceAfter=12, spaceBefore=12, textColor=HexColor('#2E86AB'))
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
        ["Status", ppa.contractStatus.value.upper()],
        ["Contract Type", ppa.contractType.value],
        ["Created By", ppa.createdBy or "-"],
        ["Updated By", ppa.updatedBy or "-"],
        ["Last Updated", ppa.updated_at.strftime("%d/%m/%Y") if ppa.updated_at else "-"]
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
        ["Estimated Annual Production", f"{ppa.system_specs.estimated_annual_production:,.0f} kWh"],
        ["Location", f"{ppa.system_specs.systemLocation.lat}, {ppa.system_specs.systemLocation.long}" if ppa.system_specs.systemLocation else "-"],
        ["Module Manufacturer", ppa.system_specs.moduleManufacturer or "-"],
        ["Inverter Brand", ppa.system_specs.inverterBrand or "-"],
        ["Expected Generation", f"{ppa.system_specs.expectedGeneration} kWh" if ppa.system_specs.expectedGeneration else "-"],
        ["Actual Generation", f"{ppa.system_specs.actualGeneration} kWh" if ppa.system_specs.actualGeneration else "-"],
        ["System Age", f"{ppa.system_specs.systemAgeInMonths} months" if ppa.system_specs.systemAgeInMonths else "-"]
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
        ["Base Tariff Rate", f"{ppa.billing_terms.currency} {ppa.billing_terms.tariff_rate:.2f}/kWh"],
        ["Annual Escalation Rate", f"{ppa.billing_terms.escalation_rate*100:.1f}%"],
        ["Billing Cycle", ppa.billing_terms.billing_cycle.capitalize()],
        ["Payment Terms", ppa.billing_terms.payment_terms.upper()],
        ["Tax Rate", f"{ppa.billing_terms.taxRate}%" if ppa.billing_terms.taxRate else "-"],
        ["Late Payment Penalty", f"{ppa.billing_terms.latePaymentPenaltyRate}%" if ppa.billing_terms.latePaymentPenaltyRate else "-"],
        ["Currency", ppa.billing_terms.currency],
        ["Subsidy Scheme ID", ppa.billing_terms.subsidySchemeId or "-"],
        ["Auto Invoice", "Yes" if ppa.billing_terms.autoInvoice else "No"],
        ["Grace Period (days)", ppa.billing_terms.gracePeriodDays]
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
    story.append(Spacer(1, 10))

    # Slab-based Tariffs
    if ppa.billing_terms.slabs:
        story.append(Paragraph("Slab-based Tariffs", heading_style))
        slab_data = [["Min (kWh)", "Max (kWh)", "Rate", "Unit"]]
        for slab in ppa.billing_terms.slabs:
            slab_data.append([
                slab.min, slab.max, f"{ppa.billing_terms.currency} {slab.rate}", slab.unit
            ])
        slab_table = Table(slab_data, colWidths=[1.2*inch, 1.2*inch, 1.2*inch, 1.2*inch])
        slab_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), HexColor('#2E86AB')),
            ('TEXTCOLOR', (0, 0), (-1, 0), white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('BACKGROUND', (0, 1), (-1, -1), HexColor('#F8F9FA')),
            ('GRID', (0, 0), (-1, -1), 1, black),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [HexColor('#F8F9FA'), white])
        ]))
        story.append(slab_table)
        story.append(Spacer(1, 10))

    # ToU Pricing
    if ppa.billing_terms.touRates:
        story.append(Paragraph("Time-of-Use (ToU) Pricing", heading_style))
        tou_data = [["Time Range", "Rate", "Unit"]]
        for tou in ppa.billing_terms.touRates:
            tou_data.append([
                tou.timeRange, f"{ppa.billing_terms.currency} {tou.rate}", tou.unit
            ])
        tou_table = Table(tou_data, colWidths=[2*inch, 2*inch, 2*inch])
        tou_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), HexColor('#2E86AB')),
            ('TEXTCOLOR', (0, 0), (-1, 0), white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('BACKGROUND', (0, 1), (-1, -1), HexColor('#F8F9FA')),
            ('GRID', (0, 0), (-1, -1), 1, black),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [HexColor('#F8F9FA'), white])
        ]))
        story.append(tou_table)
        story.append(Spacer(1, 10))

    # Additional Clauses
    if ppa.terminationClause:
        story.append(Paragraph("Termination Clause", heading_style))
        story.append(Paragraph(ppa.terminationClause, normal_style))
        story.append(Spacer(1, 10))
    if ppa.curtailmentClauses:
        story.append(Paragraph("Curtailment Clauses", heading_style))
        story.append(Paragraph(ppa.curtailmentClauses, normal_style))
        story.append(Spacer(1, 10))
    if ppa.generationGuarantees:
        story.append(Paragraph("Generation Guarantees", heading_style))
        story.append(Paragraph(ppa.generationGuarantees, normal_style))
        story.append(Spacer(1, 10))

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

    # Signatories
    if ppa.signatories:
        story.append(Paragraph("5. SIGNATORIES", heading_style))
        signatory_data = [["Name", "Role", "Signed At"]]
        for s in ppa.signatories:
            signatory_data.append([
                s.name, s.role, s.signedAt.strftime("%d/%m/%Y") if s.signedAt else "-"
            ])
        signatory_table = Table(signatory_data, colWidths=[2*inch, 2*inch, 2*inch])
        signatory_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), HexColor('#2E86AB')),
            ('TEXTCOLOR', (0, 0), (-1, 0), white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('BACKGROUND', (0, 1), (-1, -1), HexColor('#F8F9FA')),
            ('GRID', (0, 0), (-1, -1), 1, black),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [HexColor('#F8F9FA'), white])
        ]))
        story.append(signatory_table)
        story.append(Spacer(1, 20))
    else:
        # Default signature blocks
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
        contractStatus=initial_status,
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
        'contractStatus': 'active',
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
    
    # Use last_billing_date if available, otherwise use start_date
    base_date = ppa.last_billing_date if ppa.last_billing_date is not None else ppa.start_date
    
    # Calculate next billing date
    if ppa.billing_terms.billing_cycle == "monthly":
        next_date = base_date + timedelta(days=32)
        update_data['next_billing_date'] = next_date.replace(day=1)
    elif ppa.billing_terms.billing_cycle == "quarterly":
        next_date = base_date + timedelta(days=92)
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