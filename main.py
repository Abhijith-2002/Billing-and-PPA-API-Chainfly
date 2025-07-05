from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, BackgroundTasks, Form, Request
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.concurrency import run_in_threadpool
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone, timedelta
import os
import tempfile
from pydantic import BaseModel, Field, validator, root_validator
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
    update_ppa_payment, SystemLocation, Signatory,
    get_dynamic_tariff, update_discom_tariffs
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
    """Customer type classification for billing and regulatory purposes."""
    residential = "residential"
    commercial = "commercial"
    ci = "C&I"
    industrial = "industrial"
    government = "government"
    other = "other"

class ContractType(str, Enum):
    """Type of power purchase agreement contract."""
    net_metering = "net_metering"
    gross_metering = "gross_metering"
    open_access = "open_access"

class ContractStatus(str, Enum):
    """Current status of the PPA contract."""
    draft = "draft"
    active = "active"
    expired = "expired"
    terminated = "terminated"

class BusinessModel(str, Enum):
    """Business model for the PPA arrangement."""
    capex = "capex"  # Capital Expenditure - customer owns the system
    opex = "opex"    # Operational Expenditure - service provider owns the system

class EscalationType(str, Enum):
    """Type of escalation applied to tariff rates."""
    fixed_percentage = "fixed_percentage"  # Fixed percentage per year
    cpi_linked = "cpi_linked"              # Consumer Price Index linked
    wholesale_price_index = "wholesale_price_index"  # Wholesale price index linked
    custom_schedule = "custom_schedule"    # Custom escalation schedule

class TariffSource(str, Enum):
    """Source of tariff data."""
    discom_api = "discom_api"              # Real-time from DISCOM API
    regulatory_order = "regulatory_order"  # From regulatory commission orders
    manual_override = "manual_override"    # Manually entered override
    calculated = "calculated"              # Calculated based on rules

class TariffCategory(str, Enum):
    """Tariff categories for different customer types and consumption levels."""
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
    """Indian state codes for subsidy schemes."""
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

# Models
class Customer(BaseModel):
    """Customer information model."""
    name: str = Field(..., description="Full name of the customer", example="John Doe")
    email: str = Field(..., description="Email address for communication and billing", example="john.doe@example.com")
    address: str = Field(..., description="Complete postal address of the customer", example="123 Solar Street, Green City, 12345")

class EscalationScheduleRequest(BaseModel):
    """Custom escalation schedule for tariff rates."""
    year: int = Field(..., description="Year from contract start (1, 2, 3, etc.)", example=1)
    escalation_rate: float = Field(..., description="Escalation rate for this year (e.g., 0.03 for 3%)", example=0.03)
    description: Optional[str] = Field(None, description="Description of the escalation", example="First year escalation")

class SlabRequest(BaseModel):
    """Energy consumption slab for tiered billing."""
    min: float = Field(..., description="Minimum consumption for this slab (inclusive) in kWh", example=0.0)
    max: float = Field(..., description="Maximum consumption for this slab (exclusive) in kWh", example=100.0)
    rate: float = Field(..., description="Rate per kWh for this consumption slab in currency units", example=8.5)
    unit: str = Field(..., description="Unit for this slab rate (e.g., 'INR/kWh', 'USD/kWh')", example="INR/kWh")

class ToURateRequest(BaseModel):
    """Time-of-Use rate for different time periods."""
    timeRange: str = Field(..., description="Time range in 24-hour format (HH:MM-HH:MM)", example="22:00-06:00")
    rate: float = Field(..., description="Rate per kWh for this time period in currency units", example=6.5)
    unit: str = Field(..., description="Unit for this rate (e.g., 'INR/kWh', 'USD/kWh')", example="INR/kWh")

class BillingTermsRequest(BaseModel):
    """Billing terms and conditions for the PPA."""
    tariff_rate: float = Field(..., description="Base tariff rate per kWh in currency units", example=8.0)
    escalation_type: EscalationType = Field(EscalationType.fixed_percentage, description="Type of escalation applied")
    escalation_rate: float = Field(..., description="Annual escalation rate as decimal (e.g., 0.02 for 2%)", example=0.02)
    escalation_schedule: Optional[List[EscalationScheduleRequest]] = Field(None, description="Custom escalation schedule")
    billing_cycle: str = Field(..., description="Billing cycle frequency", example="monthly")
    payment_terms: str = Field(..., description="Payment terms in days (net15/net30/net45/net60)", example="net30")
    slabs: Optional[List[SlabRequest]] = Field(None, description="Tiered billing slabs for different consumption levels")
    touRates: Optional[List[ToURateRequest]] = Field(None, description="Time-of-Use rates for different time periods")
    taxRate: Optional[float] = Field(0, description="Tax rate as percentage (e.g., 18.0 for 18%)", example=18.0)
    latePaymentPenaltyRate: Optional[float] = Field(0, description="Late payment penalty rate as percentage (max 10%)", example=2.0)
    currency: str = Field("INR", description="Currency code for billing", example="INR")
    subsidySchemeId: Optional[str] = Field(None, description="Reference to applicable subsidy scheme", example="SUBSIDY_2024_001")
    autoInvoice: bool = Field(False, description="Whether invoices should be generated automatically")
    gracePeriodDays: int = Field(0, description="Grace period in days before late payment penalties apply", example=7)
    
    # CAPEX vs OPEX specific fields
    business_model: BusinessModel = Field(BusinessModel.capex, description="Business model (CAPEX or OPEX)")
    capex_amount: Optional[float] = Field(None, description="Total CAPEX amount in currency units", example=500000.0)
    opex_monthly_fee: Optional[float] = Field(None, description="Monthly OPEX fee in currency units", example=5000.0)
    opex_energy_rate: Optional[float] = Field(None, description="Energy rate for OPEX model in currency/kWh", example=6.5)
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

class SystemLocationRequest(BaseModel):
    """Geographic location of the solar system."""
    lat: float = Field(..., description="Latitude in decimal degrees (WGS84)", example=12.9716)
    long: float = Field(..., description="Longitude in decimal degrees (WGS84)", example=77.5946)

class SystemSpecificationsRequest(BaseModel):
    """Technical specifications of the solar power system."""
    capacity_kw: float = Field(..., description="System capacity in kilowatts (kW)", example=10.5)
    panel_type: str = Field(..., description="Type of solar panels used", example="Monocrystalline")
    inverter_type: str = Field(..., description="Type of inverter used", example="String Inverter")
    installation_date: datetime = Field(..., description="Date when the system was installed")
    estimated_annual_production: float = Field(..., description="Estimated annual energy production in kWh", example=15000.0)
    systemLocation: Optional[SystemLocationRequest] = Field(None, description="Geographic coordinates of the system")
    moduleManufacturer: Optional[str] = Field(None, description="Manufacturer of the solar modules", example="SunPower")
    inverterBrand: Optional[str] = Field(None, description="Brand of the inverter", example="SMA")
    expectedGeneration: Optional[float] = Field(None, description="Expected monthly generation in kWh", example=1250.0)
    actualGeneration: Optional[float] = Field(None, description="Actual monthly generation in kWh", example=1180.0)
    systemAgeInMonths: Optional[int] = Field(None, description="Age of the system in months", example=24)

class CustomerRequest(BaseModel):
    """Customer creation request with extended information."""
    name: str = Field(..., description="Full name of the customer", example="John Doe")
    email: str = Field(..., description="Email address for communication", example="john.doe@example.com")
    address: str = Field(..., description="Complete postal address", example="123 Solar Street, Green City, 12345")
    customerType: CustomerType = Field(..., description="Classification of customer type")
    gstNumber: Optional[str] = Field(None, description="GST registration number for business customers", example="22AAAAA0000A1Z5")
    linkedPPAs: List[str] = Field(default_factory=list, description="List of PPA IDs linked to this customer")

class SignatoryRequest(BaseModel):
    """Information about contract signatories."""
    name: str = Field(..., description="Full name of the signatory", example="Jane Smith")
    role: str = Field(..., description="Role of the signatory in the contract", example="Customer Representative")
    signedAt: Optional[datetime] = Field(None, description="Timestamp when the document was signed")

class PPACreateRequest(BaseModel):
    """Request to create a new Power Purchase Agreement."""
    customer_id: str = Field(..., description="Unique identifier of the customer", example="cust_12345")
    system_specs: SystemSpecificationsRequest = Field(..., description="Technical specifications of the solar system")
    billing_terms: BillingTermsRequest = Field(..., description="Billing terms and conditions")
    start_date: datetime = Field(..., description="Contract start date")
    end_date: datetime = Field(..., description="Contract end date")
    contractType: ContractType = Field(ContractType.net_metering, description="Type of PPA contract")
    signatories: Optional[List[SignatoryRequest]] = Field(None, description="List of contract signatories")
    terminationClause: Optional[str] = Field(None, description="Contract termination terms and conditions")
    paymentTerms: Optional[str] = Field(None, description="Detailed payment terms and conditions")
    curtailmentClauses: Optional[str] = Field(None, description="Energy curtailment terms and conditions")
    generationGuarantees: Optional[str] = Field(None, description="Energy generation guarantees and penalties")
    createdBy: Optional[str] = Field(None, description="User ID who created the PPA", example="user_12345")

    def ensure_timezone(self):
        if self.start_date.tzinfo is None:
            self.start_date = self.start_date.replace(tzinfo=timezone.utc)
        if self.end_date.tzinfo is None:
            self.end_date = self.end_date.replace(tzinfo=timezone.utc)
        if self.system_specs.installation_date.tzinfo is None:
            self.system_specs.installation_date = self.system_specs.installation_date.replace(tzinfo=timezone.utc)

class EnergyUsageRequest(BaseModel):
    """Energy consumption data for billing and monitoring."""
    ppa_id: str = Field(..., description="Unique identifier of the PPA", example="ppa_12345")
    kwh_used: float = Field(..., description="Energy consumed in kilowatt-hours (kWh)", example=1250.5)
    reading_date: datetime = Field(..., description="Date and time of the energy reading")
    source: Optional[str] = Field(None, description="Source of the energy data (e.g., 'inverter', 'smart_meter')", example="smart_meter")
    unit: str = Field("kWh", description="Unit of measurement for energy consumption", example="kWh")
    timestampStart: Optional[datetime] = Field(None, description="Start timestamp for interval-based readings")
    timestampEnd: Optional[datetime] = Field(None, description="End timestamp for interval-based readings")
    importEnergy: Optional[float] = Field(None, description="Imported energy from grid in kWh (for net metering)", example=50.0)
    exportEnergy: Optional[float] = Field(None, description="Exported energy to grid in kWh (for net metering)", example=200.0)

class HTTPValidationError(BaseModel):
    """Standard error response for validation failures."""
    detail: Any = Field(..., description="Detailed error information")
    errorCode: Optional[str] = Field(None, description="Machine-readable error code", example="VALIDATION_ERROR")
    documentationLink: Optional[str] = Field(None, description="Link to error documentation", example="https://docs.yourapi.com/errors#VALIDATION_ERROR")

class ValidationError(BaseModel):
    """Validation error details."""
    loc: List[str] = Field(..., description="Location of the validation error in the request")
    msg: str = Field(..., description="Human-readable error message")
    type: str = Field(..., description="Type of validation error")
    errorCode: Optional[str] = Field(None, description="Machine-readable error code")
    documentationLink: Optional[str] = Field(None, description="Link to error documentation")

# Authentication dependency
async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if not FIREBASE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Authentication service unavailable")
    
    user = await run_in_threadpool(verify_token, credentials.credentials)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user

# Health check endpoint
@app.get("/health",
    summary="Health check",
    description="Checks the health status of the API and its dependencies. Returns information about the service status, Firebase availability, and current timestamp.",
    response_description="Health status information")
async def health_check():
    """
    Health check endpoint to verify API and service status.
    
    **Returns:**
    - **status**: Service health status ("healthy" or "unhealthy")
    - **firebase_available**: Whether Firebase authentication and database are available
    - **timestamp**: Current UTC timestamp in ISO format
    
    **Use Cases:**
    - Monitoring and alerting systems
    - Load balancer health checks
    - Service dependency verification
    """
    return {
        "status": "healthy",
        "firebase_available": FIREBASE_AVAILABLE,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

# Customer endpoints
@app.post("/customers", 
    response_model=Customer,
    summary="Create a new customer",
    description="Creates a new customer record in the system. The customer will be assigned a unique ID and can be linked to PPAs.",
    response_description="Customer created successfully with assigned ID")
async def create_customer(customer: Customer, current_user: dict = Depends(get_current_user)):
    """
    Create a new customer in the system.
    
    - **name**: Full name of the customer (required)
    - **email**: Email address for communication and billing (required)
    - **address**: Complete postal address (required)
    
    Returns the created customer with an assigned unique ID.
    """
    if not FIREBASE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database service unavailable")
    
    customer_ref = db.collection('customers').document()
    customer_dict = customer.model_dump()
    customer_dict['id'] = customer_ref.id
    await run_in_threadpool(customer_ref.set, customer_dict)
    return customer_dict

@app.get("/customers",
    summary="List all customers",
    description="Retrieves a list of all customers in the system. Can be used to view customer information and their associated PPAs.",
    response_description="List of all customers")
async def list_customers(current_user: dict = Depends(get_current_user)):
    """
    Retrieve all customers from the system.
    
    Returns a list of all customer records including their basic information and assigned IDs.
    """
    if not FIREBASE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database service unavailable")
    
    customers_ref = db.collection('customers')
    customers = await run_in_threadpool(customers_ref.get)
    return [doc.to_dict() for doc in customers]

# PPA endpoints
@app.post("/ppas", 
    response_model=PPA, 
    responses={422: {"model": HTTPValidationError}},
    summary="Create a new PPA",
    description="Creates a new Power Purchase Agreement with comprehensive specifications, billing terms, and system details. Validates for overlapping contracts and ensures all required fields are provided.",
    response_description="PPA created successfully with all specifications")
async def create_ppa(
    ppa_request: PPACreateRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Create a new Power Purchase Agreement (PPA) with comprehensive validation.
    
    **Key Parameters:**
    - **customer_id**: Unique identifier of the customer (required)
    - **system_specs**: Technical specifications including capacity, panel type, installation date
    - **billing_terms**: Tariff rates, escalation, billing cycle, payment terms
    - **start_date**: Contract start date (required)
    - **end_date**: Contract end date (required)
    - **contractType**: Type of PPA (net_metering, gross_metering, open_access)
    
    **Validation Checks:**
    - Ensures no overlapping active/draft PPAs for the same customer
    - Validates customer exists in the system
    - Enforces timezone awareness for all datetime fields
    - Validates billing terms and system specifications
    
    **Returns:** Complete PPA object with generated ID and audit trail
    """
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
            escalation_type=ppa_request.billing_terms.escalation_type,
            escalation_rate=ppa_request.billing_terms.escalation_rate,
            escalation_schedule=[s.dict() for s in ppa_request.billing_terms.escalation_schedule] if ppa_request.billing_terms.escalation_schedule else None,
            billing_cycle=ppa_request.billing_terms.billing_cycle,
            payment_terms=ppa_request.billing_terms.payment_terms,
            slabs=[s.dict() for s in ppa_request.billing_terms.slabs] if ppa_request.billing_terms.slabs else None,
            touRates=[t.dict() for t in ppa_request.billing_terms.touRates] if ppa_request.billing_terms.touRates else None,
            taxRate=ppa_request.billing_terms.taxRate,
            latePaymentPenaltyRate=ppa_request.billing_terms.latePaymentPenaltyRate,
            currency=ppa_request.billing_terms.currency,
            subsidySchemeId=ppa_request.billing_terms.subsidySchemeId,
            autoInvoice=ppa_request.billing_terms.autoInvoice,
            gracePeriodDays=ppa_request.billing_terms.gracePeriodDays,
            business_model=ppa_request.billing_terms.business_model,
            capex_amount=ppa_request.billing_terms.capex_amount,
            opex_monthly_fee=ppa_request.billing_terms.opex_monthly_fee,
            opex_energy_rate=ppa_request.billing_terms.opex_energy_rate,
            maintenance_included=ppa_request.billing_terms.maintenance_included,
            insurance_included=ppa_request.billing_terms.insurance_included
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

@app.get("/ppas",
    summary="List PPAs",
    description="Retrieves a list of Power Purchase Agreements. Can be filtered by customer_id to get PPAs for a specific customer.",
    response_description="List of PPAs with full specifications")
async def list_ppas(customer_id: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    """
    List all PPAs or PPAs for a specific customer.
    
    **Query Parameters:**
    - **customer_id** (optional): Filter PPAs by customer ID
    
    **Returns:** List of PPA objects with complete specifications and billing terms
    """
    if customer_id:
        return await get_customer_ppas(customer_id)
    
    ppas_ref = db.collection('ppas')
    ppas = await run_in_threadpool(ppas_ref.get)
    return [doc.to_dict() for doc in ppas]

@app.get("/ppas/{ppa_id}",
    summary="Get PPA by ID",
    description="Retrieves a specific Power Purchase Agreement by its unique identifier. Includes all specifications, billing terms, and current status.",
    response_description="Complete PPA details")
async def get_ppa(ppa_id: str, current_user: dict = Depends(get_current_user)):
    """
    Get a specific PPA by its unique identifier.
    
    **Path Parameters:**
    - **ppa_id**: Unique identifier of the PPA (required)
    
    **Returns:** Complete PPA object with all specifications and current status
    """
    ppa = await get_ppa_by_id(ppa_id)
    if not ppa:
        raise HTTPException(status_code=404, detail="PPA not found")
    return ppa

@app.post("/ppas/{ppa_id}/sign",
    summary="Sign and activate PPA",
    description="Marks a PPA as signed and changes its status from 'draft' to 'active'. This action enables billing and energy usage tracking.",
    response_description="PPA marked as signed and activated")
async def sign_ppa(ppa_id: str, current_user: dict = Depends(get_current_user)):
    """
    Mark a PPA as signed and activate it for billing.
    
    **Path Parameters:**
    - **ppa_id**: Unique identifier of the PPA to sign (required)
    
    **Returns:** Updated PPA object with 'active' status
    """
    ppa = await mark_ppa_as_signed(ppa_id)
    if not ppa:
        raise HTTPException(status_code=404, detail="PPA not found")
    return ppa

@app.get("/ppas/{ppa_id}/pdf",
    summary="Generate PPA PDF",
    description="Generates a downloadable PDF document containing the complete PPA details, terms, and conditions. The PDF includes customer information, system specifications, and billing terms.",
    response_description="PDF file containing PPA document")
async def get_ppa_pdf(ppa_id: str, background_tasks: BackgroundTasks, current_user: dict = Depends(get_current_user)):
    """
    Generate and download PPA as a PDF document.
    
    **Path Parameters:**
    - **ppa_id**: Unique identifier of the PPA (required)
    
    **Returns:** PDF file containing the complete PPA document
    """
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
@app.post("/ppas/{ppa_id}/energy-usage",
    summary="Add energy usage data",
    description="Records energy consumption data for a PPA. Updates the PPA's energy production tracking and stores the usage record for billing calculations.",
    response_description="Energy usage record created successfully")
async def add_energy_usage(
    ppa_id: str,
    usage: EnergyUsageRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Add energy usage data for a PPA.
    
    **Path Parameters:**
    - **ppa_id**: Unique identifier of the PPA (required)
    
    **Request Body:**
    - **kwh_used**: Energy consumed in kilowatt-hours (required)
    - **reading_date**: Date and time of the energy reading (required)
    - **source**: Source of the energy data (optional, e.g., 'inverter', 'smart_meter')
    - **unit**: Unit of measurement for energy consumption (default: 'kWh')
    - **importEnergy**: Imported energy from grid in kWh (for net metering)
    - **exportEnergy**: Exported energy to grid in kWh (for net metering)
    
    **Returns:** Energy usage record with assigned ID
    """
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
@app.post("/ppas/{ppa_id}/invoices/generate",
    summary="Generate invoice",
    description="Generates an invoice for a PPA based on energy usage data. Calculates the current tariff rate considering escalation and applies any applicable slabs or time-of-use rates.",
    response_description="Invoice generated successfully with calculated amounts")
async def create_invoice(
    ppa_id: str,
    usage: EnergyUsageRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Generate an invoice for a PPA based on energy usage.
    
    **Path Parameters:**
    - **ppa_id**: Unique identifier of the PPA (required)
    
    **Request Body:**
    - **kwh_used**: Energy consumed in kilowatt-hours (required)
    - **reading_date**: Date and time of the energy reading (required)
    - **source**: Source of the energy data (optional)
    - **unit**: Unit of measurement (default: 'kWh')
    
    **Calculation Process:**
    1. Validates PPA is active and invoice generation is due
    2. Calculates current tariff rate considering annual escalation
    3. Applies tiered billing slabs if configured
    4. Applies time-of-use rates if configured
    5. Calculates taxes and any applicable penalties
    6. Updates PPA billing information
    
    **Returns:** Complete invoice with calculated amounts and billing details
    """
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

@app.get("/ppas/{ppa_id}/invoices",
    summary="List PPA invoices",
    description="Retrieves all invoices generated for a specific PPA. Includes invoice history, amounts, and payment status.",
    response_description="List of all invoices for the PPA")
async def list_ppa_invoices(ppa_id: str, current_user: dict = Depends(get_current_user)):
    """
    List all invoices for a specific PPA.
    
    **Path Parameters:**
    - **ppa_id**: Unique identifier of the PPA (required)
    
    **Returns:** List of invoice objects with amounts, dates, and payment status
    """
    ppa = await get_ppa_by_id(ppa_id)
    if not ppa:
        raise HTTPException(status_code=404, detail="PPA not found")
    
    invoices_ref = db.collection('invoices').where('ppa_id', '==', ppa_id)
    invoices = await run_in_threadpool(invoices_ref.get)
    return [doc.to_dict() for doc in invoices]

@app.get("/ppas/{ppa_id}/invoices/{invoice_id}/pdf",
    summary="Generate invoice PDF",
    description="Generates a downloadable PDF invoice containing billing details, energy usage, and payment information. The PDF includes customer details, energy consumption, and calculated amounts.",
    response_description="PDF file containing invoice")
async def get_invoice_pdf(
    ppa_id: str,
    invoice_id: str,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user)
):
    """
    Generate and download invoice as a PDF document.
    
    **Path Parameters:**
    - **ppa_id**: Unique identifier of the PPA (required)
    - **invoice_id**: Unique identifier of the invoice (required)
    
    **Returns:** PDF file containing the complete invoice
    """
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

@app.post("/ppas/{ppa_id}/invoices/{invoice_id}/pay",
    summary="Mark invoice as paid",
    description="Marks an invoice as paid and updates the PPA's payment tracking. This action records the payment and updates the customer's payment history.",
    response_description="Invoice marked as paid successfully")
async def pay_invoice(
    ppa_id: str,
    invoice_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Mark an invoice as paid and update PPA payment information.
    
    **Path Parameters:**
    - **ppa_id**: Unique identifier of the PPA (required)
    - **invoice_id**: Unique identifier of the invoice (required)
    
    **Process:**
    1. Validates both PPA and invoice exist
    2. Marks invoice as paid with payment timestamp
    3. Updates PPA payment tracking information
    4. Records payment amount and date
    
    **Returns:** Updated invoice object with paid status
    """
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

@app.get("/", 
    response_class=HTMLResponse,
    summary="Frontend interface",
    description="Serves the main frontend interface for the Solar Billing API. Provides a web-based interface for managing customers, PPAs, and billing operations.",
    response_description="HTML frontend interface")
def serve_frontend(request: Request):
    """
    Serve the main frontend interface.
    
    **Returns:** HTML page with the web-based interface for the Solar Billing API
    """
    return templates.TemplateResponse("index.html", {"request": request})

FIREBASE_API_KEY = os.environ.get("FIREBASE_API_KEY")
if not FIREBASE_API_KEY:
    raise RuntimeError("FIREBASE_API_KEY environment variable must be set for authentication.")

@app.post("/auth/login",
    summary="User authentication",
    description="Authenticates users using Firebase Authentication. Validates email and password credentials and returns authentication tokens for API access.",
    response_description="Authentication result with tokens or error")
def login_auth(data: dict):
    """
    Authenticate user with Firebase Authentication.
    
    **Request Body:**
    - **email**: User's email address (required)
    - **password**: User's password (required)
    
    **Returns:**
    - **idToken**: Firebase ID token for API authentication
    - **refreshToken**: Token for refreshing authentication
    - **expiresIn**: Token expiration time in seconds
    - **localId**: User's unique identifier
    - **error**: Error details if authentication fails
    
    **Error Responses:**
    - **INVALID_EMAIL**: Invalid email format
    - **EMAIL_NOT_FOUND**: Email not registered
    - **INVALID_PASSWORD**: Incorrect password
    - **USER_DISABLED**: Account has been disabled
    
    **Usage:**
    Use the returned `idToken` in the Authorization header as "Bearer {token}" for subsequent API calls.
    """
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

# Subsidy Scheme endpoints
@app.post("/subsidy-schemes",
    summary="Create subsidy scheme",
    description="Creates a new state-specific subsidy scheme for solar installations. Includes eligibility criteria, subsidy rates, and validity periods.",
    response_description="Subsidy scheme created successfully")
async def create_subsidy_scheme(
    scheme: dict,
    current_user: dict = Depends(get_current_user)
):
    """
    Create a new subsidy scheme for solar installations.
    
    **Request Body:**
    - **scheme_id**: Unique identifier for the scheme (required)
    - **scheme_name**: Name of the subsidy scheme (required)
    - **state_code**: State where scheme is applicable (required)
    - **subsidy_type**: Type of subsidy (capital, generation, tax) (required)
    - **subsidy_rate**: Subsidy rate as percentage or fixed amount (required)
    - **subsidy_unit**: Unit for subsidy (% or currency/kW or currency/kWh) (required)
    - **max_capacity_kw**: Maximum system capacity eligible (optional)
    - **min_capacity_kw**: Minimum system capacity eligible (optional)
    - **valid_from**: Scheme validity start date (required)
    - **valid_until**: Scheme validity end date (optional)
    - **description**: Detailed description of the scheme (optional)
    - **documentation_url**: URL to official documentation (optional)
    
    **Returns:** Created subsidy scheme with assigned ID
    """
    if not FIREBASE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database service unavailable")
    
    scheme_ref = db.collection('subsidy_schemes').document()
    scheme_dict = scheme
    scheme_dict['id'] = scheme_ref.id
    scheme_dict['created_at'] = datetime.now(timezone.utc)
    scheme_dict['created_by'] = current_user.get('uid') if current_user else None
    
    await run_in_threadpool(scheme_ref.set, scheme_dict)
    return scheme_dict

@app.get("/subsidy-schemes",
    summary="List subsidy schemes",
    description="Retrieves all available subsidy schemes, optionally filtered by state or subsidy type.",
    response_description="List of subsidy schemes")
async def list_subsidy_schemes(
    state_code: Optional[StateCode] = None,
    subsidy_type: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """
    List all subsidy schemes with optional filtering.
    
    **Query Parameters:**
    - **state_code** (optional): Filter by state code
    - **subsidy_type** (optional): Filter by subsidy type (capital, generation, tax)
    
    **Returns:** List of subsidy schemes matching the criteria
    """
    if not FIREBASE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database service unavailable")
    
    schemes_ref = db.collection('subsidy_schemes')
    
    # Apply filters if provided
    if state_code:
        schemes_ref = schemes_ref.where('state_code', '==', state_code.value)
    if subsidy_type:
        schemes_ref = schemes_ref.where('subsidy_type', '==', subsidy_type)
    
    schemes = await run_in_threadpool(schemes_ref.get)
    return [doc.to_dict() for doc in schemes]

@app.get("/subsidy-schemes/{scheme_id}",
    summary="Get subsidy scheme by ID",
    description="Retrieves detailed information about a specific subsidy scheme including eligibility criteria and validity.",
    response_description="Detailed subsidy scheme information")
async def get_subsidy_scheme(
    scheme_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Get a specific subsidy scheme by its unique identifier.
    
    **Path Parameters:**
    - **scheme_id**: Unique identifier of the subsidy scheme (required)
    
    **Returns:** Complete subsidy scheme details
    """
    if not FIREBASE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database service unavailable")
    
    scheme_ref = db.collection('subsidy_schemes').document(scheme_id)
    scheme = await run_in_threadpool(scheme_ref.get)
    
    if not scheme.exists:
        raise HTTPException(status_code=404, detail="Subsidy scheme not found")
    
    return scheme.to_dict()

# Enhanced PPA details endpoint
@app.get("/ppas/{ppa_id}/details",
    summary="Get comprehensive PPA details",
    description="Retrieves comprehensive PPA details including business model (CAPEX vs OPEX), escalation history, tenure information, subsidy details, and financial projections.",
    response_description="Comprehensive PPA details with business model and financial information")
async def get_ppa_details(
    ppa_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Get comprehensive PPA details including business model and financial information.
    
    **Path Parameters:**
    - **ppa_id**: Unique identifier of the PPA (required)
    
    **Returns:** Comprehensive PPA details including:
    - Basic PPA information
    - Business model details (CAPEX vs OPEX)
    - Escalation history and projections
    - Tenure information and remaining period
    - Subsidy details and eligibility
    - Financial projections and payment schedules
    """
    if not FIREBASE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database service unavailable")
    
    ppa = await get_ppa_by_id(ppa_id)
    if not ppa:
        raise HTTPException(status_code=404, detail="PPA not found")
    
    # Get customer information
    customer_ref = db.collection('customers').document(ppa.customer_id)
    customer = await run_in_threadpool(customer_ref.get)
    customer_data = customer.to_dict() if customer.exists else None
    
    # Get subsidy scheme details if applicable
    subsidy_details = None
    if ppa.subsidySchemeId:
        subsidy_ref = db.collection('subsidy_schemes').document(ppa.subsidySchemeId)
        subsidy = await run_in_threadpool(subsidy_ref.get)
        if subsidy.exists:
            subsidy_details = subsidy.to_dict()
    
    # Calculate financial projections
    current_date = datetime.now(timezone.utc)
    current_tariff = ppa.calculate_current_tariff(current_date)
    tenure_remaining = ppa.get_tenure_remaining()
    
    # Business model specific calculations
    business_model_details = {}
    if ppa.business_model == BusinessModel.capex:
        capex_schedule = ppa.calculate_capex_payment_schedule()
        business_model_details = {
            "model_type": "CAPEX",
            "total_capex": ppa.billing_terms.capex_amount,
            "payment_schedule": capex_schedule,
            "maintenance_included": ppa.billing_terms.maintenance_included,
            "insurance_included": ppa.billing_terms.insurance_included
        }
    elif ppa.business_model == BusinessModel.opex:
        # Calculate OPEX projections for next 12 months
        opex_projections = []
        for month in range(12):
            projection_date = current_date + timedelta(days=30*month)
            monthly_fee = ppa.billing_terms.opex_monthly_fee or 0.0
            # Estimate energy consumption based on system capacity
            estimated_energy = ppa.system_specs.estimated_annual_production / 12
            energy_cost = (ppa.billing_terms.opex_energy_rate or 0.0) * estimated_energy
            total_monthly = monthly_fee + energy_cost
            
            opex_projections.append({
                "month": month + 1,
                "date": projection_date,
                "monthly_fee": monthly_fee,
                "estimated_energy_kwh": estimated_energy,
                "energy_cost": energy_cost,
                "total_monthly_payment": total_monthly
            })
        
        business_model_details = {
            "model_type": "OPEX",
            "monthly_fee": ppa.billing_terms.opex_monthly_fee,
            "energy_rate": ppa.billing_terms.opex_energy_rate,
            "projections": opex_projections,
            "maintenance_included": ppa.billing_terms.maintenance_included,
            "insurance_included": ppa.billing_terms.insurance_included
        }
    
    # Escalation projections
    escalation_projections = []
    if ppa.billing_terms.escalation_type == EscalationType.fixed_percentage:
        current_rate = ppa.billing_terms.tariff_rate
        for year in range(1, int(tenure_remaining) + 1):
            current_rate *= (1 + ppa.billing_terms.escalation_rate)
            escalation_projections.append({
                "year": year,
                "escalation_rate": ppa.billing_terms.escalation_rate,
                "projected_tariff": round(current_rate, 4)
            })
    elif ppa.billing_terms.escalation_type == EscalationType.custom_schedule:
        current_rate = ppa.billing_terms.tariff_rate
        for year in range(1, int(tenure_remaining) + 1):
            # Find escalation for this year
            year_escalation = next(
                (s for s in (ppa.billing_terms.escalation_schedule or []) if s.year == year),
                None
            )
            if year_escalation:
                current_rate *= (1 + year_escalation.escalation_rate)
            
            escalation_projections.append({
                "year": year,
                "escalation_rate": year_escalation.escalation_rate if year_escalation else 0,
                "projected_tariff": round(current_rate, 4)
            })
    
    # Compile comprehensive response
    response = {
        "ppa_id": ppa.id,
        "customer": customer_data,
        "basic_info": {
            "contract_type": ppa.contractType,
            "contract_status": ppa.contractStatus,
            "start_date": ppa.start_date,
            "end_date": ppa.end_date,
            "tenure_years": ppa.tenure_years,
            "tenure_remaining_years": tenure_remaining,
            "system_capacity_kw": ppa.system_specs.capacity_kw,
            "estimated_annual_production_kwh": ppa.system_specs.estimated_annual_production
        },
        "business_model": business_model_details,
        "billing_terms": {
            "current_tariff_rate": current_tariff,
            "base_tariff_rate": ppa.billing_terms.tariff_rate,
            "escalation_type": ppa.billing_terms.escalation_type,
            "escalation_rate": ppa.billing_terms.escalation_rate,
            "billing_cycle": ppa.billing_terms.billing_cycle,
            "payment_terms": ppa.billing_terms.payment_terms,
            "currency": ppa.billing_terms.currency
        },
        "escalation": {
            "history": ppa.escalation_history,
            "projections": escalation_projections,
            "next_escalation_date": ppa.next_escalation_date
        },
        "subsidy": {
            "scheme_id": ppa.subsidySchemeId,
            "scheme_details": subsidy_details,
            "subsidy_applied": ppa.subsidy_applied,
            "subsidy_details": ppa.subsidy_details
        },
        "financial_summary": {
            "total_energy_produced_kwh": ppa.total_energy_produced,
            "total_billed": ppa.total_billed,
            "total_paid": ppa.total_paid,
            "outstanding_amount": ppa.total_billed - ppa.total_paid,
            "last_billing_date": ppa.last_billing_date
        },
        "performance_metrics": {
            "energy_production_history": ppa.energy_production_history[-12:],  # Last 12 records
            "billing_history": ppa.billing_history[-12:],  # Last 12 records
            "payment_history": ppa.payment_history[-12:]   # Last 12 records
        }
    }
    
    return response

# OPEX payment endpoint
@app.post("/ppas/{ppa_id}/opex-payment",
    summary="Record OPEX payment",
    description="Records an OPEX payment for a PPA, including energy consumption and monthly fee breakdown.",
    response_description="OPEX payment recorded successfully")
async def record_opex_payment(
    ppa_id: str,
    payment_data: dict,
    current_user: dict = Depends(get_current_user)
):
    """
    Record an OPEX payment for a PPA.
    
    **Path Parameters:**
    - **ppa_id**: Unique identifier of the PPA (required)
    
    **Request Body:**
    - **amount**: Total payment amount (required)
    - **energy_consumed_kwh**: Energy consumed in kWh (required)
    - **payment_date**: Date of payment (optional, defaults to current date)
    - **payment_method**: Method of payment (optional)
    - **reference_number**: Payment reference number (optional)
    
    **Returns:** Recorded OPEX payment details
    """
    if not FIREBASE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database service unavailable")
    
    ppa = await get_ppa_by_id(ppa_id)
    if not ppa:
        raise HTTPException(status_code=404, detail="PPA not found")
    
    if ppa.business_model != BusinessModel.opex:
        raise HTTPException(status_code=400, detail="This PPA is not an OPEX model")
    
    if not ppa.is_active():
        raise HTTPException(status_code=400, detail="PPA is not active")
    
    amount = payment_data.get('amount')
    energy_consumed = payment_data.get('energy_consumed_kwh')
    payment_date = payment_data.get('payment_date', datetime.now(timezone.utc))
    
    if not amount or amount <= 0:
        raise HTTPException(status_code=400, detail="Payment amount must be greater than 0")
    
    if not energy_consumed or energy_consumed < 0:
        raise HTTPException(status_code=400, detail="Energy consumed must be non-negative")
    
    # Add OPEX payment record
    ppa.add_opex_payment(amount, payment_date, energy_consumed)
    
    # Update PPA in database
    ppa_ref = db.collection('ppas').document(ppa_id)
    update_data = {
        'total_paid': ppa.total_paid,
        'opex_payment_history': ppa.opex_payment_history,
        'updated_at': datetime.now(timezone.utc),
        'updatedBy': current_user.get('uid') if current_user else None
    }
    
    await run_in_threadpool(ppa_ref.update, update_data)
    
    return {
        "payment_id": f"opex_payment_{datetime.now(timezone.utc).timestamp()}",
        "ppa_id": ppa_id,
        "amount": amount,
        "energy_consumed_kwh": energy_consumed,
        "payment_date": payment_date,
        "monthly_fee": ppa.billing_terms.opex_monthly_fee or 0.0,
        "energy_cost": amount - (ppa.billing_terms.opex_monthly_fee or 0.0),
        "payment_method": payment_data.get('payment_method'),
        "reference_number": payment_data.get('reference_number')
    }

# DISCOM Management endpoints
@app.post("/discoms",
    summary="Create DISCOM",
    description="Creates a new Distribution Company (DISCOM) with API configuration for dynamic tariff retrieval.",
    response_description="DISCOM created successfully")
async def create_discom(
    discom: dict,
    current_user: dict = Depends(get_current_user)
):
    """
    Create a new Distribution Company (DISCOM) with API configuration.
    
    **Request Body:**
    - **discom_id**: Unique identifier for the DISCOM (required)
    - **discom_name**: Name of the distribution company (required)
    - **state_code**: State where DISCOM operates (required)
    - **license_number**: DISCOM license number (optional)
    - **website**: DISCOM website URL (optional)
    - **api_endpoint**: DISCOM API endpoint for tariff data (optional)
    - **api_key**: API key for DISCOM tariff API (optional)
    - **tariff_update_frequency**: How often tariffs are updated (default: monthly)
    
    **Returns:** Created DISCOM with assigned ID
    """
    if not FIREBASE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database service unavailable")
    
    discom_ref = db.collection('discoms').document(discom.get('discom_id'))
    discom_doc = await run_in_threadpool(discom_ref.get)
    
    if discom_doc.exists:
        raise HTTPException(status_code=409, detail="DISCOM with this ID already exists")
    
    discom_dict = discom
    discom_dict['created_at'] = datetime.now(timezone.utc)
    discom_dict['created_by'] = current_user.get('uid') if current_user else None
    discom_dict['is_active'] = True
    
    await run_in_threadpool(discom_ref.set, discom_dict)
    return discom_dict

@app.get("/discoms",
    summary="List DISCOMs",
    description="Retrieves all DISCOMs, optionally filtered by state.",
    response_description="List of DISCOMs")
async def list_discoms(
    state_code: Optional[StateCode] = None,
    current_user: dict = Depends(get_current_user)
):
    """
    List all DISCOMs with optional filtering.
    
    **Query Parameters:**
    - **state_code** (optional): Filter by state code
    
    **Returns:** List of DISCOMs matching the criteria
    """
    if not FIREBASE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database service unavailable")
    
    discoms_ref = db.collection('discoms')
    
    if state_code:
        discoms_ref = discoms_ref.where('state_code', '==', state_code.value)
    
    discoms = await run_in_threadpool(discoms_ref.get)
    return [doc.to_dict() for doc in discoms]

@app.get("/discoms/{discom_id}",
    summary="Get DISCOM by ID",
    description="Retrieves detailed information about a specific DISCOM including API configuration.",
    response_description="Detailed DISCOM information")
async def get_discom(
    discom_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Get a specific DISCOM by its unique identifier.
    
    **Path Parameters:**
    - **discom_id**: Unique identifier of the DISCOM (required)
    
    **Returns:** Complete DISCOM details
    """
    if not FIREBASE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database service unavailable")
    
    discom_ref = db.collection('discoms').document(discom_id)
    discom = await run_in_threadpool(discom_ref.get)
    
    if not discom.exists:
        raise HTTPException(status_code=404, detail="DISCOM not found")
    
    return discom.to_dict()

@app.put("/discoms/{discom_id}",
    summary="Update DISCOM",
    description="Updates DISCOM configuration including API settings.",
    response_description="DISCOM updated successfully")
async def update_discom(
    discom_id: str,
    discom_update: dict,
    current_user: dict = Depends(get_current_user)
):
    """
    Update DISCOM configuration.
    
    **Path Parameters:**
    - **discom_id**: Unique identifier of the DISCOM (required)
    
    **Request Body:** DISCOM update fields
    
    **Returns:** Updated DISCOM details
    """
    if not FIREBASE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database service unavailable")
    
    discom_ref = db.collection('discoms').document(discom_id)
    discom = await run_in_threadpool(discom_ref.get)
    
    if not discom.exists:
        raise HTTPException(status_code=404, detail="DISCOM not found")
    
    update_data = discom_update
    update_data['updated_at'] = datetime.now(timezone.utc)
    update_data['updated_by'] = current_user.get('uid') if current_user else None
    
    await run_in_threadpool(discom_ref.update, update_data)
    
    # Get updated DISCOM
    updated_discom = await run_in_threadpool(discom_ref.get)
    return updated_discom.to_dict()

# Tariff Structure Management endpoints
@app.post("/tariffs",
    summary="Create tariff structure",
    description="Creates a new tariff structure for a specific DISCOM and customer category.",
    response_description="Tariff structure created successfully")
async def create_tariff_structure(
    tariff: dict,
    current_user: dict = Depends(get_current_user)
):
    """
    Create a new tariff structure.
    
    **Request Body:**
    - **discom_id**: DISCOM identifier (required)
    - **state_code**: State code (required)
    - **tariff_category**: Tariff category (required)
    - **customer_type**: Customer type (required)
    - **base_rate**: Base tariff rate per kWh (required)
    - **currency**: Currency for the tariff (default: INR)
    - **effective_from**: When this tariff becomes effective (required)
    - **effective_until**: When this tariff expires (optional)
    - **regulatory_order**: Regulatory order reference (optional)
    - **order_number**: Regulatory order number (optional)
    - **order_date**: Regulatory order date (optional)
    - **source**: Source of tariff data (default: regulatory_order)
    
    **Returns:** Created tariff structure with assigned ID
    """
    if not FIREBASE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database service unavailable")
    
    tariff_ref = db.collection('tariffs').document()
    tariff_dict = tariff
    tariff_dict['tariff_id'] = tariff_ref.id
    tariff_dict['created_at'] = datetime.now(timezone.utc)
    tariff_dict['created_by'] = current_user.get('uid') if current_user else None
    tariff_dict['is_active'] = True
    
    await run_in_threadpool(tariff_ref.set, tariff_dict)
    return tariff_dict

@app.post("/tariffs/{tariff_id}/slabs",
    summary="Add tariff slab",
    description="Adds a tariff slab to an existing tariff structure.",
    response_description="Tariff slab added successfully")
async def add_tariff_slab(
    tariff_id: str,
    slab: dict,
    current_user: dict = Depends(get_current_user)
):
    """
    Add a tariff slab to an existing tariff structure.
    
    **Path Parameters:**
    - **tariff_id**: Unique identifier of the tariff (required)
    
    **Request Body:**
    - **min_consumption**: Minimum consumption for this slab (required)
    - **max_consumption**: Maximum consumption for this slab (optional)
    - **rate**: Rate per kWh for this slab (required)
    - **unit**: Unit for the rate (default: INR/kWh)
    - **description**: Description of the slab (optional)
    
    **Returns:** Created tariff slab
    """
    if not FIREBASE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database service unavailable")
    
    # Verify tariff exists
    tariff_ref = db.collection('tariffs').document(tariff_id)
    tariff = await run_in_threadpool(tariff_ref.get)
    
    if not tariff.exists:
        raise HTTPException(status_code=404, detail="Tariff not found")
    
    slab_ref = db.collection('tariff_slabs').document()
    slab_dict = slab
    slab_dict['slab_id'] = slab_ref.id
    slab_dict['created_at'] = datetime.now(timezone.utc)
    slab_dict['is_active'] = True
    
    await run_in_threadpool(slab_ref.set, slab_dict)
    return slab_dict

@app.post("/tariffs/{tariff_id}/tou-rates",
    summary="Add time-of-use tariff",
    description="Adds a time-of-use tariff rate to an existing tariff structure.",
    response_description="Time-of-use tariff added successfully")
async def add_tou_tariff(
    tariff_id: str,
    tou: dict,
    current_user: dict = Depends(get_current_user)
):
    """
    Add a time-of-use tariff rate to an existing tariff structure.
    
    **Path Parameters:**
    - **tariff_id**: Unique identifier of the tariff (required)
    
    **Request Body:**
    - **time_range**: Time range in 24-hour format (required)
    - **rate**: Rate per kWh for this time period (required)
    - **unit**: Unit for the rate (default: INR/kWh)
    - **season**: Season (summer, winter, monsoon) (optional)
    - **day_type**: Day type (weekday, weekend, holiday) (optional)
    - **description**: Description of the ToU period (optional)
    
    **Returns:** Created time-of-use tariff
    """
    if not FIREBASE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database service unavailable")
    
    # Verify tariff exists
    tariff_ref = db.collection('tariffs').document(tariff_id)
    tariff = await run_in_threadpool(tariff_ref.get)
    
    if not tariff.exists:
        raise HTTPException(status_code=404, detail="Tariff not found")
    
    tou_ref = db.collection('tou_tariffs').document()
    tou_dict = tou
    tou_dict['tou_id'] = tou_ref.id
    tou_dict['created_at'] = datetime.now(timezone.utc)
    tou_dict['is_active'] = True
    
    await run_in_threadpool(tou_ref.set, tou_dict)
    return tou_dict

# Dynamic Tariff Retrieval endpoint
@app.post("/tariffs/dynamic",
    summary="Get dynamic tariff",
    description="Retrieves real-time tariff based on DISCOM, state, and customer type. Attempts to fetch from DISCOM API first, then falls back to database and calculated rates.",
    response_description="Dynamic tariff information")
async def get_dynamic_tariff(
    request: dict,
    current_user: dict = Depends(get_current_user)
):
    """
    Get dynamic tariff based on DISCOM, state, and customer type.
    
    **Request Body:**
    - **discom_id**: DISCOM identifier (required)
    - **state_code**: State code (required)
    - **tariff_category**: Tariff category (required)
    - **customer_type**: Customer type (required)
    - **consumption_kwh**: Monthly consumption in kWh (optional)
    - **contract_date**: Contract date for tariff calculation (required)
    - **include_slabs**: Whether to include tariff slabs (default: true)
    - **include_tou**: Whether to include time-of-use rates (default: true)
    
    **Retrieval Priority:**
    1. DISCOM API (if available and configured)
    2. Regulatory order database
    3. Manual override
    4. Calculated based on rules
    5. Fallback tariff
    
    **Returns:** Dynamic tariff information including source, effective dates, and calculated rates
    """
    if not FIREBASE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database service unavailable")
    
    try:
        tariff_response = await get_dynamic_tariff(request)
        return tariff_response
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving dynamic tariff: {str(e)}")

@app.post("/discoms/{discom_id}/update-tariffs",
    summary="Update DISCOM tariffs",
    description="Manually triggers tariff update for a specific DISCOM from their API.",
    response_description="Tariff update status")
async def update_discom_tariffs(
    discom_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Manually trigger tariff update for a specific DISCOM.
    
    **Path Parameters:**
    - **discom_id**: Unique identifier of the DISCOM (required)
    
    **Process:**
    1. Checks if DISCOM API is configured
    2. Fetches latest tariffs from DISCOM API
    3. Stores updated tariffs in database
    4. Updates last tariff update timestamp
    
    **Returns:** Update status and timestamp
    """
    if not FIREBASE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database service unavailable")
    
    try:
        success = await update_discom_tariffs(discom_id)
        
        if success:
            return {
                "discom_id": discom_id,
                "status": "success",
                "message": "Tariffs updated successfully",
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to update tariffs")
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating tariffs: {str(e)}")

@app.get("/tariffs/search",
    summary="Search tariffs",
    description="Search for tariffs based on various criteria including DISCOM, state, category, and effective dates.",
    response_description="List of matching tariffs")
async def search_tariffs(
    discom_id: Optional[str] = None,
    state_code: Optional[StateCode] = None,
    tariff_category: Optional[TariffCategory] = None,
    customer_type: Optional[CustomerType] = None,
    source: Optional[TariffSource] = None,
    effective_from: Optional[datetime] = None,
    effective_until: Optional[datetime] = None,
    current_user: dict = Depends(get_current_user)
):
    """
    Search for tariffs based on various criteria.
    
    **Query Parameters:**
    - **discom_id** (optional): Filter by DISCOM ID
    - **state_code** (optional): Filter by state code
    - **tariff_category** (optional): Filter by tariff category
    - **customer_type** (optional): Filter by customer type
    - **source** (optional): Filter by tariff source
    - **effective_from** (optional): Filter by effective from date
    - **effective_until** (optional): Filter by effective until date
    
    **Returns:** List of tariffs matching the criteria
    """
    if not FIREBASE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database service unavailable")
    
    tariffs_ref = db.collection('tariffs')
    
    # Apply filters
    if discom_id:
        tariffs_ref = tariffs_ref.where('discom_id', '==', discom_id)
    if state_code:
        tariffs_ref = tariffs_ref.where('state_code', '==', state_code.value)
    if tariff_category:
        tariffs_ref = tariffs_ref.where('tariff_category', '==', tariff_category.value)
    if customer_type:
        tariffs_ref = tariffs_ref.where('customer_type', '==', customer_type.value)
    if source:
        tariffs_ref = tariffs_ref.where('source', '==', source.value)
    if effective_from:
        tariffs_ref = tariffs_ref.where('effective_from', '>=', effective_from)
    if effective_until:
        tariffs_ref = tariffs_ref.where('effective_until', '<=', effective_until)
    
    tariffs = await run_in_threadpool(tariffs_ref.get)
    return [doc.to_dict() for doc in tariffs]

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)