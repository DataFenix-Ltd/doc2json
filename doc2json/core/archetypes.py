"""Library of document schema archetypes to guide LLM extraction.

Archetypes provide a consistent starting point for common document types.
They include fields that are typically expected for each type.
"""

from typing import Dict, List, Any

ARCHETYPES: Dict[str, Dict[str, Any]] = {
    "Invoice": {
        "description": "Standard financial invoice for goods or services.",
        "fields": [
            {"name": "invoice_number", "type": "str", "description": "Unique identifier for the invoice"},
            {"name": "invoice_date", "type": "date", "description": "Date the invoice was issued"},
            {"name": "vendor_name", "type": "str", "description": "Name of the entity providing the goods or services"},
            {"name": "vendor_tax_id", "type": "Optional[str]", "description": "VAT or tax registration number of the vendor"},
            {"name": "customer_name", "type": "str", "description": "Name of the entity receiving the goods or services"},
            {"name": "line_items", "type": "list[InvoiceItem]", "description": "List of individual items or services charged"},
            {"name": "subtotal", "type": "float", "description": "Total amount before taxes"},
            {"name": "tax_amount", "type": "Optional[float]", "description": "Total tax/VAT amount"},
            {"name": "total_amount", "type": "float", "description": "Final amount due including taxes"},
            {"name": "currency", "type": "str", "description": "Three-letter currency code (e.g., USD, EUR, GBP)"},
            {"name": "payment_terms", "type": "Optional[str]", "description": "Terms of payment (e.g., Net 30)"}
        ],
        "nested_models": {
            "InvoiceItem": [
                {"name": "description", "type": "str", "description": "Description of the item or service"},
                {"name": "quantity", "type": "float", "description": "Number of units"},
                {"name": "unit_price", "type": "float", "description": "Price per unit"},
                {"name": "amount", "type": "float", "description": "Total amount for this line item"}
            ]
        }
    },
    "Contract": {
        "description": "Legal agreement between two or more parties.",
        "fields": [
            {"name": "contract_title", "type": "str", "description": "Title or name of the agreement"},
            {"name": "parties", "type": "list[Party]", "description": "Entities involved in the contract"},
            {"name": "effective_date", "type": "Optional[date]", "description": "Date the contract becomes active"},
            {"name": "expiration_date", "type": "Optional[date]", "description": "Date the contract ends"},
            {"name": "governing_law", "type": "Optional[str]", "description": "The jurisdiction whose laws apply to the contract"},
            {"name": "termination_clause", "type": "Optional[str]", "description": "Short summary of how the contract can be ended"}
        ],
        "nested_models": {
            "Party": [
                {"name": "name", "type": "str", "description": "Legal name of the party"},
                {"name": "role", "type": "str", "description": "Role in the contract (e.g., Client, Vendor, Employer)"},
                {"name": "address", "type": "Optional[str]", "description": "Registered address of the party"}
            ]
        }
    },
    "MedicalRecord": {
        "description": "Information from a clinical visit or patient record.",
        "fields": [
            {"name": "patient_name", "type": "str", "description": "Full name of the patient"},
            {"name": "patient_dob", "type": "Optional[date]", "description": "Patient's date of birth"},
            {"name": "visit_date", "type": "date", "description": "Date of the medical encounter"},
            {"name": "symptoms", "type": "list[str]", "description": "Primary complaints or symptoms reported"},
            {"name": "diagnoses", "type": "list[Diagnosis]", "description": "Medical conclusions or ICD codes"},
            {"name": "medications", "type": "list[Medication]", "description": "Prescribed or current medications"},
            {"name": "vitals", "type": "Optional[Vitals]", "description": "Patient vital signs"}
        ],
        "nested_models": {
            "Diagnosis": [
                {"name": "condition", "type": "str", "description": "Name of the condition"},
                {"name": "code", "type": "Optional[str]", "description": "Medical classification code (e.g., ICD-10)"}
            ],
            "Medication": [
                {"name": "name", "type": "str", "description": "Name of the drug"},
                {"name": "dosage", "type": "Optional[str]", "description": "Amount and frequency (e.g., 500mg daily)"}
            ],
            "Vitals": [
                {"name": "blood_pressure", "type": "Optional[str]", "description": "BP reading (e.g., 120/80)"},
                {"name": "heart_rate", "type": "Optional[int]", "description": "Pulse in BPM"},
                {"name": "temperature", "type": "Optional[float]", "description": "Body temperature"}
            ]
        }
    },
    "Receipt": {
        "description": "Simplified retail or service receipt.",
        "fields": [
            {"name": "merchant_name", "type": "str", "description": "Name of the store or service provider"},
            {"name": "transaction_date", "type": "date", "description": "Date of purchase"},
            {"name": "items", "type": "list[ReceiptItem]", "description": "Items purchased"},
            {"name": "total", "type": "float", "description": "Final amount paid"},
            {"name": "currency", "type": "str", "description": "Currency code"},
            {"name": "payment_method", "type": "Optional[str]", "description": "How the payment was made (e.g., Credit Card, Cash)"}
        ],
        "nested_models": {
            "ReceiptItem": [
                {"name": "description", "type": "str", "description": "Name of the product or service"},
                {"name": "price", "type": "float", "description": "Price of the item"}
            ]
        }
    },
    "GeneralDocument": {
        "description": "Basic metadata for any document type.",
        "fields": [
            {"name": "title", "type": "str", "description": "Title or subject of the document"},
            {"name": "date", "type": "Optional[date]", "description": "Primary date mentioned in the document"},
            {"name": "author", "type": "Optional[str]", "description": "Author, sender, or creator of the document"},
            {"name": "summary", "type": "str", "description": "High-level summary of the document content"}
        ]
    },
    "Resume": {
        "description": "Professional CV or Resume document.",
        "fields": [
            {"name": "full_name", "type": "str", "description": "Full name of the candidate"},
            {"name": "contact_email", "type": "Optional[str]", "description": "Primary email address"},
            {"name": "contact_phone", "type": "Optional[str]", "description": "Primary contact phone number"},
            {"name": "linkedin_url", "type": "Optional[str]", "description": "Link to candidate's LinkedIn profile"},
            {"name": "summary", "type": "Optional[str]", "description": "Professional summary or objective statement"},
            {"name": "work_experience", "type": "list[Experience]", "description": "List of professional roles and responsibilities"},
            {"name": "education", "type": "list[Education]", "description": "List of academic qualifications"},
            {"name": "skills", "type": "list[str]", "description": "Technical or soft skills mention"},
            {"name": "languages", "type": "list[str]", "description": "Languages spoken and proficiency levels"}
        ],
        "nested_models": {
            "Experience": [
                {"name": "company", "type": "str", "description": "Name of the organization"},
                {"name": "position", "type": "str", "description": "Job title or role"},
                {"name": "start_date", "type": "Optional[date]", "description": "Date the role started"},
                {"name": "end_date", "type": "Optional[date]", "description": "Date the role ended (or 'Present')"},
                {"name": "description", "type": "Optional[str]", "description": "Summary of achievements and tasks"}
            ],
            "Education": [
                {"name": "institution", "type": "str", "description": "Name of the school or university"},
                {"name": "degree", "type": "str", "description": "Qualification earned (e.g., BSc, PhD)"},
                {"name": "graduation_date", "type": "Optional[date]", "description": "Completion date or expected graduation"},
                {"name": "major", "type": "Optional[str]", "description": "Primary field of study"}
            ]
        }
    }
}


def get_archetype_prompt(document_type: str) -> str:
    """Get a prompt snippet for a given archetype."""
    archetype = ARCHETYPES.get(document_type)
    if not archetype:
        return ""

    lines = [f"Archetype: {document_type} - {archetype['description']}"]
    lines.append("Common fields for this document type:")
    for field in archetype["fields"]:
        lines.append(f"- {field['name']} ({field['type']}): {field['description']}")

    if "nested_models" in archetype:
        lines.append("\nSupporting models:")
        for name, fields in archetype["nested_models"].items():
            lines.append(f"Model {name}:")
            for field in fields:
                lines.append(f"  - {field['name']} ({field['type']}): {field['description']}")

    return "\n".join(lines)
