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

    try:
        df = pd.read_excel(uploaded_file)

        st.subheader("Preview")
        st.dataframe(df.head())

        if st.button("Convert"):
            # ⚠️ Replace this with your REAL parser call
            # Example:
            # from your_parser import convert
            # result_df = convert(df)

            result_df = df  # temporary placeholder

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
