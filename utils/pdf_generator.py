from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from typing import Optional
from invoice_generator import Invoice

def create_invoice_pdf(invoice: Invoice, customer_name: str, output_path: str) -> str:
    """Generate a PDF invoice"""
    doc = SimpleDocTemplate(output_path, pagesize=letter)
    styles = getSampleStyleSheet()
    elements = []

    # Title
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        spaceAfter=30
    )
    elements.append(Paragraph("INVOICE", title_style))
    elements.append(Spacer(1, 20))

    # Invoice Details
    invoice_data = [
        ["Invoice Date:", invoice.created_at.strftime("%Y-%m-%d")],
        ["Customer:", customer_name],
        ["Customer ID:", invoice.customer_id],
        ["Period:", f"{invoice.month}/{invoice.year}"],
        ["Status:", invoice.status.capitalize()]
    ]
    
    if invoice.paid_at:
        invoice_data.append(["Paid Date:", invoice.paid_at.strftime("%Y-%m-%d")])

    # Create invoice details table
    invoice_table = Table(invoice_data, colWidths=[2*inch, 4*inch])
    invoice_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 12),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ('TOPPADDING', (0, 0), (-1, -1), 12),
    ]))
    elements.append(invoice_table)
    elements.append(Spacer(1, 30))

    # Usage Details
    usage_data = [
        ["Description", "Quantity", "Rate", "Amount"],
        ["Energy Usage", f"{invoice.kwh_used} kWh", f"INR {invoice.tariff_rate:.2f}", f"INR {invoice.total_amount:.2f}"]
    ]

    # Create usage table
    usage_table = Table(usage_data, colWidths=[3*inch, 1.5*inch, 1.5*inch, 1.5*inch])
    usage_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 12),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 12),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ('TOPPADDING', (0, 0), (-1, -1), 12),
    ]))
    elements.append(usage_table)
    elements.append(Spacer(1, 30))

    # Total
    total_data = [["Total Amount:", f"INR {invoice.total_amount:.2f}"]]
    total_table = Table(total_data, colWidths=[4*inch, 2*inch])
    total_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 14),
    ]))
    elements.append(total_table)

    # Build PDF
    doc.build(elements)
    return output_path 