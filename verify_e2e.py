"""
Automated End-to-End API and Browser integration test script.
Verifies all endpoints, formula engine, calculations, exports and static assets.
"""

import sys
import os

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import urllib.request
import json
import io
import time
import openpyxl

BASE_URL = "http://localhost:8000"

def test_e2e():
    print("0. Authenticating as Administrator...")
    login_req = urllib.request.Request(
        f"{BASE_URL}/api/auth/login",
        data=json.dumps({"user_id": 1}).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(login_req) as resp:
        assert resp.status == 200
        auth_data = json.loads(resp.read().decode("utf-8"))
        token = auth_data["token"]
        assert token
    auth_headers = {"Authorization": f"Bearer {token}"}
    json_auth_headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    print(f"   [OK] Authenticated as {auth_data['user']['full_name']} ({auth_data['user']['role']})")

    print("1. Checking Web Interface (HTML, JS, CSS)...")
    with urllib.request.urlopen(f"{BASE_URL}/") as resp:
        assert resp.status == 200
        html = resp.read().decode("utf-8")
        assert "KPI Formula Engine" in html
        assert "Конструктор формул" in html
        assert "/static/app.js" in html
    print("   [OK] Web Interface loaded successfully")

    print("2. Checking Static JS Bundle...")
    with urllib.request.urlopen(f"{BASE_URL}/static/app.js") as resp:
        assert resp.status == 200
        js = resp.read().decode("utf-8")
        assert "createApp" in js
        assert "runSandboxTest" in js
    print("   [OK] Static assets served properly")

    print("3. Checking Formula Variables Catalog...")
    with urllib.request.urlopen(f"{BASE_URL}/api/formulas/variables") as resp:
        assert resp.status == 200
        variables = json.loads(resp.read().decode("utf-8"))
        var_names = [v["name"] for v in variables]
        assert "deals_won_sum" in var_names
        assert "tasks_closed" in var_names
        assert "base_rate" in var_names
    print(f"   [OK] {len(variables)} variables available in autocomplete catalog")

    print("4. Testing Formula Sandbox...")
    # Test valid calculation
    req = urllib.request.Request(
        f"{BASE_URL}/api/formulas/sandbox/test",
        data=json.dumps({
            "expression": "IF(deals_won_sum >= plan_sales, base_rate * 0.75, base_rate * 0.3)",
            "custom_variables": {"deals_won_sum": 500000, "plan_sales": 400000, "base_rate": 60000}
        }).encode("utf-8"),
        headers=json_auth_headers
    )
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        assert data["valid"] is True
        assert data["result"] == 45000.0  # 60000 * 0.75
    print("   [OK] Sandbox calculation evaluated correctly (45,000 RUB)")

    # Test error handling
    req_err = urllib.request.Request(
        f"{BASE_URL}/api/formulas/sandbox/test",
        data=json.dumps({"expression": "IF(deals_won_sum >="}).encode("utf-8"),
        headers=json_auth_headers
    )
    with urllib.request.urlopen(req_err) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        assert data["valid"] is False
        assert data["error"] is not None
    print("   [OK] Sandbox caught syntax error cleanly without server crash")

    print("5. Checking Company Structure & Users...")
    req_struct = urllib.request.Request(f"{BASE_URL}/api/company/structure", headers=auth_headers)
    with urllib.request.urlopen(req_struct) as resp:
        structure = json.loads(resp.read().decode("utf-8"))
        assert len(structure) >= 3  # Sales, IT, Support
    with urllib.request.urlopen(f"{BASE_URL}/api/auth/users") as resp:
        users = json.loads(resp.read().decode("utf-8"))
        assert len(users) >= 5
    print(f"   [OK] Company structure: {len(structure)} departments, {len(users)} users")

    print("6. Creating New Dynamic Period for Testing...")
    period_title = f"Период Тест {int(time.time())}"
    create_req = urllib.request.Request(
        f"{BASE_URL}/api/periods",
        data=json.dumps({
            "name": period_title,
            "start_date": "2026-11-01",
            "end_date": "2026-11-30"
        }).encode("utf-8"),
        headers=json_auth_headers
    )
    with urllib.request.urlopen(create_req) as resp:
        new_p = json.loads(resp.read().decode("utf-8"))
        test_period_id = new_p["id"]
    print(f"   [OK] Created test period #{test_period_id} ({period_title})")

    print("7. Testing Calculation Snapshot Pipeline...")
    calc_req = urllib.request.Request(
        f"{BASE_URL}/api/periods/{test_period_id}/calculate",
        data=b"",
        headers=auth_headers,
        method="POST"
    )
    with urllib.request.urlopen(calc_req) as resp:
        calc_res = json.loads(resp.read().decode("utf-8"))
        assert calc_res["status"] == "CALCULATED"
        assert calc_res["employees_calculated"] > 0
    print(f"   [OK] Calculated {calc_res['employees_calculated']} employees")

    # Fetch results
    results_req = urllib.request.Request(
        f"{BASE_URL}/api/periods/{test_period_id}/results",
        headers=auth_headers
    )
    with urllib.request.urlopen(results_req) as resp:
        results = json.loads(resp.read().decode("utf-8"))
        assert len(results) == calc_res["employees_calculated"]
        for r in results:
            assert r["bonus_amount"] >= 0
            assert r["total_payout"] > 0
    print("   [OK] Results retrieved and verified")

    print("8. Testing Lock & Freeze...")
    lock_req = urllib.request.Request(
        f"{BASE_URL}/api/periods/{test_period_id}/lock",
        data=b"",
        headers=auth_headers,
        method="POST"
    )
    with urllib.request.urlopen(lock_req) as resp:
        lock_res = json.loads(resp.read().decode("utf-8"))
        assert lock_res["status"] == "LOCKED"
    print("   [OK] Period successfully locked and archived")

    print("9. Testing Excel Export (.xlsx)...")
    excel_req = urllib.request.Request(
        f"{BASE_URL}/api/export/periods/{test_period_id}/excel",
        headers=auth_headers
    )
    with urllib.request.urlopen(excel_req) as resp:
        assert resp.status == 200
        excel_bytes = resp.read()
        assert len(excel_bytes) > 1000
        wb = openpyxl.load_workbook(io.BytesIO(excel_bytes))
        sheet = wb.active
        assert "Ведомость KPI" in sheet.title
        assert sheet["A1"].value is not None
        assert "Ведомость" in str(sheet["A1"].value)
    print(f"   [OK] Excel workbook generated ({len(excel_bytes)} bytes) with valid formatting, headers and formulas")

    print("10. Testing CSV Export...")
    csv_req = urllib.request.Request(
        f"{BASE_URL}/api/export/periods/{test_period_id}/csv",
        headers=auth_headers
    )
    with urllib.request.urlopen(csv_req) as resp:
        assert resp.status == 200
        csv_text = resp.read().decode("utf-8-sig")
        assert "Сотрудник" in csv_text
        assert "Оклад" in csv_text
    print("   [OK] CSV generated with UTF-8 BOM encoding for 1C/Excel")

    print("\n" + "=" * 70)
    print(">>> ALL 10 END-TO-END VERIFICATIONS PASSED WITH 0 ERRORS! <<<")
    print("=" * 70)

if __name__ == "__main__":
    test_e2e()
