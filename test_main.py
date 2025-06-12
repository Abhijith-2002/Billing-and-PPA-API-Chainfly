import pytest
from fastapi.testclient import TestClient
from datetime import datetime, timedelta
import os
from unittest.mock import patch, MagicMock
from main import app
from firebase_config import verify_token
from invoice_generator import Invoice

client = TestClient(app)

# Mock data
MOCK_CUSTOMER = {
    "name": "Test Customer",
    "email": "test@example.com",
    "address": "123 Test St",
    "tariff_rate": 0.15
}

MOCK_ENERGY_USAGE = {
    "customer_id": "test_customer_id",
    "month": datetime.now().month,
    "year": datetime.now().year,
    "usage_kwh": 100.0,
    "timestamp": datetime.now().isoformat()
}

MOCK_CONTRACT = {
    "customer_id": "test_customer_id",
    "start_date": datetime.now().isoformat(),
    "end_date": (datetime.now() + timedelta(days=365)).isoformat(),
    "status": "active"
}

# Mock authentication
@pytest.fixture
def mock_auth():
    with patch('main.verify_token') as mock_verify:
        mock_verify.return_value = {"uid": "test_user_id"}
        yield mock_verify

@pytest.fixture
def mock_db():
    with patch('main.db') as mock_db:
        # Mock customer document
        mock_customer_doc = MagicMock()
        mock_customer_doc.exists = True
        mock_customer_doc.to_dict.return_value = {**MOCK_CUSTOMER, "id": "test_customer_id"}
        
        # Mock customer collection
        mock_customer_collection = MagicMock()
        mock_customer_collection.document.return_value = mock_customer_doc
        mock_customer_collection.get.return_value = [mock_customer_doc]
        
        # Mock energy usage collection
        mock_energy_collection = MagicMock()
        mock_energy_doc = MagicMock()
        mock_energy_doc.to_dict.return_value = {**MOCK_ENERGY_USAGE, "id": "test_usage_id"}
        mock_energy_collection.get.return_value = [mock_energy_doc]
        
        # Mock invoice collection
        mock_invoice_collection = MagicMock()
        mock_invoice_doc = MagicMock()
        mock_invoice_doc.to_dict.return_value = {
            "id": "test_invoice_id",
            "customer_id": "test_customer_id",
            "month": datetime.now().month,
            "year": datetime.now().year,
            "usage_kwh": 100.0,
            "tariff_rate": 0.15,
            "total_amount": 15.0,
            "status": "pending",
            "created_at": datetime.now().isoformat()
        }
        mock_invoice_collection.get.return_value = [mock_invoice_doc]
        mock_invoice_collection.document.return_value = mock_invoice_doc
        
        # Mock contract collection
        mock_contract_collection = MagicMock()
        mock_contract_doc = MagicMock()
        mock_contract_doc.exists = True
        mock_contract_doc.to_dict.return_value = {**MOCK_CONTRACT, "id": "test_contract_id", "file_path": "test.pdf"}
        mock_contract_collection.get.return_value = [mock_contract_doc]
        mock_contract_collection.document.return_value = mock_contract_doc
        
        mock_db.collection.side_effect = {
            'customers': mock_customer_collection,
            'energy_usage': mock_energy_collection,
            'invoices': mock_invoice_collection,
            'contracts': mock_contract_collection
        }.get
        
        yield mock_db

# Test authentication
def test_invalid_token():
    response = client.get("/customers", headers={"Authorization": "Bearer invalid_token"})
    assert response.status_code == 401

# Test customer endpoints
def test_create_customer(mock_auth, mock_db):
    response = client.post("/customers", json=MOCK_CUSTOMER, headers={"Authorization": "Bearer valid_token"})
    assert response.status_code == 200
    assert response.json()["name"] == MOCK_CUSTOMER["name"]

def test_list_customers(mock_auth, mock_db):
    response = client.get("/customers", headers={"Authorization": "Bearer valid_token"})
    assert response.status_code == 200
    assert len(response.json()) > 0

# Test energy usage endpoints
def test_add_energy_usage(mock_auth, mock_db):
    response = client.post("/energy-usage", json=MOCK_ENERGY_USAGE, headers={"Authorization": "Bearer valid_token"})
    assert response.status_code == 200
    assert response.json()["customer_id"] == MOCK_ENERGY_USAGE["customer_id"]

# Test invoice endpoints
def test_create_invoice(mock_auth, mock_db):
    response = client.post("/invoices/generate", json=MOCK_ENERGY_USAGE, headers={"Authorization": "Bearer valid_token"})
    assert response.status_code == 200
    assert "total_amount" in response.json()

def test_list_invoices(mock_auth, mock_db):
    response = client.get("/invoices", headers={"Authorization": "Bearer valid_token"})
    assert response.status_code == 200
    assert len(response.json()) > 0

def test_get_invoice_pdf(mock_auth, mock_db):
    with patch('main.create_invoice_pdf') as mock_create_pdf, \
         patch('os.path.exists') as mock_exists, \
         patch('main.get_invoice_by_id') as mock_get_invoice_by_id:
        mock_create_pdf.return_value = None
        mock_exists.return_value = True
        mock_get_invoice_by_id.return_value = Invoice(
            id="test_invoice_id",
            customer_id="test_customer_id",
            month=datetime.now().month,
            year=datetime.now().year,
            usage_kwh=100.0,
            tariff_rate=0.15,
            total_amount=15.0,
            status="pending",
            created_at=datetime.now()
        )
        response = client.get("/invoices/test_invoice_id/pdf", headers={"Authorization": "Bearer valid_token"})
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"

# Test contract endpoints
def test_upload_contract(mock_auth, mock_db):
    test_file = ("test.pdf", b"test content", "application/pdf")
    now = datetime.now().replace(microsecond=0)
    contract_data = {
        "customer_id": "test_customer_id",
        "start_date": now.strftime('%Y-%m-%dT%H:%M:%S'),
        "end_date": (now + timedelta(days=365)).strftime('%Y-%m-%dT%H:%M:%S')
    }
    response = client.post(
        "/contracts",
        files={"file": test_file},
        data=contract_data,
        headers={"Authorization": "Bearer valid_token"}
    )
    if response.status_code != 200:
        print("\nContract upload error response:", response.status_code, response.text)
    assert response.status_code == 200
    assert response.json()["customer_id"] == "test_customer_id"

def test_list_contracts(mock_auth, mock_db):
    response = client.get("/contracts", headers={"Authorization": "Bearer valid_token"})
    assert response.status_code == 200
    assert len(response.json()) > 0

def test_get_contract(mock_auth, mock_db):
    with patch('os.path.exists') as mock_exists:
        mock_exists.return_value = True
        response = client.get("/contracts/test_contract_id", headers={"Authorization": "Bearer valid_token"})
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
