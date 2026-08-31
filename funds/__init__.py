"""Fund package.

Business objects are imported from their concrete modules. Keeping package
initialization side-effect free avoids import-lock conflicts during Streamlit
Cloud hot reloads.
"""
