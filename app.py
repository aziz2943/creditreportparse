import streamlit as st
import pandas as pd
import re
from PyPDF2 import PdfReader
from io import BytesIO

st.set_page_config(page_title="PDF Loan Parser", layout="centered")
st.title("📄 PDF Credit Report Parser (Colab)")

uploaded_files = st.file_uploader(
    "Upload one or more PDF credit reports",
    type="pdf",
    accept_multiple_files=True
)

if uploaded_files:
    applicant_types = {}
    st.write("### Select Borrower Type for each PDF")
    for uploaded_file in uploaded_files:
        label = f"{uploaded_file.name} - Borrower Type"
        applicant_types[uploaded_file.name] = st.radio(
            label, ["Applicant", "Co-Applicant"], key=uploaded_file.name
        )

    if st.button("🔍 Parse & Generate Excel"):
        output = BytesIO()
        writer = pd.ExcelWriter(output, engine="openpyxl")
        summary_rows = []

        for uploaded_file in uploaded_files:
            file_name = uploaded_file.name
            app_type = applicant_types[file_name]

            reader = PdfReader(uploaded_file)
            full_text = ""
            for page in reader.pages:
                full_text += page.extract_text() + "\n"

            namepattern = r"CONSUMER:\s*(.+)"
            match = re.search(namepattern, full_text)
            customer_name = match.group(1).strip() if match else "Unknown"

            datepattern = r"DATE:\s*(\d{2}-\d{2}-\d{4})"
            match = re.search(datepattern, full_text)
            customer_date = match.group(1).strip() if match else "Unknown"

            scorepattern = r'CREDITVISION® SCORE\s*(\d{3})'
            match = re.search(scorepattern, full_text)
            cscore = match.group(1) if match else "None"

            summary_rows.append({
                "Customer Name": customer_name,
                "Score": cscore,
                "DATE": customer_date,
                "Borrower Type": app_type
            })

            matches = re.findall(r'STATUS(.*?)(?:ACCOUNT DATES|ENQUIRIES:)', full_text, re.DOTALL)

            current_pdf_data_rows = []

            for i, entry in enumerate(matches, start=1):
                dpdmatch_entry = re.findall(r'LEFT TO RIGHT\)(.*)', entry, re.DOTALL)
                new_dpdtext_entry = []
                tokens = ["TransUnion CIBIL", "MEMBER ID", "MEMBER REFERENCE", "TIME:",
                          "CONTROL NUMBER", "CONSUMER CIR", "CONSUMER:"]
                pattern_tokens = "|".join(re.escape(token) for token in tokens)
                regex = rf"^.*(?:{pattern_tokens}).*$\n?"
                dpd_values_entry = []

                for dpd_item_entry in dpdmatch_entry:
                    new_dpdtext_entry.append(
                        re.sub(regex, "", dpd_item_entry, flags=re.IGNORECASE | re.MULTILINE)
                    )

                for match_entry in new_dpdtext_entry:
                    pattern_entry = re.findall(r'([0-9XSTD]{3})\s*(\d{2}-\d{2})', match_entry)
                    for value, date in pattern_entry:
                        try:
                            dpd = int(value)
                        except ValueError:
                            dpd = 0
                        dpd_values_entry.append((dpd, date))

                last_12_entry = dpd_values_entry[:12]
                max_12_months_entry = max([val for val, _ in last_12_entry], default=0)
                max_36_months_entry = max([val for val, _ in dpd_values_entry], default=0)

                def parse_loan_data(data_str, customer_name):
                    patterns = {
                        'ACCOUNT NUMBER': r'ACCOUNT NUMBER:\s*(.+)',
                        'TYPE': r'TYPE:\s*(.+)',
                        'OWNERSHIP': r'OWNERSHIP:\s*(.+?)(?:OPENED|\n|LAST|REPORTED|CLOSED|PMT|$)',
                        'OPENED': r'OPENED:\s*(\d{2}-\d{2}-\d{4})',
                        'LAST PAYMENT': r'LAST PAYMENT:\s*(\d{2}-\d{2}-\d{4})',
                        'REPORTED AND CERTIFIED': r'REPORTED AND CERTIFIED:\s*(\d{2}-\d{2}-\d{4})',
                        'PMT HIST START': r'PMT HIST START:\s*(\d{2}-\d{2}-\d{4})',
                        'PMT HIST END': r'PMT HIST END:\s*(\d{2}-\d{2}-\d{4})',
                        'SANCTIONED': r'SANCTIONED:\s*([\d,]+)',
                        'CURRENT BALANCE': r'CURRENT BALANCE:\s*(-?[\d,]+)',
                        'EMI': r'EMI:\s*([\d,]+)',
                        'REPAYMENT TENURE': r'REPAYMENT TENURE:\s*(\d+)',
                        'CLOSED': r'CLOSED:\s*(.+)',
                    }
                    extracted_data = {'MEMBER NAME': customer_name}
                    type_match = re.search(patterns['TYPE'], data_str, re.IGNORECASE)
                    loan_type = type_match.group(1).strip() if type_match else ''
                    extracted_data['TYPE'] = loan_type
                    if loan_type == 'CREDIT CARD':
                        patterns['SANCTIONED'] = r'CREDIT LIMIT:\s*([\d,]+)'
                    for key, pattern in patterns.items():
                        if key == 'MEMBER NAME':
                            continue
                        match = re.search(pattern, data_str, re.IGNORECASE)
                        extracted_data[key] = match.group(1).strip() if match else ''
                    return extracted_data

                parsed = parse_loan_data(entry, customer_name)

                def create_loan_row(parsed_data, sr_no, customer_name, app_type, dpd12, dpd36):
                    status = "Active" if parsed_data.get('CLOSED', '') == '' else "Closed"
                    return {
                        'Sr. No.': sr_no,
                        'Borrower type': app_type,
                        'Borrower': customer_name,
                        'Type of loan': parsed_data.get('TYPE', ''),
                        'Financiers': '',
                        'Sanction date (DD/MM/YYYY)': (parsed_data.get('OPENED', '')).replace('-', '/'),
                        'Seasoning': '',
                        'Sanction amount (INR)/ CC outstanding Amount': parsed_data.get('SANCTIONED', ''),
                        'Monthly EMI (INR)': parsed_data.get('EMI', ''),
                        'Current outstanding (INR)': parsed_data.get('CURRENT BALANCE', ''),
                        'STATUS': status,
                        'Max DPD in L12 Months': dpd12,
                        'Max DPD in L36 Months': dpd36,
                        'Ownership type': parsed_data.get('OWNERSHIP', ''),
                    }

                row = create_loan_row(
                    parsed, sr_no=len(current_pdf_data_rows) + 1, customer_name=customer_name,
                    app_type=app_type, dpd12=max_12_months_entry, dpd36=max_36_months_entry
                )
                current_pdf_data_rows.append(row)

            current_pdf_df = pd.DataFrame(current_pdf_data_rows)
            sheet_name = f"{customer_name}_{app_type}"[:31]
            current_pdf_df.to_excel(writer, index=False, sheet_name=sheet_name)

        summary_df = pd.DataFrame(summary_rows)
        summary_df.to_excel(writer, index=False, sheet_name="Summary")
        writer._save()

        st.success("✅ Excel generated!")
        st.download_button(
            label="📥 Download Excel file",
            data=output.getvalue(),
            file_name="All_Customers_Personal_Obligations.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
