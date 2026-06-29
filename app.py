
from converter.processor import process_job
from converter.dataclasses import JobRecord
import uuid
from datetime import datetime, UTC

import streamlit as st
import pandas as pd
import sys
from pathlib import Path

# ✅ Make sure your project modules can be imported
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

st.title("AOS Schedule Converter")

st.write("Upload an Excel file to convert it to EAI format.")

# Upload section
uploaded_file = st.file_uploader("Upload Excel file", type=["xlsx"])

if uploaded_file:
    st.success("File uploaded successfully")
template = st.selectbox(
    "Select template",
    ["auto", "ryanair", "emerald", "aer_lingus"]
)

    try:
        df = pd.read_excel(uploaded_file)

        st.subheader("Preview")
        st.dataframe(df.head())

        if st.button("Convert"):
            # ⚠️ Replace this with your REAL parser call
            # Example:
            # from your_parser import convert
            # result_df = convert(df)

            import tempfile
            from pathlib import Path
            
            with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
                tmp.write(uploaded_file.read())
                temp_path = Path(tmp.name)
            
            job = JobRecord(
                id=str(uuid.uuid4()),
                file_name=temp_path.name,
                file_path=str(temp_path),
                file_size=temp_path.stat().st_size,
                timestamp=datetime.now(UTC).isoformat(),
            )
            
            job = process_job(
                job,
                template_override=template if template != "auto" else None
            )
            
            if job.processing_status != "completed":
                st.error("Conversion failed")
                st.write(job.error_messages)
            else:
                st.success("Conversion complete ✅")
            
                # read output CSV
                output_path = Path(job.output_file_path)
                csv_data = output_path.read_text()
            
                st.download_button(
                    label="Download CSV",
                    data=csv_data,
                    file_name=output_path.name,
                    mime="text/csv"
                )

            csv = result_df.to_csv(index=False)

            st.success("Conversion complete ✅")

            st.download_button(
                label="Download CSV",
                data=csv,
                file_name="converted.csv",
                mime="text/csv"
            )

    except Exception as e:
        st.error(f"Error processing file: {e}")
