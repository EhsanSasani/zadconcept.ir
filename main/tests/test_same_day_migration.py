from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class SameDayScopeDataMigrationTests(TransactionTestCase):
    migrate_from = ("main", "0024_telegram_bot_user")
    migrate_to = ("main", "0025_same_day_catalog_scope")

    def setUp(self):
        super().setUp()
        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_from])
        old_apps = executor.loader.project_state([self.migrate_from]).apps
        CategoryV24 = old_apps.get_model("main", "Category")
        ProductV24 = old_apps.get_model("main", "Product")
        TagV24 = old_apps.get_model("main", "Tag")

        category = CategoryV24.objects.create(
            name="Migration same-day flowers",
            slug="migration-same-day-flowers",
            section="flowers",
            is_active=True,
        )
        tag, _ = TagV24.objects.update_or_create(
            slug="same-day",
            defaults={
                "name": "ارسال روز",
                "is_active": True,
                "is_occasion": False,
                "sort_order": 100,
            },
        )
        product = ProductV24.objects.create(
            name="Migration same-day product",
            product_code="MIG-SD-9001",
            slug="migration-same-day-product",
            category=category,
            catalog_scope="general",
            publish_status="published",
            is_active=True,
        )
        product.tags.add(tag)
        self.product_pk = product.pk
        self.tag_pk = tag.pk

        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_to])

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_forward_and_reverse_move_membership_without_recreating_product(self):
        executor = MigrationExecutor(connection)
        migrated_apps = executor.loader.project_state([self.migrate_to]).apps
        ProductV25 = migrated_apps.get_model("main", "Product")
        TagV25 = migrated_apps.get_model("main", "Tag")

        product = ProductV25.objects.get(pk=self.product_pk)
        tag = TagV25.objects.get(pk=self.tag_pk)
        self.assertEqual(product.catalog_scope, "same_day")
        self.assertEqual(product.product_code, "MIG-SD-9001")
        self.assertFalse(product.tags.exists())
        self.assertFalse(tag.is_active)
        self.assertFalse(tag.is_occasion)

        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_from])
        reversed_apps = executor.loader.project_state([self.migrate_from]).apps
        ReversedProduct = reversed_apps.get_model("main", "Product")
        ReversedTag = reversed_apps.get_model("main", "Tag")

        reversed_product = ReversedProduct.objects.get(pk=self.product_pk)
        reversed_tag = ReversedTag.objects.get(pk=self.tag_pk)
        self.assertEqual(reversed_product.catalog_scope, "general")
        self.assertEqual(reversed_product.product_code, "MIG-SD-9001")
        self.assertEqual(
            set(reversed_product.tags.values_list("pk", flat=True)),
            {self.tag_pk},
        )
        self.assertTrue(reversed_tag.is_active)
        self.assertFalse(reversed_tag.is_occasion)
