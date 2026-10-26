import unittest
import tempfile
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch

from openpyxl import Workbook, load_workbook

from web_app.app import app
from nutrition_tool.models import NutrientProfile
from nutrition_tool.repository import NutrientRepository


class WebAppHealthTests(unittest.TestCase):
    def test_healthz_returns_ok(self):
        response = app.test_client().get("/healthz")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"status": "ok"})

    def test_process_exports_primary_and_secondary_results(self):
        source = BytesIO()
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "9月A餐配料sop"
        sheet.append([
            "編號/圖片", "套餐", "菜式", "食材/系統名稱", "安士（小學）",
            "人均餐盒實際下單用量（g）（小學）", "安士（中學）",
            "人均餐盒實際下單用量（g）（中學）", "編碼",
        ])
        sheet.append([46266, "雞肉飯", "主菜", "雞肉", 1, 100, 2, 200, "CHICKEN"])
        workbook.save(source)
        workbook.close()
        source.seek(0)

        repository = NutrientRepository([
            NutrientProfile(
                ingredient_code="CHICKEN", ingredient_name="雞肉", energy_kcal=100,
                protein_g=20, total_fat_g=1, saturated_fat_g=0.5,
                available_carbohydrate_g=2, sugars_g=1, sodium_mg=50,
            )
        ])
        with tempfile.TemporaryDirectory(prefix="nutri_out_") as folder, \
                patch("web_app.app.tempfile.mkdtemp", return_value=folder), \
                patch("web_app.app._cleanup_old_tmpdirs"), \
                patch("web_app.app.get_history_repo", return_value=SimpleNamespace(find_confirmed=lambda recipe: None)), \
                patch("web_app.app.get_repo", return_value=repository):
            client = app.test_client()
            response = client.post(
                "/api/process",
                data={"sop_files": (source, "sample.xlsx")},
                content_type="multipart/form-data",
            )

            self.assertEqual(response.status_code, 200)
            payload = response.get_json()
            self.assertEqual(payload["incomplete"], 0)
            download = client.get(payload["download"])
            self.assertEqual(download.status_code, 200)
            result_workbook = load_workbook(BytesIO(download.data), read_only=True, data_only=True)
            self.assertEqual(result_workbook.sheetnames, ["小学标准", "中学标准"])
            for sheet_name in ("小学标准", "中学标准"):
                sheet = result_workbook[sheet_name]
                self.assertEqual(sheet.max_column, 15)
                self.assertEqual(sheet["A2"].value, "A(1)雞肉飯")
                self.assertTrue(sheet["E2"].value.startswith("能量"))
                for column in (2, 3, 4, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15):
                    self.assertIn(sheet.cell(2, column).value, (None, ""))
            self.assertIn("能量100(Kcal)", result_workbook["小学标准"]["E2"].value)
            self.assertIn("蛋白質20(g)", result_workbook["小学标准"]["E2"].value)
            self.assertIn("能量200(Kcal)", result_workbook["中学标准"]["E2"].value)
            self.assertIn("蛋白質40(g)", result_workbook["中学标准"]["E2"].value)
            result_workbook.close()
            download.close()

    def test_process_reports_specific_missing_items(self):
        source = BytesIO()
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "9月A餐配料sop"
        sheet.append([
            "編號/圖片", "套餐", "菜式", "食材/系統名稱", "安士（小學）",
            "人均餐盒實際下單用量（g）（小學）", "安士（中學）",
            "人均餐盒實際下單用量（g）（中学）", "編碼",
        ])
        sheet.append([46266, "待补数据饭", "主菜", "未知酱料", 1, 10, 1, 20, "SAUCE"])
        workbook.save(source)
        workbook.close()
        source.seek(0)

        repository = NutrientRepository([])
        with tempfile.TemporaryDirectory(prefix="nutri_out_") as folder, \
                patch("web_app.app.tempfile.mkdtemp", return_value=folder), \
                patch("web_app.app._cleanup_old_tmpdirs"), \
                patch("web_app.app.get_history_repo", return_value=SimpleNamespace(find_confirmed=lambda recipe: None)), \
                patch("web_app.app.get_repo", return_value=repository):
            with app.test_client() as client:
                response = client.post(
                    "/api/process",
                    data={"sop_files": (source, "missing.xlsx")},
                    content_type="multipart/form-data",
                )
                self.assertEqual(response.status_code, 200)
                payload = response.get_json()
                self.assertEqual(payload["incomplete"], 2)
                download = client.get(payload["download"])
                self.assertEqual(download.status_code, 200)
                result_workbook = load_workbook(BytesIO(download.data), data_only=True)
                # Incomplete recipes are excluded from the storefront upload file.
                for sheet_name in ("小学标准", "中学标准"):
                    sheet = result_workbook[sheet_name]
                    self.assertEqual(sheet.max_row, 1)
                    self.assertEqual(sheet.max_column, 15)
                self.assertEqual(payload["upload_count"], 0)
                result_workbook.close()
                download.close()


if __name__ == "__main__":
    unittest.main()
