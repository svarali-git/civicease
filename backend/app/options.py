"""Allowed values for the anonymous demographic profile."""

STATES = [
    "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh", "Goa",
    "Gujarat", "Haryana", "Himachal Pradesh", "Jharkhand", "Karnataka", "Kerala",
    "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya", "Mizoram", "Nagaland",
    "Odisha", "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana", "Tripura",
    "Uttar Pradesh", "Uttarakhand", "West Bengal", "Andaman and Nicobar Islands",
    "Chandigarh", "Dadra and Nagar Haveli and Daman and Diu", "Delhi",
    "Jammu and Kashmir", "Ladakh", "Lakshadweep", "Puducherry",
]

OCCUPATIONS = [
    "farmer", "agricultural_laborer", "small_business_owner", "self_employed",
    "salaried", "student", "homemaker", "unemployed", "other",
]
CATEGORIES = ["general", "obc", "sc", "st", "ews"]
GENDERS = ["female", "male", "other"]
BUSINESS_TYPES = ["manufacturing", "service", "trading"]

# Fields the user must fill before eligibility matching runs.
REQUIRED_PROFILE_FIELDS = ["state", "occupation", "annual_income_lakh", "category"]

FIELD_LABELS = {
    "state": "State",
    "occupation": "Occupation",
    "annual_income_lakh": "Annual family income (Rs lakh)",
    "category": "Category",
    "age": "Age",
    "gender": "Gender",
    "business_type": "Business type",
}
