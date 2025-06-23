# Solar Billing and PPA API Documentation

## Overview
This API provides endpoints for managing solar client billing and Power Purchase Agreements (PPAs) following Indian standards. The API is built using FastAPI and uses Firebase for authentication and data storage. The PPA (Power Purchase Agreement) is the central component of the system, with all other functionalities (energy usage, billing, invoices) being derived from or dependent on the PPA.

## Base URL
```
http://localhost:8000
```

## Authentication
All endpoints require authentication using Firebase JWT tokens. Include the token in the Authorization header:
```
Authorization: Bearer <your-token>
```

## API Endpoints

### Customer Management

#### Create Customer
```http
POST /customers
```
Request body:
```json
{
    "name": "John Doe",
    "email": "john@example.com",
    "address": "123 Solar Street, Mumbai, Maharashtra",
    "customerType": "commercial",
    "gstNumber": "27AAAPL1234C1ZV",
    "linkedPPAs": ["ppa123", "ppa456"]
}
```

#### List Customers
```http
GET /customers
```

### Power Purchase Agreement (PPA) Management

#### Create PPA
```http
POST /ppas
```
Request body:
```json
{
    "customer_id": "customer123",
    "system_specs": {
        "capacity_kw": 10.5,
        "panel_type": "Monocrystalline",
        "inverter_type": "String Inverter",
        "installation_date": "2024-03-15T00:00:00Z",
        "estimated_annual_production": 15000.0,
        "systemLocation": {"lat": 19.076, "long": 72.8777},
        "moduleManufacturer": "Tata Power Solar",
        "inverterBrand": "SMA",
        "expectedGeneration": 15500.0,
        "actualGeneration": 14800.0,
        "systemAgeInMonths": 12
    },
    "billing_terms": {
        "tariff_rate": 8.50,
        "escalation_rate": 0.03,
        "billing_cycle": "monthly",
        "payment_terms": "net30",
        "slabs": [
            {"min": 0, "max": 100, "rate": 8.0, "unit": "kWh"},
            {"min": 100, "max": 500, "rate": 7.5, "unit": "kWh"}
        ],
        "touRates": [
            {"timeRange": "22:00-06:00", "rate": 6.5, "unit": "kWh"},
            {"timeRange": "06:00-22:00", "rate": 8.5, "unit": "kWh"}
        ],
        "taxRate": 18.0,
        "latePaymentPenaltyRate": 2.0,
        "currency": "INR",
        "subsidySchemeId": "MNRE-2024-01",
        "autoInvoice": true,
        "gracePeriodDays": 7
    },
    "start_date": "2024-03-15T00:00:00Z",
    "end_date": "2034-03-14T00:00:00Z",
    "contractType": "net_metering",
    "signatories": [
        {"name": "Abhi Kumar", "role": "Customer", "signedAt": "2024-03-15T00:00:00Z"},
        {"name": "Chainfly Rep", "role": "Company", "signedAt": null}
    ],
    "terminationClause": "Either party may terminate with 30 days written notice.",
    "paymentTerms": "net30",
    "curtailmentClauses": "Curtailment as per grid operator instructions.",
    "generationGuarantees": "Minimum 95% of expected generation guaranteed.",
    "createdBy": "admin@chainfly.com"
}
```

Response (success):
```json
{
    "id": "ppa123",
    "customer_id": "customer123",
    "system_specs": { ... },
    "billing_terms": { ... },
    "start_date": "2024-03-15T00:00:00Z",
    "end_date": "2034-03-14T00:00:00Z",
    "contractStatus": "active",
    "contractType": "net_metering",
    "created_at": "2024-03-15T10:00:00Z",
    "updated_at": "2024-03-15T10:00:00Z",
    "createdBy": "admin@chainfly.com",
    "updatedBy": "admin@chainfly.com",
    "signed_at": null,
    "signatories": [ ... ],
    "total_energy_produced": 0,
    "total_billed": 0,
    "total_paid": 0,
    "last_billing_date": null,
    "contract_duration_years": 10.0,
    "current_tariff_rate": 8.50,
    "next_escalation_date": "2025-03-15T00:00:00Z",
    "payment_history": [],
    "energy_production_history": [],
    "billing_history": [],
    "file_path": null,
    "pdfDownloadLink": null,
    "terminationClause": "Either party may terminate with 30 days written notice.",
    "paymentTerms": "net30",
    "curtailmentClauses": "Curtailment as per grid operator instructions.",
    "generationGuarantees": "Minimum 95% of expected generation guaranteed.",
    "subsidySchemeId": "MNRE-2024-01"
}
```

Response (overlap error):
```json
{
    "detail": "Overlapping active/draft PPA exists for this customer/site.",
    "errorCode": "PPA_OVERLAP",
    "documentationLink": "https://docs.yourapi.com/errors#PPA_OVERLAP"
}
```

### Field Descriptions & Enums
- `contractType`: `net_metering`, `gross_metering`, `open_access`
- `contractStatus`: `draft`, `active`, `expired`, `terminated`
- `customerType`: `residential`, `commercial`, `C&I`, `industrial`, `government`, `other`
- `unit`: Always specified (e.g., kW, kWh, INR)
- `currency`: e.g., INR
- `signatories`: Array of `{ name, role, signedAt }`
- `slabs`: Array of `{ min, max, rate, unit }`
- `touRates`: Array of `{ timeRange, rate, unit }`
- `audit trail`: `createdBy`, `updatedBy`, `updated_at`

### Validation Rules
- No two active/draft PPAs for the same site (overlap check)
- latePaymentPenaltyRate ≤ 10%
- All units must be specified
- All enums must use allowed values
- All required fields must be present

### Error Responses

#### 400/422 Validation Error
```json
{
    "detail": "Validation error message",
    "errorCode": "VALIDATION_ERROR",
    "documentationLink": "https://docs.yourapi.com/errors#VALIDATION_ERROR"
}
```

#### 422 Overlapping PPA
```json
{
    "detail": "Overlapping active/draft PPA exists for this customer/site.",
    "errorCode": "PPA_OVERLAP",
    "documentationLink": "https://docs.yourapi.com/errors#PPA_OVERLAP"
}
```

#### 404 Not Found
```json
{
    "detail": "Customer not found"
}
```

#### 401 Unauthorized
```json
{
    "detail": "Invalid token"
}
```

#### 500 Internal Server Error
```json
{
    "detail": "Internal server error"
}
```

### Data Models

#### Customer
```python
class Customer(BaseModel):
    id: Optional[str]
    name: str
    email: str
    address: str
    customerType: CustomerType
    gstNumber: Optional[str]
    linkedPPAs: List[str]
```

#### SystemSpecifications
```python
class SystemSpecifications(BaseModel):
    capacity_kw: float
    panel_type: str
    inverter_type: str
    installation_date: datetime
    estimated_annual_production: float
    systemLocation: Optional[SystemLocation]
    moduleManufacturer: Optional[str]
    inverterBrand: Optional[str]
    expectedGeneration: Optional[float]
    actualGeneration: Optional[float]
    systemAgeInMonths: Optional[int]
```

#### BillingTerms
```python
class BillingTerms(BaseModel):
    tariff_rate: float
    escalation_rate: float
    billing_cycle: str
    payment_terms: str
    slabs: Optional[List[Slab]]
    touRates: Optional[List[ToURate]]
    taxRate: Optional[float]
    latePaymentPenaltyRate: Optional[float]
    currency: str
    subsidySchemeId: Optional[str]
    autoInvoice: bool
    gracePeriodDays: int
```

#### Slab
```python
class Slab(BaseModel):
    min: float
    max: float
    rate: float
    unit: str
```

#### ToURate
```python
class ToURate(BaseModel):
    timeRange: str
    rate: float
    unit: str
```

#### Signatory
```python
class Signatory(BaseModel):
    name: str
    role: str
    signedAt: Optional[datetime]
```

#### PPA
```python
class PPA(BaseModel):
    id: Optional[str]
    customer_id: str
    system_specs: SystemSpecifications
    billing_terms: BillingTerms
    start_date: datetime
    end_date: datetime
    contractStatus: ContractStatus
    contractType: ContractType
    created_at: datetime
    updated_at: Optional[datetime]
    createdBy: Optional[str]
    updatedBy: Optional[str]
    signed_at: Optional[datetime]
    signatories: List[Signatory]
    total_energy_produced: float
    total_billed: float
    total_paid: float
    last_billing_date: Optional[datetime]
    contract_duration_years: float
    current_tariff_rate: float
    next_escalation_date: datetime
    payment_history: List[dict]
    energy_production_history: List[dict]
    billing_history: List[dict]
    file_path: Optional[str]
    pdfDownloadLink: Optional[str]
    terminationClause: Optional[str]
    paymentTerms: Optional[str]
    curtailmentClauses: Optional[str]
    generationGuarantees: Optional[str]
    subsidySchemeId: Optional[str]
```

#### EnergyUsage
```python
class EnergyUsage(BaseModel):
    ppa_id: str
    kwh_used: float
    reading_date: datetime
    source: Optional[str]
    unit: str
    timestampStart: Optional[datetime]
    timestampEnd: Optional[datetime]
    importEnergy: Optional[float]
    exportEnergy: Optional[float]
```

#### HTTPValidationError
```python
class HTTPValidationError(BaseModel):
    detail: Any
    errorCode: Optional[str]
    documentationLink: Optional[str]
```

#### ValidationError
```python
class ValidationError(BaseModel):
    loc: List[str]
    msg: str
    type: str
    errorCode: Optional[str]
    documentationLink: Optional[str]
```

## Setup and Installation

1. Clone the repository
2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up Firebase:
   - Create a Firebase project
   - Download the service account key
   - Set the environment variable:
```bash
export FIREBASE_CREDENTIALS_JSON='{"type": ... }'
```

4. Create a `.env` file with the following variables (optional):
```
FIREBASE_PROJECT_ID=your-project-id
```

5. Run the development server:
```bash
uvicorn main:app --reload
```

## Testing
Run the test suite:
```bash
pytest
```

## Contributing
1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License
MIT 