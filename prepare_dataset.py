import pandas as pd

INPUT_FILE  = "EntitiesRegisteredwithACRA.csv"
#file name is to be kept the same as this is the name that is being read in finalServer.py
OUTPUT_FILE = "reference_dataset.csv"

df = pd.read_csv(INPUT_FILE, usecols=["reg_street_name"])

df = df.dropna(subset=["reg_street_name"])
df = df.rename(columns={"reg_street_name": "address"})

#normalising before removing duplicates
df["address"] = (
    df["address"]
    .str.strip()
    .str.upper()
    .str.replace(r"\s+", " ", regex=True)
)

df = df[df["address"] != ""]
df = df.drop_duplicates(subset=["address"]).reset_index(drop=True)
df.insert(0, "id", range(1, len(df) + 1))

df.to_csv(OUTPUT_FILE, index=False)
print(f"Done. {len(df)} unique street names saved to {OUTPUT_FILE}")