import re
from pathlib import Path

from django.test import SimpleTestCase


class SourceLayoutTests(SimpleTestCase):
    app_root = Path(__file__).resolve().parents[1]
    project_root = app_root.parent
    template_root = app_root / "templates"
    static_root = app_root / "static"

    static_tag_pattern = re.compile(
        r"{%\s*static\s+['\"]([^'\"]+)['\"]\s*%}"
    )
    css_url_pattern = re.compile(
        r"url\(\s*(?:['\"])?([^'\")]+)(?:['\"])?\s*\)",
        re.IGNORECASE,
    )
    source_static_path_pattern = re.compile(
        r"['\"](main/(?:css|js|vendor)/[^'\"]+)['\"]"
    )

    def test_literal_template_static_references_exist(self):
        missing = []
        for template in sorted(self.template_root.rglob("*.html")):
            source = template.read_text(encoding="utf-8")
            for reference in self.static_tag_pattern.findall(source):
                if not (self.static_root / reference).is_file():
                    missing.append(f"{template.relative_to(self.project_root)}: {reference}")

        self.assertEqual([], missing, "Missing literal static assets:\n" + "\n".join(missing))

    def test_relative_css_assets_exist(self):
        missing = []
        static_root = self.static_root.resolve()

        for stylesheet in sorted((self.static_root / "main" / "css").rglob("*.css")):
            source = stylesheet.read_text(encoding="utf-8")
            for reference in self.css_url_pattern.findall(source):
                reference = reference.strip()
                if reference.startswith(("data:", "http:", "https:", "//", "#", "var(")):
                    continue

                asset = (stylesheet.parent / reference).resolve()
                try:
                    asset.relative_to(static_root)
                except ValueError:
                    missing.append(
                        f"{stylesheet.relative_to(self.project_root)} escapes static root: {reference}"
                    )
                    continue

                if not asset.is_file():
                    missing.append(f"{stylesheet.relative_to(self.project_root)}: {reference}")

        self.assertEqual([], missing, "Broken relative CSS assets:\n" + "\n".join(missing))

    def test_css_blocks_are_balanced(self):
        failures = []

        for stylesheet in sorted((self.static_root / "main" / "css").rglob("*.css")):
            source = stylesheet.read_text(encoding="utf-8")
            depth = 0
            quote = None
            escaped = False
            in_comment = False
            index = 0

            while index < len(source):
                char = source[index]
                following = source[index + 1] if index + 1 < len(source) else ""

                if in_comment:
                    if char == "*" and following == "/":
                        in_comment = False
                        index += 2
                        continue
                    index += 1
                    continue

                if quote:
                    if escaped:
                        escaped = False
                    elif char == "\\":
                        escaped = True
                    elif char == quote:
                        quote = None
                    index += 1
                    continue

                if char == "/" and following == "*":
                    in_comment = True
                    index += 2
                    continue
                if char in {"'", '"'}:
                    quote = char
                elif char == "{":
                    depth += 1
                elif char == "}":
                    depth -= 1
                    if depth < 0:
                        failures.append(
                            f"{stylesheet.relative_to(self.project_root)} closes a block too early"
                        )
                        break
                index += 1

            if depth != 0:
                failures.append(
                    f"{stylesheet.relative_to(self.project_root)} has brace depth {depth}"
                )
            if quote:
                failures.append(
                    f"{stylesheet.relative_to(self.project_root)} has an unterminated string"
                )
            if in_comment:
                failures.append(
                    f"{stylesheet.relative_to(self.project_root)} has an unterminated comment"
                )

        self.assertEqual([], failures, "Invalid CSS structure:\n" + "\n".join(failures))

    def test_public_css_and_javascript_are_domain_scoped(self):
        css_root = self.static_root / "main" / "css"
        js_root = self.static_root / "main" / "js"

        loose_css = sorted(
            path.name
            for path in css_root.glob("*.css")
            if path.name not in {"admin-wedding-page.css", "admin_custom.css"}
        )
        loose_js = sorted(path.name for path in js_root.glob("*.js"))

        self.assertEqual([], loose_css, f"Loose public CSS files: {loose_css}")
        self.assertEqual([], loose_js, f"Loose public JavaScript files: {loose_js}")

    def test_test_modules_are_package_scoped(self):
        loose_tests = sorted(path.name for path in self.app_root.glob("test*.py"))

        self.assertEqual([], loose_tests, f"Loose test modules: {loose_tests}")

    def test_frontend_has_no_legacy_or_hotfix_buckets(self):
        public_roots = [
            self.static_root / "main" / "css",
            self.static_root / "main" / "js",
        ]
        forbidden_names = re.compile(r"(?:^|[-_])(legacy|hotfix|polish|final-fix)(?:[-_.]|$)")
        failures = []

        for public_root in public_roots:
            for path in public_root.rglob("*"):
                relative = path.relative_to(public_root)
                if "legacy" in relative.parts or forbidden_names.search(path.name):
                    failures.append(relative.as_posix())

        self.assertEqual([], failures, f"Legacy/hotfix frontend buckets: {failures}")

    def test_responsive_contract_load_order_and_canonical_product_card(self):
        base = (self.template_root / "main" / "layout" / "base.html").read_text(
            encoding="utf-8"
        )
        responsive = "main/css/foundation/responsive.css"
        navigation = "main/css/layout/navigation.css"
        hero_policy = "main/css/layout/hero-policy.css"

        self.assertLess(base.index(responsive), base.index(navigation))
        self.assertLess(base.index(navigation), base.index(hero_policy))

        hero_source = (
            self.static_root / "main" / "css" / "layout" / "hero-policy.css"
        ).read_text(encoding="utf-8")
        self.assertIn("aspect-ratio: 16 / 5 !important", hero_source)
        self.assertIn("clamp(440px, calc(65svh + 20px), 620px)", hero_source)
        self.assertIn("object-position: left 70% !important", hero_source)

        card_template = (
            self.template_root / "main" / "components" / "product_card.html"
        ).read_text(encoding="utf-8")
        rail_script = (
            self.static_root / "main" / "js" / "components" / "product-rail.js"
        ).read_text(encoding="utf-8")
        self.assertNotIn("card_variant", card_template)
        self.assertNotIn("featured-product-card", rail_script)
        self.assertIn(".flowers-product-card", rail_script)

    def test_every_first_party_stylesheet_and_script_is_referenced(self):
        references = set()
        source_files = [
            *self.template_root.rglob("*.html"),
            *self.app_root.rglob("*.py"),
            *(self.project_root / "config").rglob("*.py"),
        ]

        for source_file in source_files:
            if source_file == Path(__file__).resolve() or source_file.name.startswith("test"):
                continue
            source = source_file.read_text(encoding="utf-8")
            references.update(self.static_tag_pattern.findall(source))
            references.update(self.source_static_path_pattern.findall(source))

        assets = [
            *(self.static_root / "main" / "css").rglob("*.css"),
            *(self.static_root / "main" / "js").rglob("*.js"),
        ]
        unreferenced = sorted(
            asset.relative_to(self.static_root).as_posix()
            for asset in assets
            if asset.relative_to(self.static_root).as_posix() not in references
        )

        self.assertEqual(
            [],
            unreferenced,
            "Unreferenced first-party CSS/JavaScript:\n" + "\n".join(unreferenced),
        )
