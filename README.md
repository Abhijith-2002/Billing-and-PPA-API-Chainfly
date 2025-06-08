# Solar Client Billing and PPA Management API

A lightweight API for managing solar client billing and Power Purchase Agreements (PPAs).

## Features

- Customer management
- Energy usage tracking
- Automatic invoice generation
- PPA contract management
- PDF invoice generation and export
- Firebase authentication
- Optional email notifications

## Tech Stack

- FastAPI (Backend)
- Firebase (Authentication & Database)
- ReportLab (PDF Generation)
- Bootstrap (Frontend - Optional)

## Setup Instructions

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
   SMTP_HOST=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USER=your-email@gmail.com
   SMTP_PASSWORD=your-app-password
   ```

5. Run the development server:
   ```bash
   uvicorn main:app --reload
   ```

## API Endpoints

- `POST /customers` - Add new customer
- `GET /customers` - List all customers
- `POST /energy-usage` - Upload energy usage data
- `GET /invoices` - List all invoices
- `POST /invoices/generate` - Generate new invoice
- `GET /invoices/{id}/pdf` - Download invoice PDF
- `POST /contracts` - Upload PPA contract
- `GET /contracts` - List all contracts

## Development

- Backend: FastAPI
- Database: Firebase Firestore
- Authentication: Firebase Auth
- PDF Generation: ReportLab
- Email: SMTP/SendGrid

## Deployment

The API can be deployed to:
- Vercel
- Render
- Railway

## License

MIT 