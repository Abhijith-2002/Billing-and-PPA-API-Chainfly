# Solar Billing and PPA API Documentation

## Overview
The Solar Billing and PPA API is a FastAPI-based service that manages solar client billing and Power Purchase Agreements (PPAs). It provides endpoints for customer management, energy usage tracking, invoice generation, and contract management.

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

**Request Body:**
```json
{
    "name": "string",
    "email": "string",
    "address": "string",
    "tariff_rate": float
}
```

**Response:**
```json
{
    "id": "string",
    "name": "string",
    "email": "string",
    "address": "string",
    "tariff_rate": float
}
```

#### List Customers
```http
GET /customers
```

**Response:**
```json
[
    {
        "id": "string",
        "name": "string",
        "email": "string",
        "address": "string",
        "tariff_rate": float
    }
]
```

### Energy Usage

#### Add Energy Usage
```http
POST /energy-usage
```

**Request Body:**
```json
{
    "customer_id": "string",
    "month": integer,
    "year": integer,
    "usage_kwh": float,
    "timestamp": "datetime"
}
```

**Response:**
```json
{
    "id": "string",
    "customer_id": "string",
    "month": integer,
    "year": integer,
    "usage_kwh": float,
    "timestamp": "datetime"
}
```

### Invoice Management

#### Generate Invoice
```http
POST /invoices/generate
```

**Request Body:**
```json
{
    "customer_id": "string",
    "month": integer,
    "year": integer,
    "usage_kwh": float
}
```

**Response:**
```json
{
    "id": "string",
    "customer_id": "string",
    "month": integer,
    "year": integer,
    "usage_kwh": float,
    "tariff_rate": float,
    "total_amount": float,
    "status": "string",
    "created_at": "datetime",
    "paid_at": "datetime"
}
```

#### List Invoices
```http
GET /invoices
```

**Query Parameters:**
- `customer_id` (optional): Filter invoices by customer

**Response:**
```json
[
    {
        "id": "string",
        "customer_id": "string",
        "month": integer,
        "year": integer,
        "usage_kwh": float,
        "tariff_rate": float,
        "total_amount": float,
        "status": "string",
        "created_at": "datetime",
        "paid_at": "datetime"
    }
]
```

#### Download Invoice PDF
```http
GET /invoices/{invoice_id}/pdf
```

**Response:**
- PDF file with Content-Type: application/pdf

### Contract Management

#### Upload Contract
```http
POST /contracts
```

**Form Data:**
- `customer_id`: string
- `start_date`: datetime
- `end_date`: datetime
- `file`: PDF file

**Response:**
```json
{
    "id": "string",
    "customer_id": "string",
    "start_date": "datetime",
    "end_date": "datetime",
    "status": "string",
    "file_path": "string"
}
```

#### List Contracts
```http
GET /contracts
```

**Query Parameters:**
- `customer_id` (optional): Filter contracts by customer

**Response:**
```json
[
    {
        "id": "string",
        "customer_id": "string",
        "start_date": "datetime",
        "end_date": "datetime",
        "status": "string",
        "file_path": "string"
    }
]
```

#### Download Contract
```http
GET /contracts/{contract_id}
```

**Response:**
- PDF file with Content-Type: application/pdf

## Error Responses

### 400 Bad Request
```json
{
    "detail": "Invalid request parameters"
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
    "detail": "Resource not found"
}
```

### 422 Unprocessable Entity
```json
{
    "detail": [
        {
            "type": "validation_error",
            "loc": ["field_name"],
            "msg": "Error message",
            "input": null
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
    tariff_rate: float
```

### EnergyUsage
```python
class EnergyUsage(BaseModel):
    customer_id: str
    month: int
    year: int
    usage_kwh: float
    timestamp: datetime = datetime.now()
```

### Invoice
```python
class Invoice(BaseModel):
    id: Optional[str] = None
    customer_id: str
    month: int
    year: int
    usage_kwh: float
    tariff_rate: float
    total_amount: float
    status: str = "pending"
    created_at: datetime = datetime.now()
    paid_at: Optional[datetime] = None
```

### Contract
```python
class Contract(BaseModel):
    customer_id: str
    start_date: datetime
    end_date: datetime
    status: str = "active"
    file_path: Optional[str] = None
```

## Setup and Installation

1. Clone the repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Set up Firebase:
   - Create a Firebase project
   - Download service account key
   - Save as `firebase-credentials.json` in project root

4. Create `.env` file with:
   ```
   FIREBASE_CREDENTIALS_PATH=firebase-credentials.json
   ```

5. Run the development server:
   ```bash
   uvicorn main:app --reload
   ```

## Testing

Run the test suite:
```bash
pytest test_main.py -v
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

MIT 