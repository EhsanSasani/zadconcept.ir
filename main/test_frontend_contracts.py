import json
import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


class CssArchitectureContractTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.root = Path(settings.BASE_DIR)
        cls.css_root = cls.root / "main" / "static" / "main" / "css"
        cls.base_template = (
            cls.root / "main" / "templates" / "base.html"
        ).read_text(encoding="utf-8")

    def test_foundation_styles_load_in_dependency_order(self):
        ordered_files = (
            "tokens.css",
            "base.css",
            "utilities.css",
            "layout.css",
            "navbar.css",
            "hero.css",
            "components.css",
            "page.css",
        )
        positions = [self.base_template.index(file_name) for file_name in ordered_files]

        self.assertEqual(positions, sorted(positions))

    def test_tokens_file_is_the_only_global_root_owner(self):
        root_owners = []
        for css_file in self.css_root.glob("*.css"):
            source = css_file.read_text(encoding="utf-8")
            if re.search(r"(?m)^:root\s*\{", source):
                root_owners.append(css_file.name)

        self.assertEqual(root_owners, ["tokens.css"])

    def test_patch_stylesheets_do_not_return(self):
        forbidden_fragments = ("final", "polish", "hotfix")
        offenders = [
            path.name
            for path in self.css_root.glob("*.css")
            if any(fragment in path.stem for fragment in forbidden_fragments)
        ]

        self.assertEqual(offenders, [])
        self.assertNotIn("final-ui-polish.css", self.base_template)
        self.assertNotIn("home-final-polish.css", self.base_template)

    def test_retired_product_card_selectors_do_not_return(self):
        all_css = "\n".join(
            path.read_text(encoding="utf-8") for path in self.css_root.glob("*.css")
        )

        self.assertNotRegex(all_css, r"\.featured-product-card(?:\b|__)")
        self.assertNotRegex(all_css, r"(?<!flowers-)\.product-card(?:\b|__)")

    def test_legacy_important_budget_does_not_grow(self):
        exempt_files = {"admin_custom.css", "hero-config.css", "utilities.css"}
        important_count = sum(
            path.read_text(encoding="utf-8").count("!important")
            for path in self.css_root.glob("*.css")
            if path.name not in exempt_files
        )

        self.assertLessEqual(important_count, 127)

    def test_css_lint_command_is_versioned(self):
        package = json.loads((self.root / "package.json").read_text(encoding="utf-8"))

        self.assertEqual(
            package["scripts"]["lint:css"],
            'stylelint "main/static/main/css/**/*.css"',
        )
        self.assertRegex(package["devDependencies"]["stylelint"], r"^\d+\.\d+\.\d+$")
