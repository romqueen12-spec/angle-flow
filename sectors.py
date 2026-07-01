"""
Maps F&O stock symbols to their NSE sector/industry group.
"""

SECTOR_MAP = {
    # ---- IT, Software & Internet ----
    "TCS": "IT", "INFY": "IT", "WIPRO": "IT", "HCLTECH": "IT", "TECHM": "IT", "LTIM": "IT", 
    "MPHASIS": "IT", "PERSISTENT": "IT", "COFORGE": "IT", "LTTS": "IT", "TATAELXSI": "IT", 
    "BSOFT": "IT", "OFSS": "IT", "NAUKRI": "IT", "KPITTECH": "IT", "LTM": "IT",

    # ---- Banking (Private & PSU) ----
    "HDFCBANK": "Banking", "ICICIBANK": "Banking", "KOTAKBANK": "Banking", "AXISBANK": "Banking", 
    "SBIN": "Banking", "INDUSINDBK": "Banking", "BANKBARODA": "Banking", "PNB": "Banking", 
    "CANBK": "Banking", "FEDERALBNK": "Banking", "IDFCFIRSTB": "Banking", "AUBANK": "Banking",
    "BANDHANBNK": "Banking", "RBLBANK": "Banking", "BANKINDIA": "Banking", "INDIANB": "Banking", 
    "UNIONBANK": "Banking", "YESBANK": "Banking",

    # ---- Auto & Auto Ancillary ----
    "MARUTI": "Auto", "TATAMOTORS": "Auto", "M&M": "Auto", "BAJAJ-AUTO": "Auto", "EICHERMOT": "Auto", 
    "HEROMOTOCO": "Auto", "TVSMOTOR": "Auto", "ASHOKLEY": "Auto", "BHARATFORG": "Auto",
    "MOTHERSON": "Auto", "BOSCHLTD": "Auto", "EXIDEIND": "Auto", "FORCEMOT": "Auto", 
    "HYUNDAI": "Auto", "SONACOMS": "Auto", "UNOMINDA": "Auto", "TMPV": "Auto",

    # ---- Pharma, Healthcare & Diagnostics ----
    "SUNPHARMA": "Pharma", "DRREDDY": "Pharma", "CIPLA": "Pharma", "DIVISLAB": "Pharma", 
    "AUROPHARMA": "Pharma", "LUPIN": "Pharma", "TORNTPHARM": "Pharma", "ALKEM": "Pharma", 
    "BIOCON": "Pharma", "ZYDUSLIFE": "Pharma", "GLENMARK": "Pharma", "LAURUSLABS": "Pharma",
    "MANKIND": "Pharma", "APOLLOHOSP": "Healthcare", "LALPATHLAB": "Healthcare",
    "METROPOLIS": "Healthcare", "FORTIS": "Healthcare", "MAXHEALTH": "Healthcare",

    # ---- FMCG, Agri & Beverages ----
    "HINDUNILVR": "FMCG", "ITC": "FMCG", "NESTLEIND": "FMCG", "BRITANNIA": "FMCG", "TATACONSUM": "FMCG", 
    "DABUR": "FMCG", "GODREJCP": "FMCG", "MARICO": "FMCG", "COLPAL": "FMCG", "UNITDSPR": "FMCG", 
    "VBL": "FMCG", "RADICO": "FMCG", "GODFRYPHLP": "FMCG", "PATANJALI": "FMCG",

    # ---- Metal & Mining ----
    "TATASTEEL": "Metal", "JSWSTEEL": "Metal", "HINDALCO": "Metal", "VEDL": "Metal", 
    "JINDALSTEL": "Metal", "SAIL": "Metal", "NMDC": "Metal", "NATIONALUM": "Metal", 
    "HINDZINC": "Metal", "COALINDIA": "Metal",

    # ---- Energy, Power & Utilities ----
    "RELIANCE": "Energy", "ONGC": "Energy", "BPCL": "Energy", "IOC": "Energy", "GAIL": "Energy", 
    "PETRONET": "Energy", "OIL": "Energy", "HINDPETRO": "Energy", "TATAPOWER": "Energy",
    "NTPC": "Energy", "POWERGRID": "Energy", "ADANIGREEN": "Energy", "ADANIPOWER": "Energy", 
    "JSWENERGY": "Energy", "ADANIENSOL": "Energy", "INOXWIND": "Energy", "IREDA": "Energy", 
    "NHPC": "Energy", "SUZLON": "Energy", "WAAREEENER": "Energy",

    # ---- Financial Services, NBFC, Exchanges & Fintech ----
    "BAJFINANCE": "Finance", "BAJAJFINSV": "Finance", "HDFCLIFE": "Finance", "SBILIFE": "Finance", 
    "ICICIPRULI": "Finance", "ICICIGI": "Finance", "SBICARD": "Finance", "CHOLAFIN": "Finance", 
    "MUTHOOTFIN": "Finance", "MANAPPURAM": "Finance", "PFC": "Finance", "RECLTD": "Finance", 
    "LICHSGFIN": "Finance", "HDFCAMC": "Finance", "IRFC": "Finance", "SAMMAANCAP": "Finance", 
    "LICI": "Finance", "SHRIRAMFIN": "Finance", "M&MFIN": "Finance", "ABCAPITAL": "Finance", 
    "IEX": "Finance", "MCX": "Finance", "360ONE": "Finance", "ANGELONE": "Finance", "BSE": "Finance", 
    "CDSL": "Finance", "CAMS": "Finance", "BAJAJHLDNG": "Finance", "JIOFIN": "Finance", 
    "KFINTECH": "Finance", "LTF": "Finance", "MFSL": "Finance", "MOTILALOFS": "Finance", 
    "NUVAMA": "Finance", "PAYTM": "Finance", "POLICYBZR": "Finance", "PNBHOUSING": "Finance",

    # ---- Cement & Building Materials ----
    "ULTRACEMCO": "Cement", "SHREECEM": "Cement", "GRASIM": "Cement", "AMBUJACEM": "Cement", 
    "ACC": "Cement", "DALBHARAT": "Cement", "ASTRAL": "Cement", "SUPREMEIND": "Cement", "APLAPOLLO": "Cement",

    # ---- Realty & Infrastructure ----
    "DLF": "Realty", "GODREJPROP": "Realty", "OBEROIRLTY": "Realty", "PRESTIGE": "Realty", 
    "PHOENIXLTD": "Realty", "LODHA": "Realty", "LT": "Infra", "RVNL": "Infra", "NBCC": "Infra",

    # ---- Capital Goods & Defense ----
    "ABB": "Capital Goods", "SIEMENS": "Capital Goods", "CUMMINSIND": "Capital Goods",
    "POLYCAB": "Capital Goods", "BHEL": "Capital Goods", "CGPOWER": "Capital Goods",
    "GVT&D": "Capital Goods", "POWERINDIA": "Capital Goods", "KEI": "Capital Goods",
    "KAYNES": "Capital Goods", "PGEL": "Capital Goods", "PREMIERENE": "Capital Goods",
    "BEL": "Defense", "HAL": "Defense", "BDL": "Defense", "COCHINSHIP": "Defense", 
    "MAZDOCK": "Defense", "SOLARINDS": "Defense",

    # ---- Telecom, Media & Entertainment ----
    "BHARTIARTL": "Telecom", "IDEA": "Telecom", "INDUSTOWER": "Telecom", "TATACOMM": "Telecom", 
    "ZEEL": "Media", "SUNTV": "Media", "PVRINOX": "Media",

    # ---- Consumer Durables ----
    "TITAN": "Consumer Durables", "VOLTAS": "Consumer Durables", "HAVELLS": "Consumer Durables", 
    "DIXON": "Consumer Durables", "CROMPTON": "Consumer Durables", "BATAINDIA": "Consumer Durables",
    "PAGEIND": "Consumer Durables", "AMBER": "Consumer Durables", "BLUESTARCO": "Consumer Durables",

    # ---- Retail & E-Commerce ----
    "TRENT": "Retail", "DMART": "Retail", "ABFRL": "Retail", "NYKAA": "Retail", 
    "KALYANKJIL": "Retail", "SWIGGY": "Retail", "VMM": "Retail", "JUBLFOOD": "Retail",

    # ---- Chemicals & Fertilizers ----
    "PIDILITIND": "Chemicals", "SRF": "Chemicals", "UPL": "Chemicals", "AARTIIND": "Chemicals", 
    "DEEPAKNTR": "Chemicals", "PIIND": "Chemicals", "TATACHEM": "Chemicals", "NAVINFLUOR": "Chemicals", "ATUL": "Chemicals",

    # ---- Logistics, Aviation & Hospitality ----
    "ADANIPORTS": "Logistics", "CONCOR": "Logistics", "DELHIVERY": "Logistics", "GMRAIRPORT": "Logistics", 
    "INDIGO": "Aviation", "IRCTC": "Hospitality", "INDHOTEL": "Hospitality",

    # ---- Paints & Coatings ----
    "ASIANPAINT": "Paints",

    # ---- Misc / newly-added F&O underlyings ----
    "ADANIENT": "Other",        # diversified conglomerate
    "ETERNAL": "Retail",        # ex-Zomato, food delivery
    "NAM-INDIA": "Finance",     # Nippon Life India AMC
    "TIINDIA": "Auto",          # Tube Investments — auto ancillary
}

# Index futures that ride in the same NSE_FO/FUT segment as stock futures.
# They are needed in the market sweep (NIFTY is the relative-strength
# benchmark) but must NOT appear as tradeable stock picks or be bucketed
# into the sector matrix — they have no sector and only add noise.
INDEX_SYMBOLS = {"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "NIFTYNXT50"}


def is_index(symbol: str) -> bool:
    return symbol in INDEX_SYMBOLS


def sector_for(symbol: str) -> str:
    return SECTOR_MAP.get(symbol, "Other")