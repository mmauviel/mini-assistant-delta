import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import fetch_bts  # noqa: E402
import parse_opsnet  # noqa: E402
import fetch_weather  # noqa: E402
import trace_root_cause as trc  # noqa: E402


def test_months_cross_year():
    assert list(fetch_bts.months("2022-11", "2023-02")) == [(2022, 11), (2022, 12), (2023, 1), (2023, 2)]


def test_filter_network_keeps_shared_tails_only():
    d = pd.DataFrame({
        "Marketing_Airline_Network": ["DL", "UA", "UA", "AA"],
        "Operating_Airline": ["OO", "OO", "OO", "AA"],
        "Tail_Number": ["N1", "N1", "N2", "N1"],
    })
    kept = fetch_bts.filter_network(d)
    # DL flight + the UA flight flown by the same SkyWest aircraft; not N2, not AA's N1
    assert kept.Marketing_Airline_Network.tolist() == ["DL", "UA"]


def test_download_rejects_foreign_host(tmp_path):
    with pytest.raises(ValueError):
        fetch_bts.download("https://example.com/x.zip", tmp_path / "x.zip")


def test_station_id_validation():
    with pytest.raises(ValueError):
        fetch_weather.build_url("ATL&data=all", "2023-01-01", "2023-01-02")


def test_iem_station_mapping():
    meta = {"ATL": {"icao": "KATL"}, "HNL": {"icao": "PHNL"}, "DJT": {"icao": "KDJT"}}
    assert fetch_weather.iem_station("ATL", meta) == "ATL"
    assert fetch_weather.iem_station("HNL", meta) == "PHNL"
    assert fetch_weather.iem_station("PBI", meta) == "DJT"


def _flights(rows):
    cols = ["Operating_Airline", "Tail_Number", "Origin", "Dest", "crs_dep",
            "CarrierDelay", "WeatherDelay", "NASDelay", "SecurityDelay", "LateAircraftDelay"]
    return pd.DataFrame(rows, columns=cols)


def test_resolve_propagates_through_two_legs():
    d = _flights([
        ["DL", "N1", "ATL", "BOS", 0, 30, 0, 10, 0, 0],    # root: 30 carrier + 10 NAS
        ["DL", "N1", "BOS", "LGA", 120, 0, 0, 0, 0, 40],   # inherits 40
        ["DL", "N1", "LGA", "ATL", 240, 0, 0, 0, 0, 20],   # inherits 20 from leg 2
    ])
    r = trc.resolve(d)
    assert r.loc[1, ["Carrier", "NAS"]].tolist() == [30.0, 10.0]
    assert r.loc[2, ["Carrier", "NAS"]].tolist() == [15.0, 5.0]
    assert (r.trace_status.iloc[1:] == "traced").all()


def test_resolve_leaves_broken_chain_unresolved():
    d = _flights([
        ["DL", "N1", "ATL", "BOS", 0, 30, 0, 0, 0, 0],
        ["DL", "N1", "JFK", "LGA", 120, 0, 0, 0, 0, 25],   # previous leg landed elsewhere
    ])
    r = trc.resolve(d)
    assert r.loc[1, "Unresolved"] == 25.0
    assert r.loc[1, "trace_status"] == "previous_leg_elsewhere"


def _opsnet_row(date, fac, vals):
    cells = "".join(f"\n<td nowrap align=right>{v}</td>" for v in vals)
    return (f"<tr>\n<td nowrap style=text-align:left;>{date}</td>\n"
            f"<td nowrap style=text-align:left;>{fac} </td>{cells}\n</tr>")


def test_parse_opsnet(tmp_path):
    # total(3) = weather(2) + volume(1); cells: delays, avg, min per cause
    vals = [3, 20, "1,060", 2, 30, 60, 1, 1000, 1000, 0, 0, 0, 0, 0, 0, 0, 0, 0]
    html = "<h1>OPSNET : Delays : Delay By Cause Report</h1>" + _opsnet_row("01/02/2023", "ATL", vals)
    p = tmp_path / "r.xls"
    p.write_text(html, encoding="latin-1")
    d = parse_opsnet.parse(p)
    assert d.loc[0, ["facility", "total_delays", "weather_delays", "total_min"]].tolist() == ["ATL", 3, 2, 1060]


def test_parse_opsnet_rejects_inconsistent_totals(tmp_path):
    vals = [5, 0, 0, 2, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
    p = tmp_path / "r.xls"
    p.write_text("Delay By Cause Report" + _opsnet_row("01/02/2023", "ATL", vals), encoding="latin-1")
    with pytest.raises(ValueError):
        parse_opsnet.parse(p)
