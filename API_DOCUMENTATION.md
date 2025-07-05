# Solar Billing API Documentation

## Overview

The Solar Billing API is a comprehensive system for managing Power Purchase Agreements (PPAs), customer billing, and energy usage tracking for solar power systems. The API provides endpoints for creating and managing customers, PPAs, energy usage records, invoices, and generating PDF documents.

## Base URL

```
http://localhost:8000
```

## Authentication

The API uses Firebase Authentication. All endpoints (except `/health`, `/`, and `/auth/login`) require authentication via Bearer token in the Authorization header.

### Getting an Authentication Token

```bash
POST /auth/login
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "your_password"
}
```

**Response:**
```json
{
  "idToken": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refreshToken": "AMf-vBw...",
  "expiresIn": "3600",
  "localId": "user123"
}
```

### Using Authentication

Include the token in subsequent requests:
```bash
Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...
```

## Data Models

### Customer Types

- `residential`: Residential customers
- `commercial`: Commercial establishments
- `ci`: Commercial & Industrial
- `industrial`: Industrial facilities
- `government`: Government entities
- `other`: Other customer types

### Contract Types

- `net_metering`: Net metering arrangement
- `gross_metering`: Gross metering arrangement
- `open_access`: Open access arrangement

### Contract Status

- `draft`: PPA in draft state
- `active`: Active PPA contract
- `expired`: Expired PPA contract
- `terminated`: Terminated PPA contract

### Business Models

- `capex`: Capital Expenditure - customer owns the system
- `opex`: Operational Expenditure - service provider owns the system

### Escalation Types

- `fixed_percentage`: Fixed percentage per year
- `cpi_linked`: Consumer Price Index linked
- `wholesale_price_index`: Wholesale price index linked
- `custom_schedule`: Custom escalation schedule

### State Codes

All Indian states and union territories are supported (AP, AR, AS, BR, CT, GA, GJ, HR, HP, JH, KA, KL, MP, MH, MN, ML, MZ, NL, OR, PB, RJ, SK, TN, TS, TR, UP, UT, WB, DL, JK, LA, CH, DN, DD, AN, PY)

### Tariff Categories

- `residential_low`: Residential low consumption
- `residential_high`: Residential high consumption
- `commercial_small`: Small commercial
- `commercial_large`: Large commercial
- `industrial_lt`: Industrial LT
- `industrial_ht`: Industrial HT
- `agricultural`: Agricultural
- `government`: Government institutions
- `street_light`: Street lighting
- `solar_rooftop`: Solar rooftop specific
- `solar_utility`: Solar utility scale

## Endpoints

### Health Check

**GET** `/health`

Check API health and service status.

**Response:**
```json
{
  "status": "healthy",
  "firebase_available": true,
  "timestamp": "2024-01-15T10:30:00Z"
}
```

### DISCOM Management

#### Create DISCOM

**POST** `/discoms`

Create a new Distribution Company (DISCOM) with API configuration for dynamic tariff retrieval.

**Request Body:**
```json
{
  "discom_id": "TATA_POWER_DELHI",
  "discom_name": "Tata Power Delhi Distribution Limited",
  "state_code": "DL",
  "license_number": "DL-01-2024",
  "website": "https://www.tatapower-ddl.com",
  "api_endpoint": "https://api.tatapower-ddl.com/tariffs",
  "api_key": "your_api_key_here",
  "tariff_update_frequency": "monthly"
}
```

**Parameters:**
- `discom_id` (string, required): Unique identifier for the DISCOM
- `discom_name` (string, required): Name of the distribution company
- `state_code` (StateCode, required): State where DISCOM operates
- `license_number` (string, optional): DISCOM license number
- `website` (string, optional): DISCOM website URL
- `api_endpoint` (string, optional): DISCOM API endpoint for tariff data
- `api_key` (string, optional): API key for DISCOM tariff API
- `tariff_update_frequency` (string, optional): How often tariffs are updated (default: monthly)

#### List DISCOMs

**GET** `/discoms`

Retrieve all DISCOMs with optional filtering.

**Query Parameters:**
- `state_code` (StateCode, optional): Filter by state code

**Response:**
```json
[
  {
    "discom_id": "TATA_POWER_DELHI",
    "discom_name": "Tata Power Delhi Distribution Limited",
    "state_code": "DL",
    "license_number": "DL-01-2024",
    "website": "https://www.tatapower-ddl.com",
    "api_endpoint": "https://api.tatapower-ddl.com/tariffs",
    "tariff_update_frequency": "monthly",
    "last_tariff_update": "2024-01-15T10:30:00Z",
    "is_active": true,
    "created_at": "2024-01-15T10:30:00Z"
  }
]
```

#### Get DISCOM by ID

**GET** `/discoms/{discom_id}`

Retrieve detailed information about a specific DISCOM.

**Path Parameters:**
- `discom_id` (string, required): Unique identifier of the DISCOM

#### Update DISCOM

**PUT** `/discoms/{discom_id}`

Update DISCOM configuration including API settings.

**Path Parameters:**
- `discom_id` (string, required): Unique identifier of the DISCOM

**Request Body:** DISCOM update fields

### Dynamic Tariff Management

#### Get Dynamic Tariff

**POST** `/tariffs/dynamic`

Retrieves real-time tariff based on DISCOM, state, and customer type.

**Request Body:**
```json
{
  "discom_id": "TATA_POWER_DELHI",
  "state_code": "DL",
  "tariff_category": "residential_low",
  "customer_type": "residential",
  "consumption_kwh": 500.0,
  "contract_date": "2024-01-15T00:00:00Z",
  "include_slabs": true,
  "include_tou": true
}
```

**Parameters:**
- `discom_id` (string, required): DISCOM identifier
- `state_code` (StateCode, required): State code
- `tariff_category` (TariffCategory, required): Tariff category
- `customer_type` (CustomerType, required): Customer type
- `consumption_kwh` (float, optional): Monthly consumption in kWh
- `contract_date` (datetime, required): Contract date for tariff calculation
- `include_slabs` (boolean, optional): Whether to include tariff slabs (default: true)
- `include_tou` (boolean, optional): Whether to include time-of-use rates (default: true)

**Retrieval Priority:**
1. DISCOM API (if available and configured)
2. Regulatory order database
3. Manual override
4. Calculated based on rules
5. Fallback tariff

**Response:**
```json
{
  "tariff_id": "tariff_123",
  "discom_name": "Tata Power Delhi Distribution Limited",
  "state_code": "DL",
  "tariff_category": "residential_low",
  "customer_type": "residential",
  "base_rate": 8.5,
  "currency": "INR",
  "effective_from": "2024-01-01T00:00:00Z",
  "effective_until": "2024-12-31T23:59:59Z",
  "regulatory_order": "DERC/2024/01",
  "source": "discom_api",
  "slabs": [
    {
      "slab_id": "slab_1",
      "min_consumption": 0.0,
      "max_consumption": 100.0,
      "rate": 8.0,
      "unit": "INR/kWh",
      "description": "First 100 units"
    },
    {
      "slab_id": "slab_2",
      "min_consumption": 100.0,
      "max_consumption": 500.0,
      "rate": 9.0,
      "unit": "INR/kWh",
      "description": "101-500 units"
    }
  ],
  "tou_rates": [
    {
      "tou_id": "tou_1",
      "time_range": "22:00-06:00",
      "rate": 6.5,
      "unit": "INR/kWh",
      "description": "Off-peak hours"
    }
  ],
  "calculated_rate": 8.0,
  "last_updated": "2024-01-15T10:30:00Z",
  "next_update": "2024-02-15T10:30:00Z"
}
```

#### Create Tariff Structure

**POST** `/tariffs`

Create a new tariff structure for a specific DISCOM and customer category.

**Request Body:**
```json
{
  "discom_id": "TATA_POWER_DELHI",
  "state_code": "DL",
  "tariff_category": "residential_low",
  "customer_type": "residential",
  "base_rate": 8.5,
  "currency": "INR",
  "effective_from": "2024-01-01T00:00:00Z",
  "effective_until": "2024-12-31T23:59:59Z",
  "regulatory_order": "DERC/2024/01",
  "order_number": "DERC-2024-001",
  "order_date": "2024-01-01T00:00:00Z",
  "source": "regulatory_order"
}
```

#### Add Tariff Slab

**POST** `/tariffs/{tariff_id}/slabs`

Adds a tariff slab to an existing tariff structure.

**Path Parameters:**
- `tariff_id` (string, required): Unique identifier of the tariff

**Request Body:**
```json
{
  "min_consumption": 0.0,
  "max_consumption": 100.0,
  "rate": 8.0,
  "unit": "INR/kWh",
  "description": "First 100 units"
}
```

#### Add Time-of-Use Tariff

**POST** `/tariffs/{tariff_id}/tou-rates`

Adds a time-of-use tariff rate to an existing tariff structure.

**Path Parameters:**
- `tariff_id` (string, required): Unique identifier of the tariff

**Request Body:**
```json
{
  "time_range": "22:00-06:00",
  "rate": 6.5,
  "unit": "INR/kWh",
  "season": "summer",
  "day_type": "weekday",
  "description": "Off-peak hours"
}
```

#### Update DISCOM Tariffs

**POST** `/discoms/{discom_id}/update-tariffs`

Manually triggers tariff update for a specific DISCOM from their API.

**Path Parameters:**
- `discom_id` (string, required): Unique identifier of the DISCOM

**Process:**
1. Checks if DISCOM API is configured
2. Fetches latest tariffs from DISCOM API
3. Stores updated tariffs in database
4. Updates last tariff update timestamp

**Response:**
```json
{
  "discom_id": "TATA_POWER_DELHI",
  "status": "success",
  "message": "Tariffs updated successfully",
  "updated_at": "2024-01-15T10:30:00Z"
}
```

#### Search Tariffs

**GET** `/tariffs/search`

Search for tariffs based on various criteria.

**Query Parameters:**
- `discom_id` (string, optional): Filter by DISCOM ID
- `state_code` (StateCode, optional): Filter by state code
- `tariff_category` (TariffCategory, optional): Filter by tariff category
- `customer_type` (CustomerType, optional): Filter by customer type
- `source` (TariffSource, optional): Filter by tariff source
- `effective_from` (datetime, optional): Filter by effective from date
- `effective_until` (datetime, optional): Filter by effective until date

**Response:**
```json
[
  {
    "tariff_id": "tariff_123",
    "discom_id": "TATA_POWER_DELHI",
    "state_code": "DL",
    "tariff_category": "residential_low",
    "customer_type": "residential",
    "base_rate": 8.5,
    "currency": "INR",
    "effective_from": "2024-01-01T00:00:00Z",
    "effective_until": "2024-12-31T23:59:59Z",
    "regulatory_order": "DERC/2024/01",
    "source": "regulatory_order",
    "is_active": true
  }
]
```

### Customer Management

#### Create Customer

**POST** `/customers`

Create a new customer in the system.

**Request Body:**
```json
{
  "name": "John Doe",
  "email": "john.doe@example.com",
  "address": "123 Solar Street, Green City, 12345"
}
```

**Parameters:**
- `name` (string, required): Full name of the customer
- `email` (string, required): Email address for communication and billing
- `address` (string, required): Complete postal address

**Response:**
```json
{
  "id": "cust_abc123",
  "name": "John Doe",
  "email": "john.doe@example.com",
  "address": "123 Solar Street, Green City, 12345"
}
```

#### List Customers

**GET** `/customers`

Retrieve all customers in the system.

**Response:**
```json
[
  {
    "id": "cust_abc123",
    "name": "John Doe",
    "email": "john.doe@example.com",
    "address": "123 Solar Street, Green City, 12345"
  }
]
```

### Subsidy Scheme Management

#### Create Subsidy Scheme

**POST** `/subsidy-schemes`

Create a new state-specific subsidy scheme for solar installations.

**Request Body:**
```json
{
  "scheme_id": "GJ_SOLAR_2024",
  "scheme_name": "Gujarat Solar Rooftop Scheme 2024",
  "state_code": "GJ",
  "subsidy_type": "capital",
  "subsidy_rate": 30.0,
  "subsidy_unit": "%",
  "max_capacity_kw": 10.0,
  "min_capacity_kw": 1.0,
  "valid_from": "2024-01-01T00:00:00Z",
  "valid_until": "2024-12-31T23:59:59Z",
  "description": "30% capital subsidy for residential solar installations",
  "documentation_url": "https://gujarat.gov.in/solar-scheme"
}
```

**Parameters:**
- `scheme_id` (string, required): Unique identifier for the scheme
- `scheme_name` (string, required): Name of the subsidy scheme
- `state_code` (StateCode, required): State where scheme is applicable
- `subsidy_type` (string, required): Type of subsidy (capital, generation, tax)
- `subsidy_rate` (float, required): Subsidy rate as percentage or fixed amount
- `subsidy_unit` (string, required): Unit for subsidy (% or currency/kW or currency/kWh)
- `max_capacity_kw` (float, optional): Maximum system capacity eligible
- `min_capacity_kw` (float, optional): Minimum system capacity eligible
- `valid_from` (datetime, required): Scheme validity start date
- `valid_until` (datetime, optional): Scheme validity end date
- `description` (string, optional): Detailed description of the scheme
- `documentation_url` (string, optional): URL to official documentation

#### List Subsidy Schemes

**GET** `/subsidy-schemes`

Retrieve all available subsidy schemes with optional filtering.

**Query Parameters:**
- `state_code` (StateCode, optional): Filter by state code
- `subsidy_type` (string, optional): Filter by subsidy type

**Response:**
```json
[
  {
    "id": "scheme_123",
    "scheme_id": "GJ_SOLAR_2024",
    "scheme_name": "Gujarat Solar Rooftop Scheme 2024",
    "state_code": "GJ",
    "subsidy_type": "capital",
    "subsidy_rate": 30.0,
    "subsidy_unit": "%",
    "max_capacity_kw": 10.0,
    "min_capacity_kw": 1.0,
    "valid_from": "2024-01-01T00:00:00Z",
    "valid_until": "2024-12-31T23:59:59Z"
  }
]
```

#### Get Subsidy Scheme

**GET** `/subsidy-schemes/{scheme_id}`

Retrieve detailed information about a specific subsidy scheme.

**Path Parameters:**
- `scheme_id` (string, required): Unique identifier of the subsidy scheme

### PPA Management

#### Create PPA

**POST** `/ppas`

Create a new Power Purchase Agreement with comprehensive specifications including business model and escalation details.

**Request Body:**
```json
{
  "customer_id": "cust_abc123",
  "system_specs": {
    "capacity_kw": 10.5,
    "panel_type": "Monocrystalline",
    "inverter_type": "String Inverter",
    "installation_date": "2024-01-15T00:00:00Z",
    "estimated_annual_production": 15000.0,
    "systemLocation": {
      "lat": 12.9716,
      "long": 77.5946
    },
    "moduleManufacturer": "SunPower",
    "inverterBrand": "SMA",
    "expectedGeneration": 1250.0,
    "actualGeneration": 1180.0,
    "systemAgeInMonths": 24
  },
  "billing_terms": {
    "tariff_rate": 8.0,
    "escalation_type": "fixed_percentage",
    "escalation_rate": 0.02,
    "escalation_schedule": [
      {
        "year": 1,
        "escalation_rate": 0.03,
        "description": "First year escalation"
      },
      {
        "year": 2,
        "escalation_rate": 0.02,
        "description": "Second year escalation"
      }
    ],
    "billing_cycle": "monthly",
    "payment_terms": "net30",
    "slabs": [
      {
        "min": 0.0,
        "max": 100.0,
        "rate": 8.5,
        "unit": "INR/kWh"
      },
      {
        "min": 100.0,
        "max": 500.0,
        "rate": 9.0,
        "unit": "INR/kWh"
      }
    ],
    "touRates": [
      {
        "timeRange": "22:00-06:00",
        "rate": 6.5,
        "unit": "INR/kWh"
      }
    ],
    "taxRate": 18.0,
    "latePaymentPenaltyRate": 2.0,
    "currency": "INR",
    "subsidySchemeId": "GJ_SOLAR_2024",
    "autoInvoice": false,
    "gracePeriodDays": 7,
    "business_model": "capex",
    "capex_amount": 500000.0,
    "maintenance_included": true,
    "insurance_included": true
  },
  "start_date": "2024-01-15T00:00:00Z",
  "end_date": "2029-01-15T00:00:00Z",
  "contractType": "net_metering",
  "signatories": [
    {
      "name": "Jane Smith",
      "role": "Customer Representative"
    }
  ],
  "terminationClause": "Either party may terminate with 30 days notice",
  "paymentTerms": "Payment due within 30 days of invoice",
  "curtailmentClauses": "Grid operator may curtail generation during emergencies",
  "generationGuarantees": "Minimum 80% of estimated annual production guaranteed",
  "createdBy": "user_12345"
}
```

**Key Parameters:**

**System Specifications:**
- `capacity_kw` (float, required): System capacity in kilowatts (kW)
- `panel_type` (string, required): Type of solar panels (e.g., "Monocrystalline", "Polycrystalline")
- `inverter_type` (string, required): Type of inverter (e.g., "String Inverter", "Microinverter")
- `installation_date` (datetime, required): Date when system was installed
- `estimated_annual_production` (float, required): Estimated annual energy production in kWh
- `systemLocation` (object, optional): Geographic coordinates (lat/long in decimal degrees)
- `moduleManufacturer` (string, optional): Manufacturer of solar modules
- `inverterBrand` (string, optional): Brand of the inverter
- `expectedGeneration` (float, optional): Expected monthly generation in kWh
- `actualGeneration` (float, optional): Actual monthly generation in kWh
- `systemAgeInMonths` (integer, optional): Age of system in months

**Billing Terms:**
- `tariff_rate` (float, required): Base tariff rate per kWh in currency units
- `escalation_type` (EscalationType, required): Type of escalation applied
- `escalation_rate` (float, required): Annual escalation rate as decimal (e.g., 0.02 for 2%)
- `escalation_schedule` (array, optional): Custom escalation schedule for specific years
- `billing_cycle` (string, required): Billing frequency ("monthly", "quarterly", "annually")
- `payment_terms` (string, required): Payment terms in days ("net15", "net30", "net45", "net60")
- `slabs` (array, optional): Tiered billing slabs for different consumption levels
- `touRates` (array, optional): Time-of-Use rates for different time periods
- `taxRate` (float, optional): Tax rate as percentage (e.g., 18.0 for 18%)
- `latePaymentPenaltyRate` (float, optional): Late payment penalty rate as percentage (max 10%)
- `currency` (string, optional): Currency code for billing (default: "INR")
- `subsidySchemeId` (string, optional): Reference to applicable subsidy scheme
- `autoInvoice` (boolean, optional): Whether invoices should be generated automatically
- `gracePeriodDays` (integer, optional): Grace period in days before late payment penalties

**Business Model Fields:**
- `business_model` (BusinessModel, required): Business model (CAPEX or OPEX)
- `capex_amount` (float, optional): Total CAPEX amount in currency units (required for CAPEX)
- `opex_monthly_fee` (float, optional): Monthly OPEX fee in currency units (required for OPEX)
- `opex_energy_rate` (float, optional): Energy rate for OPEX model in currency/kWh (required for OPEX)
- `maintenance_included` (boolean, optional): Whether maintenance is included in the model
- `insurance_included` (boolean, optional): Whether insurance is included in the model

**Contract Details:**
- `customer_id` (string, required): Unique identifier of the customer
- `start_date` (datetime, required): Contract start date
- `end_date` (datetime, required): Contract end date
- `contractType` (enum, optional): Type of PPA contract (default: "net_metering")
- `signatories` (array, optional): List of contract signatories
- `terminationClause` (string, optional): Contract termination terms
- `paymentTerms` (string, optional): Detailed payment terms
- `curtailmentClauses` (string, optional): Energy curtailment terms
- `generationGuarantees` (string, optional): Energy generation guarantees
- `createdBy` (string, optional): User ID who created the PPA

**Validation Rules:**
- No overlapping active/draft PPAs for the same customer
- Customer must exist in the system
- All datetime fields must be timezone-aware
- Late payment penalty rate cannot exceed 10%
- CAPEX amount must be specified for CAPEX model
- OPEX monthly fee and energy rate must be specified for OPEX model
- Escalation schedule years must be unique and start from 1

#### Get Comprehensive PPA Details

**GET** `/ppas/{ppa_id}/details`

Retrieve comprehensive PPA details including business model, escalation history, tenure information, and financial projections.

**Path Parameters:**
- `ppa_id` (string, required): Unique identifier of the PPA

**Response:**
```json
{
  "ppa_id": "ppa_xyz789",
  "customer": {
    "id": "cust_abc123",
    "name": "John Doe",
    "email": "john.doe@example.com",
    "address": "123 Solar Street, Green City, 12345"
  },
  "basic_info": {
    "contract_type": "net_metering",
    "contract_status": "active",
    "start_date": "2024-01-15T00:00:00Z",
    "end_date": "2029-01-15T00:00:00Z",
    "tenure_years": 5.0,
    "tenure_remaining_years": 4.8,
    "system_capacity_kw": 10.5,
    "estimated_annual_production_kwh": 15000.0
  },
  "business_model": {
    "model_type": "CAPEX",
    "total_capex": 500000.0,
    "payment_schedule": [
      {
        "installment": 1,
        "percentage": 20.0,
        "amount": 100000.0,
        "due_date": "2024-01-15T00:00:00Z",
        "description": "Upfront payment"
      },
      {
        "installment": 2,
        "percentage": 80.0,
        "amount": 400000.0,
        "due_date": "2024-02-14T00:00:00Z",
        "description": "Balance payment"
      }
    ],
    "maintenance_included": true,
    "insurance_included": true
  },
  "billing_terms": {
    "current_tariff_rate": 8.16,
    "base_tariff_rate": 8.0,
    "escalation_type": "fixed_percentage",
    "escalation_rate": 0.02,
    "billing_cycle": "monthly",
    "payment_terms": "net30",
    "currency": "INR"
  },
  "escalation": {
    "history": [
      {
        "year": 1,
        "escalation_rate": 0.02,
        "new_tariff_rate": 8.16,
        "date_applied": "2025-01-15T00:00:00Z"
      }
    ],
    "projections": [
      {
        "year": 1,
        "escalation_rate": 0.02,
        "projected_tariff": 8.16
      },
      {
        "year": 2,
        "escalation_rate": 0.02,
        "projected_tariff": 8.32
      }
    ],
    "next_escalation_date": "2025-01-15T00:00:00Z"
  },
  "subsidy": {
    "scheme_id": "GJ_SOLAR_2024",
    "scheme_details": {
      "scheme_name": "Gujarat Solar Rooftop Scheme 2024",
      "subsidy_rate": 30.0,
      "subsidy_unit": "%"
    },
    "subsidy_applied": 150000.0,
    "subsidy_details": {
      "type": "capital",
      "amount": 150000.0
    }
  },
  "financial_summary": {
    "total_energy_produced_kwh": 1250.5,
    "total_billed": 10204.08,
    "total_paid": 10204.08,
    "outstanding_amount": 0.0,
    "last_billing_date": "2024-01-15T10:30:00Z"
  },
  "performance_metrics": {
    "energy_production_history": [...],
    "billing_history": [...],
    "payment_history": [...]
  }
}
```

#### Record OPEX Payment

**POST** `/ppas/{ppa_id}/opex-payment`

Record an OPEX payment for a PPA, including energy consumption and monthly fee breakdown.

**Path Parameters:**
- `ppa_id` (string, required): Unique identifier of the PPA

**Request Body:**
```json
{
  "amount": 8500.0,
  "energy_consumed_kwh": 1250.5,
  "payment_date": "2024-01-15T10:30:00Z",
  "payment_method": "bank_transfer",
  "reference_number": "TXN123456789"
}
```

**Parameters:**
- `amount` (float, required): Total payment amount
- `energy_consumed_kwh` (float, required): Energy consumed in kWh
- `payment_date` (datetime, optional): Date of payment (defaults to current date)
- `payment_method` (string, optional): Method of payment
- `reference_number` (string, optional): Payment reference number

**Response:**
```json
{
  "payment_id": "opex_payment_1705312200.123",
  "ppa_id": "ppa_xyz789",
  "amount": 8500.0,
  "energy_consumed_kwh": 1250.5,
  "payment_date": "2024-01-15T10:30:00Z",
  "monthly_fee": 5000.0,
  "energy_cost": 3500.0,
  "payment_method": "bank_transfer",
  "reference_number": "TXN123456789"
}
```

#### List PPAs

**GET** `/ppas`

Retrieve all PPAs or filter by customer.

**Query Parameters:**
- `customer_id` (string, optional): Filter PPAs by customer ID

**Response:**
```json
[
  {
    "id": "ppa_xyz789",
    "customer_id": "cust_abc123",
    "system_specs": { ... },
    "billing_terms": { ... },
    "start_date": "2024-01-15T00:00:00Z",
    "end_date": "2029-01-15T00:00:00Z",
    "contractType": "net_metering",
    "contractStatus": "draft",
    "business_model": "capex",
    "tenure_years": 5.0,
    "created_at": "2024-01-15T10:30:00Z",
    "updated_at": "2024-01-15T10:30:00Z"
  }
]
```

#### Get PPA by ID

**GET** `/ppas/{ppa_id}`

Retrieve a specific PPA by its unique identifier.

**Path Parameters:**
- `ppa_id` (string, required): Unique identifier of the PPA

#### Sign PPA

**POST** `/ppas/{ppa_id}/sign`

Mark a PPA as signed and activate it for billing.

**Path Parameters:**
- `ppa_id` (string, required): Unique identifier of the PPA to sign

#### Generate PPA PDF

**GET** `/ppas/{ppa_id}/pdf`

Generate a downloadable PDF document containing the complete PPA.

**Path Parameters:**
- `ppa_id` (string, required): Unique identifier of the PPA

**Response:** PDF file containing the PPA document

### Energy Usage Management

#### Add Energy Usage

**POST** `/ppas/{ppa_id}/energy-usage`

Record energy consumption data for a PPA.

**Path Parameters:**
- `ppa_id` (string, required): Unique identifier of the PPA

**Request Body:**
```json
{
  "kwh_used": 1250.5,
  "reading_date": "2024-01-15T10:30:00Z",
  "source": "smart_meter",
  "unit": "kWh",
  "timestampStart": "2024-01-15T00:00:00Z",
  "timestampEnd": "2024-01-15T23:59:59Z",
  "importEnergy": 50.0,
  "exportEnergy": 200.0
}
```

**Parameters:**
- `kwh_used` (float, required): Energy consumed in kilowatt-hours (kWh)
- `reading_date` (datetime, required): Date and time of the energy reading
- `source` (string, optional): Source of the energy data (e.g., "inverter", "smart_meter")
- `unit` (string, optional): Unit of measurement (default: "kWh")
- `timestampStart` (datetime, optional): Start timestamp for interval-based readings
- `timestampEnd` (datetime, optional): End timestamp for interval-based readings
- `importEnergy` (float, optional): Imported energy from grid in kWh (for net metering)
- `exportEnergy` (float, optional): Exported energy to grid in kWh (for net metering)

**Response:**
```json
{
  "id": "usage_123",
  "ppa_id": "ppa_xyz789",
  "kwh_used": 1250.5,
  "reading_date": "2024-01-15T10:30:00Z",
  "source": "smart_meter",
  "unit": "kWh",
  "importEnergy": 50.0,
  "exportEnergy": 200.0
}
```

### Invoice Management

#### Generate Invoice

**POST** `/ppas/{ppa_id}/invoices/generate`

Generate an invoice for a PPA based on energy usage.

**Path Parameters:**
- `ppa_id` (string, required): Unique identifier of the PPA

**Request Body:** Same as energy usage request

**Calculation Process:**
1. Validates PPA is active and invoice generation is due
2. Calculates current tariff rate considering escalation type and schedule
3. Applies tiered billing slabs if configured
4. Applies time-of-use rates if configured
5. Calculates taxes and any applicable penalties
6. Updates PPA billing information

**Response:**
```json
{
  "id": "inv_456",
  "customer_id": "cust_abc123",
  "ppa_id": "ppa_xyz789",
  "invoice_number": "INV-2024-001",
  "billing_period": "2024-01",
  "kwh_used": 1250.5,
  "tariff_rate": 8.16,
  "base_amount": 10204.08,
  "tax_amount": 1836.73,
  "total_amount": 12040.81,
  "due_date": "2024-02-14T00:00:00Z",
  "status": "unpaid",
  "created_at": "2024-01-15T10:30:00Z"
}
```

#### List PPA Invoices

**GET** `/ppas/{ppa_id}/invoices`

Retrieve all invoices for a specific PPA.

**Path Parameters:**
- `ppa_id` (string, required): Unique identifier of the PPA

#### Generate Invoice PDF

**GET** `/ppas/{ppa_id}/invoices/{invoice_id}/pdf`

Generate a downloadable PDF invoice.

**Path Parameters:**
- `ppa_id` (string, required): Unique identifier of the PPA
- `invoice_id` (string, required): Unique identifier of the invoice

**Response:** PDF file containing the invoice

#### Mark Invoice as Paid

**POST** `/ppas/{ppa_id}/invoices/{invoice_id}/pay`

Mark an invoice as paid and update PPA payment tracking.

**Path Parameters:**
- `ppa_id` (string, required): Unique identifier of the PPA
- `invoice_id` (string, required): Unique identifier of the invoice

**Process:**
1. Validates both PPA and invoice exist
2. Marks invoice as paid with payment timestamp
3. Updates PPA payment tracking information
4. Records payment amount and date

## Business Model Scenarios

### CAPEX Model

In the CAPEX (Capital Expenditure) model, the customer owns the solar system and pays for the entire installation upfront or through installments.

**Key Features:**
- Customer owns the system
- Upfront capital investment required
- Customer responsible for maintenance and insurance
- Lower long-term energy costs
- Tax benefits for depreciation

**Example CAPEX PPA:**
```json
{
  "business_model": "capex",
  "capex_amount": 500000.0,
  "maintenance_included": false,
  "insurance_included": false,
  "billing_terms": {
    "tariff_rate": 8.0,
    "escalation_type": "fixed_percentage",
    "escalation_rate": 0.02
  }
}
```

### OPEX Model

In the OPEX (Operational Expenditure) model, the service provider owns and maintains the solar system, and the customer pays for energy consumed.

**Key Features:**
- Service provider owns the system
- No upfront capital investment
- Service provider handles maintenance and insurance
- Predictable monthly payments
- Energy cost savings without capital risk

**Example OPEX PPA:**
```json
{
  "business_model": "opex",
  "opex_monthly_fee": 5000.0,
  "opex_energy_rate": 6.5,
  "maintenance_included": true,
  "insurance_included": true,
  "billing_terms": {
    "tariff_rate": 6.5,
    "escalation_type": "fixed_percentage",
    "escalation_rate": 0.03
  }
}
```

## Escalation Scenarios

### Fixed Percentage Escalation

Annual fixed percentage increase in tariff rates.

```json
{
  "escalation_type": "fixed_percentage",
  "escalation_rate": 0.02
}
```

### Custom Escalation Schedule

Different escalation rates for different years.

```json
{
  "escalation_type": "custom_schedule",
  "escalation_schedule": [
    {
      "year": 1,
      "escalation_rate": 0.03,
      "description": "First year escalation"
    },
    {
      "year": 2,
      "escalation_rate": 0.02,
      "description": "Second year escalation"
    },
    {
      "year": 3,
      "escalation_rate": 0.015,
      "description": "Third year escalation"
    }
  ]
}
```

### CPI-Linked Escalation

Escalation linked to Consumer Price Index (placeholder for future implementation).

```json
{
  "escalation_type": "cpi_linked"
}
```

### Wholesale Price Index Escalation

Escalation linked to wholesale electricity prices (placeholder for future implementation).

```json
{
  "escalation_type": "wholesale_price_index"
}
```

## Tenure Management

The API automatically calculates and tracks:

- **Contract Duration**: Total tenure in years
- **Remaining Tenure**: Years remaining in the contract
- **Escalation Schedule**: When tariff escalations occur
- **Payment Schedules**: CAPEX payment installments
- **OPEX Projections**: Monthly payment forecasts

## State-Specific Subsidies

The system supports state-specific subsidy schemes with:

- **Eligibility Criteria**: Capacity limits, customer types
- **Subsidy Types**: Capital, generation-based, tax benefits
- **Validity Periods**: Scheme start and end dates
- **Documentation Links**: Official scheme documentation

**Example Subsidy Scheme:**
```json
{
  "scheme_id": "GJ_SOLAR_2024",
  "scheme_name": "Gujarat Solar Rooftop Scheme 2024",
  "state_code": "GJ",
  "subsidy_type": "capital",
  "subsidy_rate": 30.0,
  "subsidy_unit": "%",
  "max_capacity_kw": 10.0,
  "min_capacity_kw": 1.0,
  "valid_from": "2024-01-01T00:00:00Z",
  "valid_until": "2024-12-31T23:59:59Z",
  "description": "30% capital subsidy for residential solar installations",
  "documentation_url": "https://gujarat.gov.in/solar-scheme"
}
```

## Error Handling

### Standard Error Response

```json
{
  "detail": "Error message",
  "errorCode": "ERROR_CODE",
  "documentationLink": "https://docs.yourapi.com/errors#ERROR_CODE"
}
```

### Common Error Codes

- `PPA_OVERLAP`: Overlapping active/draft PPA exists
- `VALIDATION_ERROR`: Request validation failed
- `CUSTOMER_NOT_FOUND`: Customer does not exist
- `PPA_NOT_FOUND`: PPA not found
- `INVOICE_NOT_FOUND`: Invoice not found
- `SUBSIDY_SCHEME_NOT_FOUND`: Subsidy scheme not found
- `INVALID_BUSINESS_MODEL`: Invalid business model configuration
- `INVALID_ESCALATION_SCHEDULE`: Invalid escalation schedule

### HTTP Status Codes

- `200`: Success
- `201`: Created
- `400`: Bad Request
- `401`: Unauthorized
- `404`: Not Found
- `422`: Validation Error
- `500`: Internal Server Error
- `503`: Service Unavailable

## Rate Limits

Currently, no rate limits are enforced. However, it's recommended to:
- Limit requests to reasonable frequencies
- Implement exponential backoff for retries
- Cache responses where appropriate

## Best Practices

### Authentication
- Store tokens securely
- Refresh tokens before expiration
- Handle authentication errors gracefully

### Data Validation
- Validate all input data before sending
- Use appropriate data types (e.g., float for monetary values)
- Ensure datetime fields include timezone information

### Business Model Selection
- **CAPEX**: Choose for customers with capital and seeking ownership
- **OPEX**: Choose for customers wanting no upfront investment
- Consider maintenance and insurance requirements
- Factor in tax implications and depreciation benefits

### Escalation Planning
- Use fixed percentage for predictable increases
- Use custom schedule for complex escalation patterns
- Plan for CPI-linked escalations when data is available
- Consider market conditions for wholesale price indexing

### Subsidy Management
- Regularly update subsidy scheme information
- Validate eligibility before applying subsidies
- Track subsidy application and disbursement
- Maintain documentation links for compliance

### Error Handling
- Implement proper error handling for all API calls
- Log errors for debugging
- Provide user-friendly error messages

### Performance
- Use pagination for large datasets
- Implement caching where appropriate
- Minimize unnecessary API calls

## Examples

### Dynamic Tariff Workflow Example

#### 1. Create DISCOM Configuration

```bash
curl -X POST "http://localhost:8000/discoms" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "discom_id": "TATA_POWER_DELHI",
    "discom_name": "Tata Power Delhi Distribution Limited",
    "state_code": "DL",
    "license_number": "DL-01-2024",
    "website": "https://www.tatapower-ddl.com",
    "api_endpoint": "https://api.tatapower-ddl.com/tariffs",
    "api_key": "your_discom_api_key_here",
    "tariff_update_frequency": "monthly"
  }'
```

#### 2. Create Tariff Structure

```bash
curl -X POST "http://localhost:8000/tariffs" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "discom_id": "TATA_POWER_DELHI",
    "state_code": "DL",
    "tariff_category": "residential_low",
    "customer_type": "residential",
    "base_rate": 8.5,
    "currency": "INR",
    "effective_from": "2024-01-01T00:00:00Z",
    "effective_until": "2024-12-31T23:59:59Z",
    "regulatory_order": "DERC/2024/01",
    "order_number": "DERC-2024-001",
    "order_date": "2024-01-01T00:00:00Z",
    "source": "regulatory_order"
  }'
```

#### 3. Add Tariff Slabs

```bash
curl -X POST "http://localhost:8000/tariffs/tariff_123/slabs" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "min_consumption": 0.0,
    "max_consumption": 100.0,
    "rate": 8.0,
    "unit": "INR/kWh",
    "description": "First 100 units"
  }'
```

```bash
curl -X POST "http://localhost:8000/tariffs/tariff_123/slabs" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "min_consumption": 100.0,
    "max_consumption": 500.0,
    "rate": 9.0,
    "unit": "INR/kWh",
    "description": "101-500 units"
  }'
```

#### 4. Add Time-of-Use Rates

```bash
curl -X POST "http://localhost:8000/tariffs/tariff_123/tou-rates" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "time_range": "22:00-06:00",
    "rate": 6.5,
    "unit": "INR/kWh",
    "season": "summer",
    "day_type": "weekday",
    "description": "Off-peak hours"
  }'
```

#### 5. Get Dynamic Tariff

```bash
curl -X POST "http://localhost:8000/tariffs/dynamic" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "discom_id": "TATA_POWER_DELHI",
    "state_code": "DL",
    "tariff_category": "residential_low",
    "customer_type": "residential",
    "consumption_kwh": 500.0,
    "contract_date": "2024-01-15T00:00:00Z",
    "include_slabs": true,
    "include_tou": true
  }'
```

#### 6. Update DISCOM Tariffs

```bash
curl -X POST "http://localhost:8000/discoms/TATA_POWER_DELHI/update-tariffs" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Complete CAPEX Workflow Example

1. **Create Customer**
```bash
curl -X POST "http://localhost:8000/customers" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "John Doe",
    "email": "john.doe@example.com",
    "address": "123 Solar Street, Green City, 12345"
  }'
```

2. **Get Dynamic Tariff for PPA**
```bash
curl -X POST "http://localhost:8000/tariffs/dynamic" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "discom_id": "TATA_POWER_DELHI",
    "state_code": "DL",
    "tariff_category": "solar_rooftop",
    "customer_type": "residential",
    "consumption_kwh": 1500.0,
    "contract_date": "2024-01-15T00:00:00Z",
    "include_slabs": true,
    "include_tou": true
  }'
```

3. **Create CAPEX PPA with Dynamic Tariff**
```bash
curl -X POST "http://localhost:8000/ppas" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "customer_id": "cust_abc123",
    "system_specs": {
      "capacity_kw": 10.5,
      "panel_type": "Monocrystalline",
      "inverter_type": "String Inverter",
      "installation_date": "2024-01-15T00:00:00Z",
      "estimated_annual_production": 15000.0
    },
    "billing_terms": {
      "tariff_rate": 8.0,
      "escalation_type": "fixed_percentage",
      "escalation_rate": 0.02,
      "billing_cycle": "monthly",
      "payment_terms": "net30",
      "taxRate": 18.0,
      "currency": "INR",
      "business_model": "capex",
      "capex_amount": 500000.0,
      "maintenance_included": false,
      "insurance_included": false
    },
    "start_date": "2024-01-15T00:00:00Z",
    "end_date": "2029-01-15T00:00:00Z",
    "contractType": "net_metering"
  }'
```

4. **Get Comprehensive PPA Details**
```bash
curl -X GET "http://localhost:8000/ppas/ppa_xyz789/details" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Complete OPEX Workflow Example

1. **Create OPEX PPA with Dynamic Tariff**
```bash
curl -X POST "http://localhost:8000/ppas" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "customer_id": "cust_abc123",
    "system_specs": {
      "capacity_kw": 10.5,
      "panel_type": "Monocrystalline",
      "inverter_type": "String Inverter",
      "installation_date": "2024-01-15T00:00:00Z",
      "estimated_annual_production": 15000.0
    },
    "billing_terms": {
      "tariff_rate": 6.5,
      "escalation_type": "fixed_percentage",
      "escalation_rate": 0.03,
      "billing_cycle": "monthly",
      "payment_terms": "net30",
      "taxRate": 18.0,
      "currency": "INR",
      "business_model": "opex",
      "opex_monthly_fee": 5000.0,
      "opex_energy_rate": 6.5,
      "maintenance_included": true,
      "insurance_included": true
    },
    "start_date": "2024-01-15T00:00:00Z",
    "end_date": "2029-01-15T00:00:00Z",
    "contractType": "net_metering"
  }'
```

2. **Record OPEX Payment**
```bash
curl -X POST "http://localhost:8000/ppas/ppa_xyz789/opex-payment" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "amount": 8500.0,
    "energy_consumed_kwh": 1250.5,
    "payment_method": "bank_transfer",
    "reference_number": "TXN123456789"
  }'
```

### Subsidy Scheme Management

1. **Create Subsidy Scheme**
```bash
curl -X POST "http://localhost:8000/subsidy-schemes" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "scheme_id": "GJ_SOLAR_2024",
    "scheme_name": "Gujarat Solar Rooftop Scheme 2024",
    "state_code": "GJ",
    "subsidy_type": "capital",
    "subsidy_rate": 30.0,
    "subsidy_unit": "%",
    "max_capacity_kw": 10.0,
    "min_capacity_kw": 1.0,
    "valid_from": "2024-01-01T00:00:00Z",
    "valid_until": "2024-12-31T23:59:59Z",
    "description": "30% capital subsidy for residential solar installations"
  }'
```

2. **List Subsidy Schemes by State**
```bash
curl -X GET "http://localhost:8000/subsidy-schemes?state_code=GJ" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

## Dynamic Tariff Best Practices

### DISCOM API Integration

1. **API Configuration**
   - Store API keys securely in environment variables
   - Implement proper error handling for API failures
   - Use rate limiting to avoid API quota issues
   - Cache responses to reduce API calls

2. **Data Validation**
   - Validate tariff data received from DISCOM APIs
   - Check for data consistency and completeness
   - Implement fallback mechanisms for missing data

3. **Update Frequency**
   - Set appropriate update frequencies based on DISCOM policies
   - Monitor for regulatory changes and updates
   - Implement automatic update scheduling

### Tariff Management

1. **Effective Date Management**
   - Always specify effective dates for tariff changes
   - Handle overlapping tariff periods correctly
   - Maintain historical tariff data for audit purposes

2. **Slab and ToU Rate Configuration**
   - Ensure slab ranges don't overlap
   - Validate time ranges for ToU rates
   - Test rate calculations with sample consumption data

3. **Regulatory Compliance**
   - Keep regulatory order references updated
   - Monitor for new regulatory orders
   - Maintain documentation links for compliance

### Error Handling

1. **API Failures**
   - Implement exponential backoff for retries
   - Use fallback tariffs when APIs are unavailable
   - Log all API interactions for debugging

2. **Data Validation**
   - Validate all input parameters
   - Check for required fields in responses
   - Handle edge cases in rate calculations

3. **Fallback Mechanisms**
   - Always have fallback tariff rates
   - Implement business rules for calculated rates
   - Provide clear error messages to users

### Performance Optimization

1. **Caching Strategy**
   - Cache tariff data to reduce API calls
   - Implement cache invalidation based on update frequency
   - Use appropriate cache TTL values

2. **Database Optimization**
   - Index tariff queries by common filters
   - Archive old tariff data periodically
   - Optimize queries for large datasets

3. **API Response Optimization**
   - Return only required fields in responses
   - Implement pagination for large result sets
   - Use compression for API responses

## Monitoring and Maintenance

### Health Checks

1. **API Availability**
   - Monitor DISCOM API availability
   - Track API response times
   - Alert on API failures

2. **Data Quality**
   - Validate tariff data completeness
   - Check for data inconsistencies
   - Monitor for missing regulatory orders

3. **System Performance**
   - Track tariff retrieval response times
   - Monitor database query performance
   - Alert on system bottlenecks

### Regular Maintenance

1. **Tariff Updates**
   - Schedule regular tariff updates
   - Monitor for regulatory changes
   - Update DISCOM configurations as needed

2. **Data Cleanup**
   - Archive old tariff data
   - Clean up expired tariff structures
   - Maintain audit trails

3. **Documentation Updates**
   - Keep API documentation current
   - Update regulatory order references
   - Maintain change logs

## Support

For technical support or questions about the API:
- Check the error documentation links in error responses
- Review the health endpoint for service status
- Contact the development team with specific error codes and request details
- Monitor system logs for detailed error information 