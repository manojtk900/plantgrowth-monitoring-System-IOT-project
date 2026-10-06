import unittest
import urllib.request
import json
import os
import re

class TestPortfolioIntegration(unittest.TestCase):
    BASE_URL = "http://127.0.0.1:5000"

    def test_homepage_contains_portfolio_view(self):
        req = urllib.request.urlopen(f"{self.BASE_URL}/")
        self.assertEqual(req.status, 200)
        html = req.read().decode("utf-8")

        # 1. Navigation item
        self.assertIn('data-view="portfolio"', html)
        self.assertIn('About / Portfolio', html)

        # 2. Portfolio View Container
        self.assertIn('id="view-portfolio"', html)

        # 3. Hero Section
        self.assertIn('MANOJ T K', html)
        self.assertIn('Computer Science & Engineering Student', html)
        self.assertIn('Building practical technology for real-world problems.', html)
        self.assertIn('https://github.com/manojtk900', html)
        self.assertIn('https://www.linkedin.com/in/manoj-t-k-00ab73378/', html)

        # 4. Profile Image & Fallback
        self.assertIn('images/profile.jpg', html)
        self.assertIn('avatar-placeholder.svg', html)

        # 5. About Me Content
        self.assertIn('Computer Science & Engineering student interested in building practical solutions', html)

        # 6. Technical Skills (No fake percentages)
        self.assertIn('Programming Languages', html)
        self.assertIn('AI & Machine Learning', html)
        self.assertIn('Web & Backend Development', html)
        self.assertIn('IoT & Hardware Engineering', html)
        self.assertIn('Databases & Cloud Storage', html)
        self.assertIn('Tools & DevOps', html)
        self.assertIn('Cybersecurity', html)
        # Verify no fake percent bars like 95%
        self.assertNotIn('95%', html)

        # 7. Featured Projects
        self.assertIn('IoT Plant Growth & Environmental Monitoring System', html)
        self.assertIn('ASTRAL PROTECTION', html)
        self.assertIn('https://github.com/manojtk900/cyber-phishing-url-detector.git', html)
        self.assertIn('MannuMitra / CropLife AI Karnataka', html)
        self.assertIn('AgriGuard AI', html)

        # 8. Deep-Dive & Formula
        self.assertIn('Why I Built This', html)
        self.assertIn('30.0 cm', html)
        self.assertIn('Capacitive Soil Moisture', html)
        self.assertIn('DS18B20 Digital Temperature', html)
        self.assertIn('HC-SR04 Ultrasonic Sonar', html)

        # 9. Research Publication
        self.assertIn('AI-Based Data-Driven Predictive Farming System with Explainable AI and Financial Insights', html)
        self.assertIn('International Journal of Versatile Research and Analysis (IJVRA)', html)
        self.assertIn('IJVRA26A4143', html)
        self.assertIn('April 2026', html)

        # 10. Team Section
        self.assertIn('id="portfolioTeamList"', html)

        # 11. Footer
        self.assertIn('Built with: ESP32 • Flask • Python • JavaScript • IoT', html)
        self.assertIn('Manoj T K', html)

    def test_static_assets_exist(self):
        # SVG fallback avatar must exist
        avatar_path = os.path.join(os.path.dirname(__file__), "..", "static", "images", "avatar-placeholder.svg")
        self.assertTrue(os.path.exists(avatar_path), "avatar-placeholder.svg must exist")

        # Fetch CSS
        req = urllib.request.urlopen(f"{self.BASE_URL}/static/style.css")
        self.assertEqual(req.status, 200)
        css = req.read().decode("utf-8")
        self.assertIn('.portfolio-hero-card', css)
        self.assertIn('.portfolio-stats-grid', css)
        self.assertIn('.skills-category-grid', css)
        self.assertIn('.projects-showcase-grid', css)
        self.assertIn('.team-showcase-grid', css)
        self.assertIn('width: 220px !important', css)

        # Fetch JS
        req = urllib.request.urlopen(f"{self.BASE_URL}/static/app.js")
        self.assertEqual(req.status, 200)
        js = req.read().decode("utf-8")
        self.assertIn('portfolio:', js)
        self.assertIn('teamMembers =', js)
        self.assertIn('renderTeamMembers', js)
        self.assertIn('hashchange', js)

    def test_api_contracts_remain_intact(self):
        # /api/latest
        req = urllib.request.urlopen(f"{self.BASE_URL}/api/latest")
        self.assertEqual(req.status, 200)
        data = json.loads(req.read().decode("utf-8"))
        self.assertTrue(data.get("success"))
        self.assertIn("data", data)

        # /api/history
        req = urllib.request.urlopen(f"{self.BASE_URL}/api/history?limit=10")
        self.assertEqual(req.status, 200)
        hist = json.loads(req.read().decode("utf-8"))
        self.assertTrue(hist.get("success"))
        self.assertIn("data", hist)

        # /api/config
        req = urllib.request.urlopen(f"{self.BASE_URL}/api/config")
        self.assertEqual(req.status, 200)
        cfg = json.loads(req.read().decode("utf-8"))
        self.assertTrue(cfg.get("success"))

if __name__ == "__main__":
    unittest.main()
