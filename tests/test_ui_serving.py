import json
import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_root_serves_index_html():
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "<html" in response.text.lower()


def test_root_serves_app_js():
    response = client.get("/app.js")
    assert response.status_code == 200
    assert "sendMessage" in response.text


def test_stats_serves_csv_formula_neutralizer_before_dashboard_script():
    response = client.get("/stats.html")

    assert response.status_code == 200
    assert response.text.index('src="csv.js?v=1"') < response.text.index('src="stats.js?v=6"')
    assert client.get("/csv.js?v=1").status_code == 200


def test_csv_cell_neutralizes_formula_markers():
    source = (Path(__file__).parents[1] / "static" / "csv.js").read_text(encoding="utf-8")
    script = (
        "const vm=require('node:vm');"
        "const context={window:{}};"
        f"vm.runInNewContext({json.dumps(source)}, context);"
        "console.log(JSON.stringify(['=1','+1','-1','@x','normal'].map(context.window.csvCell)));"
    )
    result = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True)
    cells = json.loads(result.stdout)

    assert cells == ['"\'=1"', '"\'+1"', '"\'-1"', '"\'@x"', '"normal"']
