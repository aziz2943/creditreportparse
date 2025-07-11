import streamlit as st
import pandas as pd
import re
from PyPDF2 import PdfReader
from io import BytesIO
from datetime import datetime

# ---------------- Sidebar walkthrough ----------------
st.sidebar.title("📌 How to Use")
st.sidebar.markdown("""
**Step 1:** Upload one or more PDF credit reports — both corporate and personal supported.

**Step 2:**  
- For *corporate* files, enter the entity name when prompted.  
- For *personal* files, select whether the borrower is Applicant or Co-Applicant.

**Step 3:** Click **Generate Excel** when done.

**Step 4:** Download your combined obligations file from the download button below!

**NOTE:** If corporate reports are uploaded,the excel will not include dpd,You will have to correspond to the pdf and enter into excel. 
""")

st.set_page_config(page_title="PDF Loan Parser", layout="wide")
st.title("📑 Combined Corporate & Personal Obligations Extractor")

uploaded_files = st.file_uploader(
    "📂 Upload one or more PDF credit reports below",
    type="pdf",
    accept_multiple_files=True
)

summary_rows = []
all_corporate_rows = []
all_personal_dfs = {}

if uploaded_files:
    for uploaded in uploaded_files:
        file_bytes = uploaded.read()
        reader = PdfReader(BytesIO(file_bytes))
        full_text = "".join([page.extract_text() + "\n" for page in reader.pages])

        if 'COMMERCIAL CREDIT INFORMATION REPORT' in full_text:
            # ---------------------------
            # COMMERCIAL
            # ---------------------------
            customer_name = st.text_input(f"🏢 Enter corporate name for: **{uploaded.name}**", key=uploaded.name)
            app_type = "Applicant"

            cmr = re.search(r'CMR-\s*([\d,]+)', full_text)
            cmr_score = cmr.group(1) if cmr else "None"

            summary_rows.append({
                'Name': customer_name,
                'Score': cmr_score,
                'Type': app_type
            })

            matches = re.findall(r'Credit Facility Details(.*?)Overdue Details', full_text, re.DOTALL)

            def parse_corporate(data_str):
                patterns = {
                    'TYPE': r'Type:\s*(.+)',
                    'OPENED': r'Sanctioned:\s*(\d{2}-[A-Za-z]{3}-\d{4})',
                    'SANCTIONED': r'Sanctioned INR:\s*([\d,]+)',
                    'CURRENT BALANCE': r'Outstanding Balance:\s*(-?[\d,]+)',
                    'EMI': r'Installment Amount:\s*([\d,]+)',
                    'REPAYMENT TENURE': r'Repayment Tenure:\s*(\d+)',
                    'OVERDUE': r'Overdue:\s*(-?[\d,]+)'
                }
                extracted = {}
                for key, pattern in patterns.items():
                    match = re.search(pattern, data_str, re.IGNORECASE)
                    extracted[key] = match.group(1).strip() if match else ''
                return extracted

            def corporate_row(parsed, sr_no):
                sanction_date_str = parsed.get('OPENED', '')
                formatted_date = ''
                if sanction_date_str:
                    try:
                        date_obj = datetime.strptime(sanction_date_str, "%d-%b-%Y")
                        formatted_date = date_obj.strftime("%d/%m/%Y")
                    except ValueError:
                        formatted_date = sanction_date_str

                return {
                    'Sr. No.': sr_no,
                    'Borrower type': app_type,
                    'Borrower': customer_name,
                    'Type of loan': parsed.get('TYPE', ''),
                    'Financiers': '',
                    'Sanction date (DD/MM/YYYY)': formatted_date,
                    'Seasoning': '',
                    'Sanction amount (INR)/ CC outstanding Amount': parsed.get('SANCTIONED', ''),
                    'Monthly EMI (INR)': parsed.get('EMI', ''),
                    'Current outstanding (INR)': parsed.get('CURRENT BALANCE', ''),
                    'Overdue Amount': parsed.get('OVERDUE', ''),
                    'Max DPD in L12 Months': '',
                    'Max DPD in L36 Months': ''
                }

            rows = []
            for i, entry in enumerate(matches, start=1):
                parsed = parse_corporate(entry)
                rows.append(corporate_row(parsed, i))
            all_corporate_rows.extend(rows)

        else:
            # ---------------------------
            # PERSONAL
            # ---------------------------
            app_type = st.radio(
                f"👤 Select borrower type for: **{uploaded.name}**",
                ("Applicant", "Co-Applicant"),
                key=uploaded.name + "_type"
            )

            namepattern = r"CONSUMER:\s*(.+)"
            match = re.search(namepattern, full_text)
            customer_name = match.group(1).strip() if match else "Unknown"

            scorepattern = r'CREDITVISION® SCORE\s*(\d{3})'
            match = re.search(scorepattern, full_text)
            pscore = match.group(1) if match else "None"

            summary_rows.append({
                'Name': customer_name,
                'Score': pscore,
                'Type': app_type
            })

            matches = re.findall(r'STATUS(.*?)(?:ACCOUNT DATES|ENQUIRIES:)', full_text, re.DOTALL)

            def parse_personal(data_str):
                patterns = {
                    'ACCOUNT NUMBER': r'ACCOUNT NUMBER:\s*(.+)',
                    'TYPE': r'TYPE:\s*(.+)',
                    'OWNERSHIP': r'OWNERSHIP:\s*(.+?)(?:OPENED|\n|LAST|REPORTED|CLOSED|PMT|$)',
                    'OPENED': r'OPENED:\s*(\d{2}-\d{2}-\d{4})',
                    'SANCTIONED': r'SANCTIONED:\s*([\d,]+)',
                    'CURRENT BALANCE': r'CURRENT BALANCE:\s*(-?[\d,]+)',
                    'EMI': r'EMI:\s*([\d,]+)',
                    'CLOSED': r'CLOSED:\s*(.+)'
                }
                extracted = {}
                type_match = re.search(patterns['TYPE'], data_str, re.IGNORECASE)
                loan_type = type_match.group(1).strip() if type_match else ''
                extracted['TYPE'] = loan_type

                if loan_type == 'CREDIT CARD':
                    patterns['SANCTIONED'] = r'CREDIT LIMIT:\s*([\d,]+)'

                for key, pattern in patterns.items():
                    match = re.search(pattern, data_str, re.IGNORECASE)
                    extracted[key] = match.group(1).strip() if match else ''
                return extracted

            def personal_row(parsed, sr_no, dpd12, dpd36):
                status = "Active" if parsed.get('CLOSED', '') == '' else "Closed"
                return {
                    'Sr. No.': sr_no,
                    'Borrower type': app_type,
                    'Borrower': customer_name,
                    'Type of loan': parsed.get('TYPE', ''),
                    'Financiers': '',
                    'Sanction date (DD/MM/YYYY)': parsed.get('OPENED', '').replace('-', '/'),
                    'Seasoning': '',
                    'Sanction amount (INR)/ CC outstanding Amount': parsed.get('SANCTIONED', ''),
                    'Monthly EMI (INR)': parsed.get('EMI', ''),
                    'Current outstanding (INR)': parsed.get('CURRENT BALANCE', ''),
                    'STATUS': status,
                    'Max DPD in L12 Months': dpd12,
                    'Max DPD in L36 Months': dpd36,
                    'Ownership type': parsed.get('OWNERSHIP', '')
                }

            rows = []
            for i, entry in enumerate(matches, start=1):
                dpd_match = re.findall(r'LEFT TO RIGHT\)(.*)', entry, re.DOTALL)
                clean_text = []
                tokens = ["TransUnion CIBIL", "MEMBER ID", "MEMBER REFERENCE", "TIME:", "CONTROL NUMBER", "CONSUMER CIR", "CONSUMER:"]
                pattern_tokens = "|".join(re.escape(token) for token in tokens)
                regex = rf"^.*(?:{pattern_tokens}).*$\n?"
                dpd_values = []

                for item in dpd_match:
                    clean_text.append(re.sub(regex, "", item, flags=re.IGNORECASE | re.MULTILINE))

                for t in clean_text:
                    pattern = re.findall(r'([0-9XSTD]{3})\s*(\d{2}-\d{2})', t)
                    for value, _ in pattern:
                        try:
                            dpd = int(value)
                        except ValueError:
                            dpd = 0
                        dpd_values.append(dpd)

                max12 = max(dpd_values[:12]) if dpd_values else 0
                max36 = max(dpd_values) if dpd_values else 0

                parsed = parse_personal(entry)
                rows.append(personal_row(parsed, i, max12, max36))

            sheet_name = f"{customer_name}_{app_type}"[:31]
            all_personal_dfs[sheet_name] = pd.DataFrame(rows)

    if st.button("✅ Generate Excel"):
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            summary_df = pd.DataFrame(summary_rows)
            summary_df.to_excel(writer, index=False, sheet_name="Summary")

            if all_corporate_rows:
                corp_df = pd.DataFrame(all_corporate_rows)
                corp_df.to_excel(writer, index=False, sheet_name="Corporate_Entity")

            for sheet_name, df in all_personal_dfs.items():
                df.to_excel(writer, index=False, sheet_name=sheet_name)

        output.seek(0)
        st.success("🎉 Excel file generated successfully!")
        st.download_button(
            label="📥 Download Combined_Obligations.xlsx",
            data=output,
            file_name="Combined_Obligations.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
