"""Test suite per BackupFatto."""

import json
import unittest
import sys
import os

# Add parent dir to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app, _generate_powershell, _generate_batch, _filename


class TestScriptGeneration(unittest.TestCase):
    """Test per la generazione degli script."""

    def setUp(self):
        self.source = r"C:\Users\Test\Documents"
        self.dest = r"D:\Backup"
        self.exts = ["pdf", "docx"]

    # ── PowerShell ──────────────────────────────────────────

    def test_ps_basic_copy(self):
        script = _generate_powershell(self.source, self.dest, False, False, False, [])
        self.assertIn("$Source", script)
        self.assertIn(self.source, script)
        self.assertIn("$Destination", script)
        self.assertIn(self.dest, script)
        self.assertIn("Copy-Item", script)
        self.assertIn("-Recurse", script)
        self.assertNotIn("Compress-Archive", script)

    def test_ps_no_subfolders(self):
        script = _generate_powershell(self.source, self.dest, True, False, False, [])
        self.assertIn("Copy-Item", script)
        self.assertNotIn("-Recurse", script)
        self.assertIn("ESCLUSE", script)

    def test_ps_with_zip(self):
        script = _generate_powershell(self.source, self.dest, False, True, False, [])
        self.assertIn("Compress-Archive", script)
        self.assertIn("ZIP", script)

    def test_ps_filter_extensions(self):
        script = _generate_powershell(self.source, self.dest, False, False, True, self.exts)
        self.assertIn("*.pdf", script)
        self.assertIn("*.docx", script)
        self.assertIn("-Include", script)

    def test_ps_filter_no_sub(self):
        script = _generate_powershell(self.source, self.dest, True, False, True, self.exts)
        self.assertIn("-Include", script)
        self.assertNotIn("-Recurse", script)

    def test_ps_all_options(self):
        script = _generate_powershell(self.source, self.dest, True, True, True, self.exts)
        self.assertIn("$Source", script)
        self.assertIn("Compress-Archive", script)
        self.assertIn("*.pdf", script)
        self.assertIn("ESCLUSE", script)

    def test_ps_error_handling(self):
        script = _generate_powershell(self.source, self.dest, False, False, False, [])
        self.assertIn("$ErrorActionPreference", script)
        self.assertIn("try {", script)
        self.assertIn("catch", script)
        self.assertIn("exit 1", script)

    def test_ps_output_structure(self):
        script = _generate_powershell(self.source, self.dest, False, True, True, self.exts)
        # Check header comment block
        self.assertIn("<#", script)
        self.assertIn("#>", script)
        self.assertIn(".SYNOPSIS", script)
        self.assertIn("BackupFatto", script)

    # ── Batch ───────────────────────────────────────────────

    def test_bat_basic_copy(self):
        script = _generate_batch(self.source, self.dest, False, False, False, [])
        self.assertIn("@echo off", script)
        self.assertIn(self.source, script)
        self.assertIn(self.dest, script)
        self.assertIn("xcopy", script)
        self.assertIn("/E", script)

    def test_bat_no_subfolders(self):
        script = _generate_batch(self.source, self.dest, True, False, False, [])
        self.assertIn("ESCLUSE", script)
        # Should NOT have /E /S flags
        self.assertNotIn("/E /I /H /Y", script)

    def test_bat_with_zip(self):
        script = _generate_batch(self.source, self.dest, False, True, False, [])
        self.assertIn("Compress-Archive", script)
        self.assertIn("powershell", script.lower())

    def test_bat_filter_extensions(self):
        script = _generate_batch(self.source, self.dest, False, False, True, self.exts)
        self.assertIn("*.pdf", script)
        self.assertIn("*.docx", script)
        self.assertIn("copy /y", script)

    def test_bat_all_options(self):
        script = _generate_batch(self.source, self.dest, True, True, True, self.exts)
        self.assertIn("@echo off", script)
        self.assertIn("Compress-Archive", script)
        self.assertIn("*.pdf", script)

    def test_bat_has_pause(self):
        script = _generate_batch(self.source, self.dest, False, False, False, [])
        self.assertIn("pause", script)

    # ── Filename ────────────────────────────────────────────

    def test_filename_ps(self):
        fname = _filename("powershell")
        self.assertTrue(fname.endswith(".ps1"))
        self.assertTrue(fname.startswith("backup_"))

    def test_filename_bat(self):
        fname = _filename("batch")
        self.assertTrue(fname.endswith(".bat"))


class TestAPI(unittest.TestCase):
    """Test per l'endpoint API."""

    def setUp(self):
        app.config["TESTING"] = True
        self.client = app.test_client()

    def test_index_loads(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"BackupFatto", resp.data)
        self.assertIn(b"<!DOCTYPE html>", resp.data)

    def test_robots_txt(self):
        resp = self.client.get("/robots.txt")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Sitemap:", resp.data)

    def test_sitemap_xml(self):
        resp = self.client.get("/sitemap.xml")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"<urlset", resp.data)

    def test_generate_powershell_basic(self):
        payload = {
            "source": r"C:\Users\Test\Docs",
            "destination": r"D:\Backup",
            "scriptType": "powershell",
            "excludeSubfolders": False,
            "compressZip": False,
            "filterExtensions": False,
            "extensions": "",
        }
        resp = self.client.post(
            "/api/generate",
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["success"])
        self.assertIn("$Source", data["script"])
        self.assertIn("powershell", data["scriptType"])
        self.assertTrue(data["filename"].endswith(".ps1"))

    def test_generate_batch(self):
        payload = {
            "source": r"C:\Users\Test\Docs",
            "destination": r"D:\Backup",
            "scriptType": "batch",
            "excludeSubfolders": True,
            "compressZip": True,
            "filterExtensions": True,
            "extensions": "pdf, docx",
        }
        resp = self.client.post(
            "/api/generate",
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["success"])
        self.assertIn("@echo off", data["script"])
        self.assertEqual(data["scriptType"], "batch")
        self.assertTrue(data["filename"].endswith(".bat"))

    def test_generate_all_combinations(self):
        """Test che tutte le combinazioni di opzioni producano uno script valido."""
        script_types = ["powershell", "batch"]
        bool_opts = [False, True]

        for st in script_types:
            for no_sub in bool_opts:
                for zip_it in bool_opts:
                    for filt in bool_opts:
                        payload = {
                            "source": r"C:\Test",
                            "destination": r"D:\Dest",
                            "scriptType": st,
                            "excludeSubfolders": no_sub,
                            "compressZip": zip_it,
                            "filterExtensions": filt,
                            "extensions": "txt, log" if filt else "",
                        }
                        resp = self.client.post(
                            "/api/generate",
                            data=json.dumps(payload),
                            content_type="application/json",
                        )
                        self.assertEqual(resp.status_code, 200,
                                         f"Failed for {st} no_sub={no_sub} zip={zip_it} filt={filt}")
                        data = resp.get_json()
                        self.assertTrue(data["success"])
                        self.assertGreater(len(data["script"]), 50,
                                           f"Script too short for {st} no_sub={no_sub} zip={zip_it} filt={filt}")

    # ── Validation ──────────────────────────────────────────

    def test_missing_source(self):
        payload = {
            "source": "",
            "destination": r"D:\Backup",
            "scriptType": "powershell",
            "excludeSubfolders": False,
            "compressZip": False,
            "filterExtensions": False,
            "extensions": "",
        }
        resp = self.client.post(
            "/api/generate",
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertFalse(data["success"])
        self.assertGreater(len(data["errors"]), 0)

    def test_missing_destination(self):
        payload = {
            "source": r"C:\Test",
            "destination": "",
            "scriptType": "powershell",
            "excludeSubfolders": False,
            "compressZip": False,
            "filterExtensions": False,
            "extensions": "",
        }
        resp = self.client.post(
            "/api/generate",
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertFalse(data["success"])

    def test_filter_without_extensions(self):
        payload = {
            "source": r"C:\Test",
            "destination": r"D:\Dest",
            "scriptType": "powershell",
            "excludeSubfolders": False,
            "compressZip": False,
            "filterExtensions": True,
            "extensions": "",
        }
        resp = self.client.post(
            "/api/generate",
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertFalse(data["success"])

    def test_invalid_script_type(self):
        payload = {
            "source": r"C:\Test",
            "destination": r"D:\Dest",
            "scriptType": "bash",
            "excludeSubfolders": False,
            "compressZip": False,
            "filterExtensions": False,
            "extensions": "",
        }
        resp = self.client.post(
            "/api/generate",
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_extensions_sanitized(self):
        """Test che le estensioni vengano pulite correttamente."""
        payload = {
            "source": r"C:\Test",
            "destination": r"D:\Dest",
            "scriptType": "powershell",
            "excludeSubfolders": False,
            "compressZip": False,
            "filterExtensions": True,
            "extensions": ".pdf, docx,  jpg  ; xlsx",
        }
        resp = self.client.post(
            "/api/generate",
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["success"])
        self.assertIn("*.pdf", data["script"])
        self.assertIn("*.docx", data["script"])
        self.assertIn("*.jpg", data["script"])
        self.assertIn("*.xlsx", data["script"])

    def test_empty_body(self):
        resp = self.client.post(
            "/api/generate",
            data="",
            content_type="application/json",
        )
        # Should handle gracefully
        self.assertIn(resp.status_code, (200, 400))


class TestHTMLQuality(unittest.TestCase):
    """Test di qualità frontend."""

    def setUp(self):
        app.config["TESTING"] = True
        self.client = app.test_client()

    def test_html_has_lang(self):
        resp = self.client.get("/")
        self.assertIn(b'lang="it"', resp.data)

    def test_html_has_viewport(self):
        resp = self.client.get("/")
        self.assertIn(b'name="viewport"', resp.data)

    def test_html_has_canonical(self):
        resp = self.client.get("/")
        self.assertIn(b'rel="canonical"', resp.data)

    def test_html_has_og_tags(self):
        resp = self.client.get("/")
        self.assertIn(b'og:title', resp.data)
        self.assertIn(b'og:description', resp.data)
        self.assertIn(b'og:url', resp.data)

    def test_html_has_jsonld(self):
        resp = self.client.get("/")
        self.assertIn(b'application/ld+json', resp.data)
        self.assertIn(b'BackupFatto', resp.data)

    def test_html_has_h1(self):
        resp = self.client.get("/")
        self.assertIn(b'<h1', resp.data)

    def test_html_has_landmarks(self):
        resp = self.client.get("/")
        self.assertIn(b'<header', resp.data)
        self.assertIn(b'<main', resp.data)
        self.assertIn(b'<footer', resp.data)

    def test_html_has_labels(self):
        resp = self.client.get("/")
        self.assertIn(b'<label', resp.data)

    def test_html_no_absolute_paths(self):
        """Verifica che non ci siano path assoluti nel frontend."""
        resp = self.client.get("/")
        html = resp.data.decode("utf-8")
        # Should NOT have src="/... or href="/... (except canonical, og, sitemap)
        # But external URLs (https://) are fine
        import re
        # Find href="/ or src="/ that are NOT https://
        abs_paths = re.findall(r'(?:href|src)="/(?![/])', html)
        self.assertEqual(len(abs_paths), 0,
                         f"Found absolute paths: {abs_paths}")

    def test_html_has_alt_text(self):
        resp = self.client.get("/")
        # All <img> should have alt (there might be none, that's okay)
        html = resp.data.decode("utf-8")
        # This is a weak check — just make sure no img is missing alt
        imgs_missing_alt = html.count('<img ') - html.count('alt=')
        self.assertEqual(imgs_missing_alt, 0)

    def test_html_form_has_labels(self):
        resp = self.client.get("/")
        html = resp.data.decode("utf-8")
        # Check that inputs have associated labels
        self.assertIn('for="source"', html)
        self.assertIn('for="destination"', html)
        self.assertIn('for="optNoSub"', html)
        self.assertIn('for="optZip"', html)
        self.assertIn('for="optFilter"', html)


if __name__ == "__main__":
    # Run with verbosity
    unittest.main(verbosity=2)
