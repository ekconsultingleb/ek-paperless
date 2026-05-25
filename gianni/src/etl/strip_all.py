def strip_all(cleaned : dict):
    for name, data in cleaned.items():
        text_cols = [
            col for col in data.columns
            if data[col].dropna().map(type).eq(str).all()
            and col in data.select_dtypes(include=["object", "string"]).columns
        ]
    
        for col in text_cols:
            data[col] = data[col].str.strip()
            
    return cleaned