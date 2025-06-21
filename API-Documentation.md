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
    "address": "123 Solar Street, Mumbai, Maharashtra"
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
        "estimated_annual_production": 15000.0
    },
    "billing_terms": {
        "tariff_rate": 8.50,
        "escalation_rate": 0.03,
        "billing_cycle": "monthly",
        "payment_terms": "net30"
    },
    "start_date": "2024-03-15T00:00:00Z",
    "end_date": "2034-03-14T00:00:00Z"
}
```

Response:
```json
{
    "id": "ppa123",
    "customer_id": "customer123",
    "system_specs": {
        "capacity_kw": 10.5,
        "panel_type": "Monocrystalline",
        "inverter_type": "String Inverter",
        "installation_date": "2024-03-15T00:00:00Z",
        "estimated_annual_production": 15000.0
    },
    "billing_terms": {
        "tariff_rate": 8.50,
        "escalation_rate": 0.03,
        "billing_cycle": "monthly",
        "payment_terms": "net30"
    },
    "start_date": "2024-03-15T00:00:00Z",
    "end_date": "2034-03-14T00:00:00Z",
    "status": "draft",
    "created_at": "2024-03-15T10:00:00Z",
    "signed_at": null,
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
    "file_path": null
}
```

Field Descriptions:
- `system_specs`:
  - `capacity_kw`: System capacity in kilowatts
  - `panel_type`: Type of solar panels (e.g., Monocrystalline, Polycrystalline)
  - `inverter_type`: Type of inverter (e.g., String Inverter, Microinverter)
  - `installation_date`: Date when the system was/will be installed
  - `estimated_annual_production`: Estimated annual energy production in kWh
- `billing_terms`:
  - `tariff_rate`: Base tariff rate per kWh in Indian Rupees (e.g., 8.50 for ₹8.50/kWh)
  - `escalation_rate`: Annual escalation rate (e.g., 0.03 for 3% annual increase)
  - `billing_cycle`: Billing cycle (must be one of: monthly, quarterly, annually)
  - `payment_terms`: Payment terms (must be one of: net15, net30, net45, net60)

Validation Rules:
- System capacity must be greater than 0
- Estimated annual production must be greater than 0
- Panel type and inverter type are required
- Tariff rate must be greater than 0 (typically ₹3-12/kWh for Indian market)
- Escalation rate cannot be negative (typically 0-5% for Indian market)
- Billing cycle must be one of: monthly, quarterly, annually
- Payment terms must be one of: net15, net30, net45, net60
- Start date must be before end date
- Start date cannot be more than 1 year in the past (for existing installations)
- Start date cannot be more than 2 years in the future (for planned installations)
- PPA status will be automatically set to "active" if start date is in the past or today
- PPA status will be set to "draft" if start date is in the future

#### List PPAs
```http
GET /ppas
```
Optional query parameter: `customer_id`

#### Get PPA
```http
GET /ppas/{ppa_id}
```

#### Sign PPA
```http
POST /ppas/{ppa_id}/sign
```

#### Get PPA PDF
```http
GET /ppas/{ppa_id}/pdf
```
Generates a professional PPA document in Indian format with:
- Agreement details with PPA number
- System specifications
- Billing terms in Indian Rupees
- Standard Indian terms and conditions
- Signature blocks for both parties

### Energy Usage Management

#### Add Energy Usage
```http
POST /ppas/{ppa_id}/energy-usage
```
Request body:
```json
{
    "kwh_used": 850.5,
    "reading_date": "2024-03-15T00:00:00Z"
}
```

### Invoice Management

#### Generate Invoice
```http
POST /ppas/{ppa_id}/invoices/generate
```
Request body:
```json
{
    "kwh_used": 850.5,
    "reading_date": "2024-03-15T00:00:00Z"
}
```

#### List PPA Invoices
```http
GET /ppas/{ppa_id}/invoices
```

#### Get Invoice PDF
```http
GET /ppas/{ppa_id}/invoices/{invoice_id}/pdf
```

#### Pay Invoice
```http
POST /ppas/{ppa_id}/invoices/{invoice_id}/pay
```

## Error Responses

### 400 Bad Request
```json
{
    "detail": "PPA is not active"
}
```

### 401 Unauthorized
```json
{
    "detail": "Invalid token"
}
```

### 404 Not Found
```json
{
    "detail": "PPA not found"
}
```

### 422 Unprocessable Entity
```json
{
    "detail": [
        {
            "loc": ["body", "tariff_rate"],
            "msg": "field required",
            "type": "value_error.missing"
        }
    ]
}
```

### 500 Internal Server Error
```json
{
    "detail": "Internal server error"
}
```

## Data Models

### Customer
```python
class Customer(BaseModel):
    name: str
    email: str
    address: str
```

### SystemSpecifications
```python
class SystemSpecifications(BaseModel):
    capacity_kw: float
    panel_type: str
    inverter_type: str
    installation_date: datetime
    estimated_annual_production: float
```

### BillingTerms
```python
class BillingTerms(BaseModel):
    tariff_rate: float
    escalation_rate: float
    billing_cycle: str
    payment_terms: str
```

### PPA
```python
class PPA(BaseModel):
    customer_id: str
    system_specs: SystemSpecifications
    billing_terms: BillingTerms
    start_date: datetime
    end_date: datetime
    status: str
    file_path: Optional[str]
    created_at: datetime
    signed_at: Optional[datetime]
    total_energy_produced: float = 0
    total_billed: float = 0
    total_paid: float = 0
    last_billing_date: Optional[datetime]
    contract_duration_years: float
    current_tariff_rate: float
    next_escalation_date: datetime
    payment_history: List[dict] = []
    energy_production_history: List[dict] = []
    billing_history: List[dict] = []
```

### EnergyUsage
```python
class EnergyUsage(BaseModel):
    kwh_used: float
    reading_date: datetime
```

### Invoice
```python
class Invoice(BaseModel):
    ppa_id: str
    amount: float
    kwh_used: float
    tariff_rate: float
    billing_date: datetime
    due_date: datetime
    status: str
    paid_at: Optional[datetime]
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
export GOOGLE_APPLICATION_CREDENTIALS="path/to/service-account-key.json"
```

4. Create a `.env` file with the following variables:
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