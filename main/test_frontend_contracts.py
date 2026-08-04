import json
import re
import tempfile
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from .management.commands.audit_static_modules import audit_module_manifest
from .storage import ResilientManifestStaticFilesStorage


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


class JavascriptArchitectureContractTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.root = Path(settings.BASE_DIR)
        cls.js_root = cls.root / "main" / "static" / "main" / "js"
        cls.base_template = (
            cls.root / "main" / "templates" / "base.html"
        ).read_text(encoding="utf-8")
        cls.home_template = (
            cls.root / "main" / "templates" / "index.html"
        ).read_text(encoding="utf-8")

    def test_base_loads_the_native_module_entrypoint(self):
        self.assertIn(
            '<script type="module" src="{% static \'main/js/site.js\' %}',
            self.base_template,
        )

    def test_retired_script_entrypoints_do_not_return(self):
        retired_files = (
            "navbar.js",
            "home-slider.js",
            "page-hero-slider.js",
            "sameday-slider.js",
            "occasion-slider.js",
            "featured-products-slider.js",
            "catalog-loader.js",
            "product-modal.js",
            "filter-fallback.js",
        )

        for file_name in retired_files:
            with self.subTest(file=file_name):
                self.assertFalse((self.js_root / file_name).exists())
                self.assertNotIn(file_name, self.base_template)
                self.assertNotIn(file_name, self.home_template)

    def test_modules_do_not_clone_interactive_dom_or_hijack_wheel_input(self):
        module_source = "\n".join(
            path.read_text(encoding="utf-8") for path in self.js_root.rglob("*.js")
        )

        self.assertNotIn("cloneNode", module_source)
        self.assertNotIn('addEventListener("wheel"', module_source)

    def test_javascript_quality_commands_are_versioned(self):
        package = json.loads((self.root / "package.json").read_text(encoding="utf-8"))

        self.assertEqual(package["type"], "module")
        self.assertIn("eslint", package["devDependencies"])
        self.assertIn("lint:js", package["scripts"])
        self.assertIn("test:js", package["scripts"])

    def test_every_local_module_import_resolves_to_a_source_file(self):
        import_pattern = re.compile(
            r'(?:\bfrom\s*|\bimport\s*(?:\(\s*)?)["\'](?P<path>\.{1,2}/[^"\']+\.js)["\']'
        )

        for module_path in self.js_root.rglob("*.js"):
            source = module_path.read_text(encoding="utf-8")
            for match in import_pattern.finditer(source):
                imported_path = (module_path.parent / match.group("path")).resolve()
                with self.subTest(module=module_path.name, imported=match.group("path")):
                    self.assertTrue(imported_path.is_relative_to(self.js_root.resolve()))
                    self.assertTrue(imported_path.exists())

    def test_manifest_storage_rewrites_es_module_imports(self):
        self.assertTrue(
            ResilientManifestStaticFilesStorage.support_js_module_import_aggregation
        )

    def test_static_module_audit_catches_unversioned_dynamic_imports(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source_root = root / "source"
            collected_root = root / "collected"
            (source_root / "components").mkdir(parents=True)
            (collected_root / "main" / "js").mkdir(parents=True)
            (source_root / "site.js").write_text(
                'import("./components/hero-carousel.js");', encoding="utf-8"
            )
            (source_root / "components" / "hero-carousel.js").write_text(
                "export const ready = true;", encoding="utf-8"
            )
            manifest = {
                "paths": {
                    "main/js/site.js": "main/js/site.0123456789ab.js",
                }
            }
            (collected_root / "staticfiles.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )
            collected_entry = collected_root / "main" / "js" / "site.0123456789ab.js"
            collected_entry.write_text(
                'import("./components/hero-carousel.abcdef012345.js");',
                encoding="utf-8",
            )

            self.assertEqual(
                audit_module_manifest(collected_root, source_root=source_root), []
            )

            collected_entry.write_text(
                'import("./components/hero-carousel.js");', encoding="utf-8"
            )
            errors = audit_module_manifest(collected_root, source_root=source_root)
            self.assertTrue(any("Unversioned import" in error for error in errors))
