"""Unit tests for the Clinician Dataset row-mapping functions.

Tests ONLY the pure mapping functions (no network) against the sample payloads
embedded in the verified API integration spec:
  - individual NPI-1 (official API snake_case shape)
  - organization NPI-2
  - a CMS mj5m-pzi6 row
"""
from services.external_api.npi_client import map_npi_result
from services.external_api.cms_client import map_cms_row
from utils.constants import Constants


EXPECTED_COLUMNS = [
    "NPI", "Type", "Name", "Speciality", "Address", "City", "State", "Zip",
    "Website", "Phone #", "Email", "Creds", "Why Pilot", "EHR",
    "Outreach status", "Contact date", "Notes",
]

BLANK_COLUMNS = [
    "Website", "Email", "Why Pilot", "EHR", "Outreach status", "Contact date", "Notes",
]


# --- Sample payloads from the spec ----------------------------------------

NPI_INDIVIDUAL = {
    "enumeration_type": "NPI-1",
    "number": "1234567890",
    "basic": {
        "first_name": "KARL", "middle_name": "ELVIN", "last_name": "AAMOT",
        "name_prefix": "Dr.", "name_suffix": "Jr.", "credential": "D.C.",
        "sex": "M", "status": "A",
    },
    "taxonomies": [
        {"code": "111N00000X", "desc": "Chiropractor", "primary": True,
         "state": "CA", "license": "17317", "taxonomy_group": ""},
    ],
    "addresses": [
        {"address_purpose": "MAILING", "address_1": "PO BOX 1", "telephone_number": None},
        {"address_purpose": "LOCATION", "address_1": "895 BLAIR AVENUE", "address_2": "",
         "city": "SUNNYVALE", "state": "CA", "postal_code": "940852934",
         "telephone_number": "408-739-1037", "country_code": "US"},
    ],
}

NPI_ORGANIZATION = {
    "enumeration_type": "NPI-2",
    "number": "1987654321",
    "basic": {
        "organization_name": "SUNNYVALE MEDICAL GROUP",
        "authorized_official_first_name": "JANE",
        "authorized_official_last_name": "DOE",
        "credential": "",
        "status": "A",
    },
    "taxonomies": [
        {"code": "261QP2300X", "desc": "Primary Care Clinic/Center", "primary": True,
         "state": "CA", "taxonomy_group": ""},
    ],
    "addresses": [
        {"address_purpose": "LOCATION", "address_1": "100 MAIN ST", "address_2": "SUITE 200",
         "city": "SUNNYVALE", "state": "CA", "postal_code": "94086",
         "telephone_number": "408-555-1000", "country_code": "US"},
    ],
}

CMS_ROW = {
    "npi": "1235888272",
    "provider_last_name": "BAEZ MUNIZ", "provider_first_name": "EDUARDO",
    "provider_middle_name": "", "suff": "", "gndr": "M", "cred": "",
    "med_sch": "OTHER", "grd_yr": "1984",
    "pri_spec": "CLINICAL PSYCHOLOGIST",
    "sec_spec_1": "", "sec_spec_all": "", "telehlth": "",
    "facility_name": "", "org_pac_id": "", "num_org_mem": "",
    "adr_ln_1": "", "adr_ln_2": "", "ln_2_sprs": "",
    "citytown": "AGUADA", "state": "PR", "zip_code": "00602",
    "telephone_number": "9392994522",
    "ind_assgn": "Y", "grp_assgn": "M", "adrs_id": "PR00602XXXXAG",
}


# --- Shared schema checks --------------------------------------------------

def _assert_schema(row: dict):
    # Exact 17 keys, exact order, exact spelling.
    assert list(row.keys()) == EXPECTED_COLUMNS
    assert list(row.keys()) == Constants.ClinicianDataset.COLUMNS
    # Always-blank columns.
    for col in BLANK_COLUMNS:
        assert row[col] == ""
    # All values are strings.
    assert all(isinstance(v, str) for v in row.values())


# --- NPI individual --------------------------------------------------------

def test_map_npi_individual():
    row = map_npi_result(NPI_INDIVIDUAL)
    _assert_schema(row)
    assert row["NPI"] == "1234567890"
    assert row["Type"] == "Individual"
    assert row["Name"] == "KARL ELVIN AAMOT"
    assert row["Speciality"] == "Chiropractor"
    assert row["Address"] == "895 BLAIR AVENUE"  # LOCATION, not MAILING
    assert row["City"] == "SUNNYVALE"
    assert row["State"] == "CA"
    assert row["Zip"] == "94085-2934"  # 9-digit -> #####-####
    assert row["Phone #"] == "408-739-1037"
    assert row["Creds"] == "D.C."


# --- NPI organization ------------------------------------------------------

def test_map_npi_organization():
    row = map_npi_result(NPI_ORGANIZATION)
    _assert_schema(row)
    assert row["NPI"] == "1987654321"
    assert row["Type"] == "Organization"
    assert row["Name"] == "SUNNYVALE MEDICAL GROUP"
    assert row["Speciality"] == "Primary Care Clinic/Center"
    assert row["Address"] == "100 MAIN ST SUITE 200"  # address_2 appended
    assert row["City"] == "SUNNYVALE"
    assert row["State"] == "CA"
    assert row["Zip"] == "94086"  # 5-digit left as-is
    assert row["Phone #"] == "408-555-1000"
    assert row["Creds"] == ""


# --- CMS row ---------------------------------------------------------------

def test_map_cms_row():
    row = map_cms_row(CMS_ROW)
    _assert_schema(row)
    assert row["NPI"] == "1235888272"
    assert row["Type"] == "Individual"
    assert row["Name"] == "EDUARDO BAEZ MUNIZ"  # first + last, middle blank dropped
    assert row["Speciality"] == "CLINICAL PSYCHOLOGIST"
    assert row["Address"] == ""  # adr_ln_1 empty
    assert row["City"] == "AGUADA"
    assert row["State"] == "PR"
    assert row["Zip"] == "00602"  # leading zeros preserved
    assert row["Phone #"] == "9392994522"
    assert row["Creds"] == ""


def test_map_cms_row_suffix_and_line2():
    """suff appended as ', {suff}'; adr_ln_2 appended only when ln_2_sprs != 'Y'."""
    base = dict(CMS_ROW)
    base.update({
        "suff": "JR",
        "adr_ln_1": "123 MAIN ST",
        "adr_ln_2": "APT 4",
        "ln_2_sprs": "",
    })
    row = map_cms_row(base)
    assert row["Name"] == "EDUARDO BAEZ MUNIZ, JR"
    assert row["Address"] == "123 MAIN ST APT 4"

    # ln_2_sprs == "Y" suppresses line 2.
    suppressed = dict(base)
    suppressed["ln_2_sprs"] = "Y"
    row2 = map_cms_row(suppressed)
    assert row2["Address"] == "123 MAIN ST"
