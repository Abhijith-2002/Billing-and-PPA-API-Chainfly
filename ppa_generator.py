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

class BusinessModel(str, Enum):
    """Business model for the PPA arrangement"""
    capex = "capex"  # Capital Expenditure - customer owns the system
    opex = "opex"    # Operational Expenditure - service provider owns the system

class EscalationType(str, Enum):
    """Type of escalation applied to tariff rates"""
    fixed_percentage = "fixed_percentage"  # Fixed percentage per year
    cpi_linked = "cpi_linked"              # Consumer Price Index linked
    wholesale_price_index = "wholesale_price_index"  # Wholesale price index linked
    custom_schedule = "custom_schedule"    # Custom escalation schedule

class TariffSource(str, Enum):
    """Source of tariff data"""
    discom_api = "discom_api"              # Real-time from DISCOM API
    regulatory_order = "regulatory_order"  # From regulatory commission orders
    manual_override = "manual_override"    # Manually entered override
    calculated = "calculated"              # Calculated based on rules

class TariffCategory(str, Enum):
    """Tariff categories for different customer types and consumption levels"""
    residential_low = "residential_low"      # Residential low consumption
    residential_high = "residential_high"    # Residential high consumption
    commercial_small = "commercial_small"    # Small commercial
    commercial_large = "commercial_large"    # Large commercial
    industrial_lt = "industrial_lt"          # Industrial LT
    industrial_ht = "industrial_ht"          # Industrial HT
    agricultural = "agricultural"            # Agricultural
    government = "government"                # Government institutions
    street_light = "street_light"            # Street lighting
    solar_rooftop = "solar_rooftop"          # Solar rooftop specific
    solar_utility = "solar_utility"          # Solar utility scale

class StateCode(str, Enum):
    """Indian state codes for subsidy schemes"""
    AP = "AP"  # Andhra Pradesh
    AR = "AR"  # Arunachal Pradesh
    AS = "AS"  # Assam
    BR = "BR"  # Bihar
    CT = "CT"  # Chhattisgarh
    GA = "GA"  # Goa
    GJ = "GJ"  # Gujarat
    HR = "HR"  # Haryana
    HP = "HP"  # Himachal Pradesh
    JH = "JH"  # Jharkhand
    KA = "KA"  # Karnataka
    KL = "KL"  # Kerala
    MP = "MP"  # Madhya Pradesh
    MH = "MH"  # Maharashtra
    MN = "MN"  # Manipur
    ML = "ML"  # Meghalaya
    MZ = "MZ"  # Mizoram
    NL = "NL"  # Nagaland
    OR = "OR"  # Odisha
    PB = "PB"  # Punjab
    RJ = "RJ"  # Rajasthan
    SK = "SK"  # Sikkim
    TN = "TN"  # Tamil Nadu
    TS = "TS"  # Telangana
    TR = "TR"  # Tripura
    UP = "UP"  # Uttar Pradesh
    UT = "UT"  # Uttarakhand
    WB = "WB"  # West Bengal
    DL = "DL"  # Delhi
    JK = "JK"  # Jammu & Kashmir
    LA = "LA"  # Ladakh
    CH = "CH"  # Chandigarh
    DN = "DN"  # Dadra & Nagar Haveli
    DD = "DD"  # Daman & Diu
    AN = "AN"  # Andaman & Nicobar Islands
    PY = "PY"  # Puducherry

# --- DISCOM AND TARIFF MODELS ---
class DISCOM(BaseModel):
    """Distribution Company information"""
    discom_id: str = Field(..., description="Unique identifier for the DISCOM")
    discom_name: str = Field(..., description="Name of the distribution company")
    state_code: StateCode = Field(..., description="State where DISCOM operates")
    license_number: Optional[str] = Field(None, description="DISCOM license number")
    website: Optional[str] = Field(None, description="DISCOM website URL")
    api_endpoint: Optional[str] = Field(None, description="DISCOM API endpoint for tariff data")
    api_key: Optional[str] = Field(None, description="API key for DISCOM tariff API")
    tariff_update_frequency: str = Field("monthly", description="How often tariffs are updated")
    last_tariff_update: Optional[datetime] = Field(None, description="Last tariff update timestamp")
    is_active: bool = Field(True, description="Whether DISCOM is active")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = Field(None, description="Last update timestamp")

class TariffStructure(BaseModel):
    """Tariff structure for a specific category and DISCOM"""
    tariff_id: str = Field(..., description="Unique identifier for the tariff")
    discom_id: str = Field(..., description="DISCOM identifier")
    state_code: StateCode = Field(..., description="State code")
    tariff_category: TariffCategory = Field(..., description="Tariff category")
    customer_type: CustomerType = Field(..., description="Customer type")
    base_rate: float = Field(..., description="Base tariff rate per kWh")
    currency: str = Field("INR", description="Currency for the tariff")
    effective_from: datetime = Field(..., description="When this tariff becomes effective")
    effective_until: Optional[datetime] = Field(None, description="When this tariff expires")
    regulatory_order: Optional[str] = Field(None, description="Regulatory order reference")
    order_number: Optional[str] = Field(None, description="Regulatory order number")
    order_date: Optional[datetime] = Field(None, description="Regulatory order date")
    source: TariffSource = Field(TariffSource.regulatory_order, description="Source of tariff data")
    is_active: bool = Field(True, description="Whether tariff is currently active")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = Field(None, description="Last update timestamp")

class TariffSlab(BaseModel):
    """Tariff slab for tiered pricing"""
    slab_id: str = Field(..., description="Unique identifier for the slab")
    tariff_id: str = Field(..., description="Associated tariff ID")
    min_consumption: float = Field(..., description="Minimum consumption for this slab (inclusive)")
    max_consumption: Optional[float] = Field(None, description="Maximum consumption for this slab (exclusive)")
    rate: float = Field(..., description="Rate per kWh for this slab")
    unit: str = Field("INR/kWh", description="Unit for the rate")
    description: Optional[str] = Field(None, description="Description of the slab")
    is_active: bool = Field(True, description="Whether slab is active")

class TimeOfUseTariff(BaseModel):
    """Time-of-Use tariff rates"""
    tou_id: str = Field(..., description="Unique identifier for ToU tariff")
    tariff_id: str = Field(..., description="Associated tariff ID")
    time_range: str = Field(..., description="Time range in 24-hour format (HH:MM-HH:MM)")
    rate: float = Field(..., description="Rate per kWh for this time period")
    unit: str = Field("INR/kWh", description="Unit for the rate")
    season: Optional[str] = Field(None, description="Season (summer, winter, monsoon)")
    day_type: Optional[str] = Field(None, description="Day type (weekday, weekend, holiday)")
    description: Optional[str] = Field(None, description="Description of the ToU period")
    is_active: bool = Field(True, description="Whether ToU tariff is active")

class DynamicTariffRequest(BaseModel):
    """Request for dynamic tariff calculation"""
    discom_id: str = Field(..., description="DISCOM identifier")
    state_code: StateCode = Field(..., description="State code")
    tariff_category: TariffCategory = Field(..., description="Tariff category")
    customer_type: CustomerType = Field(..., description="Customer type")
    consumption_kwh: Optional[float] = Field(None, description="Monthly consumption in kWh")
    contract_date: datetime = Field(..., description="Contract date for tariff calculation")
    include_slabs: bool = Field(True, description="Whether to include tariff slabs")
    include_tou: bool = Field(True, description="Whether to include time-of-use rates")

class DynamicTariffResponse(BaseModel):
    """Response for dynamic tariff calculation"""
    tariff_id: str = Field(..., description="Tariff identifier")
    discom_name: str = Field(..., description="DISCOM name")
    state_code: StateCode = Field(..., description="State code")
    tariff_category: TariffCategory = Field(..., description="Tariff category")
    customer_type: CustomerType = Field(..., description="Customer type")
    base_rate: float = Field(..., description="Base tariff rate per kWh")
    currency: str = Field(..., description="Currency for the tariff")
    effective_from: datetime = Field(..., description="When tariff becomes effective")
    effective_until: Optional[datetime] = Field(None, description="When tariff expires")
    regulatory_order: Optional[str] = Field(None, description="Regulatory order reference")
    source: TariffSource = Field(..., description="Source of tariff data")
    slabs: Optional[List[TariffSlab]] = Field(None, description="Tariff slabs if applicable")
    tou_rates: Optional[List[TimeOfUseTariff]] = Field(None, description="Time-of-use rates if applicable")
    calculated_rate: Optional[float] = Field(None, description="Calculated rate based on consumption")
    last_updated: datetime = Field(..., description="When tariff was last updated")
    next_update: Optional[datetime] = Field(None, description="When tariff will be updated next")

# --- ESCALATION SCHEDULE ---
class EscalationSchedule(BaseModel):
    """Custom escalation schedule for tariff rates"""
    year: int = Field(..., description="Year from contract start (1, 2, 3, etc.)")
    escalation_rate: float = Field(..., description="Escalation rate for this year (e.g., 0.03 for 3%)")
    description: Optional[str] = Field(None, description="Description of the escalation")

# --- SUBSIDY SCHEME ---
class SubsidyScheme(BaseModel):
    """State-specific subsidy scheme details"""
    scheme_id: str = Field(..., description="Unique identifier for the subsidy scheme")
    scheme_name: str = Field(..., description="Name of the subsidy scheme")
    state_code: StateCode = Field(..., description="State where the scheme is applicable")
    subsidy_type: str = Field(..., description="Type of subsidy (e.g., 'capital', 'generation', 'tax')")
    subsidy_rate: float = Field(..., description="Subsidy rate as percentage or fixed amount")
    subsidy_unit: str = Field(..., description="Unit for subsidy (e.g., '%', 'INR/kW', 'INR/kWh')")
    max_capacity_kw: Optional[float] = Field(None, description="Maximum system capacity eligible for subsidy")
    min_capacity_kw: Optional[float] = Field(0, description="Minimum system capacity eligible for subsidy")
    valid_from: datetime = Field(..., description="Scheme validity start date")
    valid_until: Optional[datetime] = Field(None, description="Scheme validity end date")
    description: Optional[str] = Field(None, description="Detailed description of the scheme")
    documentation_url: Optional[str] = Field(None, description="URL to official documentation")

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
    escalation_type: EscalationType = Field(EscalationType.fixed_percentage, description="Type of escalation applied")
    escalation_rate: float = Field(..., description="Annual escalation rate")
    escalation_schedule: Optional[List[EscalationSchedule]] = Field(None, description="Custom escalation schedule")
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
    
    # CAPEX vs OPEX specific fields
    business_model: BusinessModel = Field(BusinessModel.capex, description="Business model (CAPEX or OPEX)")
    capex_amount: Optional[float] = Field(None, description="Total CAPEX amount in currency units")
    opex_monthly_fee: Optional[float] = Field(None, description="Monthly OPEX fee in currency units")
    opex_energy_rate: Optional[float] = Field(None, description="Energy rate for OPEX model in currency/kWh")
    maintenance_included: bool = Field(True, description="Whether maintenance is included in the model")
    insurance_included: bool = Field(True, description="Whether insurance is included in the model")

    @validator('latePaymentPenaltyRate')
    def penalty_max_10(cls, v):
        if v is not None and v > 10:
            raise ValueError("latePaymentPenaltyRate cannot exceed 10%")
        return v

    @validator('escalation_schedule')
    def validate_escalation_schedule(cls, v):
        if v is not None:
            years = [schedule.year for schedule in v]
            if len(years) != len(set(years)):
                raise ValueError("Escalation schedule years must be unique")
            if min(years) < 1:
                raise ValueError("Escalation schedule years must start from 1")
        return v

    @root_validator
    def validate_business_model_fields(cls, values):
        business_model = values.get('business_model')
        capex_amount = values.get('capex_amount')
        opex_monthly_fee = values.get('opex_monthly_fee')
        opex_energy_rate = values.get('opex_energy_rate')
        
        if business_model == BusinessModel.capex:
            if capex_amount is None or capex_amount <= 0:
                raise ValueError("CAPEX amount must be specified and greater than 0 for CAPEX model")
        elif business_model == BusinessModel.opex:
            if opex_monthly_fee is None or opex_monthly_fee <= 0:
                raise ValueError("OPEX monthly fee must be specified and greater than 0 for OPEX model")
            if opex_energy_rate is None or opex_energy_rate <= 0:
                raise ValueError("OPEX energy rate must be specified and greater than 0 for OPEX model")
        
        return values

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
    
    # Enhanced fields for business model and tenure
    business_model: BusinessModel = Field(BusinessModel.capex, description="Business model (CAPEX or OPEX)")
    tenure_years: float = Field(..., description="Contract tenure in years")
    subsidy_applied: Optional[float] = Field(None, description="Subsidy amount applied to the PPA")
    subsidy_details: Optional[dict] = Field(None, description="Detailed subsidy information")
    escalation_history: List[dict] = Field(default_factory=list, description="History of tariff escalations")
    capex_payment_schedule: Optional[List[dict]] = Field(None, description="CAPEX payment schedule")
    opex_payment_history: List[dict] = Field(default_factory=list, description="OPEX payment history")

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
        """Calculate the current tariff rate based on escalation type and schedule"""
        if not self.is_active():
            return 0
        
        years_elapsed = (current_date - self.start_date).days / 365.25
        current_year = int(years_elapsed) + 1
        
        if self.billing_terms.escalation_type == EscalationType.fixed_percentage:
            # Fixed percentage escalation
            escalation_periods = int(years_elapsed)
            current_rate = self.billing_terms.tariff_rate
            for _ in range(escalation_periods):
                current_rate *= (1 + self.billing_terms.escalation_rate)
            return round(current_rate, 4)
        
        elif self.billing_terms.escalation_type == EscalationType.custom_schedule:
            # Custom escalation schedule
            if not self.billing_terms.escalation_schedule:
                return self.billing_terms.tariff_rate
            
            current_rate = self.billing_terms.tariff_rate
            for schedule in self.billing_terms.escalation_schedule:
                if schedule.year <= current_year:
                    current_rate *= (1 + schedule.escalation_rate)
                    # Record escalation in history
                    self._record_escalation(schedule.year, schedule.escalation_rate, current_rate)
            
            return round(current_rate, 4)
        
        elif self.billing_terms.escalation_type == EscalationType.cpi_linked:
            # CPI-linked escalation (placeholder for future implementation)
            # This would require external CPI data
            return self.billing_terms.tariff_rate
        
        elif self.billing_terms.escalation_type == EscalationType.wholesale_price_index:
            # Wholesale price index linked (placeholder for future implementation)
            # This would require external wholesale price data
            return self.billing_terms.tariff_rate
        
        return self.billing_terms.tariff_rate

    def _record_escalation(self, year: int, escalation_rate: float, new_rate: float):
        """Record escalation in history"""
        escalation_record = {
            "year": year,
            "escalation_rate": escalation_rate,
            "new_tariff_rate": new_rate,
            "date_applied": datetime.now(timezone.utc)
        }
        
        # Check if escalation for this year already exists
        existing = next((e for e in self.escalation_history if e["year"] == year), None)
        if not existing:
            self.escalation_history.append(escalation_record)

    def calculate_subsidy_amount(self, system_capacity_kw: float) -> float:
        """Calculate subsidy amount based on applicable subsidy scheme"""
        if not self.subsidySchemeId:
            return 0.0
        
        # This would typically fetch subsidy details from database
        # For now, return a placeholder calculation
        # In real implementation, you would:
        # 1. Fetch subsidy scheme details from database
        # 2. Check if system capacity is within eligible range
        # 3. Calculate subsidy based on type and rate
        
        return 0.0

    def calculate_capex_payment_schedule(self) -> List[dict]:
        """Calculate CAPEX payment schedule"""
        if self.business_model != BusinessModel.capex or not self.billing_terms.capex_amount:
            return []
        
        total_amount = self.billing_terms.capex_amount
        # Default: 20% upfront, 80% on completion
        schedule = [
            {
                "installment": 1,
                "percentage": 20.0,
                "amount": total_amount * 0.2,
                "due_date": self.start_date,
                "description": "Upfront payment"
            },
            {
                "installment": 2,
                "percentage": 80.0,
                "amount": total_amount * 0.8,
                "due_date": self.start_date + timedelta(days=30),
                "description": "Balance payment"
            }
        ]
        
        return schedule

    def calculate_opex_monthly_payment(self, energy_consumed_kwh: float) -> float:
        """Calculate monthly OPEX payment"""
        if self.business_model != BusinessModel.opex:
            return 0.0
        
        monthly_fee = self.billing_terms.opex_monthly_fee or 0.0
        energy_cost = (self.billing_terms.opex_energy_rate or 0.0) * energy_consumed_kwh
        
        return monthly_fee + energy_cost

    def get_tenure_remaining(self) -> float:
        """Get remaining tenure in years"""
        now = datetime.now(timezone.utc)
        if now > self.end_date:
            return 0.0
        
        remaining_days = (self.end_date - now).days
        return remaining_days / 365.25

    def is_eligible_for_subsidy(self, system_capacity_kw: float, state_code: StateCode) -> bool:
        """Check if PPA is eligible for subsidy based on capacity and state"""
        if not self.subsidySchemeId:
            return False
        
        # This would typically check against subsidy scheme database
        # For now, return True as placeholder
        return True

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

    def add_opex_payment(self, amount: float, payment_date: datetime, energy_consumed: float):
        """Add OPEX payment record"""
        self.opex_payment_history.append({
            "amount": amount,
            "date": payment_date,
            "energy_consumed": energy_consumed,
            "monthly_fee": self.billing_terms.opex_monthly_fee or 0.0,
            "energy_cost": amount - (self.billing_terms.opex_monthly_fee or 0.0)
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

# --- DYNAMIC TARIFF FUNCTIONS ---
async def get_dynamic_tariff(request: DynamicTariffRequest) -> DynamicTariffResponse:
    """
    Get dynamic tariff based on DISCOM, state, and customer type.
    
    This function attempts to retrieve the most current tariff from:
    1. DISCOM API (if available and configured)
    2. Regulatory order database
    3. Manual override
    4. Calculated based on rules
    """
    try:
        # First, try to get from DISCOM API if configured
        if await is_discom_api_available(request.discom_id):
            tariff_data = await fetch_tariff_from_discom_api(request)
            if tariff_data:
                return tariff_data
        
        # Fallback to database lookup
        tariff_data = await get_tariff_from_database(request)
        if tariff_data:
            return tariff_data
        
        # If no tariff found, calculate based on rules
        calculated_tariff = await calculate_tariff_based_on_rules(request)
        return calculated_tariff
        
    except Exception as e:
        # Log error and return fallback tariff
        print(f"Error getting dynamic tariff: {str(e)}")
        return await get_fallback_tariff(request)

async def is_discom_api_available(discom_id: str) -> bool:
    """Check if DISCOM API is available and configured"""
    try:
        discom_ref = db.collection('discoms').document(discom_id)
        discom_doc = await run_in_threadpool(discom_ref.get)
        
        if not discom_doc.exists:
            return False
        
        discom_data = discom_doc.to_dict()
        return (
            discom_data.get('is_active', False) and
            discom_data.get('api_endpoint') and
            discom_data.get('api_key')
        )
    except Exception:
        return False

async def fetch_tariff_from_discom_api(request: DynamicTariffRequest) -> Optional[DynamicTariffResponse]:
    """Fetch tariff from DISCOM API"""
    try:
        # Get DISCOM configuration
        discom_ref = db.collection('discoms').document(request.discom_id)
        discom_doc = await run_in_threadpool(discom_ref.get)
        
        if not discom_doc.exists:
            return None
        
        discom_data = discom_doc.to_dict()
        api_endpoint = discom_data.get('api_endpoint')
        api_key = discom_data.get('api_key')
        
        if not api_endpoint or not api_key:
            return None
        
        # Prepare API request
        api_request = {
            "state_code": request.state_code.value,
            "tariff_category": request.tariff_category.value,
            "customer_type": request.customer_type.value,
            "consumption_kwh": request.consumption_kwh,
            "contract_date": request.contract_date.isoformat(),
            "include_slabs": request.include_slabs,
            "include_tou": request.include_tou
        }
        
        # Make API call (this would be implemented based on specific DISCOM API)
        # For now, we'll simulate the API call
        tariff_data = await call_discom_api(api_endpoint, api_key, api_request)
        
        if tariff_data:
            # Store the fetched tariff in database for caching
            await store_tariff_in_database(tariff_data)
            return tariff_data
        
        return None
        
    except Exception as e:
        print(f"Error fetching from DISCOM API: {str(e)}")
        return None

async def call_discom_api(api_endpoint: str, api_key: str, request_data: dict) -> Optional[DynamicTariffResponse]:
    """
    Call DISCOM API to get tariff data.
    This is a placeholder implementation - actual implementation would depend on specific DISCOM APIs.
    """
    try:
        import aiohttp
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(api_endpoint, json=request_data, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    # Parse DISCOM API response and convert to DynamicTariffResponse
                    # This would be customized based on actual DISCOM API response format
                    return parse_discom_api_response(data)
                else:
                    print(f"DISCOM API error: {response.status}")
                    return None
                    
    except Exception as e:
        print(f"Error calling DISCOM API: {str(e)}")
        return None

def parse_discom_api_response(api_data: dict) -> DynamicTariffResponse:
    """
    Parse DISCOM API response and convert to DynamicTariffResponse.
    This would be customized based on actual DISCOM API response format.
    """
    # This is a sample implementation - actual parsing would depend on DISCOM API format
    return DynamicTariffResponse(
        tariff_id=f"discom_{api_data.get('tariff_id', 'unknown')}",
        discom_name=api_data.get('discom_name', 'Unknown'),
        state_code=StateCode(api_data.get('state_code', 'DL')),
        tariff_category=TariffCategory(api_data.get('tariff_category', 'residential_low')),
        customer_type=CustomerType(api_data.get('customer_type', 'residential')),
        base_rate=float(api_data.get('base_rate', 0.0)),
        currency=api_data.get('currency', 'INR'),
        effective_from=datetime.fromisoformat(api_data.get('effective_from', datetime.now(timezone.utc).isoformat())),
        effective_until=datetime.fromisoformat(api_data.get('effective_until')) if api_data.get('effective_until') else None,
        regulatory_order=api_data.get('regulatory_order'),
        source=TariffSource.discom_api,
        slabs=None,  # Parse slabs if provided
        tou_rates=None,  # Parse ToU rates if provided
        calculated_rate=float(api_data.get('calculated_rate', 0.0)),
        last_updated=datetime.now(timezone.utc),
        next_update=None
    )

async def get_tariff_from_database(request: DynamicTariffRequest) -> Optional[DynamicTariffResponse]:
    """Get tariff from database based on request parameters"""
    try:
        # Query for active tariff matching the criteria
        tariffs_ref = db.collection('tariffs').where('discom_id', '==', request.discom_id)\
            .where('state_code', '==', request.state_code.value)\
            .where('tariff_category', '==', request.tariff_category.value)\
            .where('customer_type', '==', request.customer_type.value)\
            .where('is_active', '==', True)
        
        tariffs = await run_in_threadpool(tariffs_ref.get)
        
        if not tariffs:
            return None
        
        # Find the most recent effective tariff
        current_date = request.contract_date
        best_tariff = None
        
        for doc in tariffs:
            tariff_data = doc.to_dict()
            effective_from = tariff_data.get('effective_from')
            effective_until = tariff_data.get('effective_until')
            
            if effective_from and effective_from <= current_date:
                if not effective_until or effective_until >= current_date:
                    if not best_tariff or effective_from > best_tariff.get('effective_from'):
                        best_tariff = tariff_data
        
        if not best_tariff:
            return None
        
        # Get associated slabs and ToU rates if requested
        slabs = None
        tou_rates = None
        
        if request.include_slabs:
            slabs = await get_tariff_slabs(best_tariff['tariff_id'])
        
        if request.include_tou:
            tou_rates = await get_tariff_tou_rates(best_tariff['tariff_id'])
        
        # Calculate rate based on consumption if provided
        calculated_rate = None
        if request.consumption_kwh and slabs:
            calculated_rate = calculate_slab_rate(request.consumption_kwh, slabs)
        
        return DynamicTariffResponse(
            tariff_id=best_tariff['tariff_id'],
            discom_name=best_tariff.get('discom_name', 'Unknown'),
            state_code=StateCode(best_tariff['state_code']),
            tariff_category=TariffCategory(best_tariff['tariff_category']),
            customer_type=CustomerType(best_tariff['customer_type']),
            base_rate=best_tariff['base_rate'],
            currency=best_tariff.get('currency', 'INR'),
            effective_from=best_tariff['effective_from'],
            effective_until=best_tariff.get('effective_until'),
            regulatory_order=best_tariff.get('regulatory_order'),
            source=TariffSource(best_tariff.get('source', 'regulatory_order')),
            slabs=slabs,
            tou_rates=tou_rates,
            calculated_rate=calculated_rate,
            last_updated=best_tariff.get('updated_at', best_tariff['created_at']),
            next_update=None
        )
        
    except Exception as e:
        print(f"Error getting tariff from database: {str(e)}")
        return None

async def get_tariff_slabs(tariff_id: str) -> Optional[List[TariffSlab]]:
    """Get tariff slabs for a specific tariff"""
    try:
        slabs_ref = db.collection('tariff_slabs').where('tariff_id', '==', tariff_id)\
            .where('is_active', '==', True)
        slabs = await run_in_threadpool(slabs_ref.get)
        
        return [TariffSlab(**doc.to_dict()) for doc in slabs]
    except Exception:
        return None

async def get_tariff_tou_rates(tariff_id: str) -> Optional[List[TimeOfUseTariff]]:
    """Get time-of-use rates for a specific tariff"""
    try:
        tou_ref = db.collection('tou_tariffs').where('tariff_id', '==', tariff_id)\
            .where('is_active', '==', True)
        tou_rates = await run_in_threadpool(tou_ref.get)
        
        return [TimeOfUseTariff(**doc.to_dict()) for doc in tou_rates]
    except Exception:
        return None

def calculate_slab_rate(consumption_kwh: float, slabs: List[TariffSlab]) -> float:
    """Calculate effective rate based on consumption and slabs"""
    for slab in slabs:
        if slab.min_consumption <= consumption_kwh:
            if not slab.max_consumption or consumption_kwh < slab.max_consumption:
                return slab.rate
    
    # If no slab matches, return the last slab rate
    return slabs[-1].rate if slabs else 0.0

async def calculate_tariff_based_on_rules(request: DynamicTariffRequest) -> DynamicTariffResponse:
    """Calculate tariff based on predefined rules when no tariff is found"""
    # This would implement business rules for tariff calculation
    # For now, return a default tariff based on customer type
    
    base_rates = {
        CustomerType.residential: 8.0,
        CustomerType.commercial: 10.0,
        CustomerType.ci: 12.0,
        CustomerType.industrial: 14.0,
        CustomerType.government: 9.0,
        CustomerType.other: 10.0
    }
    
    base_rate = base_rates.get(request.customer_type, 10.0)
    
    return DynamicTariffResponse(
        tariff_id=f"calculated_{request.discom_id}_{request.state_code.value}",
        discom_name="Calculated",
        state_code=request.state_code,
        tariff_category=request.tariff_category,
        customer_type=request.customer_type,
        base_rate=base_rate,
        currency="INR",
        effective_from=datetime.now(timezone.utc),
        effective_until=None,
        regulatory_order=None,
        source=TariffSource.calculated,
        slabs=None,
        tou_rates=None,
        calculated_rate=base_rate,
        last_updated=datetime.now(timezone.utc),
        next_update=None
    )

async def get_fallback_tariff(request: DynamicTariffRequest) -> DynamicTariffResponse:
    """Get fallback tariff when all other methods fail"""
    return DynamicTariffResponse(
        tariff_id="fallback",
        discom_name="Fallback",
        state_code=request.state_code,
        tariff_category=request.tariff_category,
        customer_type=request.customer_type,
        base_rate=10.0,  # Default fallback rate
        currency="INR",
        effective_from=datetime.now(timezone.utc),
        effective_until=None,
        regulatory_order=None,
        source=TariffSource.manual_override,
        slabs=None,
        tou_rates=None,
        calculated_rate=10.0,
        last_updated=datetime.now(timezone.utc),
        next_update=None
    )

async def store_tariff_in_database(tariff_data: DynamicTariffResponse):
    """Store tariff data in database for caching"""
    try:
        tariff_ref = db.collection('tariffs').document(tariff_data.tariff_id)
        tariff_dict = tariff_data.model_dump()
        tariff_dict['created_at'] = datetime.now(timezone.utc)
        
        await run_in_threadpool(tariff_ref.set, tariff_dict)
        
        # Store slabs if present
        if tariff_data.slabs:
            for slab in tariff_data.slabs:
                slab_ref = db.collection('tariff_slabs').document(slab.slab_id)
                await run_in_threadpool(slab_ref.set, slab.model_dump())
        
        # Store ToU rates if present
        if tariff_data.tou_rates:
            for tou in tariff_data.tou_rates:
                tou_ref = db.collection('tou_tariffs').document(tou.tou_id)
                await run_in_threadpool(tou_ref.set, tou.model_dump())
                
    except Exception as e:
        print(f"Error storing tariff in database: {str(e)}")

async def update_discom_tariffs(discom_id: str):
    """Update tariffs for a specific DISCOM from their API"""
    try:
        # Get DISCOM configuration
        discom_ref = db.collection('discoms').document(discom_id)
        discom_doc = await run_in_threadpool(discom_ref.get)
        
        if not discom_doc.exists:
            return False
        
        discom_data = discom_doc.to_dict()
        
        # Check if update is needed
        last_update = discom_data.get('last_tariff_update')
        update_frequency = discom_data.get('tariff_update_frequency', 'monthly')
        
        if last_update:
            last_update_date = last_update if isinstance(last_update, datetime) else datetime.fromisoformat(last_update)
            days_since_update = (datetime.now(timezone.utc) - last_update_date).days
            
            if update_frequency == 'monthly' and days_since_update < 30:
                return True  # No update needed
            elif update_frequency == 'quarterly' and days_since_update < 90:
                return True  # No update needed
        
        # Fetch new tariffs from DISCOM API
        # This would implement the actual DISCOM API integration
        success = await fetch_and_store_discom_tariffs(discom_id)
        
        if success:
            # Update last tariff update timestamp
            await run_in_threadpool(discom_ref.update, {
                'last_tariff_update': datetime.now(timezone.utc)
            })
        
        return success
        
    except Exception as e:
        print(f"Error updating DISCOM tariffs: {str(e)}")
        return False

async def fetch_and_store_discom_tariffs(discom_id: str) -> bool:
    """Fetch and store tariffs from DISCOM API"""
    # This would implement the actual DISCOM API integration
    # For now, return True as placeholder
    return True 