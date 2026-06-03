import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from scripts.seed_from_csv import parse_row, CsvRow


def _row(**kwargs):
    base = {
        "id_upc": "", "cust_frndly1_des": "", "cust_frndly2_des": "",
        "dsc_brand": "", "dsc_coo": "", "dsc_sub_comm": "",
        "id_str": "", "cust_frndly_nm": "", "add_str": "",
        "cd_zip": "78209", "sz_item": "", "aip": "", "max_sales_date": "",
    }
    base.update(kwargs)
    return base


def test_parse_row_basic_fields():
    row = parse_row(_row(
        id_upc="012345678901",
        cust_frndly1_des="Caymus Cabernet",
        cust_frndly2_des="Napa Valley",
        dsc_brand="Caymus Vineyards",
        dsc_coo="USA",
        dsc_sub_comm="Cabernet Sauvignon",
        id_str="S001",
        cust_frndly_nm="HEB Fair Oaks",
        add_str="7720 N FM 620",
        cd_zip="78726",
        sz_item="750ML",
        aip="45.99",
    ))
    assert row.upc == "012345678901"
    assert row.wine_name == "Caymus Cabernet Napa Valley"
    assert row.zip_code == "78726"
    assert row.price == 45.99
    assert row.brand == "Caymus Vineyards"


def test_parse_row_single_name_no_suffix():
    row = parse_row(_row(cust_frndly1_des="Meiomi Pinot Noir", cust_frndly2_des=""))
    assert row.wine_name == "Meiomi Pinot Noir"


def test_parse_row_handles_missing_price():
    row = parse_row(_row(id_upc="x", cust_frndly1_des="Test Wine", aip=""))
    assert row.price is None


def test_parse_row_infers_red_wine_type():
    row = parse_row(_row(cust_frndly1_des="Test", dsc_sub_comm="CABERNET SAUVIGNON", aip="20.00"))
    assert row.wine_type == "red"


def test_parse_row_infers_white_wine_type():
    row = parse_row(_row(cust_frndly1_des="Test", dsc_sub_comm="Chardonnay", aip="18.00"))
    assert row.wine_type == "white"


def test_parse_row_infers_sparkling():
    row = parse_row(_row(cust_frndly1_des="Test", dsc_sub_comm="Prosecco DOC", aip="15.00"))
    assert row.wine_type == "sparkling"


def test_parse_row_unknown_type_returns_none():
    row = parse_row(_row(cust_frndly1_des="Test", dsc_sub_comm="WINE GIFT SET", aip="30.00"))
    assert row.wine_type is None
